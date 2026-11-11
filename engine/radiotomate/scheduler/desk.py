"""Desk (pupitre) edits of the rundown: pins, suppressions, patches, reorder.

Split out of ``execution.py``; the forecast/reconcile core stays there and this
module only *edits* rows that the clock will later push.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, NamedTuple
from uuid import uuid4

from sqlalchemy import and_, or_, select

from radiotomate.domain.errors import (
    DomainConflict,
    DomainNotFound,
    DomainValidationError,
)
from radiotomate.domain.execution import (
    ENGAGED_STATUSES,
    naive_datetime,
    rundown_summary,
)
from radiotomate.enums import CommandStatus, PositionKind, RundownStatus, WhenMode
from radiotomate.models import PlayoutCommand, RundownItem, Setting, Sound
from radiotomate.scheduler.clock import _PUSHABLE_STATUSES
from radiotomate.scheduler.execution import (
    _CLOSED_DESK_STATUSES,
    DESK_KINDS,
    DESK_ORIGIN,
    _next_sequence,
    ensure_programming_version,
    item_to_payload,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

# ADR 0009: turned off, a clock line removed at the desk airs, as before.
SETTING_SKIP_REMOVED = "features.skip_removed_lines"
# ADR 0009: turned off, the clock leaves the desk lines alone, as before: they
# never air, and drop from the file once their time is over.
SETTING_DESK_LINES_AIR = "features.desk_lines_air"
_SETTING_OFF = {"0", "false", "off", ""}
REPLACED_REASON = "remplacé au pupitre"

# Handed to the playout, not yet on air. Liquidsoap plays a line in the order it
# got it and cannot give it back: removed or moved, it would air all the same.
_SENT_STATUSES = ENGAGED_STATUSES - {RundownStatus.ON_AIR.value}
_SENT_REMOVE = (
    "Cette ligne est déjà partie vers l'antenne : elle ne se retire plus. "
    "Une fois à l'antenne, « Suivant » la coupe."
)
_SENT_MOVE = "Cette ligne est déjà partie vers l'antenne : elle ne se déplace plus."
_SENT_EDIT = "Cette ligne est déjà partie vers l'antenne : elle ne se modifie plus."
# A sent line still not on air an hour after its time will not air: the queue
# cleaner takes out of Liquidsoap what waits there longer than ten minutes, by
# default (``queue_cleaner.max_age_seconds``).
SENT_GRACE = timedelta(hours=1)
# The default age past which the queue cleaner takes a request out of Liquidsoap.
QUEUE_MAX_AGE = timedelta(minutes=10)
# Details key of the line « Jouer tout de suite » sends itself: it airs at once,
# not at the time the file gives it, and moves no other line.
PLAYED_NOW = "played_now"
_OPEN_COMMANDS = {CommandStatus.PENDING.value, CommandStatus.SENDING.value}


def desk_queue_for(kind: str) -> str:
    if kind == PositionKind.JINGLE.value:
        return "jingles"
    if kind == PositionKind.MUSIQUE.value:
        return "autodj"
    return "carts"


def _desk_resource(artist: str, title: str) -> str:
    artist = artist.strip()
    title = title.strip()
    if artist and title:
        return f"{artist} — {title}"
    return title or artist or "Titre"


def _parse_iso(value: str) -> datetime:
    raw = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    parsed = naive_datetime(raw)
    if parsed is None:
        raise DomainValidationError("Horodatage invalide.", field="at")
    return parsed


def item_is_locked(item: RundownItem) -> bool:
    if item.status == RundownStatus.ON_AIR.value:
        return True
    return item.when_mode == WhenMode.ANCHORED.value


def item_is_sent(item: RundownItem) -> bool:
    """Already handed to the playout, and not yet on air."""
    return item.status in _SENT_STATUSES


async def list_active_desk_items(session: ormSession) -> list[RundownItem]:
    rows = list(
        await session.scalars(
            select(RundownItem)
            .where(
                RundownItem.origin == DESK_ORIGIN,
                RundownItem.status.notin_(list(_CLOSED_DESK_STATUSES)),
            )
            .order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )
    return rows


def merge_desk_into_items(
    forecast: list[dict],
    desk_payloads: list[dict],
) -> list[dict]:
    # A removal hides the clock rows it found at its time, by id: a row that a
    # reorder later puts at that time stays shown. Without ids, by time.
    hidden_ids: set[str] = set()
    hidden_at: set[str] = set()
    for row in desk_payloads:
        at = row.get("suppress_at") or row.get("hides_at")
        if row.get("hides_ids"):
            hidden_ids.update(row["hides_ids"])
        elif at:
            hidden_at.add(str(at))
    visible_desk = [
        row for row in desk_payloads if row.get("path") or not row.get("suppress_at")
    ]
    kept: list[dict] = []
    for item in forecast:
        origin = str(item.get("origin") or "clock")
        if origin == DESK_ORIGIN:
            continue
        stamped = dict(item)
        stamped.setdefault("origin", origin)
        if not stamped.get("id"):
            key = stamped.get("path") or stamped.get("resource") or ""
            stamped["id"] = f"clock|{stamped.get('at')}|{key}"
        at = str(stamped.get("at") or "")
        hidden = stamped["id"] in hidden_ids or at in hidden_at
        if hidden and stamped.get("when") != WhenMode.ANCHORED.value:
            continue
        kept.append(stamped)

    combined = kept + visible_desk

    def sort_key(row: dict) -> tuple[str, int]:
        origin = 0 if row.get("origin") == DESK_ORIGIN else 1
        return (str(row.get("at") or ""), origin)

    combined.sort(key=sort_key)
    return combined


async def skip_removed_lines(session: ormSession) -> bool:
    """Whether the clock leaves out the lines removed at the desk. A missing key
    leaves them out."""
    row = await Setting.from_key(session, SETTING_SKIP_REMOVED)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


async def desk_lines_air(session: ormSession) -> bool:
    """Whether the clock pushes the desk lines at their turn. A missing key says
    it does."""
    row = await Setting.from_key(session, SETTING_DESK_LINES_AIR)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


def _is_removal(row: RundownItem) -> bool:
    return bool((row.details or {}).get("suppress_at"))


def _is_replacement(row: RundownItem) -> bool:
    """A desk line put in the place of the clock rows at its time (``replace_at``)."""
    details = row.details or {}
    return bool(row.path) and bool(details.get("hides_ids") or details.get("hides_at"))


def _removed_by(removal: RundownItem):
    """The clock rows a removal takes off, those it hides from the file: by id, or
    by time for a removal posted by an older engine, which has no ids."""
    ids = (removal.details or {}).get("hides_ids")
    taken = (
        RundownItem.id.in_(list(ids))
        if ids
        else RundownItem.planned_at == removal.planned_at
    )
    return and_(
        taken,
        RundownItem.origin != DESK_ORIGIN,
        RundownItem.when_mode != WhenMode.ANCHORED.value,
    )


async def _hiding(session: ormSession, rows: list[RundownItem]) -> list[RundownItem]:
    """The desk rows that take clock rows off the antenna: the removals, and, while
    the desk lines air, the replacements, which go in their place."""
    hiding = [row for row in rows if _is_removal(row)]
    if hiding and not await skip_removed_lines(session):
        hiding = []
    replacements = [row for row in rows if _is_replacement(row)]
    if replacements and await desk_lines_air(session):
        hiding += replacements
    return hiding


async def removed_clock_ids(session: ormSession) -> set[str]:
    """Ids of the clock rows removed at the desk: the clock does not push them while
    their removal lasts. « Annuler » deletes the removal and gives them back."""
    hiding = await _hiding(session, await list_active_desk_items(session))
    if not hiding:
        return set()
    return set(
        await session.scalars(
            select(RundownItem.id).where(or_(*(_removed_by(row) for row in hiding)))
        )
    )


async def close_replaced(session: ormSession, line: RundownItem, now: datetime) -> None:
    """A replacement has gone to the playout: the clock rows it hides will never
    air. Closed « remplacé », they do not go either once it is over."""
    if not _is_replacement(line):
        return
    rows = await session.scalars(
        select(RundownItem).where(
            RundownItem.status.in_(list(_PUSHABLE_STATUSES)),
            _removed_by(line),
        )
    )
    for row in rows:
        row.status = RundownStatus.REPLACED.value
        row.reason = REPLACED_REASON
        row.closed_at = naive_datetime(now)


async def _skip_removed(
    session: ormSession, removals: list[RundownItem], now: datetime
) -> None:
    rows = await session.scalars(
        select(RundownItem).where(
            RundownItem.status.in_(list(_PUSHABLE_STATUSES)),
            or_(*(_removed_by(row) for row in removals)),
        )
    )
    for row in rows:
        row.status = RundownStatus.SKIPPED.value
        row.reason = "retiré de la file"
        row.closed_at = now


async def _detach_commands(session: ormSession, rows: list[RundownItem]) -> None:
    """Unlink the playout commands of rows about to go, as a reset of the conducteur
    does: they point at them. A command still to send expires with them."""
    ids = [row.id for row in rows if row.reserved_at is not None]
    if not ids:
        return
    commands = await session.scalars(
        select(PlayoutCommand).where(PlayoutCommand.rundown_item_id.in_(ids))
    )
    for command in commands:
        command.rundown_item_id = None
        if command.status in _OPEN_COMMANDS:
            command.status = CommandStatus.EXPIRED.value
            command.last_error = "ligne du pupitre retirée"
    await session.flush()


async def expire_past_desk_items(
    session: ormSession, now: datetime | None = None
) -> None:
    """Drop unlocked desk pins whose planned window is already over.

    A removal that goes marks its lines skipped: the clock passed them over, and
    with nothing left to hide them they would air late. A replacement that never
    went does the same, while the desk lines air. A line sent to the playout stays
    while it waits for its turn in Liquidsoap, which plays it all the same.
    """
    cutoff = naive_datetime(now) or datetime.now()
    rows = await list_active_desk_items(session)
    stale: list[RundownItem] = []
    for row in rows:
        if item_is_locked(row):
            continue
        start = row.planned_at
        if start is None:
            continue
        hold = max(float(row.duration or 0), 30.0)
        end = start + timedelta(seconds=hold)
        if item_is_sent(row):
            end += SENT_GRACE
        if end <= cutoff:
            stale.append(row)
    if not stale:
        return
    hiding = await _hiding(session, stale)
    if hiding:
        await _skip_removed(session, hiding, cutoff)
    await _detach_commands(session, stale)
    for row in stale:
        await session.delete(row)
    await session.commit()


async def attach_desk_pins(session: ormSession, payload: dict) -> dict:
    await expire_past_desk_items(session)
    desk_rows = await list_active_desk_items(session)
    desk_payloads = []
    for row in desk_rows:
        item = item_to_payload(row)
        details = dict(row.details or {})
        if details.get("suppress_at"):
            item["suppress_at"] = details["suppress_at"]
        if details.get("hides_ids"):
            item["hides_ids"] = details["hides_ids"]
        desk_payloads.append(item)
    items = merge_desk_into_items(list(payload.get("items") or []), desk_payloads)
    merged = dict(payload)
    merged["items"] = items
    merged["summary"] = rundown_summary(items)
    return merged


async def _on_air_end(session: ormSession) -> datetime | None:
    row = await session.scalar(
        select(RundownItem)
        .where(RundownItem.status == RundownStatus.ON_AIR.value)
        .order_by(RundownItem.started_at.desc(), RundownItem.planned_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    start = row.started_at or row.planned_at
    return start + timedelta(seconds=float(row.duration or 0))


async def _on_air_floor(session: ormSession) -> datetime:
    """Now, or the end of the title on air when it is later."""
    now = datetime.now()
    return max(now, naive_datetime(await _on_air_end(session)) or now)


async def _sent_end(session: ormSession) -> datetime | None:
    """While the desk lines air, the end of the last line already sent to the
    playout: Liquidsoap plays it first, in the order it got it. None otherwise."""
    if not await desk_lines_air(session):
        return None
    # A line sent longer ago is no longer in Liquidsoap: played without word, or
    # taken out by the queue cleaner. Its status says sent all the same.
    recent = datetime.now() - QUEUE_MAX_AGE
    rows = await session.scalars(
        select(RundownItem).where(
            RundownItem.status.in_(list(_SENT_STATUSES)),
            RundownItem.reserved_at >= recent,
        )
    )
    # The line of « Jouer tout de suite » is dated after the title on air, but
    # plays at once: its time says nothing of where the next line goes. On air,
    # it gives the floor as the title on air does.
    ends = [
        naive_datetime(row.planned_at) + timedelta(seconds=float(row.duration or 0))
        for row in rows
        if row.planned_at is not None and not (row.details or {}).get(PLAYED_NOW)
    ]
    return max(ends, default=None)


async def _earliest_start(session: ormSession) -> datetime:
    """Now, or the end of the title on air when it is later, or the end of the lines
    already sent to the playout (``_sent_end``).

    A line dated earlier can end before now: it leaves the antenna file, and a
    desk pin is then dropped by ``expire_past_desk_items``.
    """
    floor = await _on_air_floor(session)
    sent = await _sent_end(session)
    return floor if sent is None else max(floor, sent)


async def _planned_at_for_insert(
    session: ormSession,
    *,
    after_id: str | None,
    before_id: str | None,
    replace_at: str | None,
) -> datetime:
    if replace_at:
        return _parse_iso(replace_at)
    floor = await _earliest_start(session)
    if before_id:
        target = await RundownItem.from_id(session, before_id)
        if target is not None and target.planned_at is not None:
            # Above a line still to come, half a second ahead of it: the floor
            # could put it below, as realign_rundown leaves under 5 s of drift.
            # Never above a line already sent: it airs first all the same.
            start = target.planned_at - timedelta(milliseconds=500)
            if start <= datetime.now():
                return floor
            sent = await _sent_end(session)
            return start if sent is None else max(start, sent)
    if after_id:
        after = await RundownItem.from_id(session, after_id)
        if after is not None:
            start = after.started_at or after.planned_at
            return max(start + timedelta(seconds=float(after.duration or 0)), floor)
    return floor


async def _clock_row_ids_at(session: ormSession, at: datetime) -> list[str]:
    """Ids of the clock rows planned at that very time: those a removal hides. A row
    already sent to the playout would air anyway: the removal is refused."""
    rows = list(
        await session.scalars(
            select(RundownItem).where(
                RundownItem.planned_at == at,
                RundownItem.origin != DESK_ORIGIN,
                RundownItem.when_mode != WhenMode.ANCHORED.value,
            )
        )
    )
    if any(item_is_sent(row) for row in rows):
        raise DomainConflict(_SENT_REMOVE)
    return [row.id for row in rows]


class DeskPin(NamedTuple):
    path: str
    kind: str
    artist: str
    title: str
    duration: float


def read_desk_pin(data: dict) -> DeskPin:
    """Checked fields of a desk pin. "Play now" reads them before its order."""
    path = str(data.get("path") or "").strip()
    if not path:
        raise DomainValidationError("Chemin audio requis.", field="path")
    kind = str(data.get("kind") or PositionKind.SON.value).strip()
    if kind not in DESK_KINDS:
        raise DomainValidationError("Type audio inconnu.", field="kind")
    try:
        duration = float(data.get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("Durée invalide.", field="duration") from exc
    if duration <= 0:
        duration = 8.0
    return DeskPin(
        path=path,
        kind=kind,
        artist=str(data.get("artist") or "").strip(),
        title=str(data.get("title") or "").strip(),
        duration=duration,
    )


async def insert_desk_item(
    session: ormSession, data: dict, *, sent: bool = False
) -> RundownItem:
    """A desk line, to come. ``sent``: « Jouer tout de suite » has already handed it
    to the playout. It is then in its queue, and the clock does not push it again:
    it follows it to the antenna like any line sent."""
    suppress_at = str(data.get("suppress_at") or "").strip()
    if suppress_at:
        return await _insert_suppress(session, suppress_at)

    path, kind, artist, title, duration = read_desk_pin(data)
    sound = await Sound.from_media_path(session, path)
    version = await ensure_programming_version(session)
    replace_at = str(data.get("replace_at") or "").strip() or None
    if sent:
        planned_at = await _on_air_floor(session)
    else:
        planned_at = await _planned_at_for_insert(
            session,
            after_id=str(data.get("after_id") or "").strip() or None,
            before_id=str(data.get("before_id") or "").strip() or None,
            replace_at=replace_at,
        )
    details = {
        "artist": artist,
        "title": title or _desk_resource(artist, title),
        "cart": str(data.get("cart") or ""),
    }
    if replace_at:
        details["hides_at"] = replace_at
        details["hides_ids"] = await _clock_row_ids_at(session, planned_at)
    item = RundownItem(
        id=str(uuid4()),
        programming_version_id=version.id,
        sequence=await _next_sequence(session),
        planned_at=naive_datetime(planned_at) or datetime.now(),
        duration=duration,
        kind=kind,
        when_mode=WhenMode.SEQUENTIAL.value,
        queue=desk_queue_for(kind),
        resource=_desk_resource(artist, title),
        path=path,
        details=details,
        status=RundownStatus.PLANNED.value,
        origin=DESK_ORIGIN,
        cart_id=sound.cart_id if sound is not None else None,
        sound_id=sound.id if sound is not None else None,
    )
    if sent:
        now = datetime.now()
        item.details = {**details, PLAYED_NOW: True}
        item.status = RundownStatus.IN_QUEUE.value
        item.reserved_at = item.sent_at = item.accepted_at = item.queued_at = now
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def _insert_suppress(session: ormSession, at: str) -> RundownItem:
    planned_at = _parse_iso(at)
    version = await ensure_programming_version(session)
    item = RundownItem(
        id=str(uuid4()),
        programming_version_id=version.id,
        sequence=await _next_sequence(session),
        planned_at=planned_at,
        duration=0,
        kind=PositionKind.SON.value,
        when_mode=WhenMode.SEQUENTIAL.value,
        queue="carts",
        resource="",
        path=None,
        details={
            "suppress_at": at,
            "hides_ids": await _clock_row_ids_at(session, planned_at),
        },
        status=RundownStatus.PLANNED.value,
        origin=DESK_ORIGIN,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


def _require_mutable_desk(item: RundownItem) -> None:
    if item_is_locked(item):
        raise DomainConflict(
            "Impossible de modifier un passage à l'antenne ou une ancre dure."
        )
    if item.origin != DESK_ORIGIN:
        raise DomainConflict("Ce passage vient de l'horloge.")
    if item_is_sent(item):
        raise DomainConflict(_SENT_EDIT)


async def patch_desk_item(session: ormSession, item_id: str, data: dict) -> RundownItem:
    item = await RundownItem.from_id(session, item_id)
    if item is None:
        raise DomainNotFound("Passage introuvable.")
    _require_mutable_desk(item)
    path = str(data.get("path") or item.path or "").strip()
    if not path:
        raise DomainValidationError("Chemin audio requis.", field="path")
    kind = str(data.get("kind") or item.kind).strip()
    if kind not in DESK_KINDS:
        raise DomainValidationError("Type audio inconnu.", field="kind")
    artist = str(data.get("artist") or (item.details or {}).get("artist") or "").strip()
    title = str(data.get("title") or (item.details or {}).get("title") or "").strip()
    if data.get("duration") is not None:
        try:
            duration = float(data.get("duration") or 0)
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("Durée invalide.", field="duration") from exc
        if duration > 0:
            item.duration = duration
    sound = await Sound.from_media_path(session, path)
    item.path = path
    item.kind = kind
    item.queue = desk_queue_for(kind)
    item.resource = _desk_resource(artist, title)
    item.details = {
        **dict(item.details or {}),
        "artist": artist,
        "title": title or item.resource,
    }
    item.cart_id = sound.cart_id if sound is not None else None
    item.sound_id = sound.id if sound is not None else None
    await session.commit()
    await session.refresh(item)
    return item


async def delete_desk_item(session: ormSession, item_id: str) -> None:
    item = await RundownItem.from_id(session, item_id)
    if item is None:
        raise DomainNotFound("Passage introuvable.")
    if item_is_locked(item):
        raise DomainConflict(
            "Impossible de retirer un passage à l'antenne ou une ancre dure."
        )
    if item_is_sent(item):
        raise DomainConflict(_SENT_REMOVE)
    # A line the playout refused: its command points at it.
    await _detach_commands(session, [item])
    await session.delete(item)
    await session.commit()


async def reorder_desk_items(session: ormSession, ids: list[str]) -> None:
    """Pack the given rows from the earliest of their start times.

    Desk pins and clock rows in the antenna file both move. On-air and hard
    anchors stay put. A row that takes the first slot from another never starts
    in the past, nor before the end of the title on air: moved above a row that
    has already started, it would end before now, leave the antenna file, and a
    desk pin would then be dropped by ``expire_past_desk_items``. A first row
    that keeps its slot keeps its start: the rows behind it end after it.
    """
    if not ids:
        raise DomainValidationError("Liste d'identifiants requise.", field="ids")
    found = list(
        await session.scalars(select(RundownItem).where(RundownItem.id.in_(ids)))
    )
    by_id = {row.id: row for row in found}
    ordered: list[RundownItem] = []
    for item_id in ids:
        row = by_id.get(item_id)
        if row is None or row.status in _CLOSED_DESK_STATUSES:
            continue
        if item_is_locked(row):
            raise DomainConflict("Impossible de réordonner un passage verrouillé.")
        if item_is_sent(row):
            raise DomainConflict(_SENT_MOVE)
        ordered.append(row)
    if not ordered:
        raise DomainValidationError("Aucun passage à réordonner.", field="ids")
    starts = [row.planned_at for row in ordered if row.planned_at is not None]
    first = min(starts) if starts else None
    cursor = naive_datetime(first)
    if cursor is None or ordered[0].planned_at != first:
        floor = await _earliest_start(session)
        cursor = floor if cursor is None else max(cursor, floor)
    for index, row in enumerate(ordered):
        row.planned_at = naive_datetime(cursor) or datetime.now()
        row.sequence = index
        cursor = row.planned_at + timedelta(seconds=float(row.duration or 0))
    await session.commit()
