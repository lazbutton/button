"""
A relay cart in a clock (FON-33). A clock does not launch a relay: saving one
that names a relay is refused. A position saved with one before, or whose cart
has turned relay since, plays its fallback, or nothing: the tick never raises,
and the conducteur says why.
"""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainValidationError
from radiotomate.enums import CartMode, RundownStatus, ScheduleMode
from radiotomate.models import AutoDJSlot, Clock, ClockPosition, RundownItem
from radiotomate.models.cart import Cart
from radiotomate.models.sound import Sound
from radiotomate.scheduler.clock import PARIS, RELAY_CART, tick
from radiotomate.scheduler.execution import ensure_forecast
from radiotomate.scheduler.rundown import build_rundown
from radiotomate.services.autodj import apply_clock, create_clock
from radiotomate.services.cart_draw import next_cart_sound
from tests.scheduler.test_admin_json import _admin_client
from tests.scheduler.test_cart_draw import _clock_at, _music_on_air, _spots
from tests.scheduler.test_clock import JOURNEE_20, _client, _live
from tests.scheduler.test_rundown import _carts_sent, _soft_then_hard

RELAY_URL = "https://radio.example/flux.mp3"


def _relay(raw_app, title: str) -> Cart:
    return Cart(
        title=title,
        path=raw_app.config["DATA_ROOT"] / title.lower(),
        mode=CartMode.RELAY,
        schedule_mode=ScheduleMode.CLOCK,
        url=RELAY_URL,
        max_duration=1800,
    )


@pytest.fixture
async def relay_pubs(raw_app, dbsession: ormSession) -> Cart:
    """
    « Pubs », the cart the breaks of the seeded « Journée pubs » name, turned
    relay. It keeps the sound it held: the clock plays none of it.
    """
    cart = _relay(raw_app, "Pubs")
    dbsession.add(cart)
    await dbsession.flush()
    dbsession.add(
        Sound(
            cart_id=cart.id,
            path=cart.path / "spot.mp3",
            duration=20,
            title="Spot resté",
            gain=-1.0,
            peak=-0.5,
        )
    )
    await dbsession.commit()
    return cart


def _wants_titles(time: str) -> dict:
    """A title on air, the Auto-DJ queue empty: the clock fills it."""
    return _live(
        time,
        source="autodj",
        remaining="200",
        next_jingle={"rid": -1},
        next_autodj={"rid": -1},
        jingles_queued=0,
        autodj_queued=0,
    )


async def _lines_of(
    dbsession: ormSession, clock_name: str, minute: int
) -> list[RundownItem]:
    """The conducteur's lines of an anchor of a clock, oldest first."""
    clock = await dbsession.scalar(select(Clock).where(Clock.name == clock_name))
    pos = await dbsession.scalar(
        select(ClockPosition).where(
            ClockPosition.clock_id == clock.id, ClockPosition.minute == minute
        )
    )
    rows = await dbsession.scalars(
        select(RundownItem)
        .where(RundownItem.clock_position_id == pos.id)
        .order_by(RundownItem.planned_at)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def test_a_relay_gives_no_sound(dbsession: ormSession, relay_pubs: Cart):
    """It raised AttributeError: the relay mode has no ``next_sound_relay``."""
    cart = await Cart.from_id(dbsession, relay_pubs.id, load_sounds=True)
    assert cart.sounds
    assert cart.next_sound() is None
    assert cart.next_sound(for_display=True) is None
    assert await next_cart_sound(dbsession, cart) is None


async def test_a_hard_break_on_a_relay_plays_its_fallback(
    dbsession: ormSession,
    jingles_cart: Cart,
    relay_pubs: Cart,
    beets_integration: BeetsIntegration,
):
    """
    The replay of the fiche: the break of 10:20 names « Pubs », a relay, and the
    clock fires it itself, the conducteur having no line for it yet. The tick
    raised AttributeError. The break plays its fallback, and the titles after it
    go.
    """
    client = _client()
    actions = await tick(
        dbsession, _wants_titles(JOURNEE_20), client, beets_integration
    )
    assert "anchor:20" in actions
    assert _carts_sent(client) == ["ID BUTTON"]
    assert "autodj" in actions


async def test_a_hard_break_on_a_relay_without_fallback_is_said_once(
    dbsession: ormSession,
    relay_pubs: Cart,
    beets_integration: BeetsIntegration,
):
    """
    No fallback has a sound: the break plays nothing, cuts nothing, and the
    conducteur says why, once, « sauté », though the clock tries it again until
    10:21.
    """
    client = _client()
    first = await tick(dbsession, _wants_titles(JOURNEE_20), client, beets_integration)
    later = await tick(
        dbsession,
        _wants_titles("2026-09-14T10:20:35+02:00"),
        client,
        beets_integration,
    )
    assert not any(action.startswith("anchor:") for action in first + later)
    assert _carts_sent(client) == []
    assert "autodj" in first
    lines = await _lines_of(dbsession, "Journée pubs", 20)
    assert len(lines) == 1
    line = lines[0]
    assert line.status == RundownStatus.SKIPPED.value
    assert line.reason == RELAY_CART
    assert line.closed_at is not None
    assert line.cart_id == relay_pubs.id
    assert line.sound_id is None
    assert line.planned_at == datetime(2026, 9, 14, 10, 20, 5)


async def test_the_conducteur_says_a_break_on_a_relay_ahead(
    dbsession: ormSession,
    relay_pubs: Cart,
    beets_integration: BeetsIntegration,
):
    """
    Planned ahead, the break says « bac en relais », not « cart introuvable »,
    without a sound of the relay. At 10:20 the clock adds no line of its own.
    """
    await ensure_forecast(
        dbsession, beets_integration, now=datetime(2026, 9, 14, 10, 10, tzinfo=PARIS)
    )
    planned = await _lines_of(dbsession, "Journée pubs", 20)
    assert [(line.status, line.reason) for line in planned] == [
        (RundownStatus.FAILED.value, RELAY_CART)
    ]
    assert planned[0].sound_id is None
    assert planned[0].details["cart"] == "Pubs"
    await tick(dbsession, _wants_titles(JOURNEE_20), _client(), beets_integration)
    assert [line.id for line in await _lines_of(dbsession, "Journée pubs", 20)] == [
        planned[0].id
    ]


async def test_a_break_on_a_relay_is_planned_from_its_fallback(
    dbsession: ormSession,
    jingles_cart: Cart,
    relay_pubs: Cart,
    beets_integration: BeetsIntegration,
):
    """With a fallback that has a sound, the conducteur plans it, « secours »."""
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 10, 10, tzinfo=PARIS),
        cursor=0,
    )
    breaks = [
        item
        for item in data["items"]
        if item["when"] == "anchored" and item["minute"] == 20
    ]
    assert [(item["status"], item["cart"]) for item in breaks] == [
        ("secours", "Jingles")
    ]


