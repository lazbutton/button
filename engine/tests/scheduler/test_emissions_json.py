from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx
from quart.testing import QuartClient
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.agenda import utc_naive
from radiotomate.domain.emission import now_paris, ranges_overlap, weekly_contains
from radiotomate.interface import live as live_mod
from radiotomate.models import AgendaDiffusion, Emission, User
from radiotomate.scheduler import alerts, antenne
from radiotomate.services import agenda, emissions
from tests.scheduler.test_admin_json import _admin_client
from tests.scheduler.test_antenne_state import _next_live_slot
from tests.scheduler.test_studio_json import _interface_client, _login

PARIS = ZoneInfo("Europe/Paris")
# Monday 21 September 2026, noon in Paris: no change of time in the weeks after.
MONDAY_NOON = datetime(2026, 9, 21, 12, 0, tzinfo=PARIS)
MONDAY = MONDAY_NOON.date()


def _today() -> int:
    return datetime.now(PARIS).weekday()


async def test_weekly_overlap_and_contains():
    now = datetime(2026, 9, 23, 20, 30, tzinfo=PARIS)  # mercredi
    assert weekly_contains(now, 2, 20 * 60, 22 * 60)
    assert not weekly_contains(now, 2, 22 * 60, 23 * 60)
    assert ranges_overlap(20 * 60, 22 * 60, 21 * 60, 23 * 60)
    assert not ranges_overlap(18 * 60, 20 * 60, 20 * 60, 22 * 60)


async def test_emissions_weekly_waiting_does_not_override_title(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "emission-wait",
    )
    created = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "weekly",
            "title": "Hop Pop Hop",
            "artist": "avec l'equipe",
            "day_of_week": _today(),
            "start_minute": 0,
            "end_minute": 1440,
        },
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    live_mod.set_live_snapshot(
        live_mod.normalize_live(
            {
                "status": "playing",
                "source": "autodj",
                "artist": "BUTTON",
                "title": "On air",
            }
        )
    )
    playing = await (await client.get("/live.json")).get_json()
    assert playing["title"] == "On air"
    assert playing["artist"] == "BUTTON"
    assert playing["emission"]["state"] == "waiting"
    assert playing["emission"]["title"] == "Hop Pop Hop"
    live_mod.set_live_snapshot(None)


async def test_emissions_weekly_on_air_overrides_title(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "emission-air",
    )
    created = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "weekly",
            "title": "Hop Pop Hop",
            "artist": "avec l'equipe",
            "day_of_week": _today(),
            "start_minute": 0,
            "end_minute": 1440,
        },
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    live_mod.set_live_snapshot(
        live_mod.normalize_live(
            {
                "status": "playing",
                "source": "stream",
                "artist": "BUTT",
                "title": "encoder",
            }
        )
    )
    playing = await (await client.get("/live.json")).get_json()
    assert playing["title"] == "Hop Pop Hop"
    assert playing["artist"] == "avec l'equipe"
    assert playing["emission"]["state"] == "on_air"
    live_mod.set_live_snapshot(None)


async def test_emissions_weekly_overlap_conflict(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "emission-overlap",
    )
    first = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "weekly",
            "title": "A",
            "artist": "phrase A",
            "day_of_week": 2,
            "start_minute": 20 * 60,
            "end_minute": 22 * 60,
        },
    )
    assert first.status_code == 201, await first.get_data(as_text=True)
    second = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "weekly",
            "title": "B",
            "artist": "phrase B",
            "day_of_week": 2,
            "start_minute": 21 * 60,
            "end_minute": 23 * 60,
        },
    )
    assert second.status_code == 409
    body = await second.get_json()
    assert "chevauche" in body["error"]


