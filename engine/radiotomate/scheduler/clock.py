"""
Clock sequencer: motif + hard anchors → existing Liquidsoap queues.

Jingles cut Auto-DJ, never live / relay / a cart on air. Sequential jingles are
only pushed when the track before them is nearly over, or behind a jingle or cart
on air, ahead of the music queued after them. Hard anchors still cut — except
while the harbor is on air: the clock pauses, skips nothing, and drops due
anchors so they are not dumped after the live.

Hard-sync must not skip the output bed: that consumes the next Auto-DJ request
before the cart is ready. After the pub/jingle is on air, skip autodj_queue only.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import TYPE_CHECKING

from sqlalchemy import case, select

from radiotomate.domain.emission import is_harbor_source
from radiotomate.enums import (
    CartMode,
    PlayoutAction,
    PositionKind,
    RundownStatus,
    WhenMode,
)
from radiotomate.models import (
    AutoDJSlot,
    Cart,
    Clock,
    ClockPosition,
    MetadataLog,
    RundownItem,
    Setting,
    Sound,
)
from radiotomate.models.cart import CARTS_QUEUE
from radiotomate.scheduler.metrics import runtime_metrics
from radiotomate.scheduler.music_rules import (  # noqa: F401 — re-exported
    ARTIST_LAST_N,
    ARTIST_WINDOW,
    TITLE_LAST_N,
    _choose_item,
    _music_history,
    _pick_music,
    _rule_sets,
)
from radiotomate.scheduler.outbox import dispatch_command, enqueue_command
from radiotomate.scheduler.playout import PlayoutGateway, gateway_for
from radiotomate.scheduler.timing import (  # noqa: F401 — re-exported
    JINGLE_PREEMPT_REMAINING,
    PARIS,
    _next_anchor,
    anchor_in_daypart,
    can_push_sequential_jingle,
    hard_anchor_since,
    next_hard_anchor,
    next_hard_anchor_minute,
    next_soft_anchor,
    now_from_live,
    now_paris,
    queue_empty,
    queued_count,
    remaining_seconds,
    sequential_kind_cycle,
    source_id,
    track_would_overflow_anchor,
)
from radiotomate.services.cart_draw import next_cart_sound, planned_in_order

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration

_log = logging.getLogger(__name__)


def _finish_tick(started: float, actions: list[str]) -> list[str]:
    runtime_metrics.tick_duration_seconds = perf_counter() - started
    return actions


SETTING_CLOCK_SEQ_CURSOR = "clock_seq_cursor"
SETTING_CLOCK_SEQ_CLOCK_ID = "clock_seq_clock_id"
SETTING_CLOCK_SEQ_EPOCH = "clock_seq_epoch"
# ADR 0009: turned off, a soft anchor a hard one has overtaken goes after it, as
# before, though the conducteur says it « sauté ».
SETTING_SKIP_OVERTAKEN = "features.skip_overtaken_soft_anchors"
# ADR 0009: turned off, a jingle of the motif waits for an empty Auto-DJ queue, as
# before. The clock keeps two titles there: after the start, the jingle stays
# planned, and the music after it airs in its place.
SETTING_MOTIF_JINGLES_AIR = "features.motif_jingles_air"
# ADR 0009: turned off, the lines planned of a cart in order keep their sound
# when the clock draws an anchor of that cart itself, as before: the next one
# may replay the sound drawn.
SETTING_ORDERED_FOLLOW = "features.ordered_lines_follow_clock"
_SETTING_OFF = {"0", "false", "off", ""}
# Why an anchor line closes without going, as the conducteur shows it.
HELD_BY_LIVE = "retenue pendant le direct"
HELD_BY_SET = "retenue pendant un set de l'Agenda"
OVERTAKEN = "dépassé par une ancre dure"
# A position whose cart is a relay, and no fallback with a sound: it plays nothing.
RELAY_CART = "bac en relais"
TARGET_QUEUE_DEPTH = 2
# Une seule avance dans la file jingles : fallback Liquidsoap les joue
# tant qu'il en reste, donc un stock de 2 bouche l'Auto-DJ.
JINGLE_QUEUE_DEPTH = 1
AUTODJ_BURST_REMAINING = 8.0
AUTODJ_BURST_DEPTH = 3
_PUSHABLE_STATUSES = {
    RundownStatus.PLANNED.value,
    RundownStatus.RESCUE.value,
}
_ROUND_MODES = {CartMode.PLAYLIST, CartMode.PLAYLIST_LOOP}
# execution.DESK_ORIGIN: execution imports this module.
_DESK_ORIGIN = "desk"
# Liquidsoap plays the carts before the jingles, and the jingles before the
# Auto-DJ, as soon as they hold a title: those two queues cut what plays.
_QUEUE_RANK = {"autodj": 0, "jingles": 1, "carts": 2}
_QUEUE_HEADS = {
    "autodj": ("next_autodj", "autodj_queued"),
    "jingles": ("next_jingle", "jingles_queued"),
}
_ITEM_ID = re.compile(r'radiotomate_item_id="([^"]*)"')


@dataclass
class CartRound:
    """
    A playlist of the carts queue launched by « Diffuser maintenant »: the clock
    queues its sounds one after the other, each once at most, then gives the
    antenna back. A loop plays all of them, from its next sound. A one-shot
    playlist plays its sounds never played, or all of them, as a loop, when none
    is left. A clock anchor, a desk line or a single sound fired by hand plays
    one sound and leaves the round as it is.
    """

    cart_id: int
    # A one-shot playlist launched with sounds never played takes only those.
    fresh_only: bool = False
    queued: set[int] = field(default_factory=set)
    # The playout has shown the round: carts on air, or queued.
    seen: bool = False

    @staticmethod
    def applies_to(cart: Cart) -> bool:
        return cart.mode in _ROUND_MODES and cart.playout_queue() == CARTS_QUEUE

    @classmethod
    def start(cls, cart: Cart) -> CartRound | None:
        """The round a launch starts, or None for a cart that plays one sound."""
        if not cls.applies_to(cart):
            return None
        first = cart.next_sound()
        fresh = (
            cart.mode is CartMode.PLAYLIST
            and first is not None
            and not first.last_played
        )
        return cls(cart.id, fresh_only=fresh)

    def next_sound(self, cart: Cart) -> Sound | None:
        """The round's next sound, or None once the round is over."""
        sound = cart.next_sound()
        if sound is None or sound.id in self.queued:
            return None
        if self.fresh_only and sound.last_played:
            return None
        return sound


@dataclass
class SequencerState:
    cursor: int = 0
    clock_id: int | None = None
    fired_anchors: set[tuple[str, int, int]] = field(default_factory=set)
    restored: bool = False
    persisted_snapshot: tuple[int, int | None, frozenset] | None = None
    cart_round: CartRound | None = None
    epoch: int = 0
    pending_autodj_skip: bool = False
    pending_autodj_skip_minute: int | None = None


_state = SequencerState()


def reset_state() -> None:
    """Reset in-memory cursor (tests and producer reset)."""
    _state.cursor = 0
    _state.clock_id = None
    _state.fired_anchors.clear()
    _state.restored = False
    _state.persisted_snapshot = None
    _state.cart_round = None
    _state.epoch = 0
    _state.pending_autodj_skip = False
    _state.pending_autodj_skip_minute = None