async def test_a_relay_fallback_is_not_said_of_its_cart(
    raw_app,
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
):
    """
    « Pubs » is a cart of sounds with none ready, and « Jingles », its fallback,
    a relay: the line names « Pubs », so it does not say « bac en relais », and
    the clock writes no line of its own, as for any empty cart.
    """
    empty = Cart(
        title="Pubs",
        path=raw_app.config["DATA_ROOT"] / "pubs",
        mode=CartMode.RANDOM,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add_all([empty, _relay(raw_app, "Jingles")])
    await dbsession.commit()
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 10, 10, tzinfo=PARIS),
        cursor=0,
    )
    breaks = [
        item
        for item in data["items"]
        if item["when"] == "anchored" and item["minute"] == 20
    ]
    assert [(item["status"], item["reason"], item["cart"]) for item in breaks] == [
        ("manquant", "cart introuvable", "Pubs")
    ]
    await tick(dbsession, _wants_titles(JOURNEE_20), _client(), beets_integration)
    assert await _lines_of(dbsession, "Journée pubs", 20) == []


async def _turned_relay(dbsession: ormSession, cart: Cart) -> None:
    """A cart a clock names turns relay after the clock is saved."""
    cart.mode = CartMode.RELAY
    cart.url = RELAY_URL
    cart.max_duration = 1800
    await dbsession.commit()


