from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import CartMode, ScheduleMode
from radiotomate.models import (
    AutoDJSlot,
    Cart,
    Clock,
    RundownItem,
    Setting,
    Sound,
    User,
)
from radiotomate.scheduler.clock import (
    PARIS,
    SETTING_CLOCK_SEQ_CLOCK_ID,
    SETTING_CLOCK_SEQ_CURSOR,
    load_sequencer_cursor,
    reset_sequencer,
    restore_sequencer_state,
    tick,
)
from radiotomate.scheduler.rundown import (
    MAX_HORIZON_MIN,
    build_rundown,
    forecast_still_covers,
    item_end_at,
    rest_of_day_minutes,
)
from radiotomate.services.autodj import create_clock
from tests.scheduler.test_clock import NIGHT, _client, _live

TUESDAY_1019 = datetime(2026, 9, 15, 10, 19, tzinfo=PARIS)
MONDAY_1010 = datetime(2026, 9, 14, 10, 10, tzinfo=PARIS)
MONDAY_1819 = datetime(2026, 9, 14, 18, 19, tzinfo=PARIS)
SATURDAY_2200 = datetime(2026, 9, 19, 22, 0, tzinfo=PARIS)
SUNDAY_0000 = datetime(2026, 9, 20, 0, 0, tzinfo=PARIS)


def test_rest_of_day_minutes_until_midnight():
    morning = datetime(2026, 9, 15, 10, 0, tzinfo=PARIS)
    assert rest_of_day_minutes(morning) == 14 * 60
    late = datetime(2026, 9, 15, 23, 0, tzinfo=PARIS)
    assert rest_of_day_minutes(late) == 4 * 60
    assert rest_of_day_minutes(morning) <= MAX_HORIZON_MIN


def test_forecast_still_covers_until_the_tail_elapses():
    now = datetime(2026, 9, 20, 13, 0, tzinfo=PARIS)
    payload = {
        "items": [
            {"at": now.isoformat(), "duration": 81},
            {"at": (now + timedelta(seconds=81)).isoformat(), "duration": 81},
        ]
    }
    assert forecast_still_covers(payload, now, min_ahead_min=1)
    assert not forecast_still_covers(
        payload,
        now + timedelta(minutes=5),
        min_ahead_min=1,
    )
    assert not forecast_still_covers({"items": []}, now)