async def test_emissions_session_then_expires_when_source_leaves(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "emission-session",
    )
    live_mod.set_live_snapshot(
        live_mod.normalize_live(
            {
                "status": "playing",
                "source": "stream",
                "artist": "BUTT",
                "title": "encoder",
            }
        )
    )
    created = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "session",
            "title": "Direct surprise",
            "artist": "en plateau",
        },
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    playing = await (await client.get("/live.json")).get_json()
    assert playing["emission"]["state"] == "on_air"
    assert playing["title"] == "Direct surprise"

    live_mod.set_live_snapshot(
        live_mod.normalize_live(
            {
                "status": "playing",
                "source": "autodj",
                "artist": "BUTTON",
                "title": "Retour rotation",
            }
        )
    )
    after = await (await client.get("/live.json")).get_json()
    assert after["title"] == "Retour rotation"
    assert after.get("emission") is None
    listed = await (await client.get("/antenne/emissions.json")).get_json()
    assert listed["current"] is None
    live_mod.set_live_snapshot(None)


async def test_emissions_session_forbidden_without_live(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    user = User(username="emission-nolive")
    user.update_password(users_password)
    user.update_permissions({"can_autodj": "true"})
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "emission-nolive", users_password)
    live_mod.set_live_snapshot(
        live_mod.normalize_live({"status": "playing", "source": "stream"})
    )
    response = await client.post(
        "/antenne/emissions.json",
        json={"scope": "session", "title": "X", "artist": "Y"},
    )
    assert response.status_code == 403
    live_mod.set_live_snapshot(None)


async def test_metadata_log_relay_uses_on_air_emission(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    auth: dict,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "emission-relay",
    )
    created = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "weekly",
            "title": "Hop Pop Hop",
            "artist": "avec l'equipe",
            "day_of_week": _today(),
            "start_minute": 0,
            "end_minute": 1440,
        },
    )
    assert created.status_code == 201, await created.get_data(as_text=True)

    raw_app.config["RELAY_METADATA_TO"] = [
        {"url": "https://website.radio/playlist/add_item"}
    ]
    with patch(
        "httpx.AsyncClient.post",
        return_value=httpx.Response(200, json={"OK": 1}),
    ) as mock_relay:
        async with raw_app.test_app():
            scheduler = raw_app.test_client()
            result = await scheduler.post(
                "/metadata_log",
                json={
                    "source": "stream",
                    "artist": "BUTT",
                    "title": "encoder",
                    "on_air": datetime.now().isoformat(),
                },
                headers=auth,
            )
            assert result.status_code == 200, await result.get_data(as_text=True)

    posted = mock_relay.call_args.kwargs["data"]
    assert posted["title"] == "Hop Pop Hop"
    assert posted["artist"] == "avec l'equipe"
    assert posted["source"] == "stream"


async def test_emissions_do_not_change_slots_or_clocks(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "emission-slots",
    )
    before_slots = await (await client.get("/autodj/slots.json")).get_json()
    before_clocks = await (await client.get("/autodj/clocks.json")).get_json()
    created = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "weekly",
            "title": "Hop Pop Hop",
            "artist": "avec l'equipe",
            "day_of_week": 2,
            "start_minute": 20 * 60,
            "end_minute": 22 * 60,
        },
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    after_slots = await (await client.get("/autodj/slots.json")).get_json()
    after_clocks = await (await client.get("/autodj/clocks.json")).get_json()
    assert after_slots == before_slots
    assert after_clocks == before_clocks


def _weekly(title: str, day: int, start: int, end: int) -> Emission:
    return Emission(
        scope="weekly",
        title=title,
        artist="avec l'équipe",
        day_of_week=day,
        start_minute=start,
        end_minute=end,
    )


def _dated(kind: str, title: str, start: datetime) -> AgendaDiffusion:
    return AgendaDiffusion(
        kind=kind,
        title=title,
        starts_at=utc_naive(start),
        ends_at=utc_naive(start + timedelta(hours=2)),
    )


async def _cancel(session: ormSession, show: Emission, day: date) -> None:
    """Cancel ``show`` on ``day``, as the Agenda's route does."""
    await agenda.add_exception(
        session, {"emission_id": show.id, "date": day.isoformat()}
    )
    await session.commit()


