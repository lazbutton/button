"""A dated set on air: start at its minute, hold the clock, hand the antenna back."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.agenda import utc_naive
from radiotomate.models import (
    AgendaDiffusion,
    AgendaException,
    AgendaFile,
    Cart,
    Emission,
    RundownItem,
    Setting,
    User,
)
from radiotomate.scheduler.clock import _state, tick
from radiotomate.scheduler.rundown import build_rundown
from radiotomate.services.emissions import harbor_allowed
from tests.scheduler.test_clock import _client, _live

PARIS = ZoneInfo("Europe/Paris")
# Monday: the "Journée pubs" clock has a hard pub anchor at :20 and :40.
T = datetime(2026, 9, 14, 10, 20, 0, tzinfo=PARIS)


def _at(moment: datetime) -> str:
    return moment.isoformat()


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    folder = tmp_path / "40-emissions" / "carte-blanche" / "entiere"
    folder.mkdir(parents=True)
    (folder / "set.mp3").write_bytes(b"ID3")
    return tmp_path


async def _diffusion(  # noqa: PLR0913
    session: ormSession,
    *,
    start: datetime = T,
    minutes: int = 60,
    kind: str = "set",
    file: bool = True,
    origin: str = "banque",
    rights: bool = True,
    host: str = "",
    title: str = "Carte blanche",
) -> AgendaDiffusion:
    row = AgendaDiffusion(
        kind=kind,
        title=title,
        starts_at=utc_naive(start),
        ends_at=utc_naive(start + timedelta(minutes=minutes)),
        host_username=host,
        rights_at=utc_naive(start - timedelta(days=1)) if rights else None,
    )
    session.add(row)
    await session.flush()
    if file and kind == "set":
        session.add(
            AgendaFile(
                diffusion_id=row.id,
                path="40-emissions/carte-blanche/entiere/set.mp3",
                origin=origin,
                duration=1800,
                gain=-3.0,
                report={"status": "ok"},
            )
        )
    await session.commit()
    return await _reload(session, row.id)


async def _reload(session: ormSession, diffusion_id: int) -> AgendaDiffusion:
    return await session.scalar(
        select(AgendaDiffusion)
        .where(AgendaDiffusion.id == diffusion_id)
        .execution_options(populate_existing=True)
    )


def _posts(client) -> list[tuple[str, dict]]:
    return [
        (call.args[0], call.kwargs.get("json") or {})
        for call in client.post.call_args_list
    ]


async def test_a_set_starts_at_its_minute_and_holds_the_pub_anchor(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
):
    row = await _diffusion(dbsession)
    client = _client()
    actions = await tick(
        dbsession,
        _live(_at(T), source="autodj", remaining="120", autodj_queued=1),
        client,
        beets_integration,
        now=T,
    )
    assert f"agenda_start:{row.id}" in actions
    assert "agenda_hold" in actions
    posts = _posts(client)
    assert ("/queue/flush", {"queues": ["carts", "jingles", "autodj"]}) in posts
    pushed = [payload for path, payload in posts if path == "/queue/carts"]
    assert len(pushed) == 1
    assert pushed[0]["path"].endswith("40-emissions/carte-blanche/entiere/set.mp3")
    assert pushed[0]["rg_track_gain"] == "-3.0"
    assert pushed[0]["artist"] == "Carte blanche"
    assert all("spot.mp3" not in str(payload.get("path")) for _, payload in posts)
    row = await _reload(dbsession, row.id)
    assert row.air_status == "on_air"
    assert row.air_item_id == pushed[0]["radiotomate_item_id"]
    assert _state.pending_autodj_skip is True


async def test_while_the_set_plays_nothing_else_is_pushed(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
):
    row = await _diffusion(dbsession)
    await tick(
        dbsession, _live(_at(T), source="autodj"), _client(), beets_integration, now=T
    )
    row = await _reload(dbsession, row.id)
    later = T + timedelta(minutes=20, seconds=5)
    client = _client()
    actions = await tick(
        dbsession,
        _live(
            _at(later),
            source="carts",
            remaining="600",
            radiotomate_item_id=row.air_item_id,
            carts_queued=0,
        ),
        client,
        beets_integration,
        now=later,
    )
    assert "agenda_hold" in actions
    assert not [path for path, _ in _posts(client) if path.startswith("/queue/")]
    near_end = T + timedelta(minutes=29, seconds=40)
    client = _client()
    actions = await tick(
        dbsession,
        _live(
            _at(near_end),
            source="carts",
            remaining="20",
            radiotomate_item_id=row.air_item_id,
            autodj_queued=0,
        ),
        client,
        beets_integration,
        now=near_end,
    )
    assert "agenda_hold" in actions
    assert "autodj" in actions


async def test_the_end_gives_the_antenna_back(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
):
    row = await _diffusion(dbsession)
    await tick(
        dbsession, _live(_at(T), source="autodj"), _client(), beets_integration, now=T
    )
    row = await _reload(dbsession, row.id)
    item = await RundownItem.from_id(dbsession, row.air_item_id)
    item.started_at = utc_naive(T).replace(tzinfo=None)
    await dbsession.commit()
    after = T + timedelta(minutes=31)
    actions = await tick(
        dbsession,
        _live(_at(after), source="autodj", remaining="200"),
        _client(),
        beets_integration,
        now=after,
    )
    assert f"agenda_end:{row.id}" in actions
    assert "agenda_hold" not in actions
    row = await _reload(dbsession, row.id)
    assert row.air_status == "aired"
    assert row.aired_end is not None


async def test_a_set_that_never_played_is_missed(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
):
    row = await _diffusion(dbsession)
    await tick(
        dbsession, _live(_at(T), source="autodj"), _client(), beets_integration, now=T
    )
    after = T + timedelta(minutes=2)
    await tick(
        dbsession,
        _live(_at(after), source="autodj"),
        _client(),
        beets_integration,
        now=after,
    )
    row = await _reload(dbsession, row.id)
    assert row.air_status == "missed"
    assert row.air_reason == "Le fichier n'est pas passé"


@pytest.mark.parametrize(
    ("file", "origin", "rights", "reason"),
    [
        (False, "banque", True, "Set attendu"),
        (True, "depot", False, "Droits non cochés"),
    ],
)
async def test_a_set_that_cannot_play_leaves_the_grid_on(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
    file,
    origin,
    rights,
    reason,
):
    row = await _diffusion(dbsession, file=file, origin=origin, rights=rights)
    client = _client()
    actions = await tick(
        dbsession,
        _live(_at(T.replace(second=5)), source="autodj", remaining="0"),
        client,
        beets_integration,
        now=T.replace(second=5),
    )
    assert f"agenda_missed:{row.id}" in actions
    assert "agenda_hold" not in actions
    pushed = [payload for path, payload in _posts(client) if path == "/queue/carts"]
    assert any("spot.mp3" in str(payload.get("path")) for payload in pushed)
    row = await _reload(dbsession, row.id)
    assert row.air_status == "missed"
    assert row.air_reason == reason


async def test_the_next_set_waits_for_the_previous_one(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
):
    first = await _diffusion(dbsession, start=T - timedelta(hours=1), minutes=60)
    first.air_status = "on_air"
    first.air_item_id = "still-playing"
    first.aired_start = utc_naive(T - timedelta(hours=1))
    await dbsession.commit()
    second = await _diffusion(dbsession, title="Suivante")
    client = _client()
    actions = await tick(
        dbsession,
        _live(
            _at(T),
            source="carts",
            remaining="300",
            radiotomate_item_id="still-playing",
        ),
        client,
        beets_integration,
        now=T,
    )
    assert f"agenda_wait:{second.id}" in actions
    assert "agenda_hold" in actions
    assert not [path for path, _ in _posts(client) if path == "/queue/carts"]


async def test_stop_cuts_the_set_after_the_refill(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
):
    row = await _diffusion(dbsession)
    await tick(
        dbsession, _live(_at(T), source="autodj"), _client(), beets_integration, now=T
    )
    row = await _reload(dbsession, row.id)
    row.stop_requested_at = utc_naive(T + timedelta(minutes=5))
    await dbsession.commit()
    moment = T + timedelta(minutes=5, seconds=5)
    client = _client()
    actions = await tick(
        dbsession,
        _live(
            _at(moment),
            source="carts",
            remaining="900",
            radiotomate_item_id=row.air_item_id,
            autodj_queued=0,
        ),
        client,
        beets_integration,
        now=moment,
    )
    assert f"agenda_end:{row.id}" in actions
    # Auto-DJ is refilled first, then the set is skipped: no gap.
    assert "autodj" in actions
    assert "/queue/autodj" in [path for path, _ in _posts(client)]
    skips = [call.kwargs.get("params") for call in client.delete.call_args_list]
    assert skips[-1] == {"queue": "carts"}
    row = await _reload(dbsession, row.id)
    assert row.air_status == "aired"
    assert row.air_reason.startswith("Arrêtée à")


async def test_a_dated_live_goes_on_air_with_the_harbor(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    live = await _diffusion(dbsession, kind="live", host="dj-lou", minutes=60)
    absent = await _diffusion(
        dbsession, kind="live", host="dj-lou", start=T + timedelta(hours=3), minutes=30
    )
    actions = await tick(
        dbsession, _live(_at(T), source="stream"), _client(), beets_integration, now=T
    )
    assert f"agenda_live:{live.id}" in actions
    after = T + timedelta(hours=1, minutes=1)
    await tick(
        dbsession,
        _live(_at(after), source="autodj"),
        _client(),
        beets_integration,
        now=after,
    )
    assert (await _reload(dbsession, live.id)).air_status == "aired"
    gone = T + timedelta(hours=4)
    await tick(
        dbsession,
        _live(_at(gone), source="autodj"),
        _client(),
        beets_integration,
        now=gone,
    )
    absent = await _reload(dbsession, absent.id)
    assert absent.air_status == "missed"
    assert absent.air_reason == "Personne ne s'est branché"


async def test_the_switch_turns_the_agenda_off(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
):
    row = await _diffusion(dbsession)
    await Setting.upsert(dbsession, "agenda_enabled", "0")
    await dbsession.commit()
    client = _client()
    actions = await tick(
        dbsession,
        _live(_at(T.replace(second=5)), source="autodj", remaining="0"),
        client,
        beets_integration,
        now=T.replace(second=5),
    )
    assert not [action for action in actions if action.startswith("agenda")]
    assert (await _reload(dbsession, row.id)).air_status == "upcoming"


async def test_harbor_access_follows_dated_lives_and_days_off(
    dbsession: ormSession,
    users_password: str,
):
    def user(name: str, **perms) -> User:
        row = User(username=name)
        row.update_password(users_password)
        row.update_permissions_map(perms)
        dbsession.add(row)
        return row

    lou = user("dj-lou", stream=True)
    other = user("dj-autre", stream=True)
    matinal = user("matinal", stream=True)
    admin = user("chef", admin=True)
    await dbsession.commit()
    # Nobody is named anywhere: the harbor is open, as before the Agenda.
    assert await harbor_allowed(dbsession, other, T)

    await _diffusion(dbsession, kind="live", host="dj-lou", minutes=60)
    assert await harbor_allowed(dbsession, lou, T - timedelta(minutes=10))
    assert not await harbor_allowed(dbsession, lou, T - timedelta(minutes=20))
    assert not await harbor_allowed(dbsession, other, T)
    assert await harbor_allowed(dbsession, admin, T)

    weekly = Emission(
        scope="weekly",
        title="Matinale",
        artist="avec l'équipe",
        day_of_week=T.weekday(),
        start_minute=7 * 60,
        end_minute=9 * 60,
        host_username="matinal",
    )
    dbsession.add(weekly)
    await dbsession.commit()
    morning = T.replace(hour=8)
    assert await harbor_allowed(dbsession, matinal, morning)
    dbsession.add(AgendaException(emission_id=weekly.id, day=morning.date()))
    await dbsession.commit()
    assert not await harbor_allowed(dbsession, matinal, morning)


async def test_the_forecast_leaves_room_for_the_set(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    media,
):
    row = await _diffusion(dbsession)
    forecast = await build_rundown(
        dbsession, beets_integration, now=T - timedelta(minutes=10), horizon_min=60
    )
    items = forecast["items"]
    blocks = [item for item in items if item.get("origin") == "agenda"]
    assert len(blocks) == 1
    assert blocks[0]["diffusion_id"] == row.id
    assert blocks[0]["kind"] == "emission"
    assert datetime.fromisoformat(blocks[0]["at"]) == T
    inside = [
        item
        for item in items
        if item.get("origin") != "agenda"
        and T <= datetime.fromisoformat(item["at"]) < T + timedelta(minutes=30)
    ]
    assert inside == []