def note_cart_round(cart_round: CartRound) -> None:
    """The clock carries on the round « Diffuser maintenant » has started."""
    _state.cart_round = cart_round


def end_cart_round(cart_round: CartRound | None = None) -> None:
    """
    No more sounds from the launched cart: « Vider les files », the Agenda, or
    its round is over. Given a round, ends it only if it is still the one on.
    """
    if cart_round is None or _state.cart_round is cart_round:
        _state.cart_round = None


def _session_engine(session: ormSession):
    bind = session.get_bind()
    return getattr(bind, "engine", bind)


async def load_sequencer_epoch(session: ormSession) -> int:
    row = await Setting.from_key(session, SETTING_CLOCK_SEQ_EPOCH)
    if row is None or row.value in {"", None}:
        return 0
    try:
        return max(0, int(row.value))
    except (TypeError, ValueError):
        return 0


async def peek_committed_epoch(session: ormSession) -> int:
    """Read epoch from a fresh connection so a producer reset wins over this tick."""
    from sqlalchemy.ext.asyncio import AsyncSession

    engine = _session_engine(session)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as probe:
            return await load_sequencer_epoch(probe)
    except Exception:
        return await load_sequencer_epoch(session)


async def persist_sequencer_cursor(
    session: ormSession,
    *,
    commit: bool = True,
) -> None:
    """Write in-memory cursor so the interface can preview without the scheduler."""
    from radiotomate.scheduler.execution import persist_fired_anchors

    committed_epoch = await peek_committed_epoch(session)
    if _state.restored and committed_epoch != _state.epoch:
        _state.restored = False
        _state.epoch = committed_epoch
        return
    snapshot = (_state.cursor, _state.clock_id, frozenset(_state.fired_anchors))
    if snapshot == _state.persisted_snapshot:
        return
    await Setting.upsert(session, SETTING_CLOCK_SEQ_CURSOR, str(_state.cursor))
    clock_id = "" if _state.clock_id is None else str(_state.clock_id)
    await Setting.upsert(session, SETTING_CLOCK_SEQ_CLOCK_ID, clock_id)
    await persist_fired_anchors(session, _state.fired_anchors)
    if commit:
        await session.commit()
    _state.persisted_snapshot = snapshot


async def restore_sequencer_state(
    session: ormSession,
    *,
    force: bool = False,
) -> None:
    """Reload cursor and fired anchors after a restart or producer reset."""
    from radiotomate.scheduler.execution import load_fired_anchors

    epoch = await load_sequencer_epoch(session)
    if _state.restored and not force and _state.epoch == epoch:
        return
    _state.fired_anchors = await load_fired_anchors(session)
    cursor, clock_id = await load_sequencer_cursor(session)
    _state.cursor = cursor
    _state.clock_id = clock_id
    _state.epoch = epoch
    _state.persisted_snapshot = (
        _state.cursor,
        _state.clock_id,
        frozenset(_state.fired_anchors),
    )
    _state.restored = True


async def reset_sequencer(session: ormSession, *, commit: bool = True) -> None:
    """
    Start the motif at position 0 and bump epoch so the scheduler process follows.
    The anchors fired stay fired, as after a restart: one that has gone, that a
    live held or that a hard one overtook does not go again once the conducteur
    is rebuilt. They are read from the base, where the scheduler saves them: this
    process may be the interface's, whose memory does not know them.
    """
    from radiotomate.scheduler.execution import load_fired_anchors

    epoch = await load_sequencer_epoch(session) + 1
    fired = await load_fired_anchors(session)
    reset_state()
    _state.fired_anchors = fired
    _state.epoch = epoch
    _state.restored = True
    _state.persisted_snapshot = (0, None, frozenset(fired))
    await Setting.upsert(session, SETTING_CLOCK_SEQ_EPOCH, str(epoch))
    await Setting.upsert(session, SETTING_CLOCK_SEQ_CURSOR, "0")
    await Setting.upsert(session, SETTING_CLOCK_SEQ_CLOCK_ID, "")
    if commit:
        await session.commit()


async def advance_sequencer_cursor(session: ormSession) -> None:
    """Move the motif cursor one step and persist it (demo skip / playhead)."""
    now = now_paris()
    minute_of_day = now.hour * 60 + now.minute
    slot = await AutoDJSlot.from_time(session, minute_of_day, now.weekday())
    clock_id = slot.clock_id if slot is not None else None
    saved_cursor, saved_clock_id = await load_sequencer_cursor(session)
    if clock_id is not None and saved_clock_id == clock_id:
        _state.cursor = saved_cursor + 1
    else:
        _state.cursor = 1
    _state.clock_id = clock_id
    await persist_sequencer_cursor(session)


async def load_sequencer_cursor(session: ormSession) -> tuple[int, int | None]:
    """Return (cursor, clock_id) stored by the last scheduler tick, or (0, None)."""
    cursor_row = await Setting.from_key(session, SETTING_CLOCK_SEQ_CURSOR)
    clock_row = await Setting.from_key(session, SETTING_CLOCK_SEQ_CLOCK_ID)
    cursor = 0
    if cursor_row is not None:
        try:
            cursor = max(0, int(cursor_row.value))
        except (TypeError, ValueError):
            cursor = 0
    clock_id = None
    if clock_row is not None and clock_row.value not in {"", None}:
        try:
            clock_id = int(clock_row.value)
        except (TypeError, ValueError):
            clock_id = None
    return cursor, clock_id


async def tick(
    session: ormSession,
    live_data: dict,
    playout_client: AsyncClient,
    beets: BeetsIntegration,
    now: datetime | None = None,
) -> list[str]:
    """
    One scheduler heartbeat. Returns action labels for tests.

    The Agenda speaks first (a dated set may hold the antenna), then the clock.
    """
    injected = now is not None
    now = now_from_live(live_data, now)
    actions: list[str] = []
    started = perf_counter()
    await restore_sequencer_state(session)
    gateway = gateway_for(playout_client)
    harbor = is_harbor_source(live_data.get("source"))
    agenda_now = now if injected else datetime.now(timezone.utc)
    agenda = await _agenda_step(session, live_data, gateway, agenda_now, harbor=harbor)
    actions.extend(agenda.actions)
    # A set about to be cut ends now: the clock fills as if nothing were left.
    clock_live = {**live_data, "remaining": "0"} if agenda.stops else live_data
    await _clock_step(
        session, clock_live, gateway, beets, now, actions, harbor=harbor, agenda=agenda
    )
    if agenda.stops:
        from radiotomate.scheduler import agenda as agenda_mod

        before = len(agenda.actions)
        try:
            await agenda_mod.finish_stops(
                session, gateway, live_data, agenda, agenda_now
            )
        except Exception:
            _log.exception("Agenda stop failed")
            await session.rollback()
        actions.extend(agenda.actions[before:])
    return _finish_tick(started, actions)


