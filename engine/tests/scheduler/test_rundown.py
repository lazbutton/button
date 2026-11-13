from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import CartMode, RundownStatus, ScheduleMode
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
    SETTING_SKIP_OVERTAKEN,
    load_sequencer_cursor,
    reset_sequencer,
    restore_sequencer_state,
    tick,
)
from radiotomate.scheduler.execution import ensure_forecast, record_live_item
from radiotomate.scheduler.rundown import (
    MAX_HORIZON_MIN,
    build_rundown,
    forecast_still_covers,
    item_end_at,
    rest_of_day_minutes,
)
from radiotomate.services.autodj import create_clock
from tests.scheduler.test_cart_draw import (
    _clock_at,
    _conducteur_line,
    _music_on_air,
    _spots,
)
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


async def _spots_in_order(
    dbsession: ormSession,
    cart: Cart,
    mode: CartMode,
    heard: tuple[int, ...] = (),
) -> list[Sound]:
    """
    Three spots a cart plays in order: « Spot test », « Spot 2 », « Spot 3 ».
    ``heard`` are the ranks of those that have played, the oldest first.
    """
    spots = await _spots(dbsession, cart, 3)
    cart.mode = mode
    for minute, rank in enumerate(heard):
        spots[rank - 1].last_played = datetime(2026, 9, 14, 9, minute)
    await dbsession.commit()
    return spots


@pytest.mark.parametrize("mode", [CartMode.PLAYLIST_LOOP, CartMode.PLAYLIST])
async def test_rundown_goes_on_after_the_last_sound_of_an_ordered_cart(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    mode: CartMode,
):
    """
    A cart that plays in order has played all its sounds, the second one last.
    A new forecast goes on with the third, break after break, as the cart does
    when the clock draws from it (``Cart.next_sound``): not with the first again.
    """
    await _spots_in_order(dbsession, pubs_cart, mode, heard=(3, 1, 2))
    forecast = await build_rundown(
        dbsession,
        beets_integration,
        now=MONDAY_1010,
        horizon_min=170,
    )
    planned = [item["title"] for item in forecast["items"] if item["kind"] == "pub"]
    assert planned[:5] == ["Spot 3", "Spot test", "Spot 2", "Spot 3", "Spot test"]
    # The very order of the cart: what it gives, each sound played in its turn.
    cart = await Cart.from_id(dbsession, pubs_cart.id, load_sounds=True)
    drawn = []
    for minute in range(len(planned)):
        sound = cart.next_sound()
        sound.last_played = datetime(2026, 9, 14, 10, minute)
        drawn.append(sound.title)
    assert planned == drawn


@pytest.mark.parametrize(
    ("mode", "heard", "expected"),
    [
        (
            CartMode.PLAYLIST_LOOP,
            (3, 1, 2),
            ["Spot 3", "Spot test", "Spot 2", "Spot 3", "Spot test"],
        ),
        (
            CartMode.PLAYLIST,
            (),
            ["Spot test", "Spot 2", "Spot 3", "Spot test", "Spot 2"],
        ),
    ],
    ids=["boucle", "une-fois-jamais-passee"],
)
async def test_rundown_grown_piece_by_piece_keeps_an_ordered_cart_in_order(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    mode: CartMode,
    heard: tuple[int, ...],
    expected: list[str],
):
    """
    The conducteur grows piece by piece, each one built with nothing in hand.
    A piece goes on after the sounds of the cart the pieces before have planned,
    which have not played yet: it does not plan them again.
    """
    await _spots_in_order(dbsession, pubs_cart, mode, heard=heard)
    for minutes in range(0, 130, 10):
        await ensure_forecast(
            dbsession,
            beets_integration,
            now=MONDAY_1010 + timedelta(minutes=minutes),
            horizon_min=30,
        )
    breaks = await dbsession.scalars(
        select(RundownItem)
        .where(RundownItem.kind == "pub")
        .order_by(RundownItem.planned_at)
    )
    assert [line.resource for line in breaks][:5] == expected