async def test_next_skips_a_show_cancelled_tonight(dbsession: ormSession):
    qg = _weekly("QG", 0, 20 * 60, 22 * 60)
    dbsession.add(qg)
    await dbsession.commit()
    nxt = await emissions.next_live(dbsession, MONDAY_NOON)
    assert (nxt["title"], nxt["at"]) == ("QG", "2026-09-21T20:00:00+02:00")
    # Cancelled tonight in the Agenda: next week's, as on the Antenne page.
    await _cancel(dbsession, qg, MONDAY)
    nxt = await emissions.next_live(dbsession, MONDAY_NOON)
    assert nxt == {
        "id": qg.id,
        "title": "QG",
        "artist": "avec l'équipe",
        "scope": "weekly",
        "at": "2026-09-28T20:00:00+02:00",
        "until": "2026-09-28T22:00:00+02:00",
        "day_of_week": 0,
        "start_minute": 20 * 60,
        "end_minute": 22 * 60,
    }
    # Next week's cancelled as well: no live within the week.
    await _cancel(dbsession, qg, MONDAY + timedelta(days=7))
    assert await emissions.next_live(dbsession, MONDAY_NOON) is None


async def test_next_is_the_other_show_when_tonight_s_is_cancelled(
    dbsession: ormSession,
):
    qg = _weekly("QG", 0, 20 * 60, 22 * 60)
    dbsession.add_all([qg, _weekly("Matinale", 2, 8 * 60, 9 * 60)])
    await dbsession.commit()
    await _cancel(dbsession, qg, MONDAY)
    nxt = await emissions.next_live(dbsession, MONDAY_NOON)
    # Wednesday's Matinale, not QG next Monday.
    assert (nxt["title"], nxt["at"]) == ("Matinale", "2026-09-23T08:00:00+02:00")


async def test_next_tells_a_dated_live(dbsession: ormSession):
    qg = _weekly("QG", 0, 20 * 60, 22 * 60)
    concert = _dated("live", "Concert", datetime(2026, 9, 24, 21, 0, tzinfo=PARIS))
    concert.host_username = "lea"
    dbsession.add_all([qg, concert])
    await dbsession.commit()
    assert (await emissions.next_live(dbsession, MONDAY_NOON))["title"] == "QG"
    # Tonight's cancelled: Thursday's dated live comes before next week's show.
    await _cancel(dbsession, qg, MONDAY)
    assert await emissions.next_live(dbsession, MONDAY_NOON) == {
        "id": concert.id,
        "title": "Concert",
        "artist": "lea",
        "scope": "dated",
        "kind": "live",
        "at": "2026-09-24T21:00:00+02:00",
        "until": "2026-09-24T23:00:00+02:00",
        "day_of_week": 3,
        "start_minute": 21 * 60,
    }


async def test_next_skips_a_show_replaced_by_a_dated_broadcast(
    dbsession: ormSession,
):
    qg = _weekly("QG", 0, 20 * 60, 22 * 60)
    # Tonight, a recorded set takes QG's slot: no live tonight.
    archives = _dated("set", "Archives", datetime(2026, 9, 21, 20, 0, tzinfo=PARIS))
    dbsession.add_all([qg, archives])
    await dbsession.commit()
    nxt = await emissions.next_live(dbsession, MONDAY_NOON)
    assert (nxt["title"], nxt["at"]) == ("QG", "2026-09-28T20:00:00+02:00")
    # Next Monday, a dated live takes it: that live is the next.
    special = _dated("live", "Spécial", datetime(2026, 9, 28, 20, 0, tzinfo=PARIS))
    dbsession.add(special)
    await dbsession.commit()
    nxt = await emissions.next_live(dbsession, MONDAY_NOON)
    assert (nxt["id"], nxt["scope"], nxt["at"]) == (
        special.id,
        "dated",
        "2026-09-28T20:00:00+02:00",
    )


async def test_next_is_not_the_show_on_air(dbsession: ormSession):
    dbsession.add(_weekly("QG", 0, 20 * 60, 22 * 60))
    await dbsession.commit()
    # On air at 20:30: that one is ``current``. The next is next week's.
    during = datetime(2026, 9, 21, 20, 30, tzinfo=PARIS)
    nxt = await emissions.next_live(dbsession, during)
    assert nxt["at"] == "2026-09-28T20:00:00+02:00"


