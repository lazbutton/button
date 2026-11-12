import copy
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from time import monotonic
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.execution import item_status_code, rundown_summary
from radiotomate.enums import CartMode, CommandStatus, ScheduleMode
from radiotomate.models import (
    AutoDJSlot,
    Cart,
    Clock,
    ClockPosition,
    MetadataLog,
    PlayoutCommand,
    RundownItem,
    Setting,
    Sound,
)
from radiotomate.scheduler import live as sched_live
from radiotomate.scheduler import timing
from radiotomate.scheduler.clock import PARIS, reset_state, tick
from radiotomate.scheduler.clock import _state as clock_state
from radiotomate.scheduler.execution import (
    MISSING_FORECAST_HOLD,
    SETTING_FIRED_ANCHORS,
    clear_live_forecast,
    ensure_forecast,
    materialize_rundown,
    published_rundown,
    reset_conducteur,
)
from radiotomate.scheduler.outbox import dispatch_command, enqueue_command
from radiotomate.scheduler.playout import PlayoutGateway
from radiotomate.services.carts import sync_cart_display_titles
from tests.scheduler.test_cart_draw import (
    MONDAY,
    _clock_at,
    _music_on_air,
    _pub_break,
    _spots,
)
from tests.scheduler.test_clock import (
    JOURNEE_20,
    NIGHT,
    _client,
    _live,
    _pushed_ids,
)

MONDAY_1010 = datetime(2026, 9, 14, 10, 10, tzinfo=PARIS)


def test_rundown_summary_counts_upcoming_rescue_and_skip():
    summary = rundown_summary(
        [
            {"kind": "musique", "status_code": "played", "when": "sequential"},
            {"kind": "jingle", "status_code": "skipped"},
            {"kind": "musique", "status_code": "planned", "when": "sequential"},
            {
                "kind": "pub",
                "status_code": "planned",
                "when": "anchored",
                "minute": 20,
                "at": "2026-09-16T10:20:00",
                "resource": "Pub locale",
                "sync": "dure",
            },
            {"kind": "son", "fallback_used": True, "status_code": "rescue"},
        ]
    )
    assert summary["counts"]["items"] == 3
    assert summary["counts"]["musique"] == 1
    assert summary["counts"]["jingle"] == 0
    assert summary["counts"]["pub"] == 1
    assert summary["counts"]["son"] == 1
    assert summary["counts"]["secours"] == 1
    assert summary["counts"]["sauté"] == 1
    assert summary["next_anchor"]["minute"] == 20
    assert summary["next_anchor"]["resource"] == "Pub locale"


def test_item_status_code_maps_manquant():
    assert item_status_code({"status": "manquant"}) == "failed"


async def test_clock_accepts_cart_id(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
):
    from radiotomate.services.autodj import create_clock

    clock = await create_clock(
        dbsession,
        {
            "name": "IDs stables",
            "fallback_cart_id": jingles_cart.id,
            "motif": [
                {
                    "kind": "jingle",
                    "cart_id": jingles_cart.id,
                }
            ],
            "anchors": [
                {
                    "kind": "pub",
                    "cart_id": pubs_cart.id,
                    "fallback_cart_id": jingles_cart.id,
                    "minute": 15,
                    "sync": "molle",
                }
            ],
        },
    )
    await dbsession.commit()
    loaded = await Clock.from_id(dbsession, clock.id)
    assert loaded.fallback_cart_id == jingles_cart.id
    assert loaded.fallback_cart_title == "Jingles"
    assert loaded.positions[0].cart_id == jingles_cart.id
    assert loaded.anchored_positions()[0].cart_id == pubs_cart.id
    assert loaded.anchored_positions()[0].is_soft_sync is True


async def test_rename_cart_updates_clock_titles(
    dbsession: ormSession,
    jingles_cart,
):
    clock = await Clock.from_name(dbsession, "24/24 Rotation habillée")
    clock = await Clock.from_id(dbsession, clock.id)
    clock.fallback_cart_id = jingles_cart.id
    clock.fallback_cart_title = jingles_cart.title
    for pos in clock.positions:
        if pos.cart_title == jingles_cart.title or pos.kind == "jingle":
            pos.cart_id = jingles_cart.id
            pos.cart_title = jingles_cart.title
    await dbsession.commit()
    jingles_cart.title = "Jingles renommés"
    await sync_cart_display_titles(dbsession, jingles_cart)
    await dbsession.commit()
    clock = await Clock.from_id(dbsession, clock.id)
    assert clock.fallback_cart_title == "Jingles renommés"
    jingle = next(pos for pos in clock.positions if pos.cart_id == jingles_cart.id)
    assert jingle.cart_title == "Jingles renommés"


async def test_materialize_rundown_persists_items(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    data = await materialize_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 15, 10, 19, tzinfo=PARIS),
        cursor=0,
    )
    assert data["programming_version"]
    assert data["items"]
    assert data["items"][0]["id"]
    assert data["items"][0]["status_code"] in {"planned", "rescue", "skipped"}
    rows = list(await dbsession.scalars(select(RundownItem)))
    assert len(rows) == len(data["items"])


async def test_published_rundown_is_stable_source(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    first = await published_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 15, 10, 19, tzinfo=PARIS),
    )
    second = await published_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 15, 10, 19, tzinfo=PARIS),
    )
    assert first["programming_version"] == second["programming_version"]
    assert [item["id"] for item in first["items"]] == [
        item["id"] for item in second["items"]
    ]
    assert {item["kind"] for item in first["items"]} == {
        item["kind"] for item in second["items"]
    }