async def test_rundown_goes_on_after_a_sound_sent_and_not_heard_yet(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """
    A spot is on its way to the antenna: the conducteur holds it, whatever the
    cart knows of it, and plans the spot after it, not the same one again.
    """
    spots = await _spots_in_order(
        dbsession, pubs_cart, CartMode.PLAYLIST_LOOP, heard=(1, 2, 3)
    )
    await _conducteur_line(dbsession, spots[0], 0, RundownStatus.SENT)
    forecast = await build_rundown(
        dbsession,
        beets_integration,
        now=MONDAY_1010,
        horizon_min=60,
    )
    planned = [item["title"] for item in forecast["items"] if item["kind"] == "pub"]
    assert planned[:2] == ["Spot 2", "Spot 3"]


@pytest.mark.parametrize("mode", [CartMode.PLAYLIST_LOOP, CartMode.PLAYLIST])
async def test_clock_sends_an_ordered_cart_in_order_break_after_break(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    mode: CartMode,
):
    """
    Each pub break is planned a few minutes ahead, then sent as planned. Three
    spots that play in order are heard in order, round after round: the antenna
    gets what the cart would have given had the clock drawn at each break.
    """
    await _spots_in_order(dbsession, pubs_cart, mode)
    sent: list[str] = []
    for hour in (10, 11, 12):
        for minute in (20, 40):
            client = _client()
            for moment in (f"{minute - 5}:00", f"{minute}:05"):
                await tick(
                    dbsession,
                    _music_on_air(f"2026-09-14T{hour}:{moment}+02:00"),
                    client,
                    beets_integration,
                )
            sent += [
                call.kwargs["json"]["title"]
                for call in client.post.call_args_list
                if call.args[0] == "/queue/carts"
            ]
    assert sent == ["Spot test", "Spot 2", "Spot 3"] * 2


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


MONDAY_11 = datetime(2026, 9, 14, 11, 0, tzinfo=PARIS)
MONDAY_23 = datetime(2026, 9, 14, 23, 0, tzinfo=PARIS)


async def _soft_then_hard(  # noqa: PLR0913
    dbsession: ormSession,
    cart: Cart,
    soft: int,
    hard: int,
    *,
    hard_cart: Cart | None = None,
    dayparts: list[tuple[datetime, bool]] | None = None,
) -> Clock:
    """
    A clock of music with two pub breaks: one that waits for the end of the
    title at ``soft``, one that cuts at ``hard``, from ``hard_cart`` if given.
    It runs in the dayparts that open at the starts marked True, the default
    clock in the others: by default, on Monday from 11:00 to 14:00.
    """
    clock = await create_clock(
        dbsession,
        {
            "name": "Molle puis dure",
            "motif": [{"kind": "musique", "category": "Rotation"}],
            "anchors": [
                {"kind": "pub", "cart_id": cart.id, "minute": soft, "sync": "molle"},
                {
                    "kind": "pub",
                    "cart_id": (hard_cart or cart).id,
                    "minute": hard,
                    "sync": "dure",
                },
            ],
        },
    )
    default = await Clock.from_name(dbsession, Clock.DEFAULT_NAME)
    if dayparts is None:
        dayparts = [(MONDAY_11, True), (MONDAY_11 + timedelta(hours=3), False)]
    for start, mine in dayparts:
        minute = start.hour * 60 + start.minute
        slot = await AutoDJSlot.from_time(
            dbsession, minute, start.weekday(), exact=True
        )
        if slot is None:
            slot = AutoDJSlot(
                day_of_week=start.weekday(), minute=minute, title="t", constraints={}
            )
            dbsession.add(slot)
        slot.clock_id = clock.id if mine else default.id
    await dbsession.commit()
    return clock


def _carts_sent(client: AsyncMock) -> list[str]:
    return [
        call.kwargs["json"]["title"]
        for call in client.post.call_args_list
        if call.args[0] == "/queue/carts"
    ]


def _spot_ends(time: str) -> dict:
    """A spot of the carts queue ends, nothing behind it."""
    return {
        **_music_on_air(time),
        "source": "carts",
        "remaining": "2",
        "next_cart": {"rid": -1},
        "carts_queued": 0,
    }


@pytest.mark.parametrize(
    ("switch", "sent"), [(None, 1), ("0", 2)], ids=["allume", "coupe"]
)
async def test_a_soft_break_overtaken_by_a_hard_one_is_skipped(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    switch: str | None,
    sent: int,
):
    """
    The title on air runs past 11:50 when the soft break of 11:49 comes: the hard
    break of 11:50 cuts it, and the soft one does not go after it, as the
    conducteur says. Switched off, it goes after it, as before.
    """
    await _spots(dbsession, pubs_cart, 3)
    await _soft_then_hard(dbsession, pubs_cart, soft=49, hard=50)
    if switch is not None:
        await Setting.upsert(dbsession, SETTING_SKIP_OVERTAKEN, switch)
        await dbsession.commit()
    client = _client()
    title_runs = {**_music_on_air("2026-09-14T11:49:05+02:00"), "remaining": "300"}
    actions = await tick(dbsession, title_runs, client, beets_integration)
    assert not any(action.startswith("soft") for action in actions)
    cut = {**title_runs, "time": "2026-09-14T11:50:05+02:00", "remaining": "240"}
    actions = await tick(dbsession, cut, client, beets_integration)
    assert "anchor:50" in actions
    assert ("soft-skip:49" in actions) is (switch is None)
    await tick(
        dbsession, _spot_ends("2026-09-14T11:50:30+02:00"), client, beets_integration
    )
    assert len(_carts_sent(client)) == sent


async def test_a_soft_break_astride_the_hour_overtaken_is_skipped(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """
    The conducteur planned the soft break of 11:58 at the end of a title astride
    the hour, but the title ran on: the hard break of 12:00 cuts it first. The
    soft one does not go after it, and its line says so.
    """
    spots = await _spots(dbsession, pubs_cart, 3)
    clock = await _soft_then_hard(dbsession, pubs_cart, soft=58, hard=0)
    soft = next(pos for pos in clock.anchored_positions() if pos.minute == 58)
    await record_live_item(
        dbsession,
        payload={
            "at": datetime(2026, 9, 14, 11, 59, 30, tzinfo=PARIS).isoformat(),
            "kind": "pub",
            "when": "anchored",
            "queue": "carts",
            "resource": spots[1].title,
            "path": str(spots[1].path),
            "clock_id": clock.id,
            "position_id": soft.id,
            "cart_id": pubs_cart.id,
            "sound_id": spots[1].id,
            "minute": 58,
        },
        status=RundownStatus.PLANNED.value,
    )
    await dbsession.commit()
    client = _client()
    cut = {**_music_on_air("2026-09-14T12:00:05+02:00"), "remaining": "240"}
    assert "anchor:0" in await tick(dbsession, cut, client, beets_integration)
    actions = await tick(
        dbsession, _spot_ends("2026-09-14T12:00:30+02:00"), client, beets_integration
    )
    assert "soft:58" not in actions
    assert len(_carts_sent(client)) == 1
    line = await dbsession.scalar(
        select(RundownItem)
        .where(RundownItem.clock_position_id == soft.id)
        .execution_options(populate_existing=True)
    )
    assert (line.status, line.reason) == ("skipped", "dépassé par une ancre dure")


@pytest.mark.parametrize(
    ("dayparts", "forecast_at", "cut_at", "ends_at"),
    [
        (
            [
                (MONDAY_11, True),
                (MONDAY_11 + timedelta(hours=1), True),
                (MONDAY_11 + timedelta(hours=3), False),
            ],
            "2026-09-14T11:57:30+02:00",
            "2026-09-14T12:00:05+02:00",
            "2026-09-14T12:00:30+02:00",
        ),
        (
            [
                (MONDAY_23, True),
                (MONDAY_23 + timedelta(hours=1), True),
                (MONDAY_23 + timedelta(hours=4), False),
            ],
            "2026-09-14T23:57:30+02:00",
            "2026-09-15T00:00:05+02:00",
            "2026-09-15T00:00:30+02:00",
        ),
    ],
    ids=["creneau", "minuit"],
)
async def test_a_soft_break_overtaken_where_a_daypart_opens_is_skipped(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    dayparts: list[tuple[datetime, bool]],
    forecast_at: str,
    cut_at: str,
    ends_at: str,
):
    """
    The title astride the soft break of 58 runs into the next daypart, which
    opens with a hard break, as at midnight, where a daypart always ends: the
    hard one cuts it. The conducteur says the soft one « sauté », with no sound,
    and the antenna does not play it after the hard one.
    """
    await _spots(dbsession, pubs_cart, 4)
    clock = await _soft_then_hard(
        dbsession, pubs_cart, soft=58, hard=0, dayparts=dayparts
    )
    soft = next(pos for pos in clock.anchored_positions() if pos.minute == 58)
    forecast = await ensure_forecast(
        dbsession, beets_integration, now=datetime.fromisoformat(forecast_at), cursor=0
    )
    breaks = [item for item in forecast["items"] if item["kind"] == "pub"]
    assert [(item["minute"], item["status"]) for item in breaks[:2]] == [
        (58, "sauté"),
        (0, "prévu"),
    ]
    assert breaks[0].get("sound_id") is None
    client = _client()
    cut = {**_music_on_air(cut_at), "remaining": "240"}
    with _clock_at(cut_at):
        assert "anchor:0" in await tick(dbsession, cut, client, beets_integration)
    with _clock_at(ends_at):
        actions = await tick(dbsession, _spot_ends(ends_at), client, beets_integration)
    assert not any(action.endswith(":58") for action in actions)
    assert len(_carts_sent(client)) == 1
    line = await dbsession.scalar(
        select(RundownItem)
        .where(RundownItem.clock_position_id == soft.id)
        .order_by(RundownItem.planned_at)
        .execution_options(populate_existing=True)
    )
    assert (line.status, line.reason, line.sound_id) == (
        "skipped",
        "dépassé par une ancre dure",
        None,
    )


async def test_a_hard_break_with_nothing_to_play_skips_no_soft_one(
    raw_app,
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """
    The hard break of 11:50 has an empty cart: it cuts nothing. The soft break
    of 11:49 is no « sauté »: it goes at the end of the title, and the
    conducteur plans it there.
    """
    await _spots(dbsession, pubs_cart, 3)
    empty = Cart(
        title="Vide",
        path=raw_app.config["DATA_ROOT"] / "vide",
        mode=CartMode.RANDOM,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(empty)
    await dbsession.commit()
    await _soft_then_hard(dbsession, pubs_cart, soft=49, hard=50, hard_cart=empty)
    forecast = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 11, 48, tzinfo=PARIS),
        horizon_min=15,
        cursor=0,
    )
    title = forecast["items"][0]
    assert title["kind"] == "musique"
    breaks = [item for item in forecast["items"] if item["kind"] == "pub"]
    assert [
        (item["minute"], item["status"], item.get("reason")) for item in breaks[:2]
    ] == [(50, "manquant", "cart introuvable"), (49, "prévu", "glissement")]
    assert _at(breaks[1]) == item_end_at(title) > _at(breaks[0])
    client = _client()
    runs = {**_music_on_air("2026-09-14T11:49:05+02:00"), "remaining": "300"}
    with _clock_at("2026-09-14T11:49:05+02:00"):
        await tick(dbsession, runs, client, beets_integration)
    passes = {**runs, "time": "2026-09-14T11:50:05+02:00", "remaining": "240"}
    with _clock_at("2026-09-14T11:50:05+02:00"):
        actions = await tick(dbsession, passes, client, beets_integration)
    assert "anchor:50" not in actions
    assert not any(action.endswith(":49") for action in actions)
    ends = {**runs, "time": "2026-09-14T11:54:03+02:00", "remaining": "1"}
    with _clock_at("2026-09-14T11:54:03+02:00"):
        assert "soft:49" in await tick(dbsession, ends, client, beets_integration)
    assert len(_carts_sent(client)) == 1


async def test_a_hard_break_of_another_clock_skips_no_soft_one_past_midnight(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
):
    """
    Monday from 23:00 has a soft break at 50; Tuesday, all day, another clock
    with a hard break at 55. The title astride Monday 23:50 ends past midnight:
    no hard break came, as 23:55 on Monday is no daypart of Tuesday's clock,
    and the soft one goes.
    """
    spots = await _spots(dbsession, pubs_cart, 3)
    monday = await create_clock(
        dbsession,
        {
            "name": "Lundi",
            "motif": [{"kind": "musique", "category": "Rotation"}],
            "anchors": [
                {"kind": "pub", "cart_id": pubs_cart.id, "minute": 50, "sync": "molle"},
            ],
        },
    )
    tuesday = await create_clock(
        dbsession,
        {
            "name": "Mardi",
            "motif": [{"kind": "musique", "category": "Rotation"}],
            "anchors": [
                {"kind": "pub", "cart_id": pubs_cart.id, "minute": 55, "sync": "dure"},
            ],
        },
    )
    late = await AutoDJSlot.from_time(dbsession, 23 * 60, 0, exact=True)
    if late is None:
        late = AutoDJSlot(day_of_week=0, minute=23 * 60, title="t", constraints={})
        dbsession.add(late)
    late.clock_id = monday.id
    await dbsession.execute(
        delete(AutoDJSlot).where(AutoDJSlot.day_of_week == 1, AutoDJSlot.minute > 0)
    )
    first = await AutoDJSlot.from_time(dbsession, 0, 1, exact=True)
    if first is None:
        first = AutoDJSlot(day_of_week=1, minute=0, title="t", constraints={})
        dbsession.add(first)
    first.clock_id = tuesday.id
    await dbsession.commit()
    soft = next(pos for pos in monday.anchored_positions() if pos.minute == 50)
    line = await record_live_item(
        dbsession,
        payload={
            "at": datetime(2026, 9, 15, 0, 5, tzinfo=PARIS).isoformat(),
            "kind": "pub",
            "when": "anchored",
            "queue": "carts",
            "resource": spots[1].title,
            "path": str(spots[1].path),
            "clock_id": monday.id,
            "position_id": soft.id,
            "cart_id": pubs_cart.id,
            "sound_id": spots[1].id,
            "minute": 50,
            "sync": "molle",
        },
        status=RundownStatus.PLANNED.value,
    )
    await dbsession.commit()
    client = _client()
    title_ends = {**_spot_ends("2026-09-15T00:04:58+02:00"), "source": "autodj"}
    with _clock_at("2026-09-15T00:04:58+02:00"):
        assert "soft:50" in await tick(dbsession, title_ends, client, beets_integration)
    assert _carts_sent(client) == [spots[1].title]
    await dbsession.refresh(line)
    assert line.status != "skipped"


@pytest.mark.parametrize("mode", [CartMode.PLAYLIST_LOOP, CartMode.RANDOM])
async def test_a_soft_break_the_conducteur_skips_takes_no_sound(
    dbsession: ormSession,
    jingles_cart,
    pubs_cart,
    beets_integration: BeetsIntegration,
    mode: CartMode,
):
    """
    Each hour, the title astride 11:49 runs past 11:50: the conducteur says the
    soft break « sauté ». That line names no sound, and the cart goes on, in its
    order or its draw, with the breaks that play.
    """
    spots = await _spots(dbsession, pubs_cart, 4)
    pubs_cart.mode = mode
    spots[0].last_played = datetime(2026, 9, 14, 9, 0)
    await dbsession.commit()
    await _soft_then_hard(dbsession, pubs_cart, soft=49, hard=50)
    forecast = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 11, 30, tzinfo=PARIS),
        horizon_min=150,
    )
    breaks = [item for item in forecast["items"] if item["kind"] == "pub"]
    skipped = [item for item in breaks if item["status"] == "sauté"]
    played = [item["title"] for item in breaks if item["status"] != "sauté"]
    assert len(skipped) >= 2
    assert [item.get("sound_id") for item in skipped] == [None] * len(skipped)
    assert len(played) >= 3
    if mode is CartMode.PLAYLIST_LOOP:
        assert played[:3] == ["Spot 2", "Spot 3", "Spot 4"]
    else:
        assert len(set(played[:3])) == 3