async def test_conducteur_json_keeps_times_across_polls(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    user = User(username="conducteur-stable")
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()

    from radiotomate.interface_app import app_factory as interface_factory

    iface = interface_factory(app_configration, False, beets_integration)
    iface.config["INTERFACE_NAME"] = "BUTTON"
    client = iface.test_client()
    login = await client.post(
        "/login",
        form={"username": "conducteur-stable", "password": users_password},
    )
    assert login.status_code == 302
    first = await (await client.get("/autodj/conducteur.json")).get_json()
    assert first["items"]
    second = await (await client.get("/autodj/conducteur.json")).get_json()
    assert [item["id"] for item in first["items"][:8]] == [
        item["id"] for item in second["items"][:8]
    ]
    assert [item["at"] for item in first["items"][:8]] == [
        item["at"] for item in second["items"][:8]
    ]
    assert [item["resource"] for item in first["items"][:8]] == [
        item["resource"] for item in second["items"][:8]
    ]


def _anchored_pubs(items: list[dict], minute: int = 20) -> list[dict]:
    return [
        item
        for item in items
        if item.get("kind") == "pub"
        and item.get("when") == "anchored"
        and item.get("minute") == minute
    ]


async def test_tick_persists_cursor(
    dbsession: ormSession,
    jingles_cart,
    beets_integration: BeetsIntegration,
):
    await tick(dbsession, _live(NIGHT), _client(), beets_integration)
    cursor_row = await Setting.from_key(dbsession, SETTING_CLOCK_SEQ_CURSOR)
    clock_row = await Setting.from_key(dbsession, SETTING_CLOCK_SEQ_CLOCK_ID)
    assert cursor_row is not None
    assert int(cursor_row.value) >= 2
    assert clock_row is not None
    assert clock_row.value.isdigit()


async def test_rundown_pub_at_1020_tuesday(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=TUESDAY_1019,
        cursor=0,
    )
    pubs = _anchored_pubs(data["items"], 20)
    assert pubs, data["items"][:8]
    first = pubs[0]
    at = datetime.fromisoformat(first["at"])
    assert at.hour == 10
    assert at.minute == 20
    assert first["queue"] == "carts"
    assert first["status"] == "prévu"
    assert first["clock"] == "Journée pubs"


async def test_rundown_no_pub_at_1819(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=MONDAY_1819,
        cursor=0,
    )
    assert _anchored_pubs(data["items"], 20) == []


async def test_rundown_short_daypart_skips_1020_pub(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    clock = await dbsession.scalar(
        select(Clock).filter(Clock.name == "24/24 Rotation habillée")
    )
    dbsession.add(
        AutoDJSlot(
            day_of_week=0,
            minute=10 * 60 + 15,
            clock_id=clock.id,
            title="court",
            constraints={},
        ),
    )
    await dbsession.commit()
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=MONDAY_1010,
        cursor=0,
    )
    assert _anchored_pubs(data["items"], 20) == []


def _at(item: dict) -> datetime:
    return datetime.fromisoformat(item["at"])


async def _live_daypart(
    dbsession: ormSession,
    raw_app,
    sync: str,
    opening: datetime = SATURDAY_2200,
) -> None:
    """One hour from ``opening``: a clock that opens on a live drawn from a bin."""
    path = raw_app.config["DATA_ROOT"] / "lives"
    cart = Cart(
        title="Lives",
        path=path,
        mode=CartMode.PLAYLIST,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(cart)
    await dbsession.flush()
    dbsession.add(
        Sound(
            cart_id=cart.id,
            path=path / "live.mp3",
            duration=35 * 60,
            title="Live du samedi",
            gain=-1.0,
            peak=-0.5,
        )
    )
    clock = await create_clock(
        dbsession,
        {
            "name": "Soirée live",
            "motif": [{"kind": "musique", "category": "Rotation"}],
            "anchors": [{"kind": "son", "cart_id": cart.id, "minute": 0, "sync": sync}],
        },
    )
    default = await Clock.from_name(dbsession, Clock.DEFAULT_NAME)
    for start, clock_id in (
        (opening, clock.id),
        (opening + timedelta(hours=1), default.id),
    ):
        minute = start.hour * 60 + start.minute
        slot = await AutoDJSlot.from_time(
            dbsession, minute, start.weekday(), exact=True
        )
        if slot is None:
            slot = AutoDJSlot(
                day_of_week=start.weekday(),
                minute=minute,
                title="live",
                constraints={},
            )
            dbsession.add(slot)
        slot.clock_id = clock_id
    await dbsession.commit()


@pytest.mark.parametrize("sync", ["dure", "molle"])
@pytest.mark.parametrize(
    ("opening", "lead_min", "cursor", "astride"),
    [
        (SATURDAY_2200, 10, 0, True),
        (SATURDAY_2200, 9, 1, False),
        (SUNDAY_0000, 10, 0, True),
    ],
    ids=["titre-a-cheval", "titre-fini-pile", "minuit"],
)
async def test_rundown_plans_the_anchor_a_daypart_opens_on(  # noqa: PLR0913
    dbsession: ormSession,
    raw_app,
    jingles_cart,
    beets_integration: BeetsIntegration,
    sync: str,
    opening: datetime,
    lead_min: int,
    cursor: int,
    astride: bool,
):
    """
    A title runs into the start of a daypart, or ends on it: by then the anchor
    of that minute is behind the forecast, and the antenna still plays it. Hard,
    it cuts the title; soft, it waits for its end.
    """
    await _live_daypart(dbsession, raw_app, sync, opening)
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=opening - timedelta(minutes=lead_min),
        horizon_min=60,
        cursor=cursor,
    )
    items = data["items"]
    title_end = item_end_at([item for item in items if _at(item) < opening][-1])
    assert title_end >= opening
    assert (title_end > opening) is astride
    lives = [item for item in items if item["kind"] == "son"]
    assert len(lives) == 1, [(item["at"], item["resource"]) for item in items[:12]]
    live = lives[0]
    assert _at(live) == (opening if sync == "dure" else title_end)
    assert (live["when"], live["minute"], live["sync"]) == ("anchored", 0, sync)
    assert (live["clock"], live["resource"]) == ("Soirée live", "Live du samedi")
    assert live.get("reason") == ("glissement" if _at(live) > opening else None)
    assert _at(items[items.index(live) + 1]) == item_end_at(live)


@pytest.mark.parametrize("sync", ["dure", "molle"])
async def test_rundown_ending_astride_a_daypart_start_plans_its_anchor(
    dbsession: ormSession,
    raw_app,
    jingles_cart,
    beets_integration: BeetsIntegration,
    sync: str,
):
    """
    The conducteur grows piece by piece, and the piece after this one starts past
    22:00: the one that ends on the title astride has to carry the anchor.
    """
    await _live_daypart(dbsession, raw_app, sync)
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=SATURDAY_2200 - timedelta(minutes=16),
        horizon_min=15,
        cursor=0,
    )
    items = data["items"]
    assert [item for item in items if _at(item) < SATURDAY_2200 < item_end_at(item)]
    assert items[-1]["kind"] == "son", [(item["at"], item["kind"]) for item in items]


async def test_rundown_window_covers_30_min(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=TUESDAY_1019,
        cursor=0,
    )
    assert data["items"]
    last_at = datetime.fromisoformat(data["items"][-1]["at"])
    assert last_at >= TUESDAY_1019 + timedelta(minutes=30)


async def test_rundown_window_covers_three_hours(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=TUESDAY_1019,
        horizon_min=180,
        cursor=0,
    )
    assert data["horizon_min"] == 180
    assert data["items"]
    last_at = datetime.fromisoformat(data["items"][-1]["at"])
    assert last_at >= TUESDAY_1019 + timedelta(minutes=170)


