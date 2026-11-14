"""Retirer des titres de la banque, et les remettre (FON-71). Sans Quart.

Le catalogue retirait seul un titre de la rotation ou d'une collection : son
fichier partait dans la corbeille de la banque, et la boucle d'import le sortait
de Beets à son tour suivant. Rien ne s'en notait, et rien ne le remettait. Le
catalogue passe maintenant la main au moteur (`/collection/remove.json`, par le
même pont que les déplacements d'ARC-09), qui, pour chaque titre :

1. refuse un titre à l'antenne ou en file, comme un déplacement ;
2. met le fichier dans la corbeille de la banque (`TRASH_TOP`), sous un nom libre ;
3. sort le titre de Beets lui-même. La boucle ne retire que ce qui manque sous la
   rotation et les collections : un titre qui suivrait son fichier à la corbeille
   resterait tirable par l'auto-DJ ;
4. note le lot au journal des gestes, avec tous les champs de chaque titre,
   flexibles compris (famille, gain), pour le remettre.

« Annuler », pendant 30 jours, remet le fichier à son chemin d'avant, jamais
par-dessus un autre, et le titre dans Beets avec ses champs : sous son ancien
identifiant s'il est libre, sous un nouveau sinon (Beets réutilise l'identifiant
d'un titre retiré pour le suivant). Une remise ne s'annule pas : on retire le
titre de nouveau.

Tout se fait sous le verrou de la bibliothèque (`bank_lock`, ARC-09), puis, pour
un titre, sous le verrou d'écriture de la base : le scheduler n'envoie pas le
titre entre la vérification et le retrait.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from beets.importer.state import ImportState
from beets.library import Item
from sqlalchemy import select

from radiotomate.domain.errors import DomainConflict, DomainNotFound
from radiotomate.models import JournalChange, JournalEntry, Setting
from radiotomate.services import title_edits
from radiotomate.services.bank_lock import BeetsPlace, bank_lock
from radiotomate.services.bank_moves import (
    GONE,
    LIBRARY,
    LINK,
    NOT_MOVED,
    PATH_FIELD,
    busy_reason,
    indexed_path,
    items_at,
    library_paths,
    place_file,
)
from radiotomate.services.bank_titles import bank_tidy_enabled
from radiotomate.services.media_bank import unique_trash_path
from radiotomate.services.title_edits import _write_lock

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)

GESTURE_REMOVE = "remove"
# Ce que note une remise : un lot `undo` de chemins, qui ne s'annule pas.
UNDOES_REMOVE = "remove"
# Comme un déplacement : 500 titres au plus, et 20 s par demande.
MAX_REMOVALS = 500
TIME_BUDGET = 20.0
# L'interrupteur du retrait par le moteur, sous celui du chantier
# (`features.bank_tidy`) : une clé absente le laisse allumé. Coupé, le catalogue
# retire comme avant, sans journal.
SETTING_REMOVALS = "features.bank_removals_noted"
_SETTING_OFF = {"0", "false", "off", "no", "non", ""}

NOT_IN_TRASH = "Son fichier n'est plus dans la corbeille : il ne revient pas."
PLACE_TAKEN = "Un autre fichier a pris sa place : il reste dans la corbeille."
NOT_BACK = "Il n'a pas pu revenir : il reste dans la corbeille."


class RemovalsOffError(DomainConflict):
    """Le moteur ne retire pas les titres : le catalogue les retire, comme avant."""

    code = "bank_removals_off"


@dataclass
class RemoveReport:
    removed: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    left: list[str] = field(default_factory=list)
    entry: int | None = None
    changes: list[JournalChange] = field(default_factory=list)
    # les champs de chaque titre retiré, par identifiant de Beets
    items: dict[str, dict] = field(default_factory=dict)

    def payload(self) -> dict:
        return {
            "removed": self.removed,
            "failed": self.failed,
            "left": self.left,
            "entry": self.entry,
        }


async def removals_on(session: AsyncSession) -> bool:
    """Le moteur retire les titres et le note : le chantier ouvert, et ce
    retrait pas coupé."""
    if not await bank_tidy_enabled(session):
        return False
    row = await Setting.from_key(session, SETTING_REMOVALS)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _run(func, *args):
    # to_thread : le fil reçoit le contexte où Beets 2.14 garde son dossier.
    return await asyncio.to_thread(func, *args)


# -- Beets ---------------------------------------------------------------------


def _jsonable(value: object) -> object:
    if isinstance(value, bytes):
        return os.fsdecode(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(part) for part in value]
    return str(value)


def snapshot(item: Item) -> dict:
    """Tous les champs d'un titre, flexibles compris, sauf son identifiant et son
    chemin : de quoi le remettre."""
    return {
        key: _jsonable(item[key])
        for key in item.keys()  # noqa: SIM118 : un Item n'est pas un dict
        if key not in {"id", "path"}
    }


def _drop_items(place: BeetsPlace, items: list[Item]) -> None:
    """Le titre sort de la bibliothèque ; son fichier reste où il est."""
    with library_paths(place.lib), place.lib.transaction():
        for item in items:
            item.remove(delete=False)


def restore_item(
    place: BeetsPlace, old_id: int | None, values: dict, path: Path
) -> int:
    """Le titre de retour dans la bibliothèque, avec ses champs, à `path` : sous
    son ancien identifiant s'il est libre, sous un nouveau sinon. Rend celui-ci.

    L'historique d'import le connaît : la boucle ne le réimporte pas."""
    lib = place.lib
    item = Item(lib)
    item.update(values)
    item.path = os.fsencode(path)
    with library_paths(lib), lib.transaction() as tx:
        free = old_id is not None and not tx.query(
            "SELECT 1 FROM items WHERE id = ?", (old_id,)
        )
        if free:
            tx.mutate("INSERT INTO items (id) VALUES (?)", (old_id,))
            item.id = old_id
            item.store()
        else:
            item.add(lib)
            if values.get("added") is not None:
                item.added = values["added"]
                item.store(fields=["added"])
    with ImportState(path=os.fsencode(place.statefile)) as state:
        state.taghistory.add((os.fsencode(path),))
    return int(item.id)


# -- le retrait ----------------------------------------------------------------


async def remove_title(  # noqa: PLR0911
    session: AsyncSession, place: BeetsPlace, source: Path
) -> tuple[list[tuple[int, str, dict]], Path | None, str | None]:
    """Un titre à la corbeille, hors de Beets : ses identifiants, libellés et
    champs, son chemin dans la corbeille, ou pourquoi pas. L'appelant tient
    `bank_lock`."""
    if source.is_symlink():
        return [], None, LINK
    if not source.is_file():
        return [], None, GONE
    items = await _run(items_at, place.lib, source)
    titles = [
        (int(item.id), title_edits.title_label(item), snapshot(item)) for item in items
    ]
    trash = await _run(unique_trash_path, source.name)
    async with _write_lock(session):
        reason = await busy_reason(session, [t[0] for t in titles], source)
        if reason:
            return titles, None, reason
        reason = await _run(place_file, source, trash)
        if reason:
            return titles, None, reason
        try:
            await _run(_drop_items, place, items)
        except Exception:
            _log.exception("bank removal: Beets keeps %s", source)
            await _run(_quiet_unlink, trash)
            return titles, None, LIBRARY
        try:
            await _run(source.unlink)
        except OSError:
            # Deux copies d'un titre valent mieux qu'aucune : il revient.
            _log.exception("bank removal: %s stays", source)
            for beets_id, _label, values in titles:
                try:
                    await _run(restore_item, place, beets_id, values, source)
                except Exception:
                    _log.exception("bank removal: %s left Beets", source)
            await _run(_quiet_unlink, trash)
            return titles, None, NOT_MOVED
    return titles, trash, None


def _quiet_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        _log.warning("bank removal: %s stays", path)


def _change(  # noqa: PLR0913
    beets_id: int | None,
    label: str,
    source: Path,
    target: Path,
    status: str,
    reason: str | None = None,
) -> JournalChange:
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


async def remove_titles(
    session: AsyncSession,
    place: BeetsPlace,
    paths: list[str],
    *,
    username: str,
    budget: float = TIME_BUDGET,
) -> RemoveReport:
    """Retire des titres de la banque, nommés sous elle, jusqu'au bout du temps,
    et note le lot au journal des gestes."""
    report = RemoveReport()
    deadline = time.monotonic() + budget
    async with bank_lock(place):
        for index, raw in enumerate(paths):
            if index and time.monotonic() > deadline:
                report.left = list(paths[index:])
                break
            found = indexed_path(raw)
            if found is None:
                report.failed.append({"from": raw, "reason": GONE})
                continue
            source, rel = found
            titles, trash, reason = await remove_title(session, place, source)
            if reason or trash is None:
                report.failed.append({"from": raw, "reason": reason or NOT_MOVED})
                continue
            report.removed.append(rel)
            for beets_id, label, values in titles:
                report.changes.append(
                    _change(beets_id, label, source, trash, title_edits.STATUS_DONE)
                )
                report.items[str(beets_id)] = values
            if not titles:
                # Un fichier que Beets n'avait pas encore indexé.
                report.changes.append(
                    _change(None, source.name, source, trash, title_edits.STATUS_DONE)
                )
    if report.changes:
        entry = JournalEntry.note(
            GESTURE_REMOVE, username, report.changes, details={"items": report.items}
        )
        session.add(entry)
        await session.commit()
        report.entry = entry.id
    return report


# -- la remise -----------------------------------------------------------------


def removes_files(entry: JournalEntry) -> bool:
    """Un lot de retraits : ce que `undo_removals` défait."""
    return entry.gesture == GESTURE_REMOVE


def is_put_back(entry: JournalEntry) -> bool:
    """Une remise après retrait, qui ne s'annule pas."""
    return (
        entry.gesture == title_edits.GESTURE_UNDO
        and (entry.details or {}).get("undoes") == UNDOES_REMOVE
    )


