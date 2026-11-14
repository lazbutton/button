"""Move or rename a title of the bank without it changing identity (ARC-09).

A title of the rotation or of a collection keeps its Beets id, its ReplayGain,
its flexible fields, and its place in the carts and in the Agenda. In order:

1. The file takes its new name, never over another: a hard link on the same
   disk, a whole copy on another. The old name stays until the end.
2. Its Beets item takes the new path through Beets itself, ``item.path`` then
   ``item.store()``, never by writing library.db: Beets alone knows how it
   keeps a path. A station's library keeps them absolute: its ``directory``
   is Beets's own folder, out of the bank (ARC-06), and Beets 2.14 keeps
   relative only what lies under it. The import history (``state.pickle``)
   follows, through Beets's ``ImportState``, absolute too.
3. What the engine keeps of the path: the sounds of the carts (``sounds.path``),
   the files of the Agenda (``agenda_files.path``) and the planned lines of the
   conducteur (``rundown_items.path``).
4. The old name goes. A failure on the way takes back what was done.

The import loop (deploy/scripts/beets-import-loop.sh) follows the disk on its
own: a file gone leaves the library, a file new enters it under a new id. The
engine and the loop take the same lock (``services/bank_lock.py``), so the loop
never sees the file at its new name before the library has it.

A title on air or in a queue of the playout does not move: the playout reads
its file (``title_edits.busy_status``). Each lot of moves is noted in the
journal of the gestures (FON-66), and is undone from it (FON-71).
"""

from __future__ import annotations

import asyncio
import errno
import logging
import os
import shutil
import time
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from beets.dbcore.query import PathQuery
from beets.importer.state import ImportState
from sqlalchemy import select, text
from sqlalchemy import update as sql_update

from radiotomate.domain.errors import DomainConflict, DomainNotFound
from radiotomate.enums import RundownStatus
from radiotomate.models import JournalChange, JournalEntry
from radiotomate.models.agenda import AgendaFile
from radiotomate.models.execution import RundownItem
from radiotomate.models.setting import Setting
from radiotomate.models.sound import Sound
from radiotomate.services import title_edits
from radiotomate.services.bank_lock import BeetsPlace, bank_lock
from radiotomate.services.bank_titles import bank_tidy_enabled
from radiotomate.services.media_bank import COLLECTIONS_TOP, ROTATION_TOP, media_root

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from beets.library import Item, Library
    from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)

# What Beets indexes, and so what keeps an identity when it moves.
INDEXED_TOPS = (ROTATION_TOP, COLLECTIONS_TOP)
# Titles moved by one request, at most, as the catalogue's moves.
MAX_MOVES = 500
# What one request may spend, under the 30 s nginx waits, the catalogue in
# between: past it, the request stops after its first title and says what is
# left, for the console to send again.
TIME_BUDGET = 20.0
# The switch of this move, on its own (ADR 0009), under the general one of the
# bank's tidying, ``features.bank_tidy`` (FON-64): a missing key leaves it on.
SETTING_MOVES = "features.bank_moves_keep_identity"
_SETTING_OFF = {"0", "false", "off", "no", "non", ""}
# A lot of moves in the journal of the gestures (FON-66, FON-71).
GESTURE_MOVE = "move"
PATH_FIELD = "path"

# The reasons, in French: the console shows them as they are.
TAKEN = "déjà là"
GONE = "fichier introuvable"
LINK = "un lien se déplace sur la machine"
ON_AIR = "à l'antenne en ce moment"
QUEUED = "en file pour l'antenne"
NO_ROOM = "pas assez de place sur le disque"
NOT_MOVED = "déplacement impossible"
LIBRARY = "la bibliothèque n'a pas pu le suivre"
# What an undone move says of a title that moved again since.
MOVED_SINCE = "Son fichier a changé de place depuis : il y reste."


class MovesOffError(DomainConflict):
    """The engine does not move titles: the catalogue moves them, as before."""

    code = "bank_moves_off"


@dataclass
class MoveReport:
    moved: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    left: list[str] = field(default_factory=list)
    # the lot in the journal, once noted
    entry: int | None = None
    # what the journal notes of each title moved
    changes: list[JournalChange] = field(default_factory=list)

    def payload(self) -> dict:
        return {
            "moved": self.moved,
            "failed": self.failed,
            "left": self.left,
            "entry": self.entry,
        }