async def _agenda_step(
    session: ormSession,
    live_data: dict,
    gateway: PlayoutGateway,
    now: datetime,
    *,
    harbor: bool,
):
    """Never lets a fault in the Agenda stop the clock."""
    from radiotomate.scheduler import agenda as agenda_mod

    try:
        return await agenda_mod.step(session, live_data, gateway, now, harbor=harbor)
    except Exception:
        _log.exception("Agenda step failed; the clock runs without it")
        await session.rollback()
        return agenda_mod.AgendaTick()


async def _clock_step(  # noqa: PLR0912, PLR0913, PLR0915
    session: ormSession,
    live_data: dict,
    gateway: PlayoutGateway,
    beets: BeetsIntegration,
    now: datetime,
    actions: list[str],
    *,
    harbor: bool,
    agenda,
) -> None:
    if harbor:
        _state.pending_autodj_skip = False
        _state.pending_autodj_skip_minute = None
    if not harbor:
        from radiotomate.scheduler.outbox import dispatch_pending_commands

        await dispatch_pending_commands(session, gateway)
        await _refill_active_cart(session, live_data, gateway, actions)
        await _skip_cut_autodj_if_ready(live_data, gateway, now, actions)
    minute_of_day = now.hour * 60 + now.minute
    slot = await AutoDJSlot.from_time(session, minute_of_day, now.weekday())
    if slot is None or not slot.clock_id:
        _log.warning(
            "No clock on Auto-DJ slot at minute %s weekday %s; not filling queues",
            minute_of_day,
            now.weekday(),
        )
        if harbor:
            actions.append("live_hold")
        await persist_sequencer_cursor(session)
        return

    clock = await Clock.from_id(session, slot.clock_id)
    if clock is None:
        _log.warning("Clock %s missing; not filling queues", slot.clock_id)
        if harbor:
            actions.append("live_hold")
        await persist_sequencer_cursor(session)
        return

    if harbor:
        actions.append("live_hold")
        _forget_fired_anchors(now)
        nxt = await AutoDJSlot.next_after(session, slot)
        slot_end = slot.daypart_end_minute(nxt)
        await _hold_due_anchors(
            session, clock, slot.minute, slot_end, now, actions, reason=HELD_BY_LIVE
        )
        await persist_sequencer_cursor(session)
        return

    if agenda.hold:
        # A dated set is on air: its anchors are dropped, never stacked behind it.
        actions.append("agenda_hold")
        _forget_fired_anchors(now)
        nxt = await AutoDJSlot.next_after(session, slot)
        slot_end = slot.daypart_end_minute(nxt)
        await _hold_due_anchors(
            session, clock, slot.minute, slot_end, now, actions, reason=HELD_BY_SET
        )
        if not agenda.fill:
            await persist_sequencer_cursor(session)
            return

    from radiotomate.scheduler.execution import (
        close_passed_jingles,
        close_past_anchor_lines,
        ensure_forecast,
    )

    await close_past_anchor_lines(session, now)
    await close_passed_jingles(session, now)
    clock_id = clock.id
    weekday = now.weekday()
    await ensure_forecast(session, beets, now=now)
    slot = await AutoDJSlot.from_time(session, minute_of_day, weekday)
    clock = await Clock.from_id(session, clock_id)
    if slot is None or clock is None:
        await persist_sequencer_cursor(session)
        return

    if _state.clock_id != clock.id:
        _state.clock_id = clock.id
        _state.cursor = 0

    _forget_fired_anchors(now)

    nxt = await AutoDJSlot.next_after(session, slot)
    slot_end = slot.daypart_end_minute(nxt)

    if not agenda.hold:
        await _fire_due_anchors(
            session,
            live_data,
            gateway,
            clock,
            slot.minute,
            slot_end,
            now,
            actions,
        )
        await _fire_due_soft_anchors(
            session,
            live_data,
            gateway,
            clock,
            slot.minute,
            slot_end,
            now,
            actions,
        )

    sequential = clock.sequential_positions()
    if not sequential:
        await persist_sequencer_cursor(session)
        return

    anchored = clock.anchored_positions()
    next_anchor = next_hard_anchor_minute(now, slot.minute, slot_end, anchored)
    jingles_q = queued_count(live_data, "jingles_queued", "next_jingle")
    autodj_q = queued_count(live_data, "autodj_queued", "next_autodj")
    autodj_target = (
        AUTODJ_BURST_DEPTH
        if remaining_seconds(live_data) < AUTODJ_BURST_REMAINING
        else TARGET_QUEUE_DEPTH
    )
    live_data, jingles_q, autodj_q = await _fill_sequential_from_rundown(
        session,
        gateway,
        live_data,
        now,
        actions,
        next_anchor=next_anchor,
        jingles_q=jingles_q,
        autodj_q=autodj_q,
        autodj_target=autodj_target,
    )
    await persist_sequencer_cursor(session)


def _meta_from_item(item: RundownItem) -> tuple[str, str]:
    details = dict(item.details or {})
    artist = str(details.get("artist") or details.get("cart") or "").strip()
    title = str(details.get("title") or "").strip()
    raw = (item.resource or "").strip()
    if (not artist or not title) and " — " in raw:
        left, right = raw.split(" — ", 1)
        artist = artist or left.strip()
        title = title or right.strip()
    if not title:
        title = raw or artist or "titre"
    return artist, title


def _is_jingle_item(item: RundownItem) -> bool:
    return item.queue == "jingles" or item.kind == PositionKind.JINGLE.value


async def _load_pushable_sequential(session: ormSession) -> list[RundownItem]:
    """The lines still to push, in the order of the file: the desk lines among them
    while they air (``features.desk_lines_air``), first at the same time, as the
    console shows them."""
    # Through execution, which loads desk: desk imported first hits their cycle.
    from radiotomate.scheduler.execution import desk_lines_air, removed_clock_ids

    removed = await removed_clock_ids(session)
    query = select(RundownItem).where(
        RundownItem.status.in_(list(_PUSHABLE_STATUSES)),
        RundownItem.when_mode != WhenMode.ANCHORED.value,
    )
    if not await desk_lines_air(session):
        query = query.where(RundownItem.origin != _DESK_ORIGIN)
    rows = await session.scalars(
        query.order_by(
            RundownItem.planned_at,
            case((RundownItem.origin == _DESK_ORIGIN, 0), else_=1),
            RundownItem.sequence,
        )
    )
    return [row for row in rows if row.id not in removed]


def _file_order(row: RundownItem) -> tuple:
    """A line's place in the file, as ``_load_pushable_sequential`` sorts it."""
    return (row.planned_at, 0 if row.origin == _DESK_ORIGIN else 1, row.sequence)


def _queue_head(live_data: dict, queue: str) -> str | None:
    """What a playout queue plays next: "" when it holds nothing, the rundown id
    of its next title, or None for a title without a line, such as a gesture."""
    cue_key, count_key = _QUEUE_HEADS[queue]
    if queued_count(live_data, count_key, cue_key) == 0:
        return ""
    cue = live_data.get(cue_key)
    uri = str(cue.get("initial_uri") or "") if isinstance(cue, dict) else ""
    found = _ITEM_ID.search(uri)
    return found.group(1) if found else None