@dataclass(frozen=True)
class RemovalIssue(title_edits.TitleIssue):
    """Un titre qu'une remise laisse à la corbeille, et pourquoi."""

    why: str = ""

    @property
    def reason(self) -> str:
        return self.why


async def _put_back(
    session: AsyncSession,
    place: BeetsPlace,
    group: list[JournalChange],
    items: dict,
) -> tuple[list[int], str | None, str]:
    """Les titres d'un fichier de retour à leur chemin : leurs nouveaux
    identifiants, ou pourquoi pas, avec le code de l'issue."""
    trash = Path(str(group[0].new_value))
    source = Path(str(group[0].old_value))
    if not trash.is_file():
        return [], NOT_IN_TRASH, title_edits.ISSUE_MISSING
    if os.path.lexists(source):
        return [], PLACE_TAKEN, title_edits.ISSUE_CHANGED
    if await _run(items_at, place.lib, source):
        return [], PLACE_TAKEN, title_edits.ISSUE_CHANGED
    reason = await _run(place_file, trash, source)
    if reason:
        return [], NOT_BACK, title_edits.ISSUE_FAILED
    ids: list[int] = []
    try:
        for change in group:
            if change.beets_id is None:
                continue
            values = items.get(str(change.beets_id)) or {}
            ids.append(await _run(restore_item, place, change.beets_id, values, source))
    except Exception:
        _log.exception("bank removal: %s could not come back", source)
        await _run(_quiet_unlink, source)
        return [], NOT_BACK, title_edits.ISSUE_FAILED
    await _run(_quiet_unlink, trash)
    return ids, None, ""


