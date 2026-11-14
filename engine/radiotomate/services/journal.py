"""Le journal des gestes sur la banque et les bacs (FON-71). Sans Quart.

Chaque geste qui écrit se note dans `journal_entries` et `journal_changes`
(`radiotomate.models.journal`) : la correction d'une fiche (FON-66), le déplacement
d'un titre (ARC-09), son retrait de la banque et le renommage (FON-68). Ce module
les lit pour la page Journal de Sons, et défait un lot entier pendant 30 jours : un
retrait par `bank_removals.undo_removals`, un déplacement ou un renommage par
`bank_moves.undo_moves`, le reste par `title_edits.undo_entry`.

C'est le premier morceau de SEC-10 : la même table s'étendra aux horloges, aux
réglages des bacs et aux comptes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from radiotomate.domain.agenda import iso_paris
from radiotomate.domain.errors import (
    DomainConflict,
    DomainNotFound,
    DomainValidationError,
)
from radiotomate.models import JournalChange, JournalEntry
from radiotomate.services import bank_moves, bank_removals, title_edits
from radiotomate.services.bank_lock import BeetsPlace

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration

# Un lot s'annule pendant ce temps.
UNDO_DAYS = 30
PAGE = 50
MAX_PAGE = 200
# Les lignes d'un lot que rend son détail : 500 titres, chacun avec ses champs.
MAX_CHANGES = 5000

GESTURE_LABELS = {
    title_edits.GESTURE_EDIT: "Correction",
    title_edits.GESTURE_ACCEPT: "Proposition acceptée",
    title_edits.GESTURE_UNDO: "Annulation",
    "rename": "Renommage",
    "move": "Déplacement",
    "remove": "Retrait",
}
# Les gestes qui savent se défaire, et comment.
UNDOABLE = frozenset(
    (
        *title_edits.GESTURES,
        bank_moves.GESTURE_MOVE,
        bank_moves.GESTURE_RENAME,
        bank_removals.GESTURE_REMOVE,
    )
)

STATUSES = (
    title_edits.STATUS_DONE,
    title_edits.STATUS_WAITING,
    title_edits.STATUS_KEPT,
    title_edits.STATUS_CANCELLED,
    title_edits.STATUS_FAILED,
    title_edits.STATUS_PENDING,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def undo_limit(now: datetime | None = None) -> datetime:
    """Le plus vieux lot qui s'annule encore, en UTC naïf."""
    return (now or _utcnow()) - timedelta(days=UNDO_DAYS)


def why_not_undoable(
    entry: JournalEntry, undone_by: JournalEntry | None, now: datetime | None = None
) -> str | None:
    """Pourquoi un lot ne s'annule pas, ou None."""
    if entry.gesture not in UNDOABLE:
        return "Ce geste ne s'annule pas encore."
    if bank_removals.is_put_back(entry):
        return "Une remise ne s'annule pas : retire ces titres de nouveau."
    if undone_by is not None:
        return "Ce lot a déjà été défait."
    if entry.created < undo_limit(now):
        return f"Ce lot a plus de {UNDO_DAYS} jours : il ne s'annule plus."
    return None


def _entry_payload(
    entry: JournalEntry,
    counts: Counter,
    undone_by: JournalEntry | None,
    now: datetime,
) -> dict:
    reason = why_not_undoable(entry, undone_by, now)
    return {
        "id": entry.id,
        "gesture": entry.gesture,
        "gesture_label": GESTURE_LABELS.get(entry.gesture, entry.gesture),
        "username": entry.username,
        "created": iso_paris(entry.created),
        "titles": entry.titles,
        "fields": list((entry.details or {}).get("fields") or []),
        "undo_of": entry.undo_of,
        "undone_by": None
        if undone_by is None
        else {
            "id": undone_by.id,
            "username": undone_by.username,
            "created": iso_paris(undone_by.created),
        },
        "undoable": reason is None,
        "why_not": reason,
        "counts": {status: counts.get(status, 0) for status in STATUSES},
    }


async def _counts(session: ormSession, ids: list[int]) -> dict[int, Counter]:
    """Les lignes de chaque lot par état, comptées par titre."""
    counts: dict[int, Counter] = defaultdict(Counter)
    if not ids:
        return counts
    rows = await session.execute(
        select(
            JournalChange.entry_id,
            JournalChange.status,
            func.count(func.distinct(JournalChange.beets_id)),
        )
        .where(JournalChange.entry_id.in_(ids))
        .group_by(JournalChange.entry_id, JournalChange.status)
    )
    for entry_id, status, count in rows:
        counts[entry_id][status] = count
    return counts