async def _line_turn(session: ormSession, line: RundownItem, live_data: dict) -> bool:
    """
    Whether a line for the jingles or carts queue goes now, at its place: a desk
    line, or a jingle of the motif (``features.motif_jingles_air``).

    Those queues cut what plays. The line waits until no title queued before it is
    left in a queue it would pass: the lines after it may already wait in the
    Auto-DJ, and air after it all the same. It does not cut the title on air
    either: it waits behind it in its own queue or a stronger one, or goes at its
    end.
    """
    src = source_id(live_data)
    if src in {"stream", "relay"}:
        return False
    rank = _QUEUE_RANK[line.queue]
    for queue in _QUEUE_HEADS:
        if _QUEUE_RANK[queue] >= rank:
            continue
        head = _queue_head(live_data, queue)
        if head == "":
            continue
        queued = await RundownItem.from_id(session, head) if head else None
        if (
            queued is None
            or queued.planned_at is None
            or _file_order(queued) < _file_order(line)
        ):
            return False
    if _QUEUE_RANK.get(src, 0) >= rank:
        return True
    return remaining_seconds(live_data) <= JINGLE_PREEMPT_REMAINING


def _on_air_title(live_data: dict) -> str:
    return str(live_data.get("title") or "").strip()


def _on_air_artist(live_data: dict) -> str:
    return str(live_data.get("artist") or "").strip()


def _item_matches_on_air(item: RundownItem, live_data: dict) -> bool:
    on_id = str(live_data.get("radiotomate_sound_id") or "").strip()
    if on_id and item.sound_id is not None and str(item.sound_id) == on_id:
        return True
    artist, title = _meta_from_item(item)
    on_title = _on_air_title(live_data)
    on_artist = _on_air_artist(live_data)
    if not title or not on_title:
        return False
    return title == on_title and (not artist or not on_artist or artist == on_artist)