async def test_next_without_the_agenda_keeps_every_show(dbsession: ormSession):
    qg = _weekly("QG", 0, 20 * 60, 22 * 60)
    concert = _dated("live", "Concert", datetime(2026, 9, 21, 18, 0, tzinfo=PARIS))
    dbsession.add_all([qg, concert])
    await dbsession.commit()
    await _cancel(dbsession, qg, MONDAY)
    # The Agenda switched off, as on the Antenne page: neither its lives nor
    # its cancellations count.
    await agenda.set_agenda_enabled(dbsession, False)
    await dbsession.commit()
    nxt = await emissions.next_live(dbsession, MONDAY_NOON)
    assert (nxt["title"], nxt["at"]) == ("QG", "2026-09-21T20:00:00+02:00")


async def test_emissions_json_next_follows_the_agenda_as_the_antenne_page(  # noqa: PLR0913
    container_tz: str,
    client: QuartClient,
    auth: dict,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    console = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "emission-next",
    )
    # Two shows at noon, tomorrow and the day after: ahead at any hour of today.
    tomorrow = now_paris().date() + timedelta(days=1)
    days = {"Demain": tomorrow, "Après-demain": tomorrow + timedelta(days=1)}
    ids = {}
    for title, day in days.items():
        created = await console.post(
            "/antenne/emissions.json",
            json={
                "scope": "weekly",
                "title": title,
                "artist": "avec l'équipe",
                "day_of_week": day.weekday(),
                "start_minute": 12 * 60,
                "end_minute": 13 * 60,
            },
        )
        assert created.status_code == 201, await created.get_data(as_text=True)
        ids[title] = (await created.get_json())["emission"]["id"]

    async def next_live() -> dict:
        response = await console.get("/antenne/emissions.json")
        assert response.status_code == 200, await response.get_data(as_text=True)
        return (await response.get_json())["next"]

    nxt = await next_live()
    assert nxt["title"] == "Demain"
    assert nxt["at"].startswith(f"{tomorrow.isoformat()}T12:00")
    assert (await _next_live_slot(client, auth))["title"] == "Demain"
    # Tomorrow's cancelled in the Agenda, as the console does it.
    cancelled = await console.post(
        "/agenda/exceptions.json",
        json={"emission_id": ids["Demain"], "date": tomorrow.isoformat()},
    )
    assert cancelled.status_code == 201, await cancelled.get_data(as_text=True)
    nxt = await next_live()
    assert nxt["title"] == "Après-demain"
    assert nxt["at"].startswith(f"{days['Après-demain'].isoformat()}T12:00")
    # The next live of the Antenne page.
    assert (await _next_live_slot(client, auth))["title"] == "Après-demain"


async def test_emissions_json_names_the_live_on_air_in_current_not_next(  # noqa: PLR0913
    container_tz: str,
    client: QuartClient,
    auth: dict,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    console = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "emission-on-air",
    )
    # A dated live on air at this instant, wherever the station is, and a show
    # tomorrow at noon.
    moment = datetime.now(UTC)
    dbsession.add(
        AgendaDiffusion(
            kind="live",
            title="En cours",
            starts_at=utc_naive(moment - timedelta(minutes=30)),
            ends_at=utc_naive(moment + timedelta(minutes=30)),
        )
    )
    tomorrow = now_paris().date() + timedelta(days=1)
    dbsession.add(_weekly("Demain", tomorrow.weekday(), 12 * 60, 13 * 60))
    await dbsession.commit()
    response = await console.get("/antenne/emissions.json")
    assert response.status_code == 200, await response.get_data(as_text=True)
    listed = await response.get_json()
    # On air, it is current, as the Antenne page tells it active: the next is
    # tomorrow's show.
    assert listed["current"]["title"] == "En cours"
    assert listed["next"]["title"] == "Demain"
    slot = await _next_live_slot(client, auth)
    assert (slot["title"], slot["active"]) == ("En cours", True)


async def _antenne_next(app, now: datetime) -> dict | None:
    """The next live of the Antenne page at ``now``."""
    with patch.object(alerts, "now_paris", return_value=now):
        slots = await alerts.load_live_slots(app)
    return antenne.next_live_slot(slots, now)