async def test_tick_records_commands_and_survives_restart(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    client = _client()
    live = _live(
        JOURNEE_20,
        remaining="180",
        next_jingle={"rid": 1},
        next_autodj={"rid": 1},
        jingles_queued=2,
        autodj_queued=3,
    )
    actions = await tick(dbsession, live, client, beets_integration)
    assert "anchor:20" in actions
    commands = list(await dbsession.scalars(select(PlayoutCommand)))
    assert commands
    assert commands[0].status == CommandStatus.ACKNOWLEDGED.value
    items = list(await dbsession.scalars(select(RundownItem)))
    assert items
    assert any(item.cart_id == pubs_cart.id for item in items)

    reset_state()
    client2 = _client()
    again = await tick(dbsession, live, client2, beets_integration)
    assert "anchor:20" not in again
    client2.post.assert_not_called()
    stored = await Setting.from_key(dbsession, SETTING_FIRED_ANCHORS)
    assert stored is not None
    assert "20" in stored.value


async def test_outbox_does_not_resend_acknowledged(
    dbsession: ormSession,
    jingles_cart,
):
    from radiotomate.scheduler.execution import record_live_item

    item = await record_live_item(
        dbsession,
        payload={
            "at": datetime.now().isoformat(),
            "kind": "jingle",
            "when": "sequential",
            "queue": "jingles",
            "resource": "ID BUTTON",
            "path": "/tmp/id.mp3",
            "duration": 8,
        },
    )
    payload = {"path": "/tmp/id.mp3", "radiotomate_sound_id": 1}
    first = await enqueue_command(
        dbsession,
        action="queue",
        queue="jingles",
        payload=payload,
        item=item,
    )
    second = await enqueue_command(
        dbsession,
        action="queue",
        queue="jingles",
        payload=payload,
        item=item,
    )
    assert first.id == second.id
    client = _client()
    gateway = PlayoutGateway(client, max_attempts=1)
    result = await dispatch_command(dbsession, first, gateway)
    assert result.ok
    client.post.assert_called_once()
    again = await dispatch_command(dbsession, first, gateway)
    assert again.ok
    assert client.post.call_count == 1


async def test_playout_gateway_retries_transient():
    client = AsyncMock()
    client.post = AsyncMock(
        side_effect=[
            httpx.ConnectError("down"),
            httpx.Response(200, json={"ok": 1}),
        ]
    )
    gateway = PlayoutGateway(client, max_attempts=3, backoff=(0, 0))
    result = await gateway.queue("autodj", {"path": "/tmp/a.mp3"})
    assert result.ok
    assert result.attempts == 2
    assert client.post.call_count == 2


async def test_playout_gateway_keeps_its_retries_for_the_clock():
    client = AsyncMock()
    client.post = AsyncMock(
        side_effect=[httpx.ReadTimeout(""), httpx.Response(200, json={"ok": 1})]
    )
    gateway = PlayoutGateway(client, max_attempts=3, backoff=(0, 0))
    result = await gateway.queue("autodj", {"path": "/tmp/a.mp3"})
    assert (result.ok, result.attempts) == (True, 2)


async def test_gesture_gateway_sends_an_order_once():
    client = AsyncMock()
    client.delete = AsyncMock(side_effect=httpx.ReadTimeout(""))
    client.post = AsyncMock(
        side_effect=[httpx.ConnectTimeout(""), httpx.Response(500, json={})]
    )
    gateway = PlayoutGateway(client, once=True, backoff=(0, 0))
    skipped = await gateway.skip()
    assert (skipped.ok, skipped.attempts, skipped.error) == (False, 1, "ReadTimeout")
    late = await gateway.queue("carts", {"path": "/tmp/a.mp3"})
    assert (late.ok, late.attempts) == (False, 1)
    crashed = await gateway.queue("carts", {"path": "/tmp/a.mp3"})
    assert (crashed.ok, crashed.attempts, crashed.status_code) == (False, 1, 500)
    assert (client.delete.call_count, client.post.call_count) == (1, 2)


async def test_gesture_gateway_tries_a_refused_connection_again():
    client = AsyncMock()
    client.delete = AsyncMock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200)]
    )
    gateway = PlayoutGateway(client, once=True, backoff=(0, 0))
    skipped = await gateway.skip()
    assert (skipped.ok, skipped.attempts) == (True, 2)


async def test_soft_sync_waits_then_fires_without_skip(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    clock = await Clock.from_name(dbsession, "Journée pubs")
    clock = await Clock.from_id(dbsession, clock.id)
    for pos in clock.anchored_positions():
        if pos.minute == 20:
            pos.sync = "molle"
    await dbsession.commit()

    client = _client()
    waiting = await tick(
        dbsession,
        _live(
            JOURNEE_20,
            source="autodj",
            remaining="12",
            next_jingle={"rid": 1},
            next_autodj={"rid": 1},
            jingles_queued=2,
            autodj_queued=3,
        ),
        client,
        beets_integration,
    )
    assert not any(item.startswith("soft:") for item in waiting)
    client.post.assert_not_called()

    ready = await tick(
        dbsession,
        _live(
            "2026-09-14T10:21:00+02:00",
            source="autodj",
            remaining="1",
            next_jingle={"rid": 1},
            next_autodj={"rid": 1},
            jingles_queued=2,
            autodj_queued=3,
        ),
        client,
        beets_integration,
    )
    assert "soft:20" in ready
    assert "skip" not in ready
    assert client.post.call_args.args[0] == "/queue/carts"


async def test_soft_anchor_glides_in_rundown(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    from radiotomate.scheduler.rundown import build_rundown

    clock = await Clock.from_name(dbsession, "Journée pubs")
    clock = await Clock.from_id(dbsession, clock.id)
    for pos in clock.anchored_positions():
        if pos.minute == 20:
            pos.sync = "molle"
    await dbsession.commit()
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 10, 10, tzinfo=PARIS),
        cursor=0,
    )
    soft = [
        item
        for item in data["items"]
        if item.get("when") == "anchored" and item.get("minute") == 20
    ]
    assert soft
    assert soft[0].get("reason") == "glissement"


async def _pub_anchor(
    dbsession: ormSession, sync: str, minute: int = 20
) -> ClockPosition:
    """The 10:20 pub of « Journée pubs », hard or soft, on ``minute``."""
    clock = await Clock.from_name(dbsession, "Journée pubs")
    clock = await Clock.from_id(dbsession, clock.id)
    pos = next(pos for pos in clock.anchored_positions() if pos.minute == 20)
    pos.sync = sync
    pos.minute = minute
    await dbsession.commit()
    return pos


