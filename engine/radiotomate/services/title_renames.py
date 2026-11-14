"""Rename files of the bank after their fiche (FON-68).

A title of the rotation or of a collection takes the name its fiche gives it,
after a model (``services/bank_names.py``): « Artiste - Titre »,
« Artiste - Album - Titre » or « Titre », in its folder or in a folder of its
artist. First a preview, title by title: its name now, the name it would take,
or why it keeps its own. Then the renaming itself, by the move of ARC-09
(``services/bank_moves.py``): each title keeps its identity, its place in the
carts and the Agenda, and the lot goes to the journal of the gestures, from
which it is undone.

A name already taken is never replaced. A title on air or in a queue keeps its
name until it has played.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from radiotomate.domain.errors import DomainConflict, DomainValidationError
from radiotomate.models.setting import Setting
from radiotomate.services import bank_moves
from radiotomate.services.bank_moves import (
    GESTURE_RENAME,
    busy_reason,
    indexed_path,
    library_paths,
    moves_on,
)
from radiotomate.services.bank_names import MODELS, renamed
from radiotomate.services.media_bank import media_root
from radiotomate.services.title_edits import title_label

if TYPE_CHECKING:
    from beets.library import Item
    from sqlalchemy.ext.asyncio import AsyncSession

    from radiotomate.services.bank_lock import BeetsPlace

# Titles renamed by one lot, at most, as a lot of fiches (FON-66).
MAX_TITLES = 500
# The switch of the renaming, on its own (ADR 0009), under the general one of
# the bank's tidying and the move of ARC-09: a missing key leaves it on.
SETTING_RENAMES = "features.title_renames"
_SETTING_OFF = {"0", "false", "off", "no", "non", ""}

# What the preview says of each title.
STATE_RENAME = "rename"
STATE_SAME = "same"
STATE_TAKEN = "taken"
STATE_INCOMPLETE = "incomplete"
STATE_BUSY = "busy"
STATE_MISSING = "missing"
# And what the renaming did.
STATE_RENAMED = "renamed"
STATE_FAILED = "failed"
STATE_LEFT = "left"

# The reasons, in French: the console shows them as they are.
UNKNOWN = "Ce titre n'est plus dans la bibliothèque."
OUTSIDE = "Son fichier n'est ni dans la rotation ni dans une collection."
GONE = "Son fichier a disparu du disque."
SAME = "Il porte déjà ce nom."
TAKEN = "Ce nom est déjà pris : rien n'est remplacé."


class RenamesOffError(DomainConflict):
    """The engine does not rename files: a switch is off."""

    code = "title_renames_off"


@dataclass
class RenamePlan:
    """A title of the lot: its path below the bank, the new one, or why not."""

    id: int
    label: str
    path: str
    to: str | None
    state: str
    reason: str = ""

    def payload(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "path": self.path,
            "to": self.to,
            "state": self.state,
            "reason": self.reason,
        }


@dataclass
class RenameOutcome:
    titles: list[RenamePlan] = field(default_factory=list)
    entry: int | None = None
    left: list[int] = field(default_factory=list)


async def renames_on(session: AsyncSession) -> bool:
    """Whether files are renamed: the move of ARC-09 on, and this switch not off."""
    if not await moves_on(session):
        return False
    row = await Setting.from_key(session, SETTING_RENAMES)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


def parse_lot(data: dict) -> tuple[list[int], str, bool, bool]:
    """The titles, the model, a folder per artist, and whether it only tries."""
    raw = data.get("ids")
    if not isinstance(raw, list) or not raw:
        raise DomainValidationError("Aucun titre choisi.", field="ids")
    if len(raw) > MAX_TITLES:
        raise DomainValidationError(
            f"Un lot prend {MAX_TITLES} titres au plus.", field="ids"
        )
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in raw):
        raise DomainValidationError(
            "Un titre se nomme par son identifiant.", field="ids"
        )
    model = data.get("model")
    if model not in MODELS:
        raise DomainValidationError("Modèle de nom inconnu.", field="model")
    by_artist = data.get("by_artist", False)
    if not isinstance(by_artist, bool):
        raise DomainValidationError(
            "Un dossier par artiste : oui ou non.", field="by_artist"
        )
    return list(dict.fromkeys(raw)), model, by_artist, data.get("dry_run") is True


def _items(place: BeetsPlace, ids: list[int]) -> list[tuple[int, Item | None]]:
    with library_paths(place.lib):
        return [(beets_id, place.lib.get_item(beets_id)) for beets_id in ids]


def _fiche(item: Item) -> dict:
    return {name: item.get(name) for name in ("artist", "album", "title")}


def _same_file(one: Path, other: Path) -> bool:
    try:
        return one.samefile(other)
    except OSError:
        return False


async def plan_renames(
    session: AsyncSession,
    place: BeetsPlace,
    ids: list[int],
    model: str,
    *,
    by_artist: bool = False,
) -> list[RenamePlan]:
    """What each title would be called, and why some keep their name."""
    root = media_root()
    plans: list[RenamePlan] = []
    taken: set[str] = set()
    for beets_id, item in await asyncio.to_thread(_items, place, ids):
        if item is None:
            plans.append(RenamePlan(beets_id, "", "", None, STATE_MISSING, UNKNOWN))
            continue
        path = Path(os.fsdecode(item.path))
        label = title_label(item)
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            plans.append(
                RenamePlan(beets_id, label, str(path), None, STATE_MISSING, OUTSIDE)
            )
            continue
        plan = RenamePlan(beets_id, label, rel, None, STATE_RENAME)
        plans.append(plan)
        if indexed_path(rel) is None:
            plan.state, plan.reason = STATE_MISSING, OUTSIDE
            continue
        if not path.is_file():
            plan.state, plan.reason = STATE_MISSING, GONE
            continue
        target, why = renamed(rel, _fiche(item), model, by_artist=by_artist)
        if target is None:
            plan.state, plan.reason = STATE_INCOMPLETE, why[:1].upper() + why[1:] + "."
            continue
        plan.to = target
        # The same name, or the same file under a name that only differs in
        # case, on a disk that does not tell them apart.
        if target == rel or _same_file(path, root / target):
            plan.state, plan.reason = STATE_SAME, SAME
            continue
        busy = await busy_reason(session, [beets_id], path)
        if busy:
            plan.state, plan.reason = STATE_BUSY, busy[:1].upper() + busy[1:] + "."
            continue
        if target in taken or os.path.lexists(root / target):
            plan.state, plan.reason = STATE_TAKEN, TAKEN
            continue
        taken.add(target)
    return plans


async def rename_titles(
    session: AsyncSession,
    place: BeetsPlace,
    plans: list[RenamePlan],
    *,
    username: str,
) -> RenameOutcome:
    """Rename the titles the preview lets go, by the move of ARC-09, as one lot."""
    todo = {plan.path: plan for plan in plans if plan.state == STATE_RENAME and plan.to}
    outcome = RenameOutcome(titles=plans)
    if not todo:
        return outcome
    report = await bank_moves.move_titles(
        session,
        place,
        [(plan.path, plan.to) for plan in todo.values() if plan.to],
        username=username,
        gesture=GESTURE_RENAME,
    )
    for row in report.moved:
        todo[row["from"]].state = STATE_RENAMED
    for row in report.failed:
        plan = todo[row["from"]]
        plan.state, plan.reason = STATE_FAILED, row["reason"]
    for path in report.left:
        todo[path].state = STATE_LEFT
        outcome.left.append(todo[path].id)
    outcome.entry = report.entry
    return outcome