async def test_next_is_the_next_live_of_the_antenne_page(
    raw_app, dbsession: ormSession
):
    # The Antenne page counts its own (next_live_slot): both tell the same live,
    # at the same instant, through each branch of the rule.
    async def same_next() -> str | None:
        page = await _antenne_next(raw_app, MONDAY_NOON)
        nxt = await emissions.next_live(dbsession, MONDAY_NOON)
        if page is None:
            assert nxt is None
            return None
        assert page["active"] is False
        assert nxt["title"] == page["title"]
        start = MONDAY_NOON + timedelta(seconds=page["starts_in_s"])
        assert datetime.fromisoformat(nxt["at"]) == start
        return nxt["title"]

    qg = _weekly("QG", 0, 20 * 60, 22 * 60)
    dbsession.add_all([qg, _weekly("Matinale", 2, 8 * 60, 9 * 60)])
    await dbsession.commit()
    assert await same_next() == "QG"
    # Cancelled tonight: Wednesday's Matinale.
    await _cancel(dbsession, qg, MONDAY)
    assert await same_next() == "Matinale"
    # Wednesday's replaced by a set: QG next Monday; the next Matinale is beyond.
    dbsession.add(_dated("set", "Archives", datetime(2026, 9, 23, 8, 0, tzinfo=PARIS)))
    await dbsession.commit()
    assert await same_next() == "QG"
    # Next Monday's replaced by a dated live: that live.
    special = _dated("live", "Spécial", datetime(2026, 9, 28, 20, 0, tzinfo=PARIS))
    dbsession.add(special)
    await dbsession.commit()
    assert await same_next() == "Spécial"
    # A dated live on Tuesday comes first.
    concert = _dated("live", "Concert", datetime(2026, 9, 22, 21, 0, tzinfo=PARIS))
    dbsession.add(concert)
    await dbsession.commit()
    assert await same_next() == "Concert"
    # The Agenda switched off: tonight's QG, for both.
    await agenda.set_agenda_enabled(dbsession, False)
    await dbsession.commit()
    assert await same_next() == "QG"
    # Back on, without the lives, next Monday's cancelled: none within the week.
    await agenda.set_agenda_enabled(dbsession, True)
    await dbsession.delete(special)
    await dbsession.delete(concert)
    await dbsession.commit()
    await _cancel(dbsession, qg, MONDAY + timedelta(days=7))
    assert await same_next() is None


async def test_emissions_json_still_answers_when_the_next_live_fails(
    container_tz: str, dbsession: ormSession
):
    dbsession.add(_weekly("QG", 0, 20 * 60, 22 * 60))
    await dbsession.commit()
    unreadable = AsyncMock(side_effect=RuntimeError("Agenda illisible"))
    with (
        patch.object(agenda, "blocked_weekly_days", new=unreadable),
        patch.object(emissions, "_log") as log,
    ):
        listed = await emissions.list_emissions_payload(dbsession, "autodj")
    # The list of the shows still answers, without a next live; the engine's
    # log says why.
    assert [row["title"] for row in listed["emissions"]] == ["QG"]
    assert listed["next"] is None
    log.exception.assert_called_once()


async def test_a_title_does_not_read_the_agenda_over_the_week(
    container_tz: str, dbsession: ormSession
):
    # The next live reads the Agenda over the week: the console's list does,
    # not each title that names the antenna.
    dbsession.add(_weekly("QG", 0, 20 * 60, 22 * 60))
    await dbsession.commit()
    days = AsyncMock(wraps=agenda.blocked_weekly_days)
    lives = AsyncMock(wraps=agenda.dated_live_windows)
    with (
        patch.object(agenda, "blocked_weekly_days", new=days),
        patch.object(agenda, "dated_live_windows", new=lives),
    ):
        await emissions.overlay_metadata_if_on_air(
            dbsession, {"source": "autodj", "title": "Titre", "artist": "Artiste"}
        )
        await emissions.attach_live_emission(dbsession, {"source": "autodj"})
        days.assert_not_awaited()
        lives.assert_not_awaited()
        listed = await emissions.list_emissions_payload(dbsession, "autodj")
    assert listed["next"]["title"] == "QG"
    days.assert_awaited_once()
    lives.assert_awaited_once()