# -- switch --------------------------------------------------------------------


async def moves_on(session: AsyncSession) -> bool:
    """Whether the engine moves the titles of the bank, keeping their identity:
    the general switch on, as FON-64 reads it, and this move's not said off."""
    if not await bank_tidy_enabled(session):
        return False
    row = await Setting.from_key(session, SETTING_MOVES)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


# -- paths ---------------------------------------------------------------------


def indexed_path(raw: object) -> tuple[Path, str] | None:  # noqa: PLR0911
    """A file of the rotation or of a collection, named below the bank.

    Its absolute path and its name below the bank, or None: a name that leaves
    the bank, hides itself, lies elsewhere than in what Beets indexes, or in a
    folder that is a link leading out.
    """
    text_ = raw if isinstance(raw, str) else ""
    if not text_ or "\x00" in text_ or "\\" in text_ or text_.startswith("/"):
        return None
    parts = PurePosixPath(text_).parts
    if any(part in {".", ".."} or part.startswith(".") for part in parts):
        return None
    if not parts or parts[0] not in INDEXED_TOPS:
        return None
    # rotation/<file>, or archives/<collection>/<file>
    shelf = 1 if parts[0] == ROTATION_TOP else 2
    if len(parts) <= shelf:
        return None
    root = media_root()
    path = root.joinpath(*parts)
    try:
        if not root.joinpath(*parts[:shelf]).is_dir():
            return None
        path.parent.resolve().relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return path, PurePosixPath(*parts).as_posix()


# -- the file ------------------------------------------------------------------


def _quiet_unlink(path: Path) -> None:
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _fit(name: str, limit: int = 240) -> str:
    """The name, shortened from the end of its stem to fit the file system."""
    if len(name.encode("utf-8", "surrogateescape")) <= limit:
        return name
    stem, suffix = Path(name).stem, Path(name).suffix
    room = limit - len(suffix.encode("utf-8", "surrogateescape"))
    short = stem.encode("utf-8", "surrogateescape")[: max(room, 1)]
    return (short.decode("utf-8", "ignore") or "son") + suffix


def _copy_in(source: Path, target: Path) -> str | None:  # noqa: PLR0911
    """A whole copy on another disk, never over a file, never half.

    The copy is written under a hidden name, which Beets and the loop skip, and
    only takes its own once whole.
    """
    try:
        size = source.stat().st_size
        free = shutil.disk_usage(target.parent).free
    except OSError:
        return GONE
    if size > free:
        return NO_ROOM
    partial = target.with_name(_fit(f".{target.name}.partial"))
    _quiet_unlink(partial)
    try:
        shutil.copy2(source, partial)
    except OSError as exc:
        _quiet_unlink(partial)
        return NO_ROOM if exc.errno == errno.ENOSPC else NOT_MOVED
    try:
        os.link(partial, target)
    except FileExistsError:
        _quiet_unlink(partial)
        return TAKEN
    except OSError:
        # A file system without hard links: a rename, once sure the name is free.
        try:
            if os.path.lexists(target):
                _quiet_unlink(partial)
                return TAKEN
            partial.rename(target)
        except OSError:
            _quiet_unlink(partial)
            return NOT_MOVED
        return None
    _quiet_unlink(partial)
    return None


def _missing_parents(target: Path) -> list[Path]:
    """The folders a target needs, from the deepest: the ones a failure removes."""
    missing = []
    folder = target.parent
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    return missing


def _drop_folders(folders: list[Path]) -> None:
    for folder in folders:
        try:
            folder.rmdir()
        except OSError:
            return


