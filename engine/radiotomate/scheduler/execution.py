"""Persist the forecast rundown and reconcile it with as-run events."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import and_, case, delete, func, or_, select

from radiotomate.domain.execution import (
    ENGAGED_STATUSES,
    REPLACEABLE_STATUSES,
    RESET_KEEP_STATUSES,
    naive_datetime,
    programming_fingerprint,
    rundown_summary,
    status_label,
)
from radiotomate.enums import (
    CommandStatus,
    PositionKind,
    RundownStatus,
    SyncMode,
    WhenMode,
)
from radiotomate.models import (
    AutoDJSlot,
    Cart,
    Clock,
    ClockPosition,
    MetadataLog,
    PlayoutCommand,
    ProgrammingVersion,
    RundownItem,
    Setting,
    Sound,
)
from radiotomate.scheduler.clock import (
    lost_lines_close,
    motif_jingles_air,
    now_paris,
    rebuilds_after_upgrade,
    reset_sequencer,
)
from radiotomate.scheduler.timing import queue_empty, queued_count, source_id

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration
    from radiotomate.scheduler.playout import PlayoutGateway

_log = logging.getLogger(__name__)

SETTING_FIRED_ANCHORS = "clock_fired_anchors"
SETTING_PROGRAMMING_VERSION = "clock_programming_version"
SETTING_MISSING_FORECAST = "clock_missing_forecast"
# A forecast made only of lines it knew missing (« manquant »: no title in Beets,
# no sound in the cart) holds that long, unless what it is drawn from changes
# first. Drawn anew at each call, it cost a station with nothing to play a draw
# at every tick, a second apart, and six hours of it at each call of the console.
MISSING_FORECAST_HOLD = timedelta(minutes=1)
# The last reading of the forecast in this process: when (monotonic), and whether
# it was made only of missing lines. The scheduler's tick gate asks (live.py).
_last_reading: dict = {"at": 0.0, "nothing_to_play": False}
DESK_ORIGIN = "desk"
DESK_KINDS = {
    PositionKind.MUSIQUE.value,
    PositionKind.JINGLE.value,
    PositionKind.SON.value,
    PositionKind.PUB.value,
}
_CLOSED_DESK_STATUSES = {
    RundownStatus.PLAYED.value,
    RundownStatus.SKIPPED.value,
    RundownStatus.REPLACED.value,
}
FLUSHED_REASON = "file vidée"
PAST_REASON = "heure passée"
TURN_PASSED_REASON = "tour passé"
# A hard anchor goes on its minute, a soft one at the end of the title astride
# it, an hour after its minute at most (clock._planned_anchor_item): an anchor
# line still planned an hour after its time will never go.
PAST_ANCHOR_AFTER = timedelta(hours=1)
PLAYOUT_QUEUES = ("autodj", "jingles", "carts")
# A line Liquidsoap holds: what a flush takes out of its queues.
_QUEUED_STATUSES = {
    RundownStatus.SENT.value,
    RundownStatus.ACCEPTED.value,
    RundownStatus.IN_QUEUE.value,
}
# What the beat of the playout says of a queue: how many sounds, and the next.
_QUEUE_BEAT = {
    "autodj": ("autodj_queued", "next_autodj"),
    "jingles": ("jingles_queued", "next_jingle"),
    "carts": ("carts_queued", "next_cart"),
}
LOST_REASON = "plus dans le playout"
# A push the playout has just taken may not be in its beat yet.
LOST_AFTER = timedelta(seconds=15)
# How build_rundown plans the conducteur, and how the clock and the as-run
# follow it. To bump when an engine plans another way than the one before: at
# its first tick, the lines the other left are drawn again
# (rebuild_after_upgrade). 2: the title a hard anchor cuts is planned (FON-58).
FORECAST_REVISION = "2"
SETTING_FORECAST_REVISION = "clock_forecast_revision"
_upgrade = {"checked": False}


async def programming_parts(session: ormSession) -> list[str]:
    clocks = await Clock.all(session, load_positions=False)
    slots = list(await AutoDJSlot.all(session))
    parts = [
        f"c:{clock.id}:{clock.version}:{clock.name}"
        for clock in sorted(clocks, key=lambda row: row.id)
    ]
    parts.extend(
        (
            f"s:{slot.id}:{slot.version}:{slot.day_of_week}:{slot.minute}:"
            f"{slot.clock_id}"
        )
        for slot in slots
    )
    # The motif cursor is *state*, not programming: including it minted one
    # ProgrammingVersion per track (196 rows in 20 h in production).
    return parts


async def ensure_programming_version(
    session: ormSession,
    *,
    source: str = "autodj",
) -> ProgrammingVersion:
    version_id = programming_fingerprint(await programming_parts(session))
    existing = await session.get(ProgrammingVersion, version_id)
    if existing is not None:
        return existing
    version = ProgrammingVersion(
        id=version_id,
        source=source,
        description="clocks+dayparts",
        created=datetime.now(),
    )
    session.add(version)
    await session.flush()
    await Setting.upsert(session, SETTING_PROGRAMMING_VERSION, version_id)
    return version


def fired_anchor_key(date_iso: str, hour: int, minute: int) -> str:
    return f"{date_iso}|{hour}|{minute}"


def parse_fired_anchor(raw: str) -> tuple[str, int, int] | None:
    parts = raw.split("|")
    if len(parts) != 3:
        return None
    try:
        return parts[0], int(parts[1]), int(parts[2])
    except ValueError:
        return None


async def load_fired_anchors(session: ormSession) -> set[tuple[str, int, int]]:
    row = await Setting.from_key(session, SETTING_FIRED_ANCHORS)
    if row is None or not row.value:
        return set()
    try:
        raw = json.loads(row.value)
    except json.JSONDecodeError:
        return set()
    keys: set[tuple[str, int, int]] = set()
    if not isinstance(raw, list):
        return keys
    for item in raw:
        parsed = parse_fired_anchor(str(item))
        if parsed is not None:
            keys.add(parsed)
    return keys


async def persist_fired_anchors(
    session: ormSession,
    keys: set[tuple[str, int, int]],
) -> None:
    payload = [
        fired_anchor_key(date_iso, hour, minute)
        for date_iso, hour, minute in sorted(keys)
    ]
    await Setting.upsert(session, SETTING_FIRED_ANCHORS, json.dumps(payload))


def item_to_payload(item: RundownItem) -> dict:
    details = dict(item.details or {})
    payload = {
        "id": item.id,
        "at": item.planned_at.isoformat(),
        "kind": item.kind,
        "when": item.when_mode,
        "resource": item.resource,
        "queue": item.queue,
        "status": status_label(item.status),
        "status_code": item.status,
        "reason": item.reason,
        "clock": item.clock_name,
        "daypart": item.daypart,
        "duration": item.duration,
        "clock_id": item.clock_id,
        "position_id": item.clock_position_id,
        "cart_id": item.cart_id,
        "sound_id": item.sound_id,
        "beets_id": item.beets_id,
        "fallback_used": item.fallback_used,
        "programming_version": item.programming_version_id,
        "origin": item.origin,
    }
    if item.when_mode == "anchored":
        payload["minute"] = details.get("minute", item.details.get("minute"))
        payload["sync"] = item.sync
    if details.get("category"):
        payload["category"] = details["category"]
    if details.get("cart"):
        payload["cart"] = details["cart"]
    if item.path:
        payload["path"] = item.path
    if details.get("artist"):
        payload["artist"] = details["artist"]
    if details.get("title"):
        payload["title"] = details["title"]
    if details.get("hides_at"):
        payload["hides_at"] = details["hides_at"]
    if details.get("suppress_at"):
        payload["suppress_at"] = details["suppress_at"]
    if details.get("diffusion_id") is not None:
        payload["diffusion_id"] = details["diffusion_id"]
    return payload


def _status_from_forecast(payload: dict) -> str:
    raw = str(payload.get("status") or "")
    if raw in {item.value for item in RundownStatus}:
        return raw
    if raw == "secours" or payload.get("fallback_used"):
        return RundownStatus.RESCUE.value
    if raw == "sauté":
        return RundownStatus.SKIPPED.value
    if raw == "manquant":
        return RundownStatus.FAILED.value
    return RundownStatus.PLANNED.value


def item_from_forecast(
    payload: dict,
    version: ProgrammingVersion,
    sequence: int,
) -> RundownItem:
    planned_at = naive_datetime(datetime.fromisoformat(payload["at"]))
    details = {
        "minute": payload.get("minute"),
        "category": payload.get("category"),
        "cart": payload.get("cart"),
        "glissement": payload.get("reason") == "glissement",
    }
    if payload.get("artist"):
        details["artist"] = payload["artist"]
    if payload.get("title"):
        details["title"] = payload["title"]
    if payload.get("rg_track_gain") is not None:
        details["rg_track_gain"] = payload["rg_track_gain"]
    if payload.get("diffusion_id") is not None:
        details["diffusion_id"] = payload["diffusion_id"]
    return RundownItem(
        id=str(payload.get("id") or uuid4()),
        programming_version_id=version.id,
        sequence=sequence,
        planned_at=planned_at,
        duration=float(payload.get("duration") or 0),
        kind=str(payload.get("kind") or ""),
        when_mode=str(payload.get("when") or "sequential"),
        sync=payload.get("sync"),
        queue=str(payload.get("queue") or "autodj"),
        resource=str(payload.get("resource") or ""),
        path=payload.get("path"),
        clock_name=payload.get("clock"),
        daypart=payload.get("daypart"),
        details=details,
        status=_status_from_forecast(payload),
        reason=payload.get("reason"),
        origin=str(payload.get("origin") or "clock"),
        clock_id=payload.get("clock_id"),
        clock_position_id=payload.get("position_id"),
        cart_id=payload.get("cart_id"),
        sound_id=payload.get("sound_id"),
        beets_id=payload.get("beets_id"),
        fallback_used=bool(payload.get("fallback_used")),
        created=datetime.now(),
    )


async def replace_forecast_items(
    session: ormSession,
    version: ProgrammingVersion,
    payloads: list[dict],
    *,
    now: datetime,
) -> list[RundownItem]:
    cutoff = naive_datetime(now)
    await session.execute(
        delete(RundownItem).where(
            or_(
                and_(
                    RundownItem.status.in_(list(REPLACEABLE_STATUSES)),
                    RundownItem.planned_at >= cutoff,
                ),
                # A line the forecast already knew it could not play ("manquant":
                # no title, no cart) is a forecast too, never sent: this draw
                # replaces it, even just past. Kept, it piled up at every tick of
                # a station with nothing to play, where nothing counts as runway
                # and each tick drew anew: 17 lines a second, 7 days kept.
                and_(
                    RundownItem.status == RundownStatus.FAILED.value,
                    RundownItem.sent_at.is_(None),
                    RundownItem.closed_at.is_(None),
                ),
            ),
            RundownItem.origin != DESK_ORIGIN,
        )
    )
    items = [
        item_from_forecast(payload, version, sequence)
        for sequence, payload in enumerate(payloads)
    ]
    session.add_all(items)
    await session.flush()
    return items


def _align_tz(dt: datetime, ref: datetime) -> datetime:
    if dt.tzinfo is None and ref.tzinfo is not None:
        return dt.replace(tzinfo=ref.tzinfo)
    if dt.tzinfo is not None and ref.tzinfo is None:
        return dt.replace(tzinfo=None)
    return dt


def _row_end_at(row: RundownItem) -> datetime:
    return row.planned_at + timedelta(seconds=max(0.0, float(row.duration or 0)))


def _horizon_end(rows: list[RundownItem], now: datetime) -> datetime:
    last = None
    for row in rows:
        end = _align_tz(_row_end_at(row), now)
        if last is None or end > last:
            last = end
    return last if last is not None else now


async def _cursor_after_items(
    session: ormSession,
    rows: list[RundownItem],
) -> int | None:
    for row in reversed(rows):
        if row.origin == DESK_ORIGIN:
            continue
        if row.when_mode == WhenMode.ANCHORED.value:
            continue
        if not row.clock_id or not row.clock_position_id:
            continue
        clock = await Clock.from_id(session, row.clock_id)
        if clock is None:
            continue
        for index, pos in enumerate(clock.sequential_positions()):
            if pos.id == row.clock_position_id:
                return index + 1
    return None


async def append_forecast_items(
    session: ormSession,
    version: ProgrammingVersion,
    payloads: list[dict],
    *,
    existing: list[RundownItem],
) -> list[RundownItem]:
    cutoff = None
    existing_keys: set[tuple] = set()
    for row in existing:
        end = _row_end_at(row)
        if cutoff is None or end > cutoff:
            cutoff = end
        planned = naive_datetime(row.planned_at)
        stamp = planned.replace(microsecond=0) if planned is not None else planned
        existing_keys.add((stamp, row.path or row.resource))
    sequence = await _next_sequence(session)
    items: list[RundownItem] = []
    cutoff_naive = naive_datetime(cutoff) if cutoff is not None else None
    for payload in payloads:
        try:
            planned = naive_datetime(datetime.fromisoformat(str(payload["at"])))
        except (KeyError, TypeError, ValueError):
            continue
        if planned is None:
            continue
        if cutoff_naive is not None and planned < cutoff_naive:
            continue
        key = (
            planned.replace(microsecond=0),
            payload.get("path") or payload.get("resource"),
        )
        if key in existing_keys:
            continue
        items.append(item_from_forecast(payload, version, sequence))
        sequence += 1
        existing_keys.add(key)
    if items:
        session.add_all(items)
        await session.flush()
    return items


async def _payload_from_visible(
    session: ormSession,
    rows: list[RundownItem],
    *,
    now: datetime,
    horizon_min: int,
    version: ProgrammingVersion,
) -> dict:
    items = [item_to_payload(row) for row in rows]
    clock = None
    daypart = None
    for item in items:
        if item.get("clock"):
            clock = item.get("clock")
            daypart = item.get("daypart")
            break
    if not clock:
        from radiotomate.scheduler.rundown import _header

        clock, daypart = await _header(session, now)
    return {
        "now": now.isoformat(),
        "horizon_min": horizon_min,
        "clock": clock,
        "daypart": daypart,
        "programming_version": version.id,
        "items": items,
        "summary": rundown_summary(items),
    }


def _coverage_rows(rows: list[RundownItem]) -> list[RundownItem]:
    """Rows that still count as runway ahead of now.

    Failed rows stay visible for the console but never as coverage: a burst of
    unresolvable pushes used to leave a window full of failures and silence.
    Played rows stay in the history, but a planned_at hours ahead of the real
    start must not count as runway either, or a reset keeps appending there.
    """
    ignored = {RundownStatus.FAILED.value, RundownStatus.PLAYED.value}
    return [row for row in rows if row.status not in ignored]


def _is_missing_line(row: RundownItem) -> bool:
    """A line the forecast knew it could not play (« manquant »), never sent."""
    return (
        row.status == RundownStatus.FAILED.value
        and row.sent_at is None
        and row.closed_at is None
        and row.origin != DESK_ORIGIN
    )


async def _beets_titles(beets: BeetsIntegration) -> tuple:
    """How many titles Beets has, and its highest id."""

    def count() -> tuple:
        with beets.lib.transaction() as tx:
            return tuple(tx.query("SELECT COUNT(*), MAX(id) FROM items")[0])

    return await asyncio.get_running_loop().run_in_executor(None, count)


async def _forecast_inputs(
    session: ormSession,
    beets: BeetsIntegration,
    version: ProgrammingVersion,
) -> str:
    """
    One fingerprint of what the forecast is drawn from: the programming, the
    positions of the clocks, the carts, the sounds they can play and the titles
    of Beets. A change there may give a missing line something to play.
    """
    positions = await session.execute(
        select(ClockPosition.__table__).order_by(ClockPosition.id)
    )
    # What a draw reads of a cart: its title and its mode, its sounds below. Not
    # its version: an edit with no effect on the draw, like its notes, bumps it.
    carts = await session.execute(
        select(Cart.id, Cart.title, Cart.mode).order_by(Cart.id)
    )
    # The sum too: a sound ready as another drops keeps the count, often the max.
    playable = await session.execute(
        select(func.count(Sound.id), func.max(Sound.id), func.sum(Sound.id)).where(
            Sound.active.is_(True),
            Sound.gain.is_not(None),
        )
    )
    return programming_fingerprint(
        [
            version.id,
            repr(positions.all()),
            repr(carts.all()),
            repr(playable.one()),
            repr(await _beets_titles(beets)),
        ]
    )


def _read_missing_mark(mark: Setting | None) -> tuple[datetime, int, str] | None:
    """When a forecast of missing lines was drawn, for how many minutes, and
    from what."""
    if mark is None or not mark.value:
        return None
    try:
        raw = json.loads(mark.value)
        at = datetime.fromisoformat(str(raw["at"]))
        horizon = int(raw["horizon"])
        inputs = str(raw["inputs"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if at.tzinfo is None:
        return None
    return at, horizon, inputs


def _missing_forecast_holds(
    mark: Setting | None,
    rows: list[RundownItem],
    *,
    now: datetime,
    inputs: str,
    horizon_min: int,
) -> bool:
    """
    Whether the forecast in place, made only of missing lines, still holds: drawn
    less than ``MISSING_FORECAST_HOLD`` ago, from what is there now, for
    ``horizon_min`` at least, and its lines still there. A reset takes them away,
    and the other process may have drawn shorter: it is drawn again. Where the
    lines end is not asked: hours without a slot, or carts of 8 s that fill the
    800 lines of a draw, end them short of the horizon for good.
    """
    drawn = _read_missing_mark(mark)
    if drawn is None:
        return False
    at, horizon, drawn_from = drawn
    # Either way round: the scheduler dates a draw by the clock of Liquidsoap,
    # the interface by its own, a second or so apart.
    if abs(now - at) >= MISSING_FORECAST_HOLD:
        return False
    if drawn_from != inputs or horizon < horizon_min:
        return False
    return any(_is_missing_line(row) for row in rows)


async def _mark_missing_forecast(  # noqa: PLR0913
    session: ormSession,
    mark: Setting | None,
    items: list[dict],
    *,
    now: datetime,
    horizon_min: int,
    inputs: str,
) -> bool:
    """Mark the forecast just drawn when it is made only of missing lines, so
    that it holds; clear the mark otherwise. Says whether it is."""
    missing = bool(items) and all(
        _status_from_forecast(item) == RundownStatus.FAILED.value for item in items
    )
    value = ""
    if missing:
        value = json.dumps(
            {"at": now.isoformat(), "horizon": horizon_min, "inputs": inputs}
        )
    if value != ((mark.value if mark is not None else "") or ""):
        await Setting.upsert(session, SETTING_MISSING_FORECAST, value)
    return missing


def _note_reading(*, nothing_to_play: bool) -> None:
    _last_reading["at"] = monotonic()
    _last_reading["nothing_to_play"] = nothing_to_play


def nothing_to_play(*, since: float) -> bool:
    """
    Whether this process read the forecast since ``since`` (monotonic), and found
    it made only of missing lines: the clock has nothing to push.
    """
    return _last_reading["at"] >= since and _last_reading["nothing_to_play"]


async def ensure_forecast(  # noqa: PLR0913
    session: ormSession,
    beets: BeetsIntegration,
    now: datetime | None = None,
    horizon_min: int = 30,
    cursor: int | None = None,
    *,
    commit: bool = True,
) -> dict:
    """Persist a stable rundown window: append when short, never re-draw from now."""
    from radiotomate.scheduler.rundown import build_rundown, forecast_still_covers

    now = now_paris(now)
    version = await ensure_programming_version(session)
    visible = await _visible_items(session, now, horizon_min=horizon_min)
    rows = _coverage_rows(visible)
    target_ahead = max(15, int(horizon_min))
    _note_reading(nothing_to_play=False)
    if rows and forecast_still_covers(
        {"items": [item_to_payload(row) for row in rows]},
        now,
        min_ahead_min=target_ahead,
    ):
        return await _payload_from_visible(
            session,
            rows,
            now=now,
            horizon_min=horizon_min,
            version=version,
        )

    if not rows:
        mark = await Setting.from_key(session, SETTING_MISSING_FORECAST)
        # Read before the draw: a title Beets takes while it runs changes the
        # next reading, which draws again.
        inputs = await _forecast_inputs(session, beets, version)
        if _missing_forecast_holds(
            mark,
            visible,
            now=now,
            inputs=inputs,
            horizon_min=horizon_min,
        ):
            _note_reading(nothing_to_play=True)
            return await _payload_from_visible(
                session,
                visible,
                now=now,
                horizon_min=horizon_min,
                version=version,
            )
        forecast = await build_rundown(
            session,
            beets,
            now=now,
            horizon_min=horizon_min,
            cursor=cursor,
        )
        rows = _coverage_rows(
            await _visible_items(session, now, horizon_min=horizon_min)
        )
        if rows and forecast_still_covers(
            {"items": [item_to_payload(row) for row in rows]},
            now,
            min_ahead_min=target_ahead,
        ):
            payload = await _payload_from_visible(
                session,
                rows,
                now=now,
                horizon_min=horizon_min,
                version=version,
            )
            if commit:
                await session.commit()
            return payload
        items = list(forecast.get("items") or [])
        await replace_forecast_items(session, version, items, now=now)
        missing = await _mark_missing_forecast(
            session, mark, items, now=now, horizon_min=horizon_min, inputs=inputs
        )
        _note_reading(nothing_to_play=missing)
    else:
        last_end = _horizon_end(rows, now)
        start_from = last_end if last_end > now else now
        follow = await _cursor_after_items(session, rows)
        remaining_min = int(
            (now + timedelta(minutes=horizon_min) - start_from).total_seconds() // 60
        )
        forecast = await build_rundown(
            session,
            beets,
            now=start_from,
            horizon_min=max(15, remaining_min + 1),
            cursor=follow if follow is not None else cursor,
        )
        await append_forecast_items(
            session,
            version,
            list(forecast.get("items") or []),
            existing=_coverage_rows(
                await _visible_items(session, now, horizon_min=horizon_min)
            ),
        )

    if commit:
        await session.commit()
    rows = await _visible_items(session, now, horizon_min=horizon_min)
    return await _payload_from_visible(
        session,
        rows,
        now=now,
        horizon_min=horizon_min,
        version=version,
    )


async def materialize_rundown(
    session: ormSession,
    beets: BeetsIntegration,
    now: datetime | None = None,
    horizon_min: int = 30,
    cursor: int | None = None,
) -> dict:
    return await ensure_forecast(
        session,
        beets,
        now=now,
        horizon_min=horizon_min,
        cursor=cursor,
    )


async def _visible_items(
    session: ormSession,
    now: datetime,
    *,
    horizon_min: int = 30,
) -> list[RundownItem]:
    lookback = max(15, min(int(horizon_min), 60))
    cutoff = naive_datetime(now) - timedelta(minutes=lookback)
    visible = (
        set(REPLACEABLE_STATUSES)
        | ENGAGED_STATUSES
        | {
            RundownStatus.ON_AIR.value,
            RundownStatus.PLAYED.value,
            RundownStatus.FAILED.value,
        }
    )
    rows = list(
        await session.scalars(
            select(RundownItem)
            .where(
                RundownItem.status.in_(list(visible)),
                RundownItem.planned_at >= cutoff,
            )
            .order_by(RundownItem.planned_at, RundownItem.sequence)
            .limit(800)
        )
    )
    return rows


async def preview_rundown(
    session: ormSession,
    beets: BeetsIntegration,
    now: datetime | None = None,
    horizon_min: int = 30,
) -> dict:
    """Forecast for the console: no DELETE/INSERT of rundown_items."""
    from radiotomate.scheduler.rundown import build_rundown

    now = now_paris(now)
    forecast = await build_rundown(
        session,
        beets,
        now=now,
        horizon_min=horizon_min,
    )
    items = list(forecast.get("items") or [])
    return {
        **forecast,
        "horizon_min": horizon_min,
        "items": items,
        "summary": rundown_summary(items),
    }


async def clear_replaceable_forecast(session: ormSession) -> None:
    """Drop planned/rescue forecast rows and planned desk pins. On-air stays."""
    await session.execute(
        delete(RundownItem).where(
            RundownItem.status.in_(list(REPLACEABLE_STATUSES)),
        )
    )


async def clear_live_forecast(session: ormSession) -> None:
    """Drop every rundown row except on-air and already played."""
    doomed = list(
        await session.scalars(
            select(RundownItem).where(
                RundownItem.status.notin_(list(RESET_KEEP_STATUSES)),
            )
        )
    )
    doomed_ids = [item.id for item in doomed]
    commands = list(
        await session.scalars(
            select(PlayoutCommand).where(
                PlayoutCommand.status.in_(
                    [
                        CommandStatus.PENDING.value,
                        CommandStatus.SENDING.value,
                    ]
                )
            )
        )
    )
    if doomed_ids:
        linked = list(
            await session.scalars(
                select(PlayoutCommand).where(
                    PlayoutCommand.rundown_item_id.in_(doomed_ids),
                )
            )
        )
        seen = {command.id for command in commands}
        for command in linked:
            if command.id not in seen:
                commands.append(command)
    for command in commands:
        command.rundown_item_id = None
        if command.status in {
            CommandStatus.PENDING.value,
            CommandStatus.SENDING.value,
        }:
            command.status = CommandStatus.EXPIRED.value
            command.last_error = "conducteur reset"
    if doomed_ids:
        await session.flush()
        await session.execute(delete(RundownItem).where(RundownItem.id.in_(doomed_ids)))


async def close_past_anchor_lines(session: ormSession, now: datetime) -> int:
    """
    Close the anchor lines still planned an hour after their time: skipped,
    « heure passée ». They never went, the scheduler stopped at their minute say.
    Left planned, they would stay in the conducteur for good, and the draw of
    their cart would count them as to come. Returns how many it closed.
    """
    local = naive_datetime(now)
    rows = list(
        await session.scalars(
            select(RundownItem).where(
                RundownItem.status.in_(
                    [RundownStatus.PLANNED.value, RundownStatus.RESCUE.value]
                ),
                RundownItem.when_mode == WhenMode.ANCHORED.value,
                RundownItem.origin != DESK_ORIGIN,
                RundownItem.planned_at < local - PAST_ANCHOR_AFTER,
            )
        )
    )
    for row in rows:
        row.status = RundownStatus.SKIPPED.value
        row.reason = PAST_REASON
        row.closed_at = local
    if rows:
        await session.commit()
    return len(rows)


def _in_the_motif(row: RundownItem) -> bool:
    """A line of the clock that goes at its turn, not at a minute nor by hand."""
    return row.origin != DESK_ORIGIN and row.when_mode != WhenMode.ANCHORED.value


async def _close_jingles_before(
    session: ormSession, line: RundownItem, now: datetime
) -> int:
    """Close the jingles of the motif still to push before ``line`` in the file:
    skipped, « tour passé ». Returns how many it closed."""
    local = naive_datetime(now)
    rows = list(
        await session.scalars(
            select(RundownItem).where(
                RundownItem.id != line.id,
                RundownItem.status.in_(
                    [RundownStatus.PLANNED.value, RundownStatus.RESCUE.value]
                ),
                RundownItem.origin != DESK_ORIGIN,
                RundownItem.when_mode != WhenMode.ANCHORED.value,
                or_(
                    RundownItem.queue == "jingles",
                    RundownItem.kind == PositionKind.JINGLE.value,
                ),
                or_(
                    RundownItem.planned_at < line.planned_at,
                    and_(
                        RundownItem.planned_at == line.planned_at,
                        RundownItem.sequence < line.sequence,
                    ),
                ),
            )
        )
    )
    for row in rows:
        row.status = RundownStatus.SKIPPED.value
        row.reason = TURN_PASSED_REASON
        row.closed_at = local
    if rows:
        _log.info("Closed %d jingle line(s) of the motif past their turn", len(rows))
    return len(rows)


async def close_passed_jingles(session: ormSession, now: datetime) -> int:
    """
    Close the jingles of the motif whose turn has passed: a line of the motif after
    them in the file has aired. Left planned, they would air late, as soon as the
    Auto-DJ queue empties. The as-run closes them when that line goes on air
    (``reconcile_as_run``); this catches the ones left planned before, by an engine
    that held them back, at the next tick (``features.motif_jingles_air``).
    Returns how many it closed.
    """
    if not await motif_jingles_air(session):
        return 0
    last = await session.scalar(
        select(RundownItem)
        .where(
            RundownItem.status.in_(
                [RundownStatus.ON_AIR.value, RundownStatus.PLAYED.value]
            ),
            RundownItem.origin != DESK_ORIGIN,
            RundownItem.when_mode != WhenMode.ANCHORED.value,
        )
        .order_by(RundownItem.planned_at.desc(), RundownItem.sequence.desc())
        .limit(1)
    )
    if last is None:
        return 0
    closed = await _close_jingles_before(session, last, now)
    if closed:
        await session.commit()
    return closed


async def close_flushed_items(
    session: ormSession,
    flushed: object,
    queues: list[str] | None = None,
) -> int:
    """Close the lines a flush took out of Liquidsoap: skipped, « file vidée ».

    The clock pushes planned lines only: left in queue, they would never air. The
    playout names, queue by queue, the lines of the titles it took out: it keeps
    the title a queue has loaded, on air or next, and its line stays. An older
    playout only counts them: every line in an emptied queue is closed, and the
    loaded title, once on air, gets its line back by its id (``reconcile_as_run``).
    """
    answer = flushed if isinstance(flushed, dict) else {}
    named: set[str] = set()
    counted: list[str] = []
    for queue in queues or PLAYOUT_QUEUES:
        info = answer.get(queue)
        ids = info.get("item_ids") if isinstance(info, dict) else None
        if isinstance(ids, list):
            named.update(str(item_id) for item_id in ids if item_id)
        else:
            counted.append(queue)
    taken = []
    if named:
        engaged = ENGAGED_STATUSES - {RundownStatus.ON_AIR.value}
        taken.append(
            and_(RundownItem.id.in_(named), RundownItem.status.in_(list(engaged)))
        )
    if counted:
        taken.append(
            and_(
                RundownItem.queue.in_(counted),
                RundownItem.status.in_(list(_QUEUED_STATUSES)),
            )
        )
    if not taken:
        return 0
    rows = list(await session.scalars(select(RundownItem).where(or_(*taken))))
    now = datetime.now()
    for row in rows:
        row.status = RundownStatus.SKIPPED.value
        row.reason = FLUSHED_REASON
        row.closed_at = now
    if rows:
        _log.info("Flush closed %d rundown line(s)", len(rows))
    return len(rows)


async def close_lost_lines(session: ormSession, live_data: dict) -> int:
    """
    Close the lines sent to a queue the playout says is empty: skipped, « plus
    dans le playout ». A playout that starts again has empty queues, as at every
    update of the station, which recreates it: the lines the one before held
    stayed « en file » for good. They never aired, and stood first in the file,
    with the time they had (``features.close_lines_lost_by_playout``).

    Not while a jingle or a sound of a cart is on air: behind it, the queue of
    the Auto-DJ has already taken its next title out, to play it after. Nor a
    line the playout took a moment ago, which its beat may not count yet, nor
    the line it says is on air, which the as-run is about to open, nor the line
    of « Jouer tout de suite », whose title went before it and does not name it.
    Returns how many it closed.
    """
    if source_id(live_data) != "autodj":
        return 0
    empty = [
        queue
        for queue, (count, cue) in _QUEUE_BEAT.items()
        if queued_count(live_data, count, cue) == 0 and queue_empty(live_data, cue)
    ]
    if not empty or not await lost_lines_close(session):
        return 0
    now = datetime.now()
    rows = list(
        await session.scalars(
            select(RundownItem).where(
                RundownItem.queue.in_(empty),
                RundownItem.status.in_(list(_QUEUED_STATUSES)),
                RundownItem.id != str(live_data.get("radiotomate_item_id") or ""),
                func.coalesce(
                    RundownItem.queued_at, RundownItem.sent_at, RundownItem.reserved_at
                )
                < now - LOST_AFTER,
            )
        )
    )
    rows = [row for row in rows if not (row.details or {}).get(PLAYED_NOW)]
    for row in rows:
        row.status = RundownStatus.SKIPPED.value
        row.reason = LOST_REASON
        row.closed_at = now
    if rows:
        _log.warning(
            "Closed %d line(s) the playout no longer holds: its queues are empty",
            len(rows),
        )
        await session.commit()
    return len(rows)


async def _reanchor_on_air(session: ormSession) -> None:
    """Snap a stuck on-air plan back to the real start.

    As-run realign refuses a shift past ten minutes, so a planned_at hours
    ahead stays on air. ``forecast_still_covers`` then treats that future as
    enough runway and a reset rebuilds nothing.
    """
    now = naive_datetime(now_paris()) or datetime.now()
    rows = list(
        await session.scalars(
            select(RundownItem).where(
                RundownItem.status == RundownStatus.ON_AIR.value,
            )
        )
    )
    for row in rows:
        if row.origin == DESK_ORIGIN or row.when_mode == WhenMode.ANCHORED.value:
            continue
        started = naive_datetime(row.started_at) or now
        planned = naive_datetime(row.planned_at)
        if planned is None or abs((planned - started).total_seconds()) > 10 * 60:
            row.planned_at = started


async def reset_conducteur(
    session: ormSession,
    beets: BeetsIntegration,
    horizon_min: int = 30,
    now: datetime | None = None,
) -> dict:
    """Reset motif cursor, drop queued forecast, persist a fresh window from now."""
    await reset_sequencer(session, commit=False)
    await clear_live_forecast(session)
    await _reanchor_on_air(session)
    await session.commit()
    payload = await ensure_forecast(session, beets, now=now, horizon_min=horizon_min)
    payload = dict(payload)
    payload["action"] = "reset"
    return payload


def forget_upgrade_check(*, checked: bool = False) -> None:
    """Whether this process has compared its forecast revision with the one of
    the base. Tests: a tick does it once, at the first one."""
    _upgrade["checked"] = checked


async def rebuild_after_upgrade(
    session: ormSession,
    beets: BeetsIntegration,
    gateway: PlayoutGateway,
    now: datetime | None = None,
) -> bool:
    """
    At the first tick of an engine that plans the conducteur another way than
    the one before (``FORECAST_REVISION``), rebuild it, as « Reconstruire le
    conducteur » does: the lines still to air are thrown away and drawn again
    from now, and the queues of the playout emptied. Left as they were, they
    kept the times of the engine before, an hour off on a station whose
    conducteur had drifted, and nothing brought them back: a line that starts
    sooner than planned does not move the ones planned after the next hard
    anchor (``features.rebuild_conducteur_after_upgrade``).

    A base with no line has nothing to rebuild: a new station. Returns whether
    it rebuilt.
    """
    if _upgrade["checked"]:
        return False
    stored = await Setting.from_key(session, SETTING_FORECAST_REVISION)
    if stored is not None and str(stored.value) == FORECAST_REVISION:
        _upgrade["checked"] = True
        return False
    await Setting.upsert(session, SETTING_FORECAST_REVISION, FORECAST_REVISION)
    lines = await session.scalar(select(func.count()).select_from(RundownItem))
    if not lines or not await rebuilds_after_upgrade(session):
        await session.commit()
        _upgrade["checked"] = True
        return False
    # The playout of an update starts with empty queues. One that kept running
    # still holds titles: their lines go, so they go too.
    flushed = await gateway.flush_queues()
    if not flushed.ok:
        _log.warning("flush queues before the rebuild failed: %s", flushed.error)
    await reset_conducteur(session, beets, now=now)
    _upgrade["checked"] = True
    _log.warning(
        "Conducteur rebuilt: this engine plans it another way (revision %s, was %s)",
        FORECAST_REVISION,
        stored.value if stored is not None else "none",
    )
    return True


async def published_rundown(
    session: ormSession,
    beets: BeetsIntegration,
    now: datetime | None = None,
    horizon_min: int = 30,
) -> dict:
    return await materialize_rundown(
        session,
        beets,
        now=now,
        horizon_min=horizon_min,
    )


async def record_live_item(
    session: ormSession,
    *,
    payload: dict,
    status: str = RundownStatus.RESERVED.value,
) -> RundownItem:
    version = await ensure_programming_version(session)
    item = item_from_forecast(payload, version, payload.get("sequence") or 0)
    item.status = status
    item.reserved_at = datetime.now()
    session.add(item)
    await session.flush()
    return item


async def _item_of_as_run(
    session: ormSession,
    log: MetadataLog,
) -> tuple[RundownItem | None, bool]:
    """The rundown item an as-run row is about, and whether the playout named
    it: else it is a guess, from its sound or its title."""
    item = None
    if log.rundown_item_id:
        item = await RundownItem.from_id(session, log.rundown_item_id)
    if item is None and log.extra:
        extra_id = log.extra.get("radiotomate_item_id")
        if extra_id:
            item = await RundownItem.from_id(session, str(extra_id))
    if item is not None:
        return item, True
    extra_sound = (log.extra or {}).get("radiotomate_sound_id")
    if extra_sound:
        try:
            item = await _latest_item_for_sound(session, int(extra_sound))
        except (TypeError, ValueError):
            item = None
    if item is None:
        item = await _latest_open_item(session, log)
    return item, False


async def reconcile_as_run(session: ormSession, log: MetadataLog) -> None:
    """Link an as-run row to its rundown item without merging the two tables."""
    item, exact = await _item_of_as_run(session, log)
    if item is None:
        return
    log.rundown_item_id = item.id
    if exact and await _cut_by_a_hard_anchor(session, item, log):
        # The queue of the Auto-DJ says once more the title a hard anchor cut,
        # as it takes the antenna back, then skips it
        # (clock._skip_cut_autodj_if_ready): the title does not air again. Its
        # line stays played, and the lines after it, planned after the sound of
        # the anchor, stay where they are.
        return
    previous = list(
        await session.scalars(
            select(RundownItem).where(
                RundownItem.status == RundownStatus.ON_AIR.value,
                RundownItem.id != item.id,
            )
        )
    )
    now = naive_datetime(log.on_air) or datetime.now()
    for row in previous:
        row.status = RundownStatus.PLAYED.value
        row.closed_at = now
    item.status = RundownStatus.ON_AIR.value
    item.started_at = item.started_at or now
    if log.playout_command_id:
        item.details = {
            **dict(item.details or {}),
            "playout_command_id": log.playout_command_id,
        }
    # Before the realign: it moves this line to its real start, which may come
    # before the jingle it airs in place of, but leaves that jingle where it was.
    if _in_the_motif(item) and await motif_jingles_air(session):
        await _close_jingles_before(session, item, now)
    if item.when_mode == WhenMode.ANCHORED.value and item.origin == "clock":
        await _after_the_sound(session, item, now)
    await realign_rundown(session, item, now, exact=exact)


async def _cut_by_a_hard_anchor(
    session: ormSession,
    item: RundownItem,
    log: MetadataLog,
) -> bool:
    """Whether a hard anchor has cut the title of this line: the clock wrote it
    in the as-run when it fired the anchor (clock._remember_cut_autodj)."""
    rows = await session.scalars(
        select(MetadataLog).where(MetadataLog.rundown_item_id == item.id)
    )
    return any(
        row is not log and (row.extra or {}).get("skip_reason") == "hard_sync"
        for row in rows
    )


REALIGN_TOLERANCE = timedelta(seconds=5)
# Beyond this an as-run row linked by its sound or its title was linked to the
# wrong planned item (repeated title / sound); shifting the whole rundown by an
# hour would do more harm. A row the playout linked itself, by the id of its
# line, is believed: the antenna did start that late, or that early.
REALIGN_MAX = timedelta(minutes=10)


async def realign_rundown(
    session: ormSession,
    item: RundownItem,
    started: datetime,
    *,
    exact: bool = False,
) -> timedelta:
    """
    Anchor the rundown on the as-run: the item that just went on air takes the
    real start time, and the items after it follow, up to the next hard anchor
    the conducteur plans. That one goes on its minute, whatever airs before it,
    and the items planned after its sound keep their time.

    The sequential items after it slide by the same delta. Started late, a soft
    anchor slides with them: it waits for the end of the title before it. A
    hard anchor keeps its minute. Desk lines slide like clock lines while they
    air (``features.desk_lines_air``), and keep their own time otherwise.
    Returns the delta (zero when within tolerance).

    ``exact``: the playout named the line of this as-run. Its start is believed
    whatever the delta, as after a long live: started more than ``REALIGN_MAX``
    late, the items after it start one after the other from its end, and one
    planned later than that keeps its time. Linked by its sound or its title, a
    delta beyond ``REALIGN_MAX`` is a wrong link, and moves nothing.
    """
    if item.planned_at is None or item.when_mode == WhenMode.ANCHORED.value:
        return timedelta(0)
    desk_airs = await desk_lines_air(session)
    # « Jouer tout de suite » plays its title at once, cutting the title on air,
    # which resumes after it: the lines after it do not move.
    if item.origin == DESK_ORIGIN and (
        not desk_airs or (item.details or {}).get(PLAYED_NOW)
    ):
        return timedelta(0)
    planned = naive_datetime(item.planned_at)
    started = naive_datetime(started)
    if planned is None or started is None:
        return timedelta(0)
    delta = started - planned
    if abs(delta) < REALIGN_TOLERANCE:
        return timedelta(0)
    far = abs(delta) > REALIGN_MAX
    if far and not exact:
        _log.warning(
            "rundown realign skipped: %+.0fs on %s looks like a mislinked as-run",
            delta.total_seconds(),
            item.id,
        )
        return timedelta(0)
    late = delta > timedelta(0)
    waiting = REPLACEABLE_STATUSES | (ENGAGED_STATUSES - {RundownStatus.ON_AIR.value})
    query = select(RundownItem).where(
        RundownItem.id != item.id,
        RundownItem.status.in_(list(waiting)),
        RundownItem.planned_at >= item.planned_at,
    )
    wall = await next_cut_at(session, started)
    if wall is not None:
        query = query.where(RundownItem.planned_at < wall)
    rows = await session.scalars(
        query.order_by(
            RundownItem.planned_at,
            case((RundownItem.origin == DESK_ORIGIN, 0), else_=1),
            RundownItem.sequence,
        )
    )
    following = [row for row in rows if _follows(row, desk_airs=desk_airs, late=late)]
    item.planned_at = started
    if late and far:
        _start_one_after_the_other(_ends(item, started), following)
    else:
        for row in following:
            row.planned_at = naive_datetime(row.planned_at) + delta
    _log.info(
        "rundown realigned by %+.0fs on %s (%d following item(s))",
        delta.total_seconds(),
        item.id,
        len(following),
    )
    return delta


def _follows(row: RundownItem, *, desk_airs: bool, late: bool) -> bool:
    """Whether an item planned after the one that went on air follows it."""
    if row.planned_at is None:
        return False
    if row.when_mode == WhenMode.ANCHORED.value:
        # A soft anchor of the clock goes at the end of the title before it:
        # later with it, never sooner than planned. A hard one, a set or a live
        # of the Agenda keep their time.
        return late and row.origin == "clock" and not _is_hard_line(row)
    return desk_airs or row.origin != DESK_ORIGIN


def _is_hard_line(row: RundownItem) -> bool:
    """An anchor line that cuts on its minute, as ``ClockPosition.sync_enum``
    reads its position."""
    if row.sync:
        return row.sync == SyncMode.DURE.value
    return row.kind == PositionKind.PUB.value


async def next_cut_at(session: ormSession, after: datetime) -> datetime | None:
    """
    When the next hard anchor the conducteur plans goes, after ``after``: it
    will cut what plays then. A hard anchor with nothing to play has no line
    planned, and cuts nothing.
    """
    rows = await session.scalars(
        select(RundownItem)
        .where(
            RundownItem.status.in_(
                [RundownStatus.PLANNED.value, RundownStatus.RESCUE.value]
            ),
            RundownItem.when_mode == WhenMode.ANCHORED.value,
            RundownItem.origin == "clock",
            RundownItem.planned_at > after,
        )
        .order_by(RundownItem.planned_at, RundownItem.sequence)
    )
    for row in rows:
        if _is_hard_line(row):
            return row.planned_at
    return None


def _ends(item: RundownItem, started: datetime) -> datetime:
    return started + timedelta(seconds=max(0.0, float(item.duration or 0)))


def _start_one_after_the_other(
    end: datetime,
    following: list[RundownItem],
    *,
    sooner: bool = False,
) -> None:
    """
    The item on air ends at ``end``. Of the items after it, in their order, one
    planned before the end of the one before it starts there, and one planned
    later keeps its time: after an hour of live, the items planned during it
    follow each other from now, and those planned after it stay. A closed item
    takes no time on air.

    ``sooner``: an item of the file planned later starts there too. Behind the
    sound of an anchor the queue plays on, and no title waits for the time it
    had: the ones planned before it have aired ahead of the anchor, on an
    antenna ahead of the conducteur. An anchor keeps to its minute.
    """
    for row in following:
        planned = naive_datetime(row.planned_at)
        pulled = sooner and row.when_mode != WhenMode.ANCHORED.value
        row.planned_at = end if pulled else max(planned, end)
        if row.status not in _CLOSED_DESK_STATUSES:
            end = _ends(row, row.planned_at)


async def _after_the_sound(
    session: ormSession,
    sound: RundownItem,
    started: datetime,
) -> None:
    """
    The sound of an anchor of the clock is on air: it keeps its own time, and
    the items still to air start one after the other from its end, up to the
    next hard anchor. Those the antenna had no time for before it, planned in
    the minutes before, then those planned after it: sooner than planned when
    the first of them have gone ahead of the anchor.
    """
    desk_airs = await desk_lines_air(session)
    waiting = {
        RundownStatus.PLANNED.value,
        RundownStatus.RESCUE.value,
    } | (ENGAGED_STATUSES - {RundownStatus.ON_AIR.value})
    query = select(RundownItem).where(
        RundownItem.id != sound.id,
        RundownItem.status.in_(list(waiting)),
        RundownItem.planned_at >= started - REALIGN_MAX,
    )
    wall = await next_cut_at(session, started)
    if wall is not None:
        query = query.where(RundownItem.planned_at < wall)
    rows = await session.scalars(
        query.order_by(
            RundownItem.planned_at,
            case((RundownItem.origin == DESK_ORIGIN, 0), else_=1),
            RundownItem.sequence,
        )
    )
    following = [row for row in rows if _follows(row, desk_airs=desk_airs, late=True)]
    _start_one_after_the_other(_ends(sound, started), following, sooner=True)


async def _latest_item_for_sound(
    session: ormSession,
    sound_id: int,
) -> RundownItem | None:
    """
    Fallback link when Liquidsoap did not echo ``radiotomate_item_id``: the
    earliest item of that sound already handed to the playout. A small
    rotation repeats sounds, so "most recently created" picked a row planned
    an hour ahead and dragged the whole rundown with it.
    """
    engaged = ENGAGED_STATUSES - {RundownStatus.ON_AIR.value}
    item = await session.scalar(
        select(RundownItem)
        .where(
            RundownItem.sound_id == sound_id,
            RundownItem.status.in_(list(engaged)),
        )
        .order_by(RundownItem.planned_at, RundownItem.sequence)
        .limit(1)
    )
    if item is not None:
        return item
    return await session.scalar(
        select(RundownItem)
        .where(RundownItem.sound_id == sound_id)
        .order_by(RundownItem.created.desc())
        .limit(1)
    )


async def _latest_open_item(
    session: ormSession,
    log: MetadataLog,
) -> RundownItem | None:
    q = select(RundownItem).where(
        RundownItem.status.in_(
            [
                RundownStatus.IN_QUEUE.value,
                RundownStatus.ACCEPTED.value,
                RundownStatus.SENT.value,
            ]
        )
    )
    if log.title:
        q = q.where(RundownItem.resource.contains(log.title))
    return await session.scalar(q.order_by(RundownItem.created.desc()).limit(1))


async def _next_sequence(session: ormSession) -> int:
    current = await session.scalar(
        select(RundownItem.sequence).order_by(RundownItem.sequence.desc()).limit(1)
    )
    return int(current or 0) + 1


# Desk edits live in their own module; re-exported for existing callers.
from radiotomate.scheduler.desk import (  # noqa: E402, F401
    PLAYED_NOW,
    attach_desk_pins,
    close_replaced,
    delete_desk_item,
    desk_lines_air,
    desk_queue_for,
    expire_past_desk_items,
    insert_desk_item,
    item_is_locked,
    list_active_desk_items,
    merge_desk_into_items,
    patch_desk_item,
    read_desk_pin,
    removed_clock_ids,
    reorder_desk_items,
)