async def test_conducteur_json_authenticated(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    user = User(username="conducteur-json")
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()

    from radiotomate.interface_app import app_factory as interface_factory

    iface = interface_factory(app_configration, False, beets_integration)
    iface.config["INTERFACE_NAME"] = "BUTTON"
    client = iface.test_client()
    login = await client.post(
        "/login",
        form={"username": "conducteur-json", "password": users_password},
    )
    assert login.status_code == 302
    before = await dbsession.scalar(select(func.count()).select_from(RundownItem))
    response = await client.get("/autodj/conducteur.json")
    assert response.status_code == 200
    after = await dbsession.scalar(select(func.count()).select_from(RundownItem))
    assert after > before
    payload = await response.get_json()
    assert payload["horizon_min"] == 30
    assert "items" in payload
    assert "now" in payload
    assert "summary" in payload
    assert "counts" in payload["summary"]
    wide = await client.get("/autodj/conducteur.json?horizon=180")
    assert wide.status_code == 200
    wide_payload = await wide.get_json()
    assert wide_payload["horizon_min"] == 180
    last_at = datetime.fromisoformat(wide_payload["items"][-1]["at"])
    now = datetime.fromisoformat(wide_payload["now"])
    if last_at.tzinfo is not None:
        last_at = last_at.replace(tzinfo=None)
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    assert last_at >= now + timedelta(minutes=120)
    clamped = await client.get("/autodj/conducteur.json?horizon=9999")
    assert (await clamped.get_json())["horizon_min"] == MAX_HORIZON_MIN
    html = await client.get("/autodj/conducteur")
    assert html.status_code == 200
    body = await html.get_data(as_text=True)
    assert "Conducteur" in body
    assert "<th>Cart</th>" in body


async def test_rundown_keeps_missing_clock_carts(
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
):
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 0, 30, tzinfo=PARIS),
        cursor=0,
    )
    jingles = [item for item in data["items"] if item.get("kind") == "jingle"]
    assert jingles, data["items"][:6]
    first = jingles[0]
    assert first["status"] == "manquant"
    assert first["cart"] == "Jingles"
    assert first["reason"] == "cart introuvable"


async def test_rundown_replays_exhausted_playlist_jingles(
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
    jingles_cart,
):
    from radiotomate.enums import CartMode
    from radiotomate.models import Cart

    cart = await Cart.from_id(dbsession, jingles_cart.id, load_sounds=True)
    assert cart is not None
    cart.mode = CartMode.PLAYLIST
    for sound in cart.sounds:
        sound.last_played = datetime.now()
    await dbsession.commit()
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 0, 30, tzinfo=PARIS),
        cursor=0,
    )
    jingles = [item for item in data["items"] if item.get("kind") == "jingle"]
    assert jingles, data["items"][:6]
    first = jingles[0]
    assert first["status"] != "manquant"
    assert first["resource"] == "ID BUTTON"
    assert first.get("reason") != "cart introuvable"


async def test_rundown_keeps_music_slot_when_beets_empty(
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
    jingles_cart,
):
    with patch(
        "radiotomate.scheduler.rundown._pick_music",
        AsyncMock(return_value=None),
    ):
        data = await build_rundown(
            dbsession,
            beets_integration,
            now=datetime(2026, 9, 14, 0, 30, tzinfo=PARIS),
            horizon_min=30,
            cursor=0,
        )
    items = data["items"]
    jingles = [item for item in items if item.get("kind") == "jingle"]
    missing = [
        item
        for item in items
        if item.get("kind") == "musique" and item.get("status") == "manquant"
    ]
    assert missing, items[:8]
    assert jingles
    assert len(jingles) < len(items) / 2
    assert len(jingles) < 40


async def test_rundown_rotates_playlist_jingles(
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
    jingles_cart,
):
    from radiotomate.enums import CartMode
    from radiotomate.models import Sound

    jingles_cart.mode = CartMode.PLAYLIST
    for rank, title in ((2, "Virgule"), (3, "ID nuit")):
        dbsession.add(
            Sound(
                cart_id=jingles_cart.id,
                path=jingles_cart.path / f"{title}.mp3",
                duration=8,
                title=title,
                rank=rank,
                gain=-1.0,
                peak=-0.5,
            )
        )
    await dbsession.commit()
    dbsession.expire(jingles_cart, ["sounds"])
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 0, 30, tzinfo=PARIS),
        horizon_min=60,
        cursor=0,
    )
    names = [
        item.get("resource")
        for item in data["items"]
        if item.get("kind") == "jingle" and item.get("status") != "manquant"
    ]
    assert len(set(names)) >= 2, names[:8]


async def test_reset_sequencer_reloads_after_process_restart(
    dbsession: ormSession,
    jingles_cart,
):
    await Setting.upsert(dbsession, SETTING_CLOCK_SEQ_CURSOR, "12")
    await Setting.upsert(dbsession, SETTING_CLOCK_SEQ_CLOCK_ID, "1")
    await dbsession.commit()
    await reset_sequencer(dbsession)
    from radiotomate.scheduler.clock import reset_state

    reset_state()
    await restore_sequencer_state(dbsession)
    cursor, clock_id = await load_sequencer_cursor(dbsession)
    assert cursor == 0
    assert clock_id is None
