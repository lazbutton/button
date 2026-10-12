"""Dated broadcasts on air (Agenda).

Called first in ``clock.tick``. A set starts at its minute: the queues are
emptied, its file is pushed to the carts queue (which takes the antenna at
once) and whatever was playing is cut, like a hard anchor. While the file
plays or waits in the carts queue, the clock is *held*: anchors are dropped,
not stacked behind the set, and nothing is pushed — except, in the last
seconds, the Auto-DJ refill that makes the return seamless.

A diffusion only holds the antenna while its sound is there. A missing set,
an absent DJ: the grid plays, by construction. One diffusion never cuts
another: the next one waits for the end of the previous.

Everything is read back from the database on each tick, so a restart of the
scheduler neither pushes a file twice nor forgets to give the antenna back.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete

from radiotomate.domain.agenda import (
    AIR_AIRED,
    AIR_MISSED,
    AIR_ON_AIR,
    AIR_UPCOMING,
    KIND_LIVE,
    KIND_SET,
    paris,
    playable,
    utc,
    utc_naive,
)
from radiotomate.domain.execution import REPLACEABLE_STATUSES
from radiotomate.enums import PlayoutAction, RundownStatus
from radiotomate.models import AgendaDiffusion, RundownItem
from radiotomate.scheduler.outbox import dispatch_command, enqueue_command
from radiotomate.scheduler.timing import remaining_seconds, source_id
from radiotomate.services.agenda import (
    agenda_enabled,
    diffusion_state,
    file_facts,
)
from radiotomate.services.media_bank import media_root

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.scheduler.playout import PlayoutGateway

_log = logging.getLogger(__name__)

AGENDA_ORIGIN = "agenda"
# The playout reports a pushed file a second or two later (heartbeat, start
# blank): until then the diffusion still holds.
PUSH_GRACE = timedelta(seconds=45)
# Below this, the clock may refill Auto-DJ so the set hands over without a gap.
ENDING_FILL_REMAINING = 30.0


@dataclass
class AgendaTick:
    hold: bool = False
    fill: bool = False
    actions: list[str] = field(default_factory=list)
    # Sets to cut once the clock has refilled Auto-DJ (``finish_stops``).
    stops: list[AgendaDiffusion] = field(default_factory=list)


async def _active(session: ormSession, now: datetime) -> list[AgendaDiffusion]:
    """On air, or upcoming and due: started, or past their end (missed)."""
    rows = await AgendaDiffusion.in_status(session, AIR_ON_AIR, AIR_UPCOMING)
    return [
        row for row in rows if row.air_status == AIR_ON_AIR or utc(row.starts_at) <= now
    ]


def _cue(live_data: dict, key: str) -> dict:
    raw = live_data.get(key)
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _playing(live_data: dict, row: AgendaDiffusion) -> bool:
    item_id = str(live_data.get("radiotomate_item_id") or "")
    return bool(row.air_item_id) and item_id == row.air_item_id


def _queued(live_data: dict, row: AgendaDiffusion) -> bool:
    if not row.air_item_id:
        return False
    uri = str(_cue(live_data, "next_cart").get("initial_uri") or "")
    return row.air_item_id in uri


async def _item(session: ormSession, row: AgendaDiffusion) -> RundownItem | None:
    if not row.air_item_id:
        return None
    return await RundownItem.from_id(session, row.air_item_id)


async def _drop_planned_blocks(session: ormSession) -> None:
    """The forecast is rebuilt around what really happened. Desk pins stay."""
    from radiotomate.scheduler.execution import DESK_ORIGIN

    await session.execute(
        delete(RundownItem).where(
            RundownItem.status.in_(list(REPLACEABLE_STATUSES)),
            RundownItem.origin != DESK_ORIGIN,
        )
    )


async def _push_set(
    session: ormSession,
    gateway: PlayoutGateway,
    live_data: dict,
    row: AgendaDiffusion,
    now: datetime,
) -> str | None:
    """Cut what plays and put the set on air. Returns an error, or None."""
    from radiotomate.scheduler import clock as clock_mod
    from radiotomate.scheduler.execution import record_live_item

    current = row.current_file
    if current is None:
        return "Set absent"
    path = media_root() / current.path
    if not path.is_file():
        return "Fichier introuvable"
    flushed = await gateway.flush_queues(["carts", "jingles", "autodj"])
    if not flushed.ok:
        _log.warning("agenda: flush before %s failed: %s", row.id, flushed.error)
    artist = row.guest.name if row.guest is not None else row.title
    title = row.set_title or row.title
    item = await record_live_item(
        session,
        payload={
            "at": paris(now).isoformat(),
            "kind": "son",
            "when": "anchored",
            "queue": "carts",
            "resource": f"{artist} — {title}" if artist != title else title,
            "path": str(path),
            "duration": float(current.duration or 0),
            "artist": artist,
            "title": title,
            "origin": AGENDA_ORIGIN,
            "diffusion_id": row.id,
            "status": RundownStatus.RESERVED.value,
        },
        status=RundownStatus.RESERVED.value,
    )
    payload: dict = {
        "path": str(path),
        "artist": artist,
        "title": title,
        "radiotomate_item_id": item.id,
    }
    if current.gain is not None:
        payload["rg_track_gain"] = str(current.gain)
    command = await enqueue_command(
        session,
        action=PlayoutAction.QUEUE.value,
        queue="carts",
        payload=payload,
        item=item,
        idempotency_key=f"agenda:{row.id}:{current.id}",
    )
    payload["radiotomate_command_id"] = command.id
    command.payload = payload
    result = await dispatch_command(session, command, gateway)
    if not result.ok:
        return "Le playout a refusé le fichier"
    row.air_item_id = item.id
    source = source_id(live_data)
    if source == "carts":
        await gateway.skip({"queue": "carts"})
    elif source == "relay":
        await gateway.skip({"relay": 1})
    elif source != "stream":
        await clock_mod._remember_cut_autodj(session, live_data, paris(now))
        clock_mod._state.pending_autodj_skip = True
        clock_mod._state.pending_autodj_skip_minute = paris(now).minute
    clock_mod._state.active_cart_id = None
    return None


async def _stop_set(
    gateway: PlayoutGateway, live_data: dict, row: AgendaDiffusion
) -> None:
    """Skip the set if it plays; drop it if it only waits in the carts queue."""
    if _playing(live_data, row):
        await gateway.skip({"queue": "carts"})
    elif _queued(live_data, row):
        await gateway.flush_queues(["carts"])


def _miss(row: AgendaDiffusion, reason: str, actions: list[str]) -> None:
    row.air_status = AIR_MISSED
    row.air_reason = reason
    actions.append(f"agenda_missed:{row.id}")
    _log.warning("agenda: %s « %s » missed: %s", row.id, row.title, reason)


async def _end_set(
    session: ormSession,
    row: AgendaDiffusion,
    now: datetime,
    actions: list[str],
    reason: str = "",
) -> None:
    item = await _item(session, row)
    if (item is not None and item.started_at is not None) or reason:
        row.air_status = AIR_AIRED
        row.air_reason = reason
    else:
        row.air_status = AIR_MISSED
        row.air_reason = "Le fichier n'est pas passé"
    row.aired_end = utc_naive(now)
    await _drop_planned_blocks(session)
    actions.append(f"agenda_end:{row.id}")


async def step(  # noqa: PLR0912, PLR0915
    session: ormSession,
    live_data: dict,
    gateway: PlayoutGateway,
    now: datetime,
    *,
    harbor: bool,
) -> AgendaTick:
    result = AgendaTick()
    if not await agenda_enabled(session):
        return result
    now = utc(now)
    rows = await _active(session, now)
    if not rows:
        return result
    actions = result.actions
    holder: AgendaDiffusion | None = None

    for row in [r for r in rows if r.air_status == AIR_ON_AIR]:
        if row.kind == KIND_LIVE:
            if harbor:
                row.aired_end = None
                continue
            if row.aired_end is None:
                row.aired_end = utc_naive(now)
            if now >= utc(row.ends_at):
                row.air_status = AIR_AIRED
                actions.append(f"agenda_end:{row.id}")
            continue
        if row.stop_requested_at is not None:
            result.stops.append(row)
            result.fill = True
            continue
        pushed_at = utc(row.aired_start) if row.aired_start else now
        if (
            _playing(live_data, row)
            or _queued(live_data, row)
            or now - pushed_at < PUSH_GRACE
            or harbor
        ):
            holder = row
            result.hold = True
            if (
                _playing(live_data, row)
                and remaining_seconds(live_data) <= ENDING_FILL_REMAINING
            ):
                result.fill = True
            continue
        await _end_set(session, row, now, actions)

    for row in [r for r in rows if r.air_status == AIR_UPCOMING]:
        if now >= utc(row.ends_at):
            if row.kind == KIND_LIVE:
                _miss(row, "Personne ne s'est branché", actions)
            elif holder is not None:
                _miss(row, "L'émission précédente a débordé", actions)
            else:
                _miss(row, diffusion_state(row)[1] or "Pas passée à l'antenne", actions)
            continue
        if row.kind == KIND_LIVE:
            if harbor:
                row.air_status = AIR_ON_AIR
                row.aired_start = utc_naive(now)
                actions.append(f"agenda_live:{row.id}")
            continue
        if row.kind != KIND_SET:
            continue
        if holder is not None or harbor:
            actions.append(f"agenda_wait:{row.id}")
            continue
        if not playable(
            row.kind,
            file=file_facts(row.current_file),
            rights=row.rights_at is not None,
        ):
            _miss(row, diffusion_state(row)[1] or "Set absent", actions)
            continue
        error = await _push_set(session, gateway, live_data, row, now)
        if error:
            _miss(row, error, actions)
            continue
        row.air_status = AIR_ON_AIR
        row.aired_start = utc_naive(now)
        holder = row
        result.hold = True
        await _drop_planned_blocks(session)
        actions.append(f"agenda_start:{row.id}")

    await session.commit()
    return result


async def finish_stops(
    session: ormSession,
    gateway: PlayoutGateway,
    live_data: dict,
    result: AgendaTick,
    now: datetime,
) -> None:
    """Cut the sets asked to stop, after the clock refilled Auto-DJ: no gap."""
    if not result.stops:
        return
    now = utc(now)
    for row in result.stops:
        await _stop_set(gateway, live_data, row)
        await _end_set(
            session,
            row,
            now,
            result.actions,
            reason=f"Arrêtée à {paris(now):%H:%M}",
        )
    await session.commit()
