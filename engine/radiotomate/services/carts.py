"""Application-level cart identity and integrity rules."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import delete, or_, select, update

from radiotomate.domain.autodj import require_expected_version
from radiotomate.domain.errors import DomainConflict, DomainValidationError
from radiotomate.models import Clock, ClockPosition, Sound
from radiotomate.services.media_bank import (
    REFUSAL_EMPTY,
    REFUSAL_TOO_MANY,
    REFUSALS_NAME,
    BankFolderTooLargeError,
    bind_cart_bank,
    copy_into_bank,
    forget_legacy_files,
    iter_bank_audio,
    media_root,
    owned_by_cart_bank,
    path_in_media_bank,
    probe_audio,
    read_refusals,
    resolve_bank_dir,
    trash_exclusive_file,
    write_refusals,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.models import Cart

_log = logging.getLogger(__name__)

# A file changed this recently may still be on its way in: a copy that stalls,
# or the end of an audio file that has not arrived yet. It is not refused yet.
SETTLE_SECONDS = 10.0
# An empty file waits longer: the console writes a sound it receives by 1 MB
# blocks, and leaves a small one empty until the end of the whole upload.
EMPTY_SETTLE_SECONDS = 45.0
# The folders where .refus.json cannot be written: said once in the journal,
# not at every pass.
_unwritable: set[Path] = set()


def require_cart_version(cart: Cart, expected: object) -> None:
    require_expected_version(cart.version, expected)


async def sync_cart_display_titles(session: ormSession, cart: Cart) -> None:
    """Keep legacy title columns aligned after a cart rename."""
    await session.execute(
        update(Clock)
        .where(Clock.fallback_cart_id == cart.id)
        .values(fallback_cart_title=cart.title)
    )
    await session.execute(
        update(ClockPosition)
        .where(ClockPosition.cart_id == cart.id)
        .values(cart_title=cart.title)
    )
    await session.execute(
        update(ClockPosition)
        .where(ClockPosition.fallback_cart_id == cart.id)
        .values(fallback_cart_title=cart.title)
    )


async def assert_cart_deletable(session: ormSession, cart: Cart) -> None:
    clock_id = await session.scalar(
        select(Clock.id).where(Clock.fallback_cart_id == cart.id).limit(1)
    )
    position_id = await session.scalar(
        select(ClockPosition.id)
        .where(
            or_(
                ClockPosition.cart_id == cart.id,
                ClockPosition.fallback_cart_id == cart.id,
            )
        )
        .limit(1)
    )
    if clock_id is not None or position_id is not None:
        raise DomainConflict(
            "This cart is referenced by a clock and cannot be deleted."
        )


def _resolved(path: Path | None) -> Path | None:
    if not path:
        return None
    try:
        return Path(path).resolve()
    except (OSError, RuntimeError):
        return None


async def count_path_refs(
    session: ormSession, path: Path, exclude_id: int | None = None
) -> int:
    target = _resolved(path)
    if target is None:
        return 0
    sounds = list(await session.scalars(select(Sound)))
    count = 0
    for sound in sounds:
        if exclude_id is not None and sound.id == exclude_id:
            continue
        other = _resolved(sound.path)
        if other == target:
            count += 1
    return count


async def release_sound_file(session: ormSession, cart: Cart, sound: Sound) -> None:
    resolved = _resolved(sound.path)
    if resolved is None or not resolved.is_file():
        return
    others = await count_path_refs(session, resolved, exclude_id=sound.id)
    if others > 0:
        return
    if path_in_media_bank(resolved):
        if owned_by_cart_bank(resolved, cart.bank_folder):
            await asyncio.to_thread(trash_exclusive_file, resolved, 0)
        return
    resolved.unlink(missing_ok=True)


async def migrate_cart_sounds_to_bank(session: ormSession, cart: Cart) -> list[Path]:
    """Copy DATA_ROOT sounds into the bank, then repoint Sound.path."""
    stale: list[Path] = []
    raw = str(cart.bank_folder or "").strip()
    if not raw or not cart.id:
        return stale
    try:
        dest = resolve_bank_dir(raw)
    except DomainValidationError:
        return stale
    sounds = list(await session.scalars(select(Sound).where(Sound.cart_id == cart.id)))
    for sound in sounds:
        resolved = _resolved(sound.path)
        if resolved is None:
            continue
        if path_in_media_bank(resolved) and resolved.is_file():
            continue
        if not resolved.is_file():
            continue
        copied = await asyncio.to_thread(copy_into_bank, resolved, dest, sound.id)
        if copied is None:
            continue
        stale.append(resolved)
        sound.path = copied
    return stale


async def _stable_new_files(
    files: list[Path], already: set[Path]
) -> tuple[dict[Path, float], set[Path]]:
    """New files whose size held still, with their last change, and the new
    files that are still growing. An empty file has not grown: it is stable,
    and probing it says so."""
    pending = [path for path in files if path.resolve() not in already]
    if not pending:
        return {}, set()
    sizes: dict[Path, int] = {}
    for path in pending:
        try:
            sizes[path] = path.stat().st_size
        except OSError:
            continue
    await asyncio.sleep(0.2)
    stable: dict[Path, float] = {}
    moving: set[Path] = set()
    for path, first in sizes.items():
        try:
            info = path.stat()
        except OSError:
            continue
        if info.st_size != first:
            moving.add(path)
            continue
        stable[path] = info.st_mtime
    return stable, moving


def _refusal_entries(
    folder: Path,
    files: list[Path],
    refused: dict[Path, str],
    waiting: set[Path],
    previous: list[dict],
) -> list[dict]:
    """The refusals, in folder order. A file maybe still on its way in keeps the
    reason it had: a file only leaves the list once in the cart, or gone."""
    before = {entry["path"]: entry["reason"] for entry in previous}
    entries: list[dict] = []
    seen: set[str] = set()
    for path in files:
        rel = path.relative_to(folder).as_posix()
        reason = refused.get(path)
        if reason is None and path in waiting:
            reason = before.get(rel)
        if reason is None or rel in seen:
            continue
        seen.add(rel)
        entries.append({"path": rel, "reason": reason})
    return entries


async def _save_refusals(cart: Cart, folder: Path, entries: list[dict]) -> None:
    """Write down what the cart did not take. Whatever happens, the sync goes on:
    the sounds it took still go to the analysis."""
    try:
        changed = await asyncio.to_thread(write_refusals, folder, entries)
    except Exception as exc:
        if folder not in _unwritable:
            _unwritable.add(folder)
            _log.warning(
                "bank sync: cannot write %s for cart %s: %s",
                REFUSALS_NAME,
                cart.id,
                exc,
            )
        return
    _unwritable.discard(folder)
    if changed:
        _log.info(
            "bank sync: cart %s leaves %s file(s) of its folder out",
            cart.id,
            len(entries),
        )


async def _note_refusals(
    cart: Cart,
    folder: Path,
    files: list[Path],
    failed: dict[Path, tuple[str, float]],
    moving: set[Path],
) -> None:
    """Note the files that failed, with their reason and their last change.

    A file changed in the last seconds may still be on its way in: a copy that
    stalls, or an audio file whose end has not arrived. It is not refused yet.
    """
    now = time.time()
    waiting = set(moving)
    refused: dict[Path, str] = {}
    for path, (reason, changed) in failed.items():
        settle = EMPTY_SETTLE_SECONDS if reason == REFUSAL_EMPTY else SETTLE_SECONDS
        # abs(): a file dated in the future, by a clock set wrong elsewhere,
        # is not waited for.
        if abs(now - changed) < settle:
            waiting.add(path)
        else:
            refused[path] = reason
    previous = await asyncio.to_thread(read_refusals, folder) if waiting else []
    entries = _refusal_entries(folder, files, refused, waiting, previous)
    await _save_refusals(cart, folder, entries)


def _missing_media_ids(sounds: list[Sound]) -> list[int]:
    pruned_ids: list[int] = []
    for sound in sounds:
        resolved = _resolved(sound.path)
        if resolved is None or not path_in_media_bank(resolved):
            continue
        if resolved.is_file() or sound.id is None:
            continue
        pruned_ids.append(sound.id)
    return pruned_ids


async def sync_bank_folder(
    session: ormSession, cart: Cart, uploader_id: int
) -> list[Sound]:
    """Attach stable new bank files and drop Sound rows whose file is gone.

    The files it cannot take go to the folder's .refus.json, each with why.
    """
    raw = str(cart.bank_folder or "").strip()
    if not raw or not cart.id:
        return []
    folder = resolve_bank_dir(raw)
    if not folder.is_dir() or not media_root().is_dir():
        return []
    try:
        files = await asyncio.to_thread(iter_bank_audio, folder)
    except BankFolderTooLargeError:
        # One entry for the whole folder: the cart takes nothing from it.
        too_many = [{"path": ".", "reason": REFUSAL_TOO_MANY}]
        await _save_refusals(cart, folder, too_many)
        return []
    sounds = list(await session.scalars(select(Sound).where(Sound.cart_id == cart.id)))
    already: set[Path] = set()
    for sound in sounds:
        resolved = _resolved(sound.path)
        if resolved is not None:
            already.add(resolved)

    added: list[Sound] = []
    failed: dict[Path, tuple[str, float]] = {}
    rank = await Sound.next_rank(session, cart.id)
    stable, moving = await _stable_new_files(files, already)
    for path, changed in stable.items():
        resolved = path.resolve()
        if resolved in already:
            continue
        length, reason = await asyncio.to_thread(probe_audio, path)
        if length is None:
            failed[path] = (reason, changed)
            continue
        already.add(resolved)
        sound = Sound(
            cart_id=cart.id,
            rank=rank,
            title=path.name,
            path=path,
            duration=int(length),
            uploader_id=uploader_id,
        )
        session.add(sound)
        added.append(sound)
        rank += 1

    pruned_ids = _missing_media_ids(sounds)
    if pruned_ids:
        await session.execute(delete(Sound).where(Sound.id.in_(pruned_ids)))
        for sound in sounds:
            if sound.id in pruned_ids:
                session.expunge(sound)

    if added or pruned_ids:
        await session.flush()
    await _note_refusals(cart, folder, files, failed, moving)
    return added


async def reconcile_cart_bank(
    session: ormSession, cart: Cart, uploader_id: int
) -> tuple[list[Sound], list[Path]]:
    bind_cart_bank(cart)
    stale = await migrate_cart_sounds_to_bank(session, cart)
    added = await sync_bank_folder(session, cart, uploader_id)
    return added, stale


__all__ = [
    "assert_cart_deletable",
    "forget_legacy_files",
    "reconcile_cart_bank",
    "release_sound_file",
    "require_cart_version",
    "sync_bank_folder",
    "sync_cart_display_titles",
]
