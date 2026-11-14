"""Move and copy sounds between carts, and give a cart the order of a view (FON-70).

Sans Quart. Behind the general switch of « Ranger la banque » (``features.bank_tidy``).

- **Copy** : the target cart plays the same file, never a copy of it. The trash of
  the bank does not take a file while a cart plays it (``carts.count_path_refs``).
- **Move** : the sound leaves its cart for the other one. A file of the cart's own
  folder follows it to the folder of the other cart, under a free name, never over
  another file; every sound that plays it, a copy in a third cart included, follows
  too, with the Agenda's files and the planned lines (``bank_moves._retarget_rows``).
  A file on air or in a queue does not move: its sound waits, and the console says
  why. A title of the bank (FON-69), or a file outside the cart's folder, stays
  where it is.
- **Order** : a view sorted by title, artist, duration or last play, applied to the
  cart's ranks.

Each gesture is noted in the journal (FON-71), one change per sound. They do not undo
yet: the journal says so.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy import update as sql_update

from radiotomate.domain.errors import DomainNotFound, DomainValidationError
from radiotomate.enums import CartMode
from radiotomate.models import JournalChange, JournalEntry, Sound
from radiotomate.models.execution import RundownItem
from radiotomate.services import title_edits
from radiotomate.services.bank_moves import _retarget_rows, busy_reason
from radiotomate.services.media_bank import (
    bind_cart_bank,
    cart_upload_dir,
    owned_by_cart_bank,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.models import Cart

GESTURE_CART_MOVE = "cart_move"
GESTURE_CART_COPY = "cart_copy"
GESTURE_CART_ORDER = "cart_order"
GESTURES = (GESTURE_CART_MOVE, GESTURE_CART_COPY, GESTURE_CART_ORDER)
CART_FIELD = "cart"
RANK_FIELD = "rank"
MAX_SOUNDS = 500
# What a view of a cart sorts by, and how the journal names it.
SORTS = {
    "title": "titre",
    "artist": "artiste",
    "duration": "durée",
    "last_played": "dernier passage",
}
ALREADY = "déjà dans le bac d'arrivée"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class TransferOutcome:
    """The sounds that reached the other cart, and those that did not, with why."""

    done: list[Sound] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    entry: JournalEntry | None = None


def _resolved(path: object) -> Path | None:
    try:
        return Path(str(path)).resolve()
    except (OSError, RuntimeError):
        return None


def _free_path(folder: Path, name: str) -> Path:
    """A name in the folder that no file has: « a.mp3 », then « a (2).mp3 »."""
    candidate = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    rank = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = folder / f"{stem} ({rank}){suffix}"
        rank += 1
    return candidate


def _check_carts(source: Cart, target: Cart) -> None:
    if source.id == target.id:
        raise DomainValidationError(
            "Choisis un autre bac que celui de départ.", field="to"
        )
    if target.mode is CartMode.RELAY:
        raise DomainValidationError(
            "Un relais joue un flux : il ne prend pas de son.", field="to"
        )


async def _sounds_of(
    session: ormSession, source: Cart, sound_ids: list[int]
) -> list[Sound]:
    if not sound_ids or len(sound_ids) > MAX_SOUNDS:
        raise DomainValidationError(f"Choisis de 1 à {MAX_SOUNDS} sons.", field="ids")
    rows = list(
        await session.scalars(
            select(Sound).where(Sound.id.in_(sound_ids)).order_by(Sound.rank)
        )
    )
    found = {sound.id for sound in rows}
    missing = [sound_id for sound_id in sound_ids if sound_id not in found]
    strangers = [sound for sound in rows if sound.cart_id != source.id]
    if missing or strangers:
        raise DomainNotFound("Un de ces sons n'est plus dans ce bac.")
    return rows


def _change(
    sound: Sound, field_name: str, before: object, after: object
) -> JournalChange:
    return JournalChange(
        beets_id=None,
        path=str(sound.path),
        label=sound.title,
        field=field_name,
        old_value=before,
        new_value=after,
        status=title_edits.STATUS_DONE,
        applied_at=_utcnow(),
    )


def _cart_ref(cart: Cart) -> dict:
    return {"id": cart.id, "title": cart.title}


async def _move_file(
    session: ormSession, source: Cart, target: Cart, sound: Sound
) -> str | None:
    """A file of the cart's own folder goes to the other one's. Why not, or None."""
    path = _resolved(sound.path)
    if path is None or not path.is_file():
        return None
    if not owned_by_cart_bank(path, source.bank_folder):
        return None
    reason = await busy_reason(session, [], path)
    if reason:
        return reason
    folder = await asyncio.to_thread(cart_upload_dir, target)
    new_path = _free_path(folder, path.name)
    await asyncio.to_thread(shutil.move, str(path), str(new_path))
    await _retarget_rows(session, path, new_path, [], check=False)
    sound.path = new_path
    return None


async def transfer_sounds(  # noqa: PLR0913
    session: ormSession,
    source: Cart,
    target: Cart,
    sound_ids: list[int],
    *,
    copy: bool,
    username: str,
    uploader_id: int,
) -> TransferOutcome:
    """Copy or move sounds from a cart to another one, and note it in the journal.

    The caller commits.
    """
    _check_carts(source, target)
    sounds = await _sounds_of(session, source, sound_ids)
    bind_cart_bank(target)
    held = {
        _resolved(path)
        for path in await session.scalars(
            select(Sound.path).where(Sound.cart_id == target.id)
        )
    }
    rank = await Sound.next_rank(session, target.id)
    outcome = TransferOutcome()
    changes: list[JournalChange] = []
    for sound in sounds:
        if _resolved(sound.path) in held:
            outcome.skipped.append((sound.title, ALREADY))
            continue
        if copy:
            twin = Sound(
                cart_id=target.id,
                rank=rank,
                title=sound.title,
                path=sound.path,
                duration=sound.duration,
                active=sound.active,
                gain=sound.gain,
                peak=sound.peak,
                uploader_id=uploader_id,
            )
            session.add(twin)
            outcome.done.append(twin)
        else:
            reason = await _move_file(session, source, target, sound)
            if reason:
                outcome.skipped.append((sound.title, reason))
                continue
            # The conducteur keeps its lines, without a pointer to a sound gone.
            await session.execute(
                sql_update(RundownItem)
                .where(RundownItem.sound_id == sound.id)
                .values(sound_id=None)
            )
            sound.cart_id = target.id
            sound.rank = rank
            outcome.done.append(sound)
        held.add(_resolved(sound.path))
        changes.append(_change(sound, CART_FIELD, _cart_ref(source), _cart_ref(target)))
        rank += 1
    await session.flush()
    if not copy and outcome.done:
        await Sound.update_ranks(session, source.id)
    if changes:
        outcome.entry = JournalEntry.note(
            GESTURE_CART_COPY if copy else GESTURE_CART_MOVE,
            username,
            changes,
            details={"from": _cart_ref(source), "to": _cart_ref(target)},
        )
        session.add(outcome.entry)
    return outcome


def check_sort(raw: object) -> str:
    sort = str(raw or "")
    if sort not in SORTS:
        raise DomainValidationError(f"Ordre inconnu : {sort}.", field="sorted_by")
    return sort


def note_order(
    cart: Cart, before: dict[int, int], sounds: list[Sound], sort: str, username: str
) -> JournalEntry | None:
    """The journal of « Appliquer cet ordre au bac »: each sound whose rank changed."""
    changes = [
        _change(sound, RANK_FIELD, before.get(sound.id), sound.rank)
        for sound in sounds
        if before.get(sound.id) != sound.rank
    ]
    if not changes:
        return None
    return JournalEntry.note(
        GESTURE_CART_ORDER,
        username,
        changes,
        details={"cart": _cart_ref(cart), "sorted_by": sort},
    )