def _planned_for(data: dict, pos: ClockPosition) -> list[dict]:
    return [item for item in data["items"] if item["position_id"] == pos.id]


def _anchor_due(time: str, sync: str) -> dict:
    """
    The antenna as an anchor goes: a hard one cuts a title far from over, a soft
    one has waited for its last second. The queues ask for nothing else.
    """
    return _live(
        time,
        source="autodj",
        remaining="180" if sync == "dure" else "1",
        next_jingle={"rid": 1},
        next_autodj={"rid": 1},
        jingles_queued=2,
        autodj_queued=3,
    )


def _fired(sync: str, minute: int) -> str:
    return f"{'anchor' if sync == 'dure' else 'soft'}:{minute}"


@pytest.mark.parametrize(
    ("sync", "minute", "forecast_at", "planned_at", "ticked_at"),
    [
        ("molle", 20, "10:10", "10:22:16", "10:22:15"),
        ("molle", 20, "10:10", "10:22:16", "10:20:40"),
        ("molle", 20, "10:10", "10:22:16", "10:24:09"),
        ("molle", 22, "10:10", "10:22:16", "10:22:15"),
        ("molle", 58, "10:51", "11:00:16", "10:59:30"),
        ("dure", 20, "10:10", "10:20:00", "10:20:05"),
    ],
    ids=[
        "glissee",
        "titre-plus-court",
        "titre-plus-long",
        "dans-sa-minute",
        "prevue-apres-l-heure",
        "dure",
    ],
)
async def test_anchor_pushes_its_planned_line(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    sync: str,
    minute: int,
    forecast_at: str,
    planned_at: str,
    ticked_at: str,
):
    """
    The antenna pushes the line the conducteur has planned for an anchor, and no
    other sound of the cart beside it. A soft anchor is planned at the end of
    the title astride its minute, « glissement »: past that minute most of the
    time, past the hour now and then, and that title may well end sooner or
    later than planned.
    """
    pos = await _pub_anchor(dbsession, sync, minute)
    data = await ensure_forecast(
        dbsession,
        beets_integration,
        now=datetime.fromisoformat(f"2026-09-14T{forecast_at}").replace(tzinfo=PARIS),
        cursor=0,
    )
    (planned,) = _planned_for(data, pos)
    assert planned["at"] == f"2026-09-14T{planned_at}"

    client = _client()
    live = _anchor_due(f"2026-09-14T{ticked_at}", sync)
    assert _fired(sync, minute) in await tick(
        dbsession, live, client, beets_integration
    )
    assert _pushed_ids(client) == [planned["id"]]
    lines = await dbsession.scalars(
        select(RundownItem).where(RundownItem.clock_position_id == pos.id)
    )
    assert [(line.id, line.status) for line in lines] == [(planned["id"], "in_queue")]


async def _journee_pubs_through_midnight(dbsession: ormSession) -> None:
    """Monday evening and Tuesday morning run « Journée pubs » too."""
    clock = await Clock.from_name(dbsession, "Journée pubs")
    for day, minute in ((0, 18 * 60), (1, 0)):
        slot = await AutoDJSlot.from_time(dbsession, minute, day, exact=True)
        slot.clock_id = clock.id
    await dbsession.commit()


@pytest.mark.parametrize(
    ("hour_before", "next_hour", "through_midnight"),
    [
        ("2026-09-14T10", "2026-09-14T11", False),
        ("2026-09-14T17", "2026-09-14T18", False),
        ("2026-09-14T23", "2026-09-15T00", True),
    ],
    ids=["heure", "changement-de-creneau", "minuit"],
)
async def test_soft_anchor_astride_the_hour_pushes_its_planned_line(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    hour_before: str,
    next_hour: str,
    through_midnight: bool,
):
    """
    A soft anchor waits for the end of the title astride its minute, and that
    title may end past the hour: in the next daypart, on the next day. The
    conducteur plans the anchor there, « glissement », and the antenna pushes
    that line once the title ends.
    """
    pos = await _pub_anchor(dbsession, "molle", 58)
    if through_midnight:
        await _journee_pubs_through_midnight(dbsession)
    data = await ensure_forecast(
        dbsession,
        beets_integration,
        now=datetime.fromisoformat(f"{hour_before}:51").replace(tzinfo=PARIS),
        cursor=0,
    )
    (planned,) = _planned_for(data, pos)
    assert planned["at"] == f"{next_hour}:00:16"

    client = _client()
    waiting = {**_anchor_due(f"{hour_before}:58:30", "molle"), "remaining": "106"}
    assert "soft:58" not in await tick(dbsession, waiting, client, beets_integration)
    live = _anchor_due(f"{next_hour}:00:15", "molle")
    assert "soft:58" in await tick(dbsession, live, client, beets_integration)
    assert _pushed_ids(client) == [planned["id"]]
    assert (await dbsession.get(RundownItem, planned["id"])).status == "in_queue"


@pytest.mark.parametrize(
    ("hour_before", "first_at", "source", "first_action", "then_at"),
    [
        ("14T10", "14T10:59:30", "autodj", "soft:58", "14T11:00:15"),
        ("14T10", "14T11:00:05", "stream", "anchor:58:hold", "14T11:10:15"),
        ("14T23", "14T23:59:00", "stream", "anchor:58:hold", "15T00:10:15"),
    ],
    ids=["passee-dans-son-heure", "retenue-par-un-direct", "retenue-avant-minuit"],
)
async def test_soft_anchor_astride_the_hour_goes_once(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    hour_before: str,
    first_at: str,
    source: str,
    first_action: str,
    then_at: str,
):
    """
    The anchor of the hour before goes once. The title astride it ended before
    the hour: it went then. A live took the antenna, before the hour or past it:
    it held the anchor, and the title that ends after the live does not bring it
    back, on the next day either.
    """
    await _pub_anchor(dbsession, "molle", 58)
    await _journee_pubs_through_midnight(dbsession)
    forecast_at = datetime.fromisoformat(f"2026-09-{hour_before}:51")
    await ensure_forecast(
        dbsession,
        beets_integration,
        now=forecast_at.replace(tzinfo=PARIS),
        cursor=0,
    )
    client = _client()
    first = {**_anchor_due(f"2026-09-{first_at}", "molle"), "source": source}
    assert first_action in await tick(dbsession, first, client, beets_integration)
    pushed = _pushed_ids(client)

    then = _anchor_due(f"2026-09-{then_at}", "molle")
    assert "soft:58" not in await tick(dbsession, then, client, beets_integration)
    assert _pushed_ids(client) == pushed


