"""Accept, refuse, go back, search again: the fiches read in « À relire » (FON-27).

- `decide`: accepted or refused propositions, chosen by their id, 500 at most. A
  decision is kept by the key of the title (`fiche_decisions`): a file that comes
  back under another id gets it again. A refused value is not proposed again.
- Accepting writes at once, by the write service of FON-66 (`title_edits`, the
  gesture `accept`): the file first, then Beets; the family and the verdict in Beets
  only; never a title on air or in queue, which waits; each lot in the journal of
  FON-71. A proposition `à revoir` or `rapprochée` is accepted alone, with the
  other propositions of its title only: a lot that mixes it with another title is
  refused. A proposition whose value changed since it was made is stale: 409.
- `revert`: a written value goes back to the one before, as long as nobody changed
  it since. The acceptance is forgotten: a file that comes back does not get it.
- `reopen`: « Z » of the review at the keyboard (FON-78), the last gesture undone.
  Its propositions are proposed again, as before it: a written value goes back to
  the one before, one that still waits is never written, and the decision is
  forgotten.
- `search_again`: the title is searched before the rest of the catalogue.
- `write_accepted`: the background of the interface. An accepted proposition
  follows its write in the journal (written, failed, cancelled), and one that never
  went to the journal, as on a file that came back, is written.

The genre is never written by a proposition (ADR 0017): no proposition carries it.
"""

from __future__ import annotations