def place_file(source: Path, target: Path) -> str | None:  # noqa: PLR0911
    """The file under its new name too, never over another. Returns why not."""
    if source.is_symlink():
        return LINK
    if not source.is_file():
        return GONE
    if os.path.lexists(target):
        return TAKEN
    made = _missing_parents(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        _drop_folders(made)
        return NOT_MOVED
    try:
        os.link(source, target)
        return None
    except FileExistsError:
        _drop_folders(made)
        return TAKEN
    except OSError as exc:
        if exc.errno == errno.ENAMETOOLONG:
            _drop_folders(made)
            return "nom trop long"
    # Another disk, a file the engine may not link (fs.protected_hardlinks), or
    # a file system without hard links: a copy, then.
    reason = _copy_in(source, target)
    if reason:
        _drop_folders(made)
    return reason


# -- Beets ---------------------------------------------------------------------


@contextmanager
def library_paths(lib: Library) -> Iterator[None]:
    """Name the library's root to Beets, in this thread.

    Beets 2.14 keeps relative the path of a file under its ``directory``, and
    reads and writes it against the root bound to the current context, which
    the library binds only where it was opened: in a thread of the executor,
    without this, such a path would be read relative, a query by path would
    find nothing, and a path would be written absolute. A station's root is
    Beets's own folder, which holds no title: nothing changes there. A library
    rooted on the bank, as in a test, needs it. Beets 2.5.1 has nothing to bind.
    """
    bind = getattr(lib, "music_dir_context", None)
    if bind is None:
        yield
        return
    with bind():
        yield


def items_at(lib: Library, path: Path) -> list[Item]:
    """The items of the library at this very path: one, or two an old fault made."""
    wanted = os.fsencode(path)
    with library_paths(lib):
        found = lib.items(PathQuery("path", wanted))
        return [item for item in found if item.path == wanted]


def retarget_items(
    place: BeetsPlace, items: list[Item], source: Path, target: Path
) -> None:
    """The items, and the import history, at the new path. Beets writes both."""
    if not items:
        return
    old, new = os.fsencode(source), os.fsencode(target)
    with library_paths(place.lib), place.lib.transaction():
        for item in items:
            item.path = new
            item.store(fields=["path"])
    # One entry per file, as the loop imports title by title (beet import -s).
    with ImportState(path=os.fsencode(place.statefile)) as state:
        state.taghistory.discard((old,))
        state.taghistory.add((new,))


# -- the engine's base ---------------------------------------------------------


@asynccontextmanager
async def _write_lock(session: AsyncSession) -> AsyncIterator[None]:
    """The write lock of the base: what is read under it holds until the commit
    (``BEGIN IMMEDIATE``, as ``scheduler/execution.py``)."""
    await session.flush()
    try:
        await session.execute(text("BEGIN IMMEDIATE"))
        yield
    except BaseException:
        await session.rollback()
        raise
    await session.commit()


async def busy_reason(
    session: AsyncSession, beets_ids: list[int], path: Path
) -> str | None:
    """Why the file of a title must not change now: on air, or in a queue. The
    rule of every gesture that writes a file (``title_edits.busy_status``)."""
    found = [
        await title_edits.busy_status(session, beets_id, str(path))
        for beets_id in beets_ids or [None]
    ]
    if title_edits.ISSUE_ON_AIR in found:
        return ON_AIR
    if title_edits.ISSUE_QUEUED in found:
        return QUEUED
    return None


class _Busy(Exception):  # noqa: N818
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


async def _retarget_rows(
    session: AsyncSession,
    source: Path,
    target: Path,
    beets_ids: list[int],
    *,
    check: bool = True,
) -> None:
    """The sounds, the Agenda's files and the planned lines, at the new path.

    Under the write lock: a line the scheduler sends between the check and the
    change would read the old path, which is about to go.
    """
    root = media_root()
    old_rel = source.relative_to(root).as_posix()
    new_rel = target.relative_to(root).as_posix()
    async with _write_lock(session):
        if check:
            reason = await busy_reason(session, beets_ids, source)
            if reason:
                raise _Busy(reason)
        await session.execute(
            sql_update(Sound).where(Sound.path == source).values(path=target),
            execution_options={"synchronize_session": False},
        )
        await session.execute(
            sql_update(AgendaFile)
            .where(AgendaFile.path == old_rel)
            .values(path=new_rel),
            execution_options={"synchronize_session": False},
        )
        # The version stays: the scheduler may hold the line, and only its path changes.
        await session.execute(
            sql_update(RundownItem)
            .where(
                RundownItem.status == RundownStatus.PLANNED.value,
                RundownItem.path == str(source),
            )
            .values(path=str(target)),
            execution_options={"synchronize_session": False},
        )


# -- the move ------------------------------------------------------------------


async def _run(func, *args):
    # to_thread, not run_in_executor: the thread gets the context, as Beets wants it.
    return await asyncio.to_thread(func, *args)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _take_back(  # noqa: PLR0913
    session: AsyncSession,
    place: BeetsPlace,
    items: list[Item],
    source: Path,
    target: Path,
    *,
    made: list[Path],
    rows: bool,
) -> None:
    """Undo a move halfway: the base, then Beets, then the new name. The old
    name never went: the title plays as before, even if a step fails here."""
    if rows:
        try:
            await _retarget_rows(session, target, source, [], check=False)
        except Exception:
            _log.exception("bank move: the base keeps %s", target)
    try:
        await _run(retarget_items, place, items, target, source)
    except Exception:
        _log.exception("bank move: Beets keeps %s", target)
    await _run(_quiet_unlink, target)
    await _run(_drop_folders, made)


async def move_title(  # noqa: PLR0911
    session: AsyncSession, place: BeetsPlace, source: Path, target: Path
) -> tuple[list[tuple[int, str]], str | None]:
    """One title from its path to the new one: its Beets ids and labels, or why not.

    The caller holds ``bank_lock``.
    """
    if source.is_symlink():
        return [], LINK
    if not source.is_file():
        return [], GONE
    if os.path.lexists(target):
        return [], TAKEN
    # A title the library still has at the new name, its file gone since the
    # loop's last turn, would share the path with this one.
    if await _run(items_at, place.lib, target):
        return [], TAKEN
    items = await _run(items_at, place.lib, source)
    titles = [(int(item.id), title_edits.title_label(item)) for item in items]
    ids = [beets_id for beets_id, _label in titles]
    reason = await busy_reason(session, ids, source)
    if reason:
        return titles, reason
    made = _missing_parents(target)
    reason = await _run(place_file, source, target)
    if reason:
        return titles, reason
    try:
        await _run(retarget_items, place, items, source, target)
    except Exception:
        _log.exception("bank move: Beets could not follow %s", source)
        await _take_back(session, place, items, source, target, made=made, rows=False)
        return titles, LIBRARY
    try:
        await _retarget_rows(session, source, target, ids)
    except _Busy as busy:
        await _take_back(session, place, items, source, target, made=made, rows=False)
        return titles, busy.reason
    except Exception:
        _log.exception("bank move: the base could not follow %s", source)
        await _take_back(session, place, items, source, target, made=made, rows=False)
        return titles, NOT_MOVED
    try:
        await _run(source.unlink)
    except OSError:
        # Two copies of one title are worse than none moved: the new one goes.
        _log.exception("bank move: %s stays", source)
        await _take_back(session, place, items, source, target, made=made, rows=True)
        return titles, NOT_MOVED
    return titles, None


def _change(  # noqa: PLR0913
    beets_id: int | None,
    label: str,
    source: Path,
    target: Path,
    status: str,
    reason: str | None = None,
) -> JournalChange:
    """One title of a lot, as the journal keeps it: its two paths, as Beets has them."""
    return JournalChange(
        beets_id=beets_id,
        path=str(source),
        label=label,
        field=PATH_FIELD,
        old_value=str(source),
        new_value=str(target),
        status=status,
        reason=reason,
        applied_at=_utcnow() if status == title_edits.STATUS_DONE else None,
    )


async def _move_lot(
    session: AsyncSession,
    place: BeetsPlace,
    moves: list[tuple[str, str]],
    budget: float,
) -> MoveReport:
    """Each (from, to), named below the bank, until the time is up, under the lock."""
    report = MoveReport()
    deadline = time.monotonic() + budget
    async with bank_lock(place):
        for index, (raw_from, raw_to) in enumerate(moves):
            if index and time.monotonic() > deadline:
                report.left = [source for source, _target in moves[index:]]
                break
            source = indexed_path(raw_from)
            target = indexed_path(raw_to)
            if source is None or target is None:
                report.failed.append(
                    {
                        "from": raw_from,
                        "reason": GONE if source is None else "destination refusée",
                    }
                )
                continue
            titles, reason = await move_title(session, place, source[0], target[0])
            if reason:
                report.failed.append({"from": raw_from, "reason": reason})
                continue
            report.moved.append(
                {
                    "from": source[1],
                    "to": target[1],
                    "beets_ids": [beets_id for beets_id, _label in titles],
                }
            )
            for beets_id, label in titles or [(None, source[0].name)]:
                report.changes.append(
                    _change(
                        beets_id,
                        label,
                        source[0],
                        target[0],
                        title_edits.STATUS_DONE,
                    )
                )
    return report


async def move_titles(
    session: AsyncSession,
    place: BeetsPlace,
    moves: list[tuple[str, str]],
    *,
    username: str,
    budget: float = TIME_BUDGET,
) -> MoveReport:
    """Move titles of the bank, and note the lot in the journal of the gestures."""
    report = await _move_lot(session, place, moves, budget)
    if report.changes:
        entry = JournalEntry.note(GESTURE_MOVE, username, report.changes)
        session.add(entry)
        await session.commit()
        report.entry = entry.id
    return report


# -- undo ----------------------------------------------------------------------


@dataclass(frozen=True)
class MoveIssue(title_edits.TitleIssue):
    """A title an undone lot leaves where it is, and why, in the shape of a
    correction's issues (``POST /media/journal/<id>/undo.json``)."""

    why: str = ""

    @property
    def reason(self) -> str:
        return self.why


def moves_files(entry: JournalEntry) -> bool:
    """A lot of moves, or the undoing of one: what ``undo_moves`` undoes."""
    if entry.gesture == GESTURE_MOVE:
        return True
    fields = (entry.details or {}).get("fields")
    return entry.gesture == title_edits.GESTURE_UNDO and fields == [PATH_FIELD]


def _still_there(place: BeetsPlace, change: JournalChange) -> bool:
    """The title is where the lot put it: its file, and its Beets id with it."""
    target = Path(str(change.new_value))
    if not os.path.lexists(target):
        return False
    if change.beets_id is None:
        return True
    return any(int(item.id) == change.beets_id for item in items_at(place.lib, target))


async def undo_moves(
    session: AsyncSession, place: BeetsPlace, entry: JournalEntry, *, username: str
) -> title_edits.EditOutcome:
    """« Annuler » a lot of moves: each title back at its path before, keeping
    its identity. A title moved again since stays where it is, and says so."""
    if not await moves_on(session):
        raise MovesOffError("Le moteur ne déplace pas les titres de la banque.")
    if entry.id is None:
        raise DomainNotFound("Ce geste n'est pas au journal.")
    changes = list(
        await session.scalars(
            select(JournalChange)
            .where(
                JournalChange.entry_id == entry.id,
                JournalChange.field == PATH_FIELD,
                JournalChange.status == title_edits.STATUS_DONE,
            )
            .order_by(JournalChange.id)
        )
    )
    root = media_root()
    pairs: list[tuple[str, str]] = []
    back: dict[str, list[JournalChange]] = {}
    kept: list[JournalChange] = []
    for change in changes:
        try:
            current = Path(str(change.new_value)).relative_to(root).as_posix()
            before = Path(str(change.old_value)).relative_to(root).as_posix()
        except ValueError:
            kept.append(change)
            continue
        if current in back:
            back[current].append(change)
        elif await _run(_still_there, place, change):
            back[current] = [change]
            pairs.append((current, before))
        else:
            kept.append(change)
    report = await _move_lot(session, place, pairs, budget=float("inf"))
    failed = {row["from"]: row["reason"] for row in report.failed}
    notes = list(report.changes)
    issues: list[MoveIssue] = []

    def _left(change: JournalChange, code: str, status: str, why: str) -> None:
        notes.append(
            _change(
                change.beets_id,
                change.label,
                Path(str(change.new_value)),
                Path(str(change.old_value)),
                status,
                why,
            )
        )
        issues.append(MoveIssue(change.beets_id, change.label, code, why))

    for change in kept:
        _left(change, title_edits.ISSUE_CHANGED, title_edits.STATUS_KEPT, MOVED_SINCE)
    for current, group in back.items():
        if current in failed:
            for change in group:
                why = f"Il reste où il est : {failed[current]}."
                _left(change, title_edits.ISSUE_FAILED, title_edits.STATUS_FAILED, why)
    undo = JournalEntry.note(
        title_edits.GESTURE_UNDO, username, notes, undo_of=entry.id
    )
    session.add(undo)
    await session.commit()
    return title_edits.EditOutcome(
        entry_id=undo.id,
        written=sorted(
            {beets_id for row in report.moved for beets_id in row["beets_ids"]}
        ),
        kept=issues,
    )