@pytest.mark.parametrize(
    ("sync", "day", "hour"),
    [("molle", 15, 10), ("molle", 14, 11), ("dure", 15, 10)],
    ids=["molle-veille", "molle-heure-d-avant", "dure-veille"],
)
async def test_anchor_leaves_the_line_of_an_earlier_hour(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    sync: str,
    day: int,
    hour: int,
):
    """
    A line planned for the same anchor the day before, or the hour before, never
    went: the scheduler was stopped, say. It is not the line of this hour: the
    antenna pushes its own. More than an hour past, it never goes: it closes,
    « heure passée ».
    """
    planned_at, ticked_at = ("20:00", "20:05") if sync == "dure" else ("22:16", "22:15")
    pos = await _pub_anchor(dbsession, sync)
    lines = []
    for now in (MONDAY_1010, datetime(2026, 9, day, hour, 10, tzinfo=PARIS)):
        data = await ensure_forecast(dbsession, beets_integration, now=now, cursor=0)
        lines += _planned_for(data, pos)
    earlier, planned = lines
    assert earlier["at"] == f"2026-09-14T10:{planned_at}"
    assert planned["at"] == f"2026-09-{day}T{hour}:{planned_at}"

    client = _client()
    live = _anchor_due(f"2026-09-{day}T{hour}:{ticked_at}", sync)
    assert _fired(sync, 20) in await tick(dbsession, live, client, beets_integration)
    assert _pushed_ids(client) == [planned["id"]]
    line = await dbsession.get(RundownItem, earlier["id"])
    if day == 14:
        # The hour before, 10:22:16 at 11:22:15: not quite an hour past.
        assert line.status == "planned"
    else:
        assert (line.status, line.reason) == ("skipped", "heure passée")


@pytest.mark.parametrize(
    ("sync", "forecast_at", "moved_to", "ticked_at"),
    [
        ("molle", (10, 21), 20, "10:22:15"),
        ("dure", (10, 20, 30), 20, "10:20:40"),
        ("dure", (10, 10), 50, "10:50:05"),
    ],
    ids=["prevision-apres-la-minute", "ligne-une-heure-apres-pile", "ancre-deplacee"],
)
async def test_anchor_without_a_line_of_its_own_draws_from_its_cart(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    sync: str,
    forecast_at: tuple[int, ...],
    moved_to: int,
    ticked_at: str,
):
    """
    Nothing is planned for this occurrence of the anchor: the forecast started
    past its minute, or the anchor went to another minute after the forecast.
    The lines of the hours to come, were it one hour later to the second, or of
    the minute it has left, are not its own: they stay planned, and the antenna
    draws a sound from the cart, as it does with no forecast at all.
    """
    pos = await _pub_anchor(dbsession, sync)
    data = await ensure_forecast(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, *forecast_at, tzinfo=PARIS),
        horizon_min=120,
        cursor=0,
    )
    others = [item["id"] for item in _planned_for(data, pos)]
    assert others
    pos.minute = moved_to
    await dbsession.commit()

    client = _client()
    live = _anchor_due(f"2026-09-14T{ticked_at}", sync)
    assert _fired(sync, moved_to) in await tick(
        dbsession, live, client, beets_integration
    )
    (pushed,) = _pushed_ids(client)
    assert pushed not in others
    lines = await dbsession.scalars(
        select(RundownItem).where(RundownItem.id.in_(others))
    )
    assert {line.status for line in lines} == {"planned"}


@pytest.mark.parametrize(
    "ticked_at", ["10:24:59", "10:12:05"], ids=["fin-prevue", "titre-ecourte"]
)
async def test_soft_anchor_glides_as_far_as_the_title_astride(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    ticked_at: str,
):
    """
    A fifteen-minute title astride the minute of a soft anchor: its line is
    planned thirteen minutes past that minute. It is still the one the antenna
    pushes, at the end of the title, or as soon as « Suivant » cuts it short.
    """
    astride = await dbsession.scalar(
        select(Sound).where(Sound.cart_id == jingles_cart.id)
    )
    astride.duration = 900
    pos = await _pub_anchor(dbsession, "molle", 12)
    data = await ensure_forecast(
        dbsession, beets_integration, now=MONDAY_1010, cursor=0
    )
    (planned,) = _planned_for(data, pos)
    assert planned["at"] == "2026-09-14T10:25:00"

    client = _client()
    live = _anchor_due(f"2026-09-14T{ticked_at}", "molle")
    assert "soft:12" in await tick(dbsession, live, client, beets_integration)
    assert _pushed_ids(client) == [planned["id"]]


async def test_as_run_links_rundown_item(
    dbsession: ormSession,
    jingles_cart,
    beets_integration: BeetsIntegration,
):
    from radiotomate.scheduler.execution import reconcile_as_run

    await tick(dbsession, _live(NIGHT), _client(), beets_integration)
    item = await dbsession.scalar(select(RundownItem).limit(1))
    assert item is not None
    log = MetadataLog(
        on_air=datetime.now(),
        source="autodj",
        title=item.resource.split(" — ")[-1],
        artist="",
        album="",
        extra={"radiotomate_item_id": item.id},
    )
    log.rundown_item_id = item.id
    dbsession.add(log)
    await reconcile_as_run(dbsession, log)
    await dbsession.commit()
    refreshed = await RundownItem.from_id(dbsession, item.id)
    assert refreshed.status == "on_air"
    assert log.rundown_item_id == item.id