import logging
from asyncio import to_thread
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from beets.library import FileOperationError
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from radiotomate.domain.errors import (
    DomainConflict,
    DomainNotFound,
    DomainValidationError,
)
from radiotomate.models import Fiche, JournalChange, JournalEntry
from radiotomate.models.fiche import (
    ACCEPT,
    ACCEPTED,
    PROPOSED,
    REFUSE,
    REFUSED,
    REVERTED,
    STALE,
    WRITE_FAILED,
    WRITTEN,
    FicheDecision,
    FicheProposition,
    utcnow,
)
from radiotomate.scheduler.fiches import KEY_CHANGED
from radiotomate.services import title_edits
from radiotomate.services.bank_lock import BankBusyError
from radiotomate.services.fiches import read_settings
from radiotomate.services.title_edits import (
    GESTURE_ACCEPT,
    GESTURE_UNDO,
    ISSUE_CHANGED,
    ISSUE_FAILED,
    ISSUE_MESSAGES,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_KEPT,
    STATUS_PENDING,
    STATUS_WAITING,
    EditOutcome,
    TitleEdit,
    TitlesRefused,
    current_value,
    edit_titles,
    require_title_edits,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration

_log = logging.getLogger(__name__)

MAX_PROPOSITIONS = 500
SURE = "sûr"
# A title searched again before the rest of the catalogue.
SEARCH_FIRST = KEY_CHANGED
# What the background leaves to the gesture that is still writing.
GRACE = timedelta(minutes=1)
# The undos of the journal the background looks at: far more than its period.
UNDOS_SEEN = timedelta(hours=1)
# The titles the background writes in one pass.
BACKGROUND_TITLES = 100
BUSY = "La bibliothèque est occupée : la valeur s'écrira dans un instant."
STALE_MESSAGE = (
    "Une proposition a changé depuis que la page l'a montrée : relis la page."
)


class FichesOff(DomainConflict):
    """The search is switched off: a title is not searched again."""

    code = "fiches_off"


@dataclass
class Decided:
    """What a gesture did, for the console."""

    accepted: int = 0
    refused: int = 0
    written: int = 0
    waiting: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    stale: int = 0
    entry: int | None = None

    def payload(self) -> dict:
        return {
            "accepted": self.accepted,
            "refused": self.refused,
            "written": self.written,
            "waiting": self.waiting,
            "failed": self.failed,
            "stale": self.stale,
            "entry": self.entry,
        }


# -- values ----------------------------------------------------------------------


def typed(name: str, text: str) -> object:
    """The text of a proposition, as the write service takes it."""
    if name == "year":
        try:
            return int(text or 0)
        except ValueError:
            return text
    return text or ""


def _same(name: str, left: object, right: object) -> bool:
    """Two values the console shows alike are the same."""
    if name == "year":
        try:
            return int(left or 0) == int(right or 0)
        except (TypeError, ValueError):
            return left == right
    return " ".join(str(left or "").split()) == " ".join(str(right or "").split())


def _values(proposition: FicheProposition) -> dict[str, object]:
    """What accepting one proposition writes: the verdict comes with its source."""
    values = {proposition.field: typed(proposition.field, proposition.value)}
    if proposition.field == "fmg":
        values["fmg_source"] = proposition.source
    return values


def _ids(raw: object, name: str) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(
        isinstance(one, int) and not isinstance(one, bool) for one in raw
    ):
        raise DomainValidationError(
            "Une liste d'identifiants de propositions est attendue.", field=name
        )
    return list(raw)


def parse_decisions(data: dict) -> tuple[list[int], list[int]]:
    """`{accept: [ids], refuse: [ids]}`, checked."""
    accept, refuse = (
        _ids(data.get("accept"), "accept"),
        _ids(data.get("refuse"), "refuse"),
    )
    every = accept + refuse
    if not every:
        raise DomainValidationError("Choisis au moins une proposition.", field="accept")
    if len(every) > MAX_PROPOSITIONS:
        raise DomainValidationError(
            f"Un geste prend {MAX_PROPOSITIONS} propositions au plus : "
            f"celui-ci en a {len(every)}.",
            field="accept",
        )
    if len(set(every)) != len(every):
        raise DomainValidationError(
            "Une proposition paraît deux fois dans le geste.", field="accept"
        )
    return accept, refuse


def parse_reopen(data: dict) -> list[int]:
    """`{ids: [ids]}`, the propositions of the gesture to undo, checked."""
    ids = _ids(data.get("ids"), "ids")
    if not ids:
        raise DomainValidationError("Choisis au moins une proposition.", field="ids")
    if len(ids) > MAX_PROPOSITIONS:
        raise DomainValidationError(
            f"Un geste prend {MAX_PROPOSITIONS} propositions au plus : "
            f"celui-ci en a {len(ids)}.",
            field="ids",
        )
    if len(set(ids)) != len(ids):
        raise DomainValidationError(
            "Une proposition paraît deux fois dans le geste.", field="ids"
        )
    return ids


# -- deciding --------------------------------------------------------------------


async def _load(session: ormSession, ids: Iterable[int]) -> list[FicheProposition]:
    wanted = list(ids)
    if not wanted:
        return []
    rows = list(
        await session.scalars(
            select(FicheProposition)
            .where(FicheProposition.id.in_(wanted))
            .options(selectinload(FicheProposition.fiche))
            .execution_options(populate_existing=True)
        )
    )
    if len(rows) != len(set(wanted)):
        # A search made the propositions anew: their ids changed.
        raise DomainConflict(STALE_MESSAGE)
    return rows


def _check_states(propositions: list[FicheProposition]) -> None:
    for proposition in propositions:
        if proposition.state == STALE:
            raise DomainConflict(STALE_MESSAGE)
        if proposition.state != PROPOSED:
            raise DomainConflict("Une proposition a déjà été décidée : relis la page.")


def _check_levels(accepted: list[FicheProposition]) -> None:
    titles = {proposition.fiche_id for proposition in accepted}
    fields = [(one.fiche_id, one.field) for one in accepted]
    if len(set(fields)) != len(fields):
        raise DomainValidationError(
            "Deux valeurs pour le même champ d'un titre : choisis-en une.",
            field="accept",
        )
    if len(titles) > 1 and any(one.level != SURE for one in accepted):
        raise DomainValidationError(
            "Une proposition à revoir ou rapprochée s'accepte seule, titre par "
            "titre, une fois le titre ouvert.",
            field="accept",
        )


def _read(beets: BeetsIntegration, beets_id: int) -> Any:
    """A title as the write service will see it: a file written since Beets read
    it is read again, its tags are what counts."""
    item = beets.lib.get_item(beets_id)
    if item is None:
        return None
    try:
        if item.current_mtime() != int(item.get("mtime") or 0):
            item.read()
    except (OSError, FileOperationError):
        # The write service says what is wrong with the file.
        pass
    return item


def _changed_since(beets: BeetsIntegration, accepted: list[FicheProposition]) -> list:
    """The propositions whose value in the library is no longer the one they saw."""
    changed = []
    items: dict[int, Any] = {}
    for proposition in accepted:
        beets_id = proposition.fiche.beets_id
        if beets_id not in items:
            items[beets_id] = _read(beets, beets_id)
        item = items[beets_id]
        if item is None or not _same(
            proposition.field,
            current_value(item, proposition.field),
            typed(proposition.field, proposition.before),
        ):
            changed.append(proposition)
    return changed


def _stale(propositions: Iterable[FicheProposition]) -> None:
    for proposition in propositions:
        proposition.state = STALE
        proposition.error = ""
        # Its title is searched again before the rest of the catalogue.
        proposition.fiche.next_at = SEARCH_FIRST


async def _remember(
    session: ormSession,
    propositions: Iterable[FicheProposition],
    decision: str,
    username: str,
) -> None:
    """The decision, by the key of the title: a file that comes back gets it."""
    for proposition in propositions:
        key = proposition.fiche.key
        row = await session.scalar(
            select(FicheDecision).where(
                FicheDecision.key == key,
                FicheDecision.field == proposition.field,
                FicheDecision.value == proposition.value,
            )
        )
        if row is None:
            row = FicheDecision(
                key=key, field=proposition.field, value=proposition.value
            )
            session.add(row)
        row.decision = decision
        row.username = username
        row.decided_at = utcnow()


async def decide(
    session: ormSession,
    beets: BeetsIntegration,
    accept: list[int],
    refuse: list[int],
    *,
    username: str,
) -> Decided:
    """Accepted propositions written, refused ones put aside."""
    if accept:
        await require_title_edits(session)
    accepted = await _load(session, accept)
    refused = await _load(session, refuse)
    _check_states(accepted + refused)
    _check_levels(accepted)
    changed = await to_thread(_changed_since, beets, accepted)
    if changed:
        _stale(changed)
        await session.commit()
        raise DomainConflict(STALE_MESSAGE)

    await _remember(session, refused, REFUSE, username)
    for proposition in refused:
        proposition.state = REFUSED
        proposition.error = ""
    await _remember(session, accepted, ACCEPT, username)
    for proposition in accepted:
        proposition.state = ACCEPTED
        proposition.error = ""
    await session.commit()

    outcome = Decided(accepted=len(accepted), refused=len(refused))
    if accepted:
        await _write(session, beets, accepted, username, outcome)
    return outcome


def _by_title(
    propositions: Iterable[FicheProposition],
) -> dict[int, list[FicheProposition]]:
    grouped: dict[int, list[FicheProposition]] = defaultdict(list)
    for proposition in propositions:
        grouped[proposition.fiche.beets_id].append(proposition)
    return grouped


async def _write(
    session: ormSession,
    beets: BeetsIntegration,
    accepted: list[FicheProposition],
    username: str,
    outcome: Decided,
) -> None:
    """The accepted propositions written by the write service, and each one told
    what became of it."""
    grouped = _by_title(accepted)
    edits = []
    for beets_id, group in grouped.items():
        values: dict[str, object] = {}
        expected: dict[str, object] = {}
        for proposition in group:
            values.update(_values(proposition))
            expected[proposition.field] = typed(proposition.field, proposition.before)
        edits.append(TitleEdit(beets_id, values, expected))
    try:
        done = await edit_titles(
            session, beets, edits, username=username, gesture=GESTURE_ACCEPT
        )
    except BankBusyError:
        # The import loop holds the library: the background writes them later.
        for proposition in accepted:
            proposition.error = BUSY
        await session.commit()
        outcome.waiting = [
            {"id": beets_id, "label": "", "code": "busy", "reason": BUSY}
            for beets_id in sorted(grouped)
        ]
        return
    except DomainValidationError as invalid:
        # A value the write service does not take: nothing was written. Those of
        # its field say why; the others stay accepted, written at the next pass.
        for proposition in accepted:
            if invalid.field in (None, proposition.field):
                proposition.state = WRITE_FAILED
                proposition.error = invalid.message
        await session.commit()
        outcome.failed = [
            {"id": beets_id, "label": "", "code": "invalid", "reason": invalid.message}
            for beets_id, group in grouped.items()
            if any(one.state == WRITE_FAILED for one in group)
        ]
        return
    except TitlesRefused as refused:
        # A file failed on the way: nothing was written. Its propositions say so;
        # the others stay accepted, and the background writes them later.
        failing = {issue.beets_id for issue in refused.titles}
        for beets_id in failing:
            for proposition in grouped.get(beets_id, []):
                proposition.state = WRITE_FAILED
                proposition.error = ISSUE_MESSAGES[ISSUE_FAILED]
        await session.commit()
        outcome.failed = [issue.payload() for issue in refused.titles]
        return
    _tell(grouped, done, outcome)
    await session.commit()


def _tell(
    grouped: dict[int, list[FicheProposition]],
    done: EditOutcome,
    outcome: Decided,
) -> None:
    """Each accepted proposition told what its write became."""
    outcome.entry = done.entry_id
    for beets_id in [*done.written, *done.unchanged]:
        for proposition in grouped.get(beets_id, []):
            proposition.state = WRITTEN
            proposition.error = ""
            outcome.written += 1
    for issue in done.waiting:
        for proposition in grouped.get(issue.beets_id, []):
            proposition.error = issue.reason
        outcome.waiting.append(issue.payload())
    for issue in done.kept:
        group = grouped.get(issue.beets_id, [])
        if issue.code == ISSUE_CHANGED:
            _stale(group)
            outcome.stale += len(group)
            continue
        for proposition in group:
            proposition.state = WRITE_FAILED
            proposition.error = issue.reason
        outcome.failed.append(issue.payload())


# -- going back ------------------------------------------------------------------


async def revert(
    session: ormSession,
    beets: BeetsIntegration,
    proposition_id: int,
    *,
    username: str,
) -> Decided:
    """A written value back to the one before, while nobody changed it since."""
    await require_title_edits(session)
    proposition = await session.scalar(
        select(FicheProposition)
        .where(FicheProposition.id == proposition_id)
        .options(selectinload(FicheProposition.fiche))
    )
    if proposition is None:
        raise DomainNotFound("Cette proposition n'existe plus : relis la page.")
    if proposition.state != WRITTEN:
        raise DomainConflict("Seule une valeur écrite revient à celle d'avant.")
    name = proposition.field
    beets_id = proposition.fiche.beets_id
    values = {name: typed(name, proposition.before)}
    expected = {name: typed(name, proposition.value)}
    if name == "fmg":
        values["fmg_source"] = ""
    try:
        done = await edit_titles(
            session,
            beets,
            [TitleEdit(beets_id, values, expected)],
            username=username,
            gesture=GESTURE_UNDO,
        )
    except TitlesRefused as refused:
        raise DomainConflict(
            refused.titles[0].reason if refused.titles else refused.message
        ) from refused
    if done.kept:
        raise DomainConflict(
            "Sa valeur a changé depuis qu'elle a été écrite : elle la garde."
            if done.kept[0].code == ISSUE_CHANGED
            else done.kept[0].reason
        )
    proposition.state = REVERTED
    proposition.error = done.waiting[0].reason if done.waiting else ""
    # The acceptance is forgotten: a file that comes back does not get it again.
    await session.execute(
        delete(FicheDecision).where(
            FicheDecision.key == proposition.fiche.key,
            FicheDecision.field == name,
            FicheDecision.value == proposition.value,
        )
    )
    await session.commit()
    return Decided(
        written=len(done.written) + len(done.unchanged),
        waiting=[issue.payload() for issue in done.waiting],
        entry=done.entry_id,
    )


# -- undoing the last gesture (FON-78) ------------------------------------------


def _cancel_waiting(
    proposition: FicheProposition, changes: list[JournalChange]
) -> None:
    """The write an accepted proposition still waits for, cancelled: its latest
    in the journal, as `_settle` reads it. One being written right now is not: the
    gesture is tried again in an instant."""
    value = typed(proposition.field, proposition.value)
    for change in changes:
        if not _same(proposition.field, change.new_value, value):
            continue
        if change.status == STATUS_PENDING:
            raise DomainConflict(
                "Cette valeur s'écrit en ce moment : réessaie dans un instant."
            )
        if change.status == STATUS_WAITING:
            change.status = STATUS_CANCELLED
            change.reason = "Défaite avant d'avoir été écrite."
        return


async def _forget(session: ormSession, proposition: FicheProposition) -> None:
    await session.execute(
        delete(FicheDecision).where(
            FicheDecision.key == proposition.fiche.key,
            FicheDecision.field == proposition.field,
            FicheDecision.value == proposition.value,
        )
    )


async def _write_back(
    session: ormSession,
    beets: BeetsIntegration,
    written: dict[int, list[FicheProposition]],
    username: str,
) -> Decided:
    """The written values back to the ones before, by the write service. A title
    on air meanwhile gets them after its passage: its propositions say so."""
    edits = []
    for beets_id, group in written.items():
        values: dict[str, object] = {}
        expected: dict[str, object] = {}
        for proposition in group:
            name = proposition.field
            values[name] = typed(name, proposition.before)
            expected[name] = typed(name, proposition.value)
            if name == "fmg":
                values["fmg_source"] = ""
        edits.append(TitleEdit(beets_id, values, expected))
    try:
        done = await edit_titles(
            session, beets, edits, username=username, gesture=GESTURE_UNDO
        )
    except TitlesRefused as refused:
        raise DomainConflict(
            refused.titles[0].reason if refused.titles else refused.message
        ) from refused
    if done.kept:
        raise DomainConflict(
            "Sa valeur a changé depuis qu'elle a été écrite : elle la garde."
            if done.kept[0].code == ISSUE_CHANGED
            else done.kept[0].reason
        )
    for issue in done.waiting:
        # Back after its passage on air: it is no longer to read again.
        for proposition in written.get(issue.beets_id, []):
            proposition.state = REVERTED
            proposition.error = issue.reason
    return Decided(
        written=sum(
            len(written[beets_id]) for beets_id in [*done.written, *done.unchanged]
        ),
        waiting=[issue.payload() for issue in done.waiting],
        entry=done.entry_id,
    )


async def reopen(
    session: ormSession,
    beets: BeetsIntegration,
    ids: list[int],
    *,
    username: str,
) -> Decided:
    """The propositions of a gesture proposed again, as before it. A written value
    goes back to the one before, while nobody changed it since; one that still
    waits is never written; the decision is forgotten."""
    propositions = await _load(session, ids)
    for proposition in propositions:
        # A write that failed wrote nothing: it is proposed again, as it is.
        if proposition.state not in (ACCEPTED, WRITTEN, WRITE_FAILED, REFUSED):
            raise DomainConflict("Ce geste ne s'annule plus : relis la page.")
    if any(one.state in (ACCEPTED, WRITTEN) for one in propositions):
        await require_title_edits(session)
    waiting = [one for one in propositions if one.state == ACCEPTED]
    if waiting:
        journal = await _journal(session, {one.fiche.beets_id for one in waiting})
        for proposition in waiting:
            _cancel_waiting(
                proposition,
                journal.get((proposition.fiche.beets_id, proposition.field), []),
            )
    written = _by_title(one for one in propositions if one.state == WRITTEN)
    outcome = (
        await _write_back(session, beets, written, username) if written else Decided()
    )
    for proposition in propositions:
        await _forget(session, proposition)
        if proposition.state != REVERTED:
            proposition.state = PROPOSED
            proposition.error = ""
    await session.commit()
    return outcome


# -- searching again --------------------------------------------------------------


async def search_again(session: ormSession, beets_id: int) -> None:
    """The title searched before the rest of the catalogue, at the next step."""
    fiche = await session.scalar(select(Fiche).where(Fiche.beets_id == beets_id))
    if fiche is None:
        raise DomainNotFound("Ce titre n'a pas encore de fiche.")
    if not (await read_settings(session)).enabled:
        raise FichesOff(
            "La recherche en ligne est coupée : un admin l'allume dans "
            "Réglages → Fiches."
        )
    fiche.next_at = SEARCH_FIRST
    await session.commit()


# -- the background --------------------------------------------------------------


async def _journal(
    session: ormSession, beets_ids: Iterable[int]
) -> dict[tuple[int, str], list[JournalChange]]:
    """The accepted values in the journal, latest first, by title and field."""
    rows = await session.scalars(
        select(JournalChange)
        .join(JournalEntry, JournalChange.entry_id == JournalEntry.id)
        .where(
            JournalEntry.gesture == GESTURE_ACCEPT,
            JournalChange.beets_id.in_(list(beets_ids)),
        )
        .order_by(JournalChange.id.desc())
    )
    found: dict[tuple[int, str], list[JournalChange]] = defaultdict(list)
    for row in rows:
        found[(row.beets_id, row.field)].append(row)
    return found


def _settle(proposition: FicheProposition, changes: list[JournalChange]) -> str | None:
    """What the journal says of an accepted proposition: its new state, None when
    it still waits, or "" when it never went there."""
    value = typed(proposition.field, proposition.value)
    for change in changes:
        if not _same(proposition.field, change.new_value, value):
            continue
        if change.status in (STATUS_WAITING, STATUS_PENDING):
            proposition.error = change.reason or proposition.error
            return None
        if change.status == STATUS_DONE:
            return WRITTEN
        if change.status == STATUS_CANCELLED:
            return REVERTED
        if (
            change.status == STATUS_KEPT
            and change.reason == ISSUE_MESSAGES[ISSUE_CHANGED]
        ):
            return STALE
        if change.status in (STATUS_FAILED, STATUS_KEPT):
            proposition.error = change.reason or ISSUE_MESSAGES[ISSUE_FAILED]
            return WRITE_FAILED
    return ""


async def write_accepted(session: ormSession, beets: BeetsIntegration) -> int:
    """The accepted propositions follow the journal, and those that never went
    there are written. Returns the number of titles written."""
    if not await title_edits.title_edits_enabled(session):
        return 0
    await _follow_undos(session)
    accepted = list(
        await session.scalars(
            select(FicheProposition)
            .where(FicheProposition.state == ACCEPTED)
            .options(selectinload(FicheProposition.fiche))
            .order_by(FicheProposition.id)
        )
    )
    if not accepted:
        return 0
    journal = await _journal(session, {one.fiche.beets_id for one in accepted})
    limit = utcnow() - GRACE
    to_write: list[FicheProposition] = []
    for proposition in accepted:
        state = _settle(
            proposition,
            journal.get((proposition.fiche.beets_id, proposition.field), []),
        )
        if state == STALE:
            _stale([proposition])
        elif state:
            proposition.state = state
            if state in (WRITTEN, REVERTED):
                proposition.error = ""
        elif state == "" and proposition.modified <= limit:
            to_write.append(proposition)
    await session.commit()
    if not to_write:
        return 0
    grouped = _by_title(to_write)
    titles = sorted(grouped)[:BACKGROUND_TITLES]
    written = 0
    for beets_id in titles:
        group = grouped[beets_id]
        username = await _decided_by(session, group)
        outcome = Decided()
        await _write(session, beets, group, username, outcome)
        if outcome.written:
            written += 1
    return written


async def _follow_undos(session: ormSession) -> None:
    """A written proposition whose lot « Annuler » undid in the journal (FON-71)
    went back to its value before: it says so. Read on the recent undos only: the
    task passes every quarter of a minute."""
    since = utcnow() - UNDOS_SEEN
    undone = await session.scalars(
        select(JournalChange)
        .join(JournalEntry, JournalChange.entry_id == JournalEntry.id)
        .where(
            JournalEntry.gesture == GESTURE_UNDO,
            JournalEntry.undo_of.is_not(None),
            JournalChange.status == STATUS_DONE,
            JournalChange.applied_at >= since,
        )
    )
    back = {(row.beets_id, row.field): row for row in undone}
    if not back:
        return
    written = await session.scalars(
        select(FicheProposition)
        .join(Fiche, FicheProposition.fiche_id == Fiche.id)
        .where(
            FicheProposition.state == WRITTEN,
            Fiche.beets_id.in_([beets_id for beets_id, _field in back]),
        )
        .options(selectinload(FicheProposition.fiche))
    )
    for proposition in written:
        change = back.get((proposition.fiche.beets_id, proposition.field))
        if change is None:
            continue
        name = proposition.field
        if _same(name, change.old_value, typed(name, proposition.value)) and _same(
            name, change.new_value, typed(name, proposition.before)
        ):
            proposition.state = REVERTED
            proposition.error = ""
    await session.commit()


async def _decided_by(session: ormSession, group: list[FicheProposition]) -> str:
    """Who accepted: the journal names them."""
    first = group[0]
    row = await session.scalar(
        select(FicheDecision).where(
            FicheDecision.key == first.fiche.key,
            FicheDecision.field == first.field,
            FicheDecision.value == first.value,
        )
    )
    return row.username if row is not None else "fiches"