async def _undone_by(session: ormSession, ids: list[int]) -> dict[int, JournalEntry]:
    if not ids:
        return {}
    rows = await session.scalars(
        select(JournalEntry)
        .where(JournalEntry.undo_of.in_(ids))
        .order_by(JournalEntry.id)
    )
    found: dict[int, JournalEntry] = {}
    for row in rows:
        found.setdefault(row.undo_of, row)
    return found


def _page_size(raw: object) -> int:
    if raw in (None, ""):
        return PAGE
    try:
        size = int(str(raw))
    except ValueError as exc:
        raise DomainValidationError(
            "Le nombre de lots est un nombre.", field="limit"
        ) from exc
    if not 1 <= size <= MAX_PAGE:
        raise DomainValidationError(
            f"Une page du journal prend de 1 à {MAX_PAGE} lots.", field="limit"
        )
    return size


async def journal_page(
    session: ormSession,
    *,
    gesture: str | None = None,
    username: str | None = None,
    before: int | None = None,
    limit: object = None,
) -> dict:
    """Une page du journal, du plus récent au plus ancien, filtrée par geste et
    par personne ; `before` reprend après le dernier lot d'une page. Avec, pour
    les filtres, les gestes et les personnes du journal et leurs nombres."""
    size = _page_size(limit)
    query = select(JournalEntry).order_by(JournalEntry.id.desc())
    if gesture:
        query = query.where(JournalEntry.gesture == gesture)
    if username:
        query = query.where(JournalEntry.username == username)
    if before is not None:
        query = query.where(JournalEntry.id < before)
    entries = list(await session.scalars(query.limit(size + 1)))
    more = len(entries) > size
    entries = entries[:size]
    ids = [entry.id for entry in entries]
    counts = await _counts(session, ids)
    undone = await _undone_by(session, ids)
    now = _utcnow()
    gestures = await session.execute(
        select(JournalEntry.gesture, func.count())
        .group_by(JournalEntry.gesture)
        .order_by(JournalEntry.gesture)
    )
    people = await session.execute(
        select(JournalEntry.username, func.count())
        .group_by(JournalEntry.username)
        .order_by(JournalEntry.username)
    )
    return {
        "entries": [
            _entry_payload(entry, counts[entry.id], undone.get(entry.id), now)
            for entry in entries
        ],
        "next": entries[-1].id if more else None,
        "gestures": [
            {
                "value": value,
                "label": GESTURE_LABELS.get(value, value),
                "count": count,
            }
            for value, count in gestures
        ],
        "people": [{"value": value, "count": count} for value, count in people],
        "undo_days": UNDO_DAYS,
    }


async def entry_detail(session: ormSession, entry_id: int) -> dict:
    """Un lot, et chacune de ses lignes : le titre, le champ, avant, après."""
    entry = await JournalEntry.from_id(session, entry_id)
    if entry is None:
        raise DomainNotFound("Ce geste n'est pas au journal.")
    counts = await _counts(session, [entry.id])
    undone = await _undone_by(session, [entry.id])
    changes = list(
        await session.scalars(
            select(JournalChange)
            .where(JournalChange.entry_id == entry.id)
            .order_by(JournalChange.id)
            .limit(MAX_CHANGES)
        )
    )
    payload = _entry_payload(entry, counts[entry.id], undone.get(entry.id), _utcnow())
    payload["changes"] = [
        {
            "id": change.beets_id,
            "label": change.label,
            "path": change.path,
            "field": change.field,
            "old": change.old_value,
            "new": change.new_value,
            "status": change.status,
            "reason": change.reason,
        }
        for change in changes
    ]
    return payload


async def undo(
    session: ormSession,
    beets: BeetsIntegration,
    entry_id: int,
    *,
    username: str,
) -> title_edits.EditOutcome:
    """« Annuler » : défait un lot entier, pendant 30 jours. Un titre changé depuis
    garde sa valeur, et l'annulation le dit."""
    entry = await JournalEntry.from_id(session, entry_id)
    if entry is None:
        raise DomainNotFound("Ce geste n'est pas au journal.")
    undone = await _undone_by(session, [entry.id])
    reason = why_not_undoable(entry, undone.get(entry.id))
    if reason is not None:
        raise DomainConflict(reason)
    if bank_removals.removes_files(entry):
        # Des fichiers retirés reviennent de la corbeille, et leurs titres dans Beets.
        return await bank_removals.undo_removals(
            session, BeetsPlace.of(beets.lib), entry, username=username
        )
    if bank_moves.moves_files(entry):
        # Des fichiers déplacés ou renommés reprennent leur chemin d'avant (ARC-09).
        return await bank_moves.undo_moves(
            session, BeetsPlace.of(beets.lib), entry, username=username
        )
    return await title_edits.undo_entry(session, beets, entry.id, username=username)