async def test_ensure_forecast_keeps_ids_across_calls(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    now = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
    first = await ensure_forecast(
        dbsession,
        beets_integration,
        now=now,
        cursor=0,
    )
    second = await ensure_forecast(
        dbsession,
        beets_integration,
        now=now,
        cursor=0,
    )
    assert first["items"]
    assert [item["id"] for item in first["items"]] == [
        item["id"] for item in second["items"]
    ]
    assert [item["path"] for item in first["items"]] == [
        item["path"] for item in second["items"]
    ]


async def test_tick_pushes_persisted_rundown_path(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    now = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
    data = await ensure_forecast(
        dbsession,
        beets_integration,
        now=now,
        cursor=0,
    )
    music = next(
        item
        for item in data["items"]
        if item.get("kind") == "musique" and item.get("path")
    )
    client = _client()
    await tick(
        dbsession,
        _live(
            NIGHT,
            remaining="180",
            next_jingle={"rid": 1},
            next_autodj={"rid": -1},
            jingles_queued=2,
            autodj_queued=0,
        ),
        client,
        beets_integration,
    )
    autodj_paths = [
        call.kwargs["json"]["path"]
        for call in client.post.call_args_list
        if call.args[0] == "/queue/autodj"
    ]
    assert autodj_paths
    assert autodj_paths[0] == music["path"]


async def test_reset_conducteur_rebuilds_ids(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    now = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
    first = await ensure_forecast(
        dbsession,
        beets_integration,
        now=now,
        cursor=0,
    )
    first_ids = {item["id"] for item in first["items"]}
    payload = await reset_conducteur(dbsession, beets_integration)
    second_ids = {item["id"] for item in payload["items"]}
    assert first_ids
    assert payload["action"] == "reset"
    assert first_ids.isdisjoint(second_ids)


async def test_reset_conducteur_rebuilds_when_on_air_is_hours_ahead(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """A planned_at six hours ahead must not count as coverage."""
    from datetime import timedelta

    from radiotomate.scheduler.timing import now_paris

    now = datetime(2026, 9, 14, 10, 0, tzinfo=PARIS)
    payload = await ensure_forecast(
        dbsession,
        beets_integration,
        now=now,
        cursor=0,
    )
    item_id = next(item["id"] for item in payload["items"])
    row = await RundownItem.from_id(dbsession, item_id)
    assert row is not None
    started = datetime(2026, 9, 28, 13, 40)
    row.status = "on_air"
    row.started_at = started
    row.planned_at = started + timedelta(hours=6)
    later_id = next(item["id"] for item in payload["items"] if item["id"] != item_id)
    later = await RundownItem.from_id(dbsession, later_id)
    assert later is not None
    later.status = "played"
    later.planned_at = started + timedelta(hours=6, minutes=4)
    later.closed_at = started
    await dbsession.commit()

    rebuilt = await reset_conducteur(dbsession, beets_integration)
    wall = now_paris().replace(tzinfo=None)
    planned = [
        datetime.fromisoformat(item["at"]).replace(tzinfo=None)
        for item in rebuilt["items"]
        if item.get("status_code") != "played"
    ]
    assert planned
    deltas = [(at - wall).total_seconds() for at in planned]
    assert any(abs(delta) < 30 * 60 for delta in deltas)
    assert all(delta < 2 * 3600 for delta in deltas)


@contextmanager
def _in_the_interface():
    """
    « Reconstruire le conducteur » runs in the interface's process, whose memory
    has never ticked. The scheduler keeps its own, and reads the base again at
    its next tick, once it sees that the epoch has changed.
    """
    scheduler = copy.deepcopy(vars(clock_state))
    reset_state()
    try:
        yield
    finally:
        for name, value in scheduler.items():
            setattr(clock_state, name, value)


async def _rebuild(
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
    time: str,
    *,
    elsewhere: bool = True,
) -> None:
    """« Reconstruire le conducteur » at ``time``."""
    moment = datetime.fromisoformat(time)

    def at(now=None):
        return timing.now_paris(moment if now is None else now)

    with (
        patch("radiotomate.scheduler.clock.now_paris", side_effect=at),
        patch("radiotomate.scheduler.execution.now_paris", side_effect=at),
        _in_the_interface() if elsewhere else nullcontext(),
    ):
        await reset_conducteur(dbsession, beets_integration)


def _carts_pushed(client: AsyncMock) -> list[str]:
    return [
        call.kwargs["json"]["path"]
        for call in client.post.call_args_list
        if call.args[0] == "/queue/carts"
    ]


@pytest.mark.parametrize("elsewhere", [True, False], ids=["interface", "scheduler"])
async def test_a_rebuild_does_not_play_a_break_gone_again(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    elsewhere: bool,
):
    """
    The break of 10:20 goes with the first spot, and the conducteur is rebuilt
    in that same minute: the tick of 10:20:35 does not draw it again, with the
    second spot. The break of 10:40 has it.
    """
    spots = await _spots(dbsession, pubs_cart, 3)
    pubs_cart.mode = CartMode.PLAYLIST_LOOP
    await dbsession.commit()
    aired = [await _pub_break(dbsession, beets_integration, f"{MONDAY}T10:20:05+02:00")]
    await _rebuild(
        dbsession, beets_integration, f"{MONDAY}T10:20:30+02:00", elsewhere=elsewhere
    )
    client = _client()
    time = f"{MONDAY}T10:20:35+02:00"
    with _clock_at(time):
        actions = await tick(dbsession, _music_on_air(time), client, beets_integration)
    assert "anchor:20" not in actions
    assert _carts_pushed(client) == []
    aired.append(
        await _pub_break(dbsession, beets_integration, f"{MONDAY}T10:40:05+02:00")
    )
    assert aired == [spots[0].title, spots[1].title]


@pytest.mark.parametrize(
    ("first_at", "source", "due", "first_action"),
    [
        ("10:22:15", "autodj", "molle", "soft:20"),
        ("10:22:15", "stream", "molle", "anchor:20:hold"),
        ("10:40:05", "autodj", "dure", "soft-skip:20"),
    ],
    ids=["partie", "retenue-par-un-direct", "sautee-apres-une-dure"],
)
async def test_a_rebuild_does_not_bring_back_a_soft_break_of_the_hour(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    first_at: str,
    source: str,
    due: str,
    first_action: str,
):
    """
    The soft break of 10:20 went at the end of the title astride it, or a live
    held it, or it still waited for a long title when the hard break of 10:40
    went, which skipped it. The conducteur is rebuilt at 10:45: the title that
    ends at 10:48 does not bring the break back.
    """
    await _pub_anchor(dbsession, "molle")
    await ensure_forecast(dbsession, beets_integration, now=MONDAY_1010, cursor=0)
    client = _client()
    time = f"{MONDAY}T{first_at}+02:00"
    first = {**_anchor_due(time, due), "source": source}
    with _clock_at(time):
        assert first_action in await tick(dbsession, first, client, beets_integration)
    pushed = _carts_pushed(client)
    await _rebuild(dbsession, beets_integration, f"{MONDAY}T10:45:00+02:00")
    time = f"{MONDAY}T10:48:00+02:00"
    with _clock_at(time):
        actions = await tick(
            dbsession, _anchor_due(time, "molle"), client, beets_integration
        )
    assert "soft:20" not in actions
    assert _carts_pushed(client) == pushed


async def test_a_soft_break_still_owed_goes_once_after_a_rebuild(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """
    The soft break of 10:20 still waits for the end of a long title when the
    conducteur is rebuilt, at 10:21: it is owed all the same, and goes once,
    when the title ends.
    """
    await _pub_anchor(dbsession, "molle")
    await ensure_forecast(dbsession, beets_integration, now=MONDAY_1010, cursor=0)
    client = _client()
    waiting = {**_anchor_due(f"{MONDAY}T10:20:40+02:00", "molle"), "remaining": "106"}
    assert "soft:20" not in await tick(dbsession, waiting, client, beets_integration)
    await _rebuild(dbsession, beets_integration, f"{MONDAY}T10:21:00+02:00")
    fired = []
    for second in ("22:30", "22:40"):
        time = f"{MONDAY}T10:{second}+02:00"
        with _clock_at(time):
            actions = await tick(
                dbsession, _anchor_due(time, "molle"), client, beets_integration
            )
        fired.append("soft:20" in actions)
    assert fired == [True, False]
    assert len(_carts_pushed(client)) == 1


def test_now_from_live_keeps_the_paris_wall_clock():
    from radiotomate.scheduler.timing import now_from_live

    parsed = now_from_live({"time": "2026-09-28T13:50:48+0100"})
    assert parsed.hour == 13
    assert parsed.minute == 50
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 2 * 3600


async def test_as_run_realigns_following_items(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """The item going on air takes the real start; later sequential items slide."""
    from datetime import timedelta

    from radiotomate.scheduler.execution import reconcile_as_run

    now = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
    payload = await ensure_forecast(dbsession, beets_integration, now=now, cursor=0)
    ids = [item["id"] for item in payload["items"] if item.get("origin") != "desk"]
    assert len(ids) >= 3
    first = await RundownItem.from_id(dbsession, ids[0])
    second = await RundownItem.from_id(dbsession, ids[1])
    before_first = first.planned_at
    before_second = second.planned_at

    late = before_first + timedelta(minutes=7)  # antenna is 7 min behind the plan
    log = MetadataLog(
        on_air=late,
        source="autodj",
        title=first.resource.split(" — ")[-1],
        artist="",
        album="",
        extra={"radiotomate_item_id": first.id},
    )
    dbsession.add(log)
    await reconcile_as_run(dbsession, log)
    await dbsession.commit()

    first = await RundownItem.from_id(dbsession, ids[0])
    second = await RundownItem.from_id(dbsession, ids[1])
    assert first.status == "on_air"
    assert first.planned_at == late
    assert second.planned_at == before_second + timedelta(minutes=7)


async def test_ensure_forecast_ignores_failed_coverage(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """A window full of failed pushes must be re-forecast, not treated as covered."""
    from sqlalchemy import update

    now = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
    await ensure_forecast(dbsession, beets_integration, now=now, cursor=0)
    await dbsession.execute(update(RundownItem).values(status="failed"))
    await dbsession.commit()
    payload = await ensure_forecast(dbsession, beets_integration, now=now, cursor=0)
    playable = [i for i in payload["items"] if i.get("status_code") not in {"failed"}]
    assert playable, payload["items"][:2]
    fresh = await dbsession.scalar(
        select(RundownItem).where(RundownItem.status == "planned").limit(1)
    )
    assert fresh is not None


async def test_realign_skips_implausible_shift(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    from datetime import timedelta

    from radiotomate.scheduler.execution import realign_rundown

    now = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
    payload = await ensure_forecast(dbsession, beets_integration, now=now, cursor=0)
    ids = [item["id"] for item in payload["items"] if item.get("origin") != "desk"]
    first = await RundownItem.from_id(dbsession, ids[0])
    second = await RundownItem.from_id(dbsession, ids[1])
    planned_second = second.planned_at
    shift = await realign_rundown(
        dbsession, first, first.planned_at + timedelta(minutes=16)
    )
    assert shift == timedelta(0)
    assert (await RundownItem.from_id(dbsession, ids[1])).planned_at == planned_second


@pytest.fixture
def empty_beets():
    """A Beets library without a title: with no sound in its carts, the station
    has nothing to play."""
    from radiotomate.beets.demo import BeetsMockIntegration

    empty = BeetsMockIntegration()
    for item in list(empty.lib.items()):
        item.remove()
    yield empty
    empty.teardown()


async def test_a_station_with_nothing_to_play_keeps_one_forecast(
    dbsession, empty_beets
):
    """Nothing to play: a draw replaces the lines it knew missing.

    Such a line ("manquant") never counts as runway: such a forecast is drawn
    again once a minute (FON-32), at every tick before. Kept, they piled up: 17
    lines a second on a new station, the scheduler and the interface reading
    more of them at every tick. Here, three minutes of ticks: three draws more.
    """
    start = datetime(2026, 11, 10, 9, 0, 0)
    client = _client()
    counts = []
    first = ids = set()
    for second in range(0, 200, 10):
        live = _live(
            (start + timedelta(seconds=second)).isoformat(),
            source="safe",
            autodj_queued=0,
            jingles_queued=0,
            carts_queued=0,
        )
        await tick(dbsession, live, client, empty_beets)
        ids = set(await dbsession.scalars(select(RundownItem.id)))
        first = first or ids
        counts.append(len(ids))
    statuses = set(await dbsession.scalars(select(RundownItem.status)))
    assert statuses == {"failed"}
    assert ids.isdisjoint(first)
    assert max(counts) < 2 * min(counts), counts
    client.post.assert_not_called()


async def test_a_refused_push_stays_in_the_history(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """A line Liquidsoap refused was sent: a new draw leaves it to the console."""
    from sqlalchemy import update

    now = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
    await ensure_forecast(dbsession, beets_integration, now=now, cursor=0)
    sent = datetime(2026, 9, 14, 0, 30)
    await dbsession.execute(
        update(RundownItem).values(status="failed", sent_at=sent, closed_at=sent)
    )
    await dbsession.commit()
    refused = set(await dbsession.scalars(select(RundownItem.id)))
    await ensure_forecast(dbsession, beets_integration, now=now, cursor=0)
    kept = set(await dbsession.scalars(select(RundownItem.id)))
    assert refused <= kept
    assert kept - refused


# A Tuesday at 9: the station's clock is « 24/24 Rotation habillée », a jingle of
# the cart « Jingles », then three titles.
EMPTY_START = datetime(2026, 11, 10, 9, 0, tzinfo=PARIS)


async def _forecast_ids(session, beets, now, **kwargs) -> set[str]:
    payload = await ensure_forecast(session, beets, now=now, **kwargs)
    return {item["id"] for item in payload["items"]}


async def test_two_ticks_a_second_apart_keep_a_forecast_of_missing_lines(
    dbsession, empty_beets
):
    """The second tick keeps the forecast the first one drew (FON-32).

    Nothing to play: the forecast is only lines it knows missing. Drawn again at
    every tick, a second apart, it cost the scheduler of a new station a draw a
    second, for nothing.
    """
    client = _client()
    ids = []
    for second in (0, 1):
        moment = EMPTY_START + timedelta(seconds=second)
        live = _live(
            moment.replace(tzinfo=None).isoformat(),
            source="safe",
            autodj_queued=0,
            jingles_queued=0,
            carts_queued=0,
        )
        await tick(dbsession, live, client, empty_beets)
        ids.append(set(await dbsession.scalars(select(RundownItem.id))))
    assert ids[0]
    assert ids[1] == ids[0]
    assert set(await dbsession.scalars(select(RundownItem.status))) == {"failed"}


async def test_a_forecast_of_missing_lines_is_drawn_again_after_a_minute(
    dbsession, empty_beets
):
    """Whatever the mark misses, a forecast of missing lines lasts a minute."""
    first = await _forecast_ids(dbsession, empty_beets, EMPTY_START)
    later = EMPTY_START + MISSING_FORECAST_HOLD
    held = await _forecast_ids(dbsession, empty_beets, later - timedelta(seconds=1))
    drawn = await _forecast_ids(dbsession, empty_beets, later)
    assert first
    assert held == first
    assert drawn
    assert drawn.isdisjoint(first)


async def test_a_title_added_to_beets_is_planned_at_the_next_tick(
    dbsession, empty_beets
):
    """A first title ends the wait at once: no later than the delay, as the fiche
    asks (FON-32). It waits only for Beets to take it."""
    await ensure_forecast(dbsession, empty_beets, now=EMPTY_START)
    title = empty_beets.helper.add_item(
        artist="Première Venue",
        title="Premier titre",
        grouping="rotation",
        path="/media/10-rotation/premier-titre.mp3",
    )
    payload = await ensure_forecast(
        dbsession, empty_beets, now=EMPTY_START + timedelta(seconds=1)
    )
    planned = [item for item in payload["items"] if item["status_code"] == "planned"]
    assert planned
    assert {item["beets_id"] for item in planned} == {title.id}


async def test_a_sound_ready_in_a_cart_ends_the_wait(raw_app, dbsession, empty_beets):
    """The cart of the clock is there, its sound not analysed yet: the forecast
    holds, a session a call as on a station, though each draw loads the cart
    with its sounds, which bumped its version before FON-45. The analyser gives
    the sound its gain: the jingle is planned at the next call."""
    cartpath = raw_app.config["DATA_ROOT"] / "jingles"
    cart = Cart(
        title="Jingles",
        path=cartpath,
        mode=CartMode.RANDOM,
        schedule_mode=ScheduleMode.JINGLES,
    )
    dbsession.add(cart)
    await dbsession.flush()
    sound = Sound(
        cart_id=cart.id,
        path=cartpath / "id-button.mp3",
        duration=8,
        title="ID BUTTON",
        gain=None,
        peak=None,
    )
    dbsession.add(sound)
    await dbsession.commit()
    sessions = raw_app.extensions["sqlalchemy"].session

    async def call(second: int) -> list[dict]:
        async with sessions() as session:
            payload = await ensure_forecast(
                session, empty_beets, now=EMPTY_START + timedelta(seconds=second)
            )
        return payload["items"]

    first = await call(0)
    assert {item["status_code"] for item in first} == {"failed"}
    assert [item["id"] for item in await call(1)] == [item["id"] for item in first]
    sound.gain = -1.0
    sound.peak = -0.5
    await dbsession.commit()
    planned = [item for item in await call(2) if item["status_code"] == "planned"]
    assert planned
    assert {item["kind"] for item in planned} == {"jingle"}


async def test_a_clock_edit_ends_the_wait(dbsession, empty_beets):
    """An edit of the motif is drawn at the next tick, without waiting a minute."""
    first = await _forecast_ids(dbsession, empty_beets, EMPTY_START)
    position = await dbsession.scalar(
        select(ClockPosition).where(ClockPosition.kind == "musique").limit(1)
    )
    position.kind = "jingle"
    position.cart_title = "Jingles"
    await dbsession.commit()
    drawn = await _forecast_ids(
        dbsession, empty_beets, EMPTY_START + timedelta(seconds=1)
    )
    assert drawn
    assert drawn.isdisjoint(first)


async def test_the_six_hours_of_the_console_hold_for_the_tick(dbsession, empty_beets):
    """The tick asks for 30 minutes, the console for six hours, every 3 s: the
    console draws again what reaches too short, then both keep it."""
    tick_ids = await _forecast_ids(dbsession, empty_beets, EMPTY_START)
    console_at = EMPTY_START + timedelta(seconds=1)
    console = await ensure_forecast(
        dbsession, empty_beets, now=console_at, horizon_min=360
    )
    console_ids = {item["id"] for item in console["items"]}
    assert console_ids.isdisjoint(tick_ids)
    last = max(datetime.fromisoformat(item["at"]) for item in console["items"])
    assert last.replace(tzinfo=PARIS) >= console_at + timedelta(hours=6)
    again = EMPTY_START + timedelta(seconds=2)
    assert await _forecast_ids(dbsession, empty_beets, again) == console_ids
    assert (
        await _forecast_ids(
            dbsession,
            empty_beets,
            again + timedelta(seconds=2),
            horizon_min=360,
        )
        == console_ids
    )


async def test_a_grid_with_hours_off_air_keeps_its_forecast(dbsession, empty_beets):
    """Six hours asked on an evening before a night without a slot: the lines end
    at midnight, short of the horizon for good, and the forecast holds all the
    same."""
    from sqlalchemy import delete

    await dbsession.execute(delete(AutoDJSlot).where(AutoDJSlot.day_of_week == 2))
    await dbsession.commit()
    evening = datetime(2026, 11, 10, 21, 0, tzinfo=PARIS)
    first = await _forecast_ids(dbsession, empty_beets, evening, horizon_min=360)
    again = await _forecast_ids(
        dbsession, empty_beets, evening + timedelta(seconds=3), horizon_min=360
    )
    assert first
    assert again == first


async def test_a_reset_draws_a_held_forecast_again(dbsession, empty_beets):
    """« Reconstruire le conducteur » clears the lines: the forecast is drawn again
    at once, not left empty for the rest of the minute."""
    first = await _forecast_ids(dbsession, empty_beets, EMPTY_START)
    await clear_live_forecast(dbsession)
    await dbsession.commit()
    drawn = await _forecast_ids(
        dbsession, empty_beets, EMPTY_START + timedelta(seconds=1)
    )
    assert drawn
    assert drawn.isdisjoint(first)


# What Liquidsoap posts when nothing plays: the blank of `programs`, which it says
# « autodj », no end to wait for, nothing in the queues.
IDLE_LIVE = _live(
    EMPTY_START.replace(tzinfo=None).isoformat(),
    source="autodj",
    autodj_queued=0,
    jingles_queued=0,
    carts_queued=0,
)


@pytest.fixture
def tick_gate():
    """The scheduler's tick gate, fresh, and left fresh for the tests after."""
    sched_live.reset_tick_gate()
    yield
    sched_live.reset_tick_gate()


async def _gate_after_a_tick(session, beets) -> list[bool]:
    """The tick gate for the heartbeats after a tick that read the forecast: the
    next second, four seconds on, then once the idle interval is past."""
    since = monotonic()
    await ensure_forecast(session, beets, now=EMPTY_START)
    await sched_live.note_nothing_to_play(session, since=since)
    return [
        sched_live.should_run_tick(IDLE_LIVE, now=now)
        for now in (100.0, 101.0, 104.0, 100.0 + sched_live.TICK_MAX_IDLE_SECONDS)
    ]


async def test_the_tick_of_a_station_with_nothing_to_play_waits(
    dbsession, empty_beets, tick_gate
):
    """Nothing plays, and the clock has nothing to push (FON-32): the tick no longer
    runs every second for an end that will not come. A change of the antenna, or
    the idle interval, runs it, as in the middle of a title."""
    assert await _gate_after_a_tick(dbsession, empty_beets) == [
        True,
        False,
        False,
        True,
    ]
    assert sched_live.should_run_tick({**IDLE_LIVE, "autodj_queued": 1}, now=106.0)


async def test_the_tick_keeps_its_pace_with_the_switch_off(
    dbsession, empty_beets, tick_gate
):
    await Setting.upsert(dbsession, sched_live.SETTING_QUIET_TICK, "false")
    await dbsession.commit()
    assert await _gate_after_a_tick(dbsession, empty_beets) == [True] * 4


async def test_the_tick_keeps_its_pace_when_there_is_something_to_play(
    dbsession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    tick_gate,
):
    """Titles to play: nothing playing is a queue to fill, every second."""
    assert await _gate_after_a_tick(dbsession, beets_integration) == [True] * 4


async def test_the_tick_waits_only_on_the_forecast_it_read(
    dbsession, empty_beets, tick_gate
):
    """A tick that did not read the forecast, held by a live for instance, keeps
    its pace: an earlier reading says nothing of now."""
    await ensure_forecast(dbsession, empty_beets, now=EMPTY_START)
    await sched_live.note_nothing_to_play(dbsession, since=monotonic())
    assert sched_live.should_run_tick(IDLE_LIVE, now=100.0)
    assert sched_live.should_run_tick(IDLE_LIVE, now=101.0)


async def test_the_scheduler_quiets_its_gate_after_a_tick_with_nothing_to_play(
    raw_app, empty_beets, tick_gate
):
    """The tick runner reads what its own tick found (live._run_sequencer): the
    gate stops watching for an end, but a title that plays keeps its end watched,
    a cart sent by hand for instance."""
    raw_app.extensions[BeetsIntegration.EXTENSION_NAME] = empty_beets
    async with raw_app.app_context():
        await sched_live._run_sequencer(IDLE_LIVE)
    assert sched_live.should_run_tick(IDLE_LIVE, now=100.0)
    assert not sched_live.should_run_tick(IDLE_LIVE, now=101.0)
    playing = {**IDLE_LIVE, "source": "carts", "title": "ID BUTTON", "remaining": "7"}
    assert sched_live.should_run_tick(playing, now=102.0)
    assert sched_live.should_run_tick(playing, now=103.0)