def _cue_from_item(item: RundownItem) -> dict:
    artist, title = _meta_from_item(item)
    cue: dict = {"title": title, "artist": artist, "rid": 1}
    try:
        duration = float(item.duration or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration > 0:
        cue["duration"] = duration
    if item.path:
        cue["initial_uri"] = item.path
    if item.sound_id is not None:
        cue["radiotomate_sound_id"] = str(item.sound_id)
    return cue


def _next_field_for_item(item: RundownItem) -> str:
    if _is_jingle_item(item):
        return "next_jingle"
    if item.queue == "carts":
        return "next_cart"
    return "next_autodj"


def _ls_cue_usable(value: object, live_data: dict) -> bool:
    """True if Liquidsoap already exposes a next different from on-air."""
    parsed = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return False
    if not isinstance(parsed, dict):
        return False
    try:
        rid = int(parsed.get("rid", -1))
    except (TypeError, ValueError):
        rid = -1
    title = str(parsed.get("title") or "").strip()
    artist = str(parsed.get("artist") or "").strip()
    if rid < 0 and not title:
        return False
    on_title = _on_air_title(live_data)
    on_artist = _on_air_artist(live_data)
    same_title = bool(on_title) and title == on_title
    same_artist = not artist or not on_artist or artist == on_artist
    if same_title and same_artist:
        return False
    on_id = str(live_data.get("radiotomate_sound_id") or "").strip()
    cue_id = str(parsed.get("radiotomate_sound_id") or "").strip()
    if on_id and cue_id and on_id == cue_id:
        return False
    return bool(title or rid > 0)


async def peek_next_sequential(
    session: ormSession,
    live_data: dict,
) -> tuple[str, dict] | None:
    """Next planned sequential item that is not the title on air (UI only, no push)."""
    pending = await _load_pushable_sequential(session)
    for item in pending:
        if not (item.path or "").strip():
            continue
        if _item_matches_on_air(item, live_data):
            continue
        return _next_field_for_item(item), _cue_from_item(item)
    return None


async def overlay_rundown_next(session: ormSession, live_data: dict) -> None:
    """Fill empty/duplicate LS next_* with the next rundown item."""
    peeked = await peek_next_sequential(session, live_data)
    if not peeked:
        return
    field, cue = peeked
    if _ls_cue_usable(live_data.get(field), live_data):
        return
    live_data[field] = cue


async def _planned_anchor_item(
    session: ormSession,
    pos: ClockPosition,
    now: datetime,
) -> RundownItem | None:
    rows = list(
        await session.scalars(
            select(RundownItem)
            .where(
                RundownItem.status.in_(list(_PUSHABLE_STATUSES)),
                RundownItem.when_mode == WhenMode.ANCHORED.value,
                RundownItem.origin != "desk",
            )
            .order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )
    matched = [
        row for row in rows if pos.id is not None and row.clock_position_id == pos.id
    ]
    pool = matched or [
        row
        for row in rows
        if row.kind == pos.kind
        and (
            (row.planned_at is not None and row.planned_at.minute == pos.minute)
            or (row.details or {}).get("minute") == pos.minute
        )
    ]
    # A soft anchor is planned at the end of the title astride its minute, often
    # past that minute: its line carries the minute in its details. Within the
    # hour after this occurrence, it cannot be the line of another one.
    occurrence = now.replace(minute=pos.minute, second=0, microsecond=0, tzinfo=None)
    for row in pool:
        planned = row.planned_at
        if (
            planned is not None
            and occurrence <= planned < occurrence + timedelta(hours=1)
            and (
                planned.minute == pos.minute
                or (row.details or {}).get("minute") == pos.minute
            )
        ):
            return row
    return None


async def _soft_lines_astride_the_hour(
    session: ormSession,
    now: datetime,
) -> list[tuple[tuple[str, int, int], RundownItem]]:
    """
    The planned lines of the soft anchors of the hour before, by occurrence key.

    A soft anchor waits for the end of the title astride its minute, and the
    conducteur plans it there. That title may end past the hour, in the next
    daypart or on the next day: the occurrence is then the one of the hour
    before, and its line, which carries its minute, says which. It is owed until
    the title ends, and an hour after its minute at most, as the line of an hour
    is (``_planned_anchor_item``). Never without its line. A reset of the
    conducteur drops it, as it drops every line planned, and keeps the anchors
    fired (``reset_sequencer``).
    """
    local = now.replace(tzinfo=None)
    hour_before = local.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    rows = await session.scalars(
        select(RundownItem)
        .where(
            RundownItem.status.in_(list(_PUSHABLE_STATUSES)),
            RundownItem.when_mode == WhenMode.ANCHORED.value,
            RundownItem.origin != "desk",
            RundownItem.planned_at >= hour_before,
        )
        .order_by(RundownItem.planned_at, RundownItem.sequence)
    )
    found: dict[tuple[str, int, int], RundownItem] = {}
    for row in rows:
        minute = (row.details or {}).get("minute")
        if not isinstance(minute, int) or row.clock_position_id is None:
            continue
        occurrence = hour_before.replace(minute=minute)
        owed_until = occurrence + timedelta(hours=1)
        if not (occurrence <= row.planned_at < owed_until) or local >= owed_until:
            continue
        # The anchor may have moved, or turned hard, since the forecast.
        pos = await session.get(ClockPosition, row.clock_position_id)
        if pos is None or not pos.is_soft_sync or pos.minute != minute:
            continue
        key = (occurrence.date().isoformat(), occurrence.hour, minute)
        found.setdefault(key, row)
    return list(found.items())


async def _beets_track_gain(beets_id: int) -> str | None:
    """
    ReplayGain of a Beets track, computed on the spot when the import skipped it.
    Returns ``None`` outside an application context (unit tests) or on failure.
    """
    from radiotomate.beets import BeetsIntegration

    try:
        beets = BeetsIntegration.get()
    except (RuntimeError, KeyError):
        return None
    try:
        return await beets.ensure_item_gain(beets_id)
    except Exception:
        _log.exception("ReplayGain lookup failed for beets item %s", beets_id)
        return None


async def _push_existing_rundown_item(  # noqa: PLR0912
    session: ormSession,
    gateway: PlayoutGateway,
    item: RundownItem,
    *,
    queue: str | None = None,
) -> bool:
    target = queue or item.queue or "autodj"
    path = (item.path or "").strip()
    if not path:
        return False
    if item.origin != _DESK_ORIGIN and await _cart_turned_relay(session, item):
        # Planned before its cart turned relay: the clock plays none of its sounds.
        # The line closes, committed here, or the next tick would find it again.
        _close_line(item, RELAY_CART, now_paris())
        await session.commit()
        _log.warning("Rundown %s: its cart is a relay now, the clock skips it", item.id)
        return False
    artist, title = _meta_from_item(item)
    payload: dict = {"path": path, "radiotomate_item_id": item.id}
    if artist:
        payload["artist"] = artist
    if title:
        payload["title"] = title
    if item.beets_id:
        payload["beets_id"] = item.beets_id
    if item.sound_id:
        payload["radiotomate_sound_id"] = item.sound_id
        sound = await Sound.from_id(session, item.sound_id)
        if sound is not None and sound.gain is not None:
            payload["rg_track_gain"] = str(sound.gain)
    details = dict(item.details or {})
    if details.get("rg_track_gain") is not None:
        payload.setdefault("rg_track_gain", details["rg_track_gain"])
    if item.beets_id and payload.get("rg_track_gain") is None:
        gain = await _beets_track_gain(item.beets_id)
        if gain is not None:
            payload["rg_track_gain"] = gain
            item.details = {**details, "rg_track_gain": gain}
        else:
            _log.warning(
                "Beets item %s pushed without ReplayGain (rundown %s)",
                item.beets_id,
                item.id,
            )
    command = await enqueue_command(
        session,
        action=PlayoutAction.QUEUE.value,
        queue=target,
        payload=payload,
        item=item,
    )
    payload["radiotomate_command_id"] = command.id
    command.payload = payload
    result = await dispatch_command(session, command, gateway)
    if not result.ok:
        _log.error(
            "Clock push of rundown %s to %s failed: %s",
            item.id,
            target,
            result.error,
        )
        return False
    if item.sound_id:
        sound = await Sound.from_id(session, item.sound_id)
        if sound is not None:
            sound.last_played = datetime.now()
    _log.info("Clock pushed rundown %s %s to %s", item.kind, path, target)
    return True


async def _cart_turned_relay(session: ormSession, item: RundownItem) -> bool:
    """Whether the cart of a planned line is a relay now, as it may have turned
    since the forecast."""
    if item.cart_id is None:
        return False
    mode = await session.scalar(select(Cart.mode).where(Cart.id == item.cart_id))
    return mode is CartMode.RELAY


async def _push_desk_line(
    session: ormSession,
    gateway: PlayoutGateway,
    line: RundownItem,
    now: datetime,
) -> bool:
    """Push a desk line to its queue. The tick commits when the cursor of the motif
    moves, and a desk line does not move it: its push, refused or not, is
    committed here, or the next tick, in a session of its own, could miss it and
    push the line again."""
    from radiotomate.scheduler.execution import close_replaced

    pushed = await _push_existing_rundown_item(session, gateway, line, queue=line.queue)
    if pushed:
        await close_replaced(session, line, now)
    await session.commit()
    return pushed


def _desk_would_overflow(
    line: RundownItem,
    live_data: dict,
    now: datetime,
    next_anchor: int,
    *,
    turn: bool,
) -> bool:
    """Whether a desk line would still play at the minute of the next hard anchor.
    At its turn it starts at the end of the title on air; before, not earlier
    than its time in the file, which realign_rundown keeps on the as-run."""
    start = remaining_seconds(live_data)
    if not turn and line.planned_at is not None:
        ahead = (line.planned_at - now.replace(tzinfo=None)).total_seconds()
        start = max(start, ahead)
    return track_would_overflow_anchor(
        now, start, float(line.duration or 0), next_anchor
    )


async def _fill_sequential_from_rundown(  # noqa: PLR0912, PLR0913, PLR0915
    session: ormSession,
    gateway: PlayoutGateway,
    live_data: dict,
    now: datetime,
    actions: list[str],
    *,
    next_anchor: int | None,
    jingles_q: int,
    autodj_q: int,
    autodj_target: int,
) -> tuple[dict, int, int]:
    hold = False
    jingles_air = await motif_jingles_air(session)
    for _ in range(8):
        if hold:
            break
        pending = [
            item
            for item in await _load_pushable_sequential(session)
            if (item.path or "").strip()
        ]
        if not pending:
            break
        made_progress = False
        # A desk line waits for its turn: the desk lines after it wait too.
        desk_waits = False
        for item in pending:
            if item.status not in _PUSHABLE_STATUSES:
                continue
            desk = item.origin == _DESK_ORIGIN
            if desk and item.queue in {"jingles", "carts"}:
                if desk_waits:
                    continue
                turn = await _line_turn(session, item, live_data)
                if next_anchor is not None and _desk_would_overflow(
                    item, live_data, now, next_anchor, turn=turn
                ):
                    _log.info(
                        "Holding desk line %s so hard anchor at minute %s can fire",
                        item.id,
                        next_anchor,
                    )
                    hold = True
                    break
                if not turn:
                    desk_waits = True
                    continue
                if not await _push_desk_line(session, gateway, item, now):
                    continue
                actions.append("desk")
                if item.queue == "jingles":
                    jingles_q += 1
                    live_data = {
                        **live_data,
                        "next_jingle": {"rid": 1},
                        "jingles_queued": jingles_q,
                    }
                else:
                    live_data = {
                        **live_data,
                        "next_cart": {"rid": 1},
                        "carts_queued": queued_count(
                            live_data, "carts_queued", "next_cart"
                        )
                        + 1,
                    }
                made_progress = True
                break
            if _is_jingle_item(item):
                if jingles_air:
                    if jingles_q >= JINGLE_QUEUE_DEPTH or not await _line_turn(
                        session, item, live_data
                    ):
                        # The desk lines after it wait too, or they would air
                        # before it.
                        desk_waits = True
                        continue
                elif (
                    jingles_q >= JINGLE_QUEUE_DEPTH
                    or autodj_q > 0
                    or not can_push_sequential_jingle(live_data)
                ):
                    continue
                if not await _push_existing_rundown_item(
                    session, gateway, item, queue="jingles"
                ):
                    continue
                actions.append("jingle")
                _state.cursor += 1
                jingles_q += 1
                live_data = {
                    **live_data,
                    "next_jingle": {"rid": 1},
                    "jingles_queued": jingles_q,
                }
                made_progress = True
                break
            if autodj_q >= autodj_target:
                break
            length = float(item.duration or 0)
            if next_anchor is not None and track_would_overflow_anchor(
                now,
                remaining_seconds(live_data),
                length,
                next_anchor,
            ):
                _log.info(
                    "Holding autodj track so hard anchor at minute %s can fire",
                    next_anchor,
                )
                hold = True
                break
            if desk:
                if not await _push_desk_line(session, gateway, item, now):
                    continue
                # Not a step of the motif: the cursor stays.
                actions.append("desk")
            else:
                queue = item.queue if item.queue in {"autodj", "carts"} else "autodj"
                if not await _push_existing_rundown_item(
                    session, gateway, item, queue=queue
                ):
                    continue
                actions.append(
                    "autodj"
                    if item.kind == PositionKind.MUSIQUE.value
                    else "autodj_cart"
                )
                _state.cursor += 1
            autodj_q += 1
            live_data = {
                **live_data,
                "next_autodj": {"rid": 1},
                "autodj_queued": autodj_q,
            }
            made_progress = True
            break
        if not made_progress:
            break
    return live_data, jingles_q, autodj_q


async def _enqueue_cart_sound(
    session: ormSession,
    gateway: PlayoutGateway,
    cart: Cart,
    sound: Sound,
) -> bool:
    queue = cart.playout_queue()
    result = await gateway.queue(
        queue,
        {
            "path": str(sound.path),
            "artist": cart.title,
            "title": sound.title,
            "radiotomate_sound_id": sound.id,
            "rg_track_gain": str(sound.gain),
        },
    )
    if not result.ok:
        _log.error("Cart chain push to %s failed: %s", queue, result.error)
        return False
    sound.last_played = datetime.now()
    return True


async def _refill_active_cart(
    session: ormSession,
    live_data: dict,
    gateway: PlayoutGateway,
    actions: list[str],
) -> None:
    """Queue the launched cart's next sounds until its round is over."""
    cart_round = _state.cart_round
    if cart_round is None:
        return
    src = source_id(live_data)
    carts_q = queued_count(live_data, "carts_queued", "next_cart")
    if src == "carts" or carts_q > 0:
        cart_round.seen = True
    elif cart_round.seen:
        # Nothing of it on air or queued any more: the round was cut short.
        end_cart_round(cart_round)
        return
    else:
        # News from before the launch: its sounds are not in the queue yet.
        return
    if carts_q >= TARGET_QUEUE_DEPTH:
        return
    cart = await Cart.from_id(session, cart_round.cart_id, load_sounds=True)
    if cart is None or not CartRound.applies_to(cart):
        end_cart_round(cart_round)
        return
    pushed_any = False
    # « Vider les files » or another launch during a push ends this round.
    while carts_q < TARGET_QUEUE_DEPTH and _state.cart_round is cart_round:
        sound = cart_round.next_sound(cart)
        if sound is None:
            end_cart_round(cart_round)
            break
        if not await _enqueue_cart_sound(session, gateway, cart, sound):
            break
        cart_round.queued.add(sound.id)
        carts_q += 1
        pushed_any = True
        actions.append("cart_chain")
    if pushed_any:
        await session.commit()


async def _skip_cut_autodj_if_ready(
    live_data: dict,
    gateway: PlayoutGateway,
    now: datetime,
    actions: list[str],
) -> None:
    """Skip autodj_queue once the hard-sync cart is on air, not the output bed."""
    if not _state.pending_autodj_skip:
        return
    src = source_id(live_data)
    if src in {"stream", "relay"}:
        _state.pending_autodj_skip = False
        _state.pending_autodj_skip_minute = None
        return
    if src not in {"carts", "jingles"}:
        if (
            _state.pending_autodj_skip_minute is not None
            and now.minute != _state.pending_autodj_skip_minute
        ):
            _state.pending_autodj_skip = False
            _state.pending_autodj_skip_minute = None
        return
    skip = await gateway.skip({"queue": "autodj"})
    if skip.ok:
        _state.pending_autodj_skip = False
        _state.pending_autodj_skip_minute = None
        actions.append("skip")
        return
    if not skip.transient:
        _state.pending_autodj_skip = False
        _state.pending_autodj_skip_minute = None
        _log.error("Deferred autodj skip after hard-sync failed: %s", skip.error)


async def _remember_cut_autodj(
    session: ormSession,
    live_data: dict,
    now: datetime,
) -> None:
    """Keep the cut title out of the next Beets pick even if it never logged on_air."""
    artist = str(live_data.get("artist") or "").strip()
    title = str(live_data.get("title") or "").strip()
    if not artist and not title:
        return
    payload = {
        "source": "autodj",
        "artist": artist,
        "title": title,
        "album": str(live_data.get("album") or ""),
        "initial_uri": str(
            live_data.get("initial_uri") or live_data.get("source_url") or ""
        ),
        "on_air": now.replace(tzinfo=None).isoformat(sep=" ")
        if now.tzinfo
        else now.isoformat(sep=" "),
        "skipped": True,
        "skip_reason": "hard_sync",
    }
    item_id = live_data.get("radiotomate_item_id")
    if item_id:
        payload["radiotomate_item_id"] = item_id
    log = await MetadataLog.from_playout(session, payload)
    session.add(log)


def _forget_fired_anchors(now: datetime) -> None:
    """
    Keep the anchors fired today, and those of the hour before: past midnight,
    the title astride it may still owe a soft anchor of the day before.
    """
    since = (now - timedelta(hours=1)).date().isoformat()
    _state.fired_anchors = {k for k in _state.fired_anchors if k[0] >= since}


def _close_line(line: RundownItem | None, reason: str, now: datetime) -> None:
    """An anchor line that will never go says so: « sauté », and why."""
    if line is None:
        return
    line.status = RundownStatus.SKIPPED.value
    line.reason = reason
    line.closed_at = now.replace(tzinfo=None)


async def skip_overtaken_soft(session: ormSession) -> bool:
    """Whether a soft anchor a hard one has overtaken is skipped. A missing key
    says it is."""
    row = await Setting.from_key(session, SETTING_SKIP_OVERTAKEN)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


async def motif_jingles_air(session: ormSession) -> bool:
    """Whether a jingle of the motif airs at its turn, ahead of the music queued
    after it, and is skipped once that music has aired. A missing key says so."""
    row = await Setting.from_key(session, SETTING_MOTIF_JINGLES_AIR)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


async def ordered_lines_follow_clock(session: ormSession) -> bool:
    """Whether the lines planned of a cart in order follow the sound the clock
    draws itself for an anchor of that cart. A missing key says they do."""
    row = await Setting.from_key(session, SETTING_ORDERED_FOLLOW)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


async def _hold_due_anchors(  # noqa: PLR0913
    session: ormSession,
    clock: Clock,
    slot_start: int,
    slot_end: int,
    now: datetime,
    actions: list[str],
    *,
    reason: str,
) -> None:
    """
    Drop due anchors while harbor or a dated set is on air so they are not dumped
    after it. Their planned lines will never go: they close, with ``reason``, and
    the draw of their cart no longer counts them as to come.
    """
    for pos in clock.anchored_positions():
        if pos.minute is None or not (pos.is_hard_sync or pos.is_soft_sync):
            continue
        if not anchor_in_daypart(slot_start, slot_end, now.hour, pos.minute):
            continue
        occurrence = now.replace(minute=pos.minute, second=0, microsecond=0)
        if now < occurrence:
            continue
        key = (now.date().isoformat(), now.hour, pos.minute)
        if key in _state.fired_anchors:
            continue
        _state.fired_anchors.add(key)
        actions.append(f"anchor:{pos.minute}:hold")
        _close_line(await _planned_anchor_item(session, pos, now), reason, now)
    # A soft anchor of the hour before still waits for the title astride the hour.
    for key, line in await _soft_lines_astride_the_hour(session, now):
        if key in _state.fired_anchors:
            continue
        _state.fired_anchors.add(key)
        actions.append(f"anchor:{key[2]}:hold")
        _close_line(line, reason, now)


async def _fire_due_anchors(  # noqa: PLR0913
    session: ormSession,
    live_data: dict,
    gateway: PlayoutGateway,
    clock: Clock,
    slot_start: int,
    slot_end: int,
    now: datetime,
    actions: list[str],
) -> None:
    for pos in clock.anchored_positions():
        if pos.minute is None or not pos.is_hard_sync:
            continue
        if not anchor_in_daypart(slot_start, slot_end, now.hour, pos.minute):
            continue
        if now.minute != pos.minute:
            continue
        key = (now.date().isoformat(), now.hour, pos.minute)
        if key in _state.fired_anchors:
            continue
        planned = await _planned_anchor_item(session, pos, now)
        if planned is not None:
            pushed = await _push_existing_rundown_item(
                session,
                gateway,
                planned,
                queue="carts",
            )
        else:
            pushed = await _push_cart_to_queue(
                session,
                gateway,
                pos,
                clock,
                "carts",
                now=now,
            )
        if not pushed:
            continue
        _state.fired_anchors.add(key)
        actions.append(f"anchor:{pos.minute}")
        src = source_id(live_data)
        if src not in {"carts", "stream", "relay"}:
            await _remember_cut_autodj(session, live_data, now)
            _state.pending_autodj_skip = True
            _state.pending_autodj_skip_minute = now.minute


def _skip_overtaken(
    key: tuple[str, int, int],
    line: RundownItem | None,
    now: datetime,
    actions: list[str],
) -> None:
    """A hard anchor came while this soft one waited: it does not go after it."""
    _state.fired_anchors.add(key)
    actions.append(f"soft-skip:{key[2]}")
    _close_line(line, OVERTAKEN, now)


async def _fire_soft_anchors_astride_the_hour(
    session: ormSession,
    gateway: PlayoutGateway,
    now: datetime,
    actions: list[str],
    *,
    overtaken,
) -> None:
    """The title astride the hour ends: the soft anchors it held go, with their line."""
    for key, line in await _soft_lines_astride_the_hour(session, now):
        if key in _state.fired_anchors:
            continue
        day, hour, minute = key
        occurrence = datetime.fromisoformat(day).replace(hour=hour, minute=minute)
        if await overtaken(occurrence):
            _skip_overtaken(key, line, now, actions)
            continue
        if not await _push_existing_rundown_item(session, gateway, line, queue="carts"):
            continue
        _state.fired_anchors.add(key)
        actions.append(f"soft:{key[2]}")


async def _fire_due_soft_anchors(  # noqa: PLR0913
    session: ormSession,
    live_data: dict,
    gateway: PlayoutGateway,
    clock: Clock,
    slot_start: int,
    slot_end: int,
    now: datetime,
    actions: list[str],
) -> None:
    remaining = remaining_seconds(live_data)
    src = source_id(live_data)
    title_ends = remaining <= JINGLE_PREEMPT_REMAINING or src in {"", "starting"}
    anchored = clock.anchored_positions()
    switch: list[bool] = []

    async def overtaken(occurrence: datetime) -> bool:
        """A hard anchor has gone since this soft one was due: the conducteur
        says « sauté », and the antenna does not play it after the hard one."""
        if not hard_anchor_since(
            occurrence, now, slot_start, slot_end, anchored, _state.fired_anchors
        ):
            return False
        if not switch:
            switch.append(await skip_overtaken_soft(session))
        return switch[0]

    if title_ends:
        # The hour before goes first.
        await _fire_soft_anchors_astride_the_hour(
            session, gateway, now, actions, overtaken=overtaken
        )
    for pos in anchored:
        if pos.minute is None or not pos.is_soft_sync:
            continue
        if not anchor_in_daypart(slot_start, slot_end, now.hour, pos.minute):
            continue
        occurrence = now.replace(minute=pos.minute, second=0, microsecond=0)
        if now < occurrence:
            continue
        key = (now.date().isoformat(), now.hour, pos.minute)
        if key in _state.fired_anchors:
            continue
        if await overtaken(occurrence):
            line = await _planned_anchor_item(session, pos, now)
            _skip_overtaken(key, line, now, actions)
            continue
        if not title_ends:
            continue
        planned = await _planned_anchor_item(session, pos, now)
        if planned is not None:
            pushed = await _push_existing_rundown_item(
                session,
                gateway,
                planned,
                queue="carts",
            )
        else:
            pushed = await _push_cart_to_queue(
                session,
                gateway,
                pos,
                clock,
                "carts",
                reason="glissement" if now > occurrence else None,
                now=now,
            )
        if not pushed:
            continue
        _state.fired_anchors.add(key)
        actions.append(f"soft:{pos.minute}")


async def _push_cart_to_queue(  # noqa: PLR0913
    session: ormSession,
    gateway: PlayoutGateway,
    pos: ClockPosition,
    clock: Clock,
    queue: str,
    reason: str | None = None,
    *,
    now: datetime,
) -> bool:
    references = [
        (pos.cart_id, pos.cart_title),
        (pos.fallback_cart_id, pos.fallback_cart_title),
        (clock.fallback_cart_id, clock.fallback_cart_title),
    ]
    sound: Sound | None = None
    cart: Cart | None = None
    tried: list[Cart | None] = []
    for cart_id, title in references:
        if cart_id is None and not title:
            continue
        cart = await _load_cart(session, cart_id=cart_id, title=title)
        tried.append(cart)
        if cart is not None and cart.mode is CartMode.RELAY:
            # The clock does not launch a relay: the fallback plays, if any.
            continue
        sound = await next_cart_sound(session, cart)
        if sound:
            break
    if not sound or not cart:
        _log.warning(
            "Clock position %s: no sound (tried %s)",
            pos.id,
            references,
        )
        # The cart the position names first, as its line in the conducteur does.
        named = tried[0] if tried else None
        if named is not None and named.mode is CartMode.RELAY:
            await _say_relay_passed(session, pos, clock, named, now)
        return False
    fallback_used = (
        bool(cart.id != pos.cart_id)
        if pos.cart_id
        else bool(pos.cart_title and cart.title != pos.cart_title)
    )
    payload = {
        "path": str(sound.path),
        "artist": cart.title,
        "title": sound.title,
        "radiotomate_sound_id": sound.id,
        "rg_track_gain": str(sound.gain),
    }
    item = await _record_push_item(
        session,
        kind=pos.kind,
        when=pos.when_mode,
        queue=queue,
        resource=(sound.title or "").strip() or cart.title,
        path=str(sound.path),
        clock=clock,
        pos=pos,
        cart_id=cart.id,
        sound_id=sound.id,
        fallback_used=fallback_used,
        reason=reason,
        sync=pos.sync,
    )
    payload["radiotomate_item_id"] = item.id
    command = await enqueue_command(
        session,
        action=PlayoutAction.QUEUE.value,
        queue=queue,
        payload=payload,
        item=item,
    )
    payload["radiotomate_command_id"] = command.id
    command.payload = payload
    result = await dispatch_command(session, command, gateway)
    # Sent, or waiting to be, the sound has taken its turn: the conducteur plans
    # what comes after it. Refused for good, it has not.
    await _follow_the_turn(session, cart, item)
    if result.ok:
        _log.info(
            "Clock pushed %s %s:%s to %s",
            pos.kind,
            sound.id,
            sound.path,
            queue,
        )
        sound.last_played = datetime.now()
        return True
    _log.error("Clock push to %s failed: %s", queue, result.error)
    return False


async def _follow_the_turn(session: ormSession, cart: Cart, drawn: RundownItem) -> None:
    """
    The clock has drawn an anchor itself, the conducteur holding no line for it:
    a cart in order gave the sound ``Cart.next_sound`` gives, the one the
    conducteur may already have planned for the next anchor of the cart. The
    lines it plans of the cart take the sounds that follow, named as the
    forecast names them (``rundown._prepare_cart``). ``drawn`` is the line of
    that sound.
    """
    from radiotomate.scheduler.rundown import (
        DEFAULT_CART_SEC,
        _duration_seconds,
        _media_path,
    )

    moved = await planned_in_order(session, cart, since=drawn.planned_at)
    if not moved or not await ordered_lines_follow_clock(session):
        return
    for line, sound in moved:
        title = (sound.title or "").strip() or cart.title
        line.sound_id = sound.id
        line.path = _media_path(sound.path)
        line.resource = title
        line.duration = _duration_seconds(sound.duration, DEFAULT_CART_SEC)
        line.details = {**(line.details or {}), "artist": cart.title, "title": title}
        _log.info(
            "Rundown %s now plans sound %s of cart %s", line.id, sound.id, cart.id
        )


async def _say_relay_passed(
    session: ormSession,
    pos: ClockPosition,
    clock: Clock,
    relay: Cart,
    now: datetime,
) -> None:
    """
    An anchor whose cart is a relay, without a fallback that has a sound, plays
    nothing: the conducteur says it, reason ``RELAY_CART``. By the line the
    forecast planned for this occurrence, « manquant », or else by a line closed
    here, once, « sauté »: the forecast does not see an anchor due when it is
    built. Closed, the line is no anchor to come any more.
    """
    from radiotomate.scheduler.execution import (
        ensure_programming_version,
        item_from_forecast,
    )

    local = now.replace(tzinfo=None)
    occurrence = local.replace(minute=pos.minute, second=0, microsecond=0)
    said = await session.scalar(
        select(RundownItem.id)
        .where(
            RundownItem.clock_position_id == pos.id,
            RundownItem.planned_at >= occurrence,
            RundownItem.planned_at < occurrence + timedelta(hours=1),
        )
        .limit(1)
    )
    if said is not None:
        return
    version = await ensure_programming_version(session)
    line = item_from_forecast(
        {
            "at": local.isoformat(),
            "kind": pos.kind,
            "when": pos.when_mode,
            "minute": pos.minute,
            "sync": pos.sync,
            "queue": CARTS_QUEUE,
            "resource": relay.title,
            "cart": relay.title,
            "status": RundownStatus.SKIPPED.value,
            "reason": RELAY_CART,
            "clock": clock.name,
            "clock_id": clock.id,
            "position_id": pos.id,
            "cart_id": relay.id,
        },
        version,
        0,
    )
    line.closed_at = local
    session.add(line)
    # The tick commits only when the cursor or the anchors fired change.
    await session.commit()
    _log.warning(
        "Clock position %s: cart %s is a relay, the clock does not launch it",
        pos.id,
        relay.id,
    )


async def _load_cart(
    session: ormSession,
    title: str | None = None,
    *,
    cart_id: int | None = None,
) -> Cart | None:
    if cart_id is not None:
        return await Cart.from_id(session, cart_id, load_sounds=True)
    if not title:
        return None
    cart = await Cart.from_title(session, title)
    if cart is None:
        return None
    return await Cart.from_id(session, cart.id, load_sounds=True)


async def _push_autodj_item(
    session: ormSession,
    gateway: PlayoutGateway,
    item,
    pos: ClockPosition,
    clock: Clock,
) -> bool:
    next_path = item.path.decode() if isinstance(item.path, bytes) else str(item.path)
    artist = str(getattr(item, "artist", "") or "").strip()
    title = str(getattr(item, "title", "") or "").strip()
    if artist and title:
        resource = f"{artist} — {title}"
    else:
        resource = title or artist or "musique"
    payload = {
        "path": next_path,
        "beets_id": item.id,
        "rg_track_gain": item.rg_track_gain,
    }
    if artist:
        payload["artist"] = artist
    if title:
        payload["title"] = title
    rundown_item = await _record_push_item(
        session,
        kind=pos.kind,
        when=pos.when_mode,
        queue="autodj",
        resource=resource,
        path=next_path,
        clock=clock,
        pos=pos,
        beets_id=getattr(item, "id", None),
    )
    payload["radiotomate_item_id"] = rundown_item.id
    command = await enqueue_command(
        session,
        action=PlayoutAction.QUEUE.value,
        queue="autodj",
        payload=payload,
        item=rundown_item,
    )
    payload["radiotomate_command_id"] = command.id
    command.payload = payload
    result = await dispatch_command(session, command, gateway)
    if result.ok:
        _log.info("Clock pushed track %s to autodj", next_path)
        return True
    _log.error("Clock autodj push failed: %s", result.error)
    return False


async def _record_push_item(  # noqa: PLR0913
    session: ormSession,
    *,
    kind: str,
    when: str,
    queue: str,
    resource: str,
    path: str | None,
    clock: Clock,
    pos: ClockPosition,
    cart_id: int | None = None,
    sound_id: int | None = None,
    beets_id: int | None = None,
    fallback_used: bool = False,
    reason: str | None = None,
    sync: str | None = None,
):
    from radiotomate.scheduler.execution import record_live_item

    return await record_live_item(
        session,
        payload={
            "at": now_paris().isoformat(),
            "kind": kind,
            "when": when,
            "queue": queue,
            "resource": resource,
            "path": path,
            "clock": clock.name,
            "clock_id": clock.id,
            "position_id": pos.id,
            "cart_id": cart_id,
            "sound_id": sound_id,
            "beets_id": beets_id,
            "fallback_used": fallback_used,
            "reason": reason,
            "sync": sync,
            "duration": 0,
            "status": RundownStatus.RESERVED.value,
        },
        status=RundownStatus.RESERVED.value,
    )