async def undo_removals(
    session: AsyncSession, place: BeetsPlace, entry: JournalEntry, *, username: str
) -> title_edits.EditOutcome:
    """« Annuler » un lot de retraits : chaque fichier revient à sa place, et son
    titre dans Beets. Un fichier sorti de la corbeille, ou dont la place est
    prise, y reste, et la remise le dit."""
    if not await removals_on(session):
        raise RemovalsOffError("Le moteur ne remet pas les titres retirés.")
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
    items = dict((entry.details or {}).get("items") or {})
    groups: dict[str, list[JournalChange]] = {}
    for change in changes:
        groups.setdefault(str(change.new_value), []).append(change)
    notes: list[JournalChange] = []
    issues: list[RemovalIssue] = []
    back: list[int] = []
    async with bank_lock(place):
        for group in groups.values():
            ids, why, code = await _put_back(session, place, group, items)
            trash = Path(str(group[0].new_value))
            source = Path(str(group[0].old_value))
            if why:
                for change in group:
                    notes.append(
                        _change(
                            change.beets_id,
                            change.label,
                            trash,
                            source,
                            title_edits.STATUS_KEPT
                            if code != title_edits.ISSUE_FAILED
                            else title_edits.STATUS_FAILED,
                            why,
                        )
                    )
                    issues.append(
                        RemovalIssue(change.beets_id, change.label, code, why)
                    )
                continue
            back.extend(ids)
            labels = [change.label for change in group]
            for beets_id, label in zip(ids or [None], labels, strict=False):
                notes.append(
                    _change(beets_id, label, trash, source, title_edits.STATUS_DONE)
                )
    undo = JournalEntry.note(
        title_edits.GESTURE_UNDO,
        username,
        notes,
        undo_of=entry.id,
        details={"undoes": UNDOES_REMOVE},
    )
    session.add(undo)
    await session.commit()
    return title_edits.EditOutcome(entry_id=undo.id, written=sorted(back), kept=issues)