async def test_a_break_planned_before_its_cart_turned_relay_plays_its_fallback(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """
    The conducteur planned « Spot test » for 10:20, then « Pubs » turned relay:
    the planned line does not go, it is « sauté », « bac en relais », and the
    break plays its fallback at the next tick.
    """
    await ensure_forecast(
        dbsession, beets_integration, now=datetime(2026, 9, 14, 10, 10, tzinfo=PARIS)
    )
    planned = await _lines_of(dbsession, "Journée pubs", 20)
    assert [(line.status, line.resource) for line in planned] == [
        (RundownStatus.PLANNED.value, "Spot test")
    ]
    await _turned_relay(dbsession, pubs_cart)
    client = _client()
    with _clock_at(JOURNEE_20):
        first = await tick(
            dbsession, _wants_titles(JOURNEE_20), client, beets_integration
        )
    assert "anchor:20" not in first
    assert _carts_sent(client) == []
    later = "2026-09-14T10:20:10+02:00"
    with _clock_at(later):
        second = await tick(dbsession, _wants_titles(later), client, beets_integration)
    assert "anchor:20" in second
    assert _carts_sent(client) == ["ID BUTTON"]
    lines = await _lines_of(dbsession, "Journée pubs", 20)
    assert [(line.status, line.reason) for line in lines[:1]] == [
        (RundownStatus.SKIPPED.value, RELAY_CART)
    ]
    assert lines[0].id == planned[0].id
    assert [line.fallback_used for line in lines[1:]] == [True]


async def test_a_motif_step_planned_before_its_cart_turned_relay_is_skipped(
    raw_app,
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
):
    """
    The conducteur planned « Chronique » for the step, then its cart turned
    relay: the line is « sauté », « bac en relais », and the music after it goes.
    """
    programme = await _programme_clock(raw_app, dbsession)
    await ensure_forecast(
        dbsession, beets_integration, now=datetime(2026, 9, 14, 0, 29, 50, tzinfo=PARIS)
    )
    await _turned_relay(dbsession, programme)
    client = _client()
    moment = "2026-09-14T00:30:00+02:00"
    with _clock_at(moment):
        actions = await tick(
            dbsession, _wants_titles(moment), client, beets_integration
        )
    assert "autodj" in actions
    sent = [call.kwargs["json"] for call in client.post.call_args_list]
    assert all(payload.get("title") != "Chronique" for payload in sent)
    steps = await dbsession.scalars(
        select(RundownItem)
        .where(RundownItem.kind == "son", RundownItem.resource == "Chronique")
        .order_by(RundownItem.planned_at)
        .execution_options(populate_existing=True)
    )
    first = next(iter(steps))
    assert (first.status, first.reason) == (RundownStatus.SKIPPED.value, RELAY_CART)


async def test_a_hard_break_on_a_relay_skips_no_soft_one(
    raw_app,
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """
    The hard break of 11:50 names a relay: it cuts nothing, like a break with
    nothing to play. The soft break of 11:49 goes at the end of the title.
    """
    await _spots(dbsession, pubs_cart, 3)
    partner = Cart(
        title="Partenaire",
        path=raw_app.config["DATA_ROOT"] / "partenaire",
        mode=CartMode.RANDOM,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(partner)
    await dbsession.commit()
    await _soft_then_hard(dbsession, pubs_cart, soft=49, hard=50, hard_cart=partner)
    await _turned_relay(dbsession, partner)
    forecast = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 11, 48, tzinfo=PARIS),
        horizon_min=15,
        cursor=0,
    )
    breaks = [item for item in forecast["items"] if item["kind"] == "pub"]
    assert [
        (item["minute"], item["status"], item.get("reason")) for item in breaks[:2]
    ] == [(49, "prévu", None), (50, "manquant", RELAY_CART)]
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


async def test_a_soft_break_on_a_relay_is_said_once(
    raw_app,
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """
    The soft break of 11:49 names a relay, with nothing to fall back on: at the
    end of the title it plays nothing, and the conducteur says so once.
    """
    partner = _relay(raw_app, "Partenaire")
    dbsession.add(partner)
    await dbsession.commit()
    clock = await _soft_then_hard(
        dbsession, pubs_cart, soft=49, hard=50, hard_cart=pubs_cart
    )
    soft = next(pos for pos in clock.anchored_positions() if pos.minute == 49)
    soft.cart_id = partner.id
    soft.cart_title = partner.title
    await dbsession.commit()
    client = _client()
    for time, remaining in (("11:49:30", "1"), ("11:49:40", "1")):
        moment = f"2026-09-14T{time}+02:00"
        live = {**_music_on_air(moment), "remaining": remaining}
        with _clock_at(moment):
            actions = await tick(dbsession, live, client, beets_integration)
        assert not any(action.endswith(":49") for action in actions)
    assert _carts_sent(client) == []
    lines = await _lines_of(dbsession, "Molle puis dure", 49)
    assert [(line.status, line.reason) for line in lines] == [
        (RundownStatus.SKIPPED.value, RELAY_CART)
    ]


async def test_a_motif_step_on_a_relay_plays_nothing_of_it(
    raw_app,
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
):
    """
    A step of the motif names a cart that has turned relay, its sounds still in
    it: the conducteur says « bac en relais », and the clock sends the music
    after it, never a sound of the relay.
    """
    programme = await _programme_clock(raw_app, dbsession)
    clock = await dbsession.scalar(
        select(Clock).where(Clock.name == "Programme et titres")
    )
    await _turned_relay(dbsession, programme)
    client = _client()
    actions = await tick(
        dbsession, _wants_titles("2026-09-14T00:30:00+02:00"), client, beets_integration
    )
    assert "autodj" in actions
    sent = [call.kwargs["json"] for call in client.post.call_args_list]
    assert all(payload.get("title") != "Chronique" for payload in sent)
    steps = await dbsession.scalars(
        select(RundownItem).where(
            RundownItem.kind == "son", RundownItem.clock_id == clock.id
        )
    )
    assert {(row.status, row.reason) for row in steps} == {
        (RundownStatus.FAILED.value, RELAY_CART)
    }


async def _programme_clock(raw_app, dbsession: ormSession) -> Cart:
    """
    « Programme et titres », on Mondays from midnight: a step of « Programme »,
    a loop of one sound, « Chronique », then a title of the Rotation.
    """
    programme = Cart(
        title="Programme",
        path=raw_app.config["DATA_ROOT"] / "programme",
        mode=CartMode.PLAYLIST_LOOP,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(programme)
    await dbsession.flush()
    dbsession.add(
        Sound(
            cart_id=programme.id,
            path=programme.path / "chronique.mp3",
            duration=120,
            title="Chronique",
            gain=-1.0,
            peak=-0.5,
        )
    )
    await dbsession.commit()
    clock = await create_clock(
        dbsession,
        {
            "name": "Programme et titres",
            "motif": [
                {"kind": "son", "cart_id": programme.id},
                {"kind": "musique", "category": "Rotation"},
            ],
            "anchors": [],
        },
    )
    slot = await AutoDJSlot.from_time(dbsession, 0, 0)
    slot.clock_id = clock.id
    await dbsession.commit()
    return programme


def _clock_with(cart: Cart, *, where: str) -> dict:
    """A clock that names ``cart`` at one place: a step, a fallback, the clock's."""
    step = {"kind": "jingle", "cart": "Jingles"}
    data = {"name": "Avec un relais", "motif": [step], "anchors": []}
    if where == "cart":
        step["cart"] = cart.title
    elif where == "fallback_cart":
        step["fallback_cart"] = cart.title
    else:
        data["fallback_cart"] = cart.title
    return data


@pytest.mark.parametrize(
    ("where", "field"),
    [
        ("cart", "cart"),
        ("fallback_cart", "fallback_cart"),
        ("clock", "fallback_cart"),
    ],
    ids=["etape", "secours-etape", "secours-heure"],
)
async def test_a_clock_naming_a_relay_is_refused(
    raw_app,
    dbsession: ormSession,
    jingles_cart: Cart,
    where: str,
    field: str,
):
    partner = _relay(raw_app, "Partenaire")
    dbsession.add(partner)
    await dbsession.commit()
    with pytest.raises(DomainValidationError) as refused:
        await create_clock(dbsession, _clock_with(partner, where=where))
    assert refused.value.field == field
    assert refused.value.message == (
        "Le bac « Partenaire » est un relais : une heure type ne joue que des bacs"
        " de sons. Un relais se lance par « Diffuser maintenant »."
    )


async def test_an_anchor_naming_a_relay_by_id_is_refused(
    raw_app,
    dbsession: ormSession,
    jingles_cart: Cart,
):
    partner = _relay(raw_app, "Partenaire")
    dbsession.add(partner)
    await dbsession.commit()
    clock = await dbsession.scalar(select(Clock).where(Clock.name == "Journée pubs"))
    clock = await Clock.from_id(dbsession, clock.id, load_positions=True)
    with pytest.raises(DomainValidationError) as refused:
        await apply_clock(
            dbsession,
            clock,
            {
                "motif": [{"kind": "jingle", "cart": "Jingles"}],
                "anchors": [
                    {"kind": "pub", "cart_id": partner.id, "minute": 20, "sync": "dure"}
                ],
            },
            creating=False,
        )
    assert refused.value.field == "cart"


async def test_the_clock_route_refuses_a_relay(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart: Cart,
):
    """The console reads why in French, and the clock stays as it was."""
    partner = _relay(raw_app, "Partenaire")
    dbsession.add(partner)
    await dbsession.commit()
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "relay-clock",
    )
    created = await client.post(
        "/autodj/clocks.json",
        json={"name": "Atelier", "motif": [{"kind": "jingle", "cart": "Jingles"}]},
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    clock = (await created.get_json())["clock"]
    refused = await client.put(
        f"/autodj/clocks/{clock['id']}.json",
        json={
            "version": clock["version"],
            "name": "Atelier",
            "motif": clock["motif"],
            "anchors": [
                {"kind": "pub", "cart_id": partner.id, "minute": 30, "sync": "dure"}
            ],
        },
    )
    assert refused.status_code == 400
    body = await refused.get_json()
    assert body["code"] == "validation_error"
    assert body["field"] == "cart"
    assert "« Partenaire » est un relais" in body["error"]
    clocks = await (await client.get("/autodj/clocks.json")).get_json()
    kept = next(row for row in clocks["clocks"] if row["id"] == clock["id"])
    assert kept["anchors"] == []
