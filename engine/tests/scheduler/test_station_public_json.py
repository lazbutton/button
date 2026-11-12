"""The station website's routes: the coming week and the last music tracks,
read without a session, from another domain."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.models import (
    AgendaDiffusion,
    MetadataLog,
    ProgrammingVersion,
    RundownItem,
    Setting,
)
from radiotomate.services.station_public import SETTING_SITE_ROUTES
from tests.scheduler.test_admin_json import _admin_client
from tests.scheduler.test_agenda_json import _create, _day, _wall
from tests.scheduler.test_studio_json import _interface_client

PARIS = ZoneInfo("Europe/Paris")


def _at(day: date, hour: int, minute: int = 0) -> str:
    """A Paris wall time as the programme gives it: offset, seconds."""
    return datetime.combine(day, time(hour, minute), tzinfo=PARIS).isoformat()


async def _weekly(client, title: str, day: date, hours: tuple[int, int], **fields):
    response = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "weekly",
            "title": title,
            "artist": "avec l'équipe",
            "day_of_week": day.weekday(),
            "start_minute": hours[0] * 60,
            "end_minute": hours[1] * 60,
            **fields,
        },
    )
    body = await response.get_json()
    assert response.status_code == 201, body
    return body["emission"]["id"]


async def test_the_programme_gives_titles_times_and_kinds_only(  # noqa: PLR0913
    container_tz: str,
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "site-a"
    )
    await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "dj-direct-site",
        {"stream": True, "live": True},
    )
    day = _day(2)
    after = day + timedelta(days=1)
    await _weekly(
        admin,
        "Matinale",
        day,
        (8, 10),
        artist="avec anim-hebdo",
        host_username="anim-hebdo",
    )
    [dated] = await _create(
        admin,
        kind="set",
        title="Carte blanche",
        start=_wall(day, 22),
        end=_wall(day, 23),
        guest_name="Lou Discret",
    )
    filled = await admin.put(
        f"/agenda/diffusions/{dated['id']}.json",
        json={"set_title": "set-prive", "tracklist": "piste-privee"},
    )
    assert filled.status_code == 200
    await _create(
        admin,
        kind="live",
        title="Direct du soir",
        start=_wall(after, 18),
        end=_wall(after, 19),
        host_username="dj-direct-site",
    )
    # The day after the seven days.
    await _create(
        admin,
        kind="set",
        title="Semaine suivante",
        start=_wall(_day(7), 12),
        end=_wall(_day(7), 13),
    )

    site = _interface_client(app_configration, beets_integration)
    response = await site.get("/public/programme.json")
    payload = await response.get_json()
    assert response.status_code == 200, payload
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["Cache-Control"] == "public, max-age=60"
    assert response.headers["X-Robots-Tag"] == "noindex"
    assert "Set-Cookie" not in response.headers
    assert payload == {
        "timezone": "Europe/Paris",
        "from": _day(0).isoformat(),
        "to": _day(6).isoformat(),
        "items": [
            {
                "starts_at": _at(day, 8),
                "ends_at": _at(day, 10),
                "title": "Matinale",
                "kind": "emission",
            },
            {
                "starts_at": _at(day, 22),
                "ends_at": _at(day, 23),
                "title": "Carte blanche",
                "kind": "set",
            },
            {
                "starts_at": _at(after, 18),
                "ends_at": _at(after, 19),
                "title": "Direct du soir",
                "kind": "direct",
            },
        ],
    }
    body = await response.get_data(as_text=True)
    for private in (
        "anim-hebdo",
        "dj-direct-site",
        "Lou Discret",
        "set-prive",
        "piste-privee",
        "token",
        "guest",
        "host",
    ):
        assert private not in body

    # The guest's routes keep their own headers.
    guest = await site.get(f"/public/guest/{'x' * 43}.json")
    assert guest.status_code == 404
    assert guest.headers["Cache-Control"] == "no-store"
    assert "Access-Control-Allow-Origin" not in guest.headers


async def test_a_weekly_show_cancelled_or_replaced_leaves_the_programme(  # noqa: PLR0913
    container_tz: str,
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "site-b"
    )
    cancelled_day, replaced_day, missed_day, kept_day = (_day(n) for n in (1, 2, 3, 4))
    cancelled = await _weekly(admin, "Annulée", cancelled_day, (9, 10))
    await _weekly(admin, "Remplacée", replaced_day, (20, 21))
    await _weekly(admin, "Couverte", missed_day, (20, 21))
    await _weekly(admin, "Maintenue", kept_day, (9, 10))
    response = await admin.post(
        "/agenda/exceptions.json",
        json={"emission_id": cancelled, "date": cancelled_day.isoformat()},
    )
    assert response.status_code == 201
    await _create(
        admin,
        kind="set",
        title="Remplaçante",
        start=_wall(replaced_day, 20, 30),
        end=_wall(replaced_day, 21, 30),
    )
    [missed] = await _create(
        admin,
        kind="set",
        title="Manquée",
        start=_wall(missed_day, 20),
        end=_wall(missed_day, 21),
    )
    row = await AgendaDiffusion.from_id(dbsession, missed["id"])
    row.air_status = "missed"
    await dbsession.commit()

    site = _interface_client(app_configration, beets_integration)
    payload = await (await site.get("/public/programme.json")).get_json()
    assert [(item["title"], item["kind"]) for item in payload["items"]] == [
        ("Remplaçante", "set"),
        ("Maintenue", "emission"),
    ]


async def test_the_programme_keeps_the_weekly_grid_when_the_agenda_is_off(  # noqa: PLR0913
    container_tz: str,
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "site-c"
    )
    await _weekly(admin, "Matinale", _day(1), (8, 10))
    cancelled = await _weekly(admin, "Annulée", _day(2), (9, 10))
    response = await admin.post(
        "/agenda/exceptions.json",
        json={"emission_id": cancelled, "date": _day(2).isoformat()},
    )
    assert response.status_code == 201
    await _weekly(admin, "Remplacée", _day(3), (20, 21))
    await _create(
        admin,
        kind="set",
        title="Carte blanche",
        start=_wall(_day(3), 20, 30),
        end=_wall(_day(3), 21, 30),
    )
    site = _interface_client(app_configration, beets_integration)

    async def programme() -> list[tuple[str, str]]:
        response = await site.get("/public/programme.json")
        payload = await response.get_json()
        assert response.status_code == 200, payload
        assert payload["from"] == _day(0).isoformat()
        assert payload["to"] == _day(6).isoformat()
        return [(item["title"], item["kind"]) for item in payload["items"]]

    assert await programme() == [("Matinale", "emission"), ("Carte blanche", "set")]

    off = await admin.put("/agenda/settings.json", json={"enabled": False})
    assert off.status_code == 200
    # The weekly grid still airs, as the rest of the engine has it: without the
    # Agenda's cancellations, replacements or dated broadcasts.
    assert await programme() == [
        ("Matinale", "emission"),
        ("Annulée", "emission"),
        ("Remplacée", "emission"),
    ]


def _item(item_id: str, kind: str, queue: str = "autodj") -> RundownItem:
    return RundownItem(
        id=item_id,
        programming_version_id="pv-site",
        sequence=0,
        planned_at=datetime.now(),
        duration=180,
        kind=kind,
        when_mode="sequential",
        queue=queue,
        resource="x",
        status="played",
    )


def _log(  # noqa: PLR0913
    at: datetime,
    title: str,
    *,
    artist: str = "",
    album: str = "",
    source: str = "autodj",
    item: str | None = None,
    extra: dict | None = None,
) -> MetadataLog:
    return MetadataLog(
        on_air=at,
        source=source,
        title=title,
        artist=artist,
        album=album,
        rundown_item_id=item,
        extra=extra or {},
    )


async def _seed(
    dbsession: ormSession, items: list[RundownItem], logs: list[MetadataLog]
) -> None:
    dbsession.add(ProgrammingVersion(id="pv-site", source="test", description="site"))
    await dbsession.flush()
    dbsession.add_all(items)
    await dbsession.flush()
    dbsession.add_all(logs)
    await dbsession.commit()


def _played(at: datetime) -> str:
    """A local time of metadata_log, the container's wall clock, as the history
    gives it: at Paris time, offset, seconds."""
    return at.astimezone(PARIS).isoformat()


async def test_the_history_gives_music_only_newest_first(
    container_tz: str,
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
):
    now = datetime.now().replace(microsecond=0)

    def ago(minutes: int) -> datetime:
        return now - timedelta(minutes=minutes)

    await _seed(
        dbsession,
        [
            _item("ri-first", "musique"),
            _item("ri-anchored", "musique", "carts"),
            _item("ri-last", "musique"),
            _item("ri-cut", "musique"),
            _item("ri-cut-aired", "musique"),
            _item("ri-empty", "musique"),
            _item("ri-live", "musique"),
            _item("ri-jingle", "jingle", "jingles"),
            _item("ri-pub", "pub"),
            _item("ri-set", "son", "carts"),
            _item("ri-agenda", "emission", "carts"),
        ],
        [
            _log(
                ago(40),
                "Premier titre",
                artist="Groupe A",
                album="Album A",
                item="ri-first",
            ),
            _log(
                ago(37), "Ident", artist="Jingles", source="jingles", item="ri-jingle"
            ),
            _log(
                ago(35),
                "Titre calé",
                artist="Groupe B",
                source="carts",
                item="ri-anchored",
            ),
            # A sequential ad plays from the autodj queue: its kind tells it apart.
            _log(ago(32), "Spot", artist="Pubs", item="ri-pub"),
            _log(ago(30), "Set", artist="Lou Discret", source="carts", item="ri-set"),
            _log(ago(29), "Carte blanche", artist="Lou Discret", item="ri-agenda"),
            # A live line, linked by its title to a planned track.
            _log(
                ago(25),
                "Premier",
                artist="dj-direct-site",
                source="stream",
                item="ri-live",
            ),
            _log(ago(22), "Radio amie", artist="Relais", source="relay"),
            _log(ago(20), "Sans conducteur", artist="Groupe C"),
            _log(ago(18), "   ", artist="Groupe D", item="ri-empty"),
            # Logged at its start, then cut by a hard sync: it did air.
            _log(
                ago(15),
                "Titre coupé à l'antenne",
                artist="Groupe G",
                item="ri-cut-aired",
            ),
            _log(
                ago(13),
                "Titre coupé à l'antenne",
                artist="Groupe G",
                item="ri-cut-aired",
                extra={"skipped": True, "skip_reason": "hard_sync"},
            ),
            # Cut by a hard sync, without a line of its own: only the cut's.
            _log(
                ago(12),
                "Titre coupé",
                artist="Groupe E",
                item="ri-cut",
                extra={"skipped": True, "skip_reason": "hard_sync"},
            ),
            # Back to the first track after a cut: its rundown item logs again.
            _log(
                ago(10),
                "Premier titre",
                artist="Groupe A",
                album="Album A",
                item="ri-first",
            ),
            _log(ago(5), "Dernier titre", artist="Groupe F", item="ri-last"),
        ],
    )

    site = _interface_client(app_configration, beets_integration)
    response = await site.get("/public/historique.json")
    payload = await response.get_json()
    assert response.status_code == 200, payload
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["Cache-Control"] == "public, max-age=15"
    assert response.headers["X-Robots-Tag"] == "noindex"
    assert "Set-Cookie" not in response.headers
    assert payload == {
        "items": [
            {
                "played_at": _played(ago(5)),
                "title": "Dernier titre",
                "artist": "Groupe F",
                "album": "",
            },
            {
                "played_at": _played(ago(15)),
                "title": "Titre coupé à l'antenne",
                "artist": "Groupe G",
                "album": "",
            },
            {
                "played_at": _played(ago(35)),
                "title": "Titre calé",
                "artist": "Groupe B",
                "album": "",
            },
            {
                "played_at": _played(ago(40)),
                "title": "Premier titre",
                "artist": "Groupe A",
                "album": "Album A",
            },
        ]
    }


async def test_the_history_takes_a_limit(
    container_tz: str,
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
):
    now = datetime.now().replace(microsecond=0)
    numbers = range(1, 56)
    await _seed(
        dbsession,
        [_item(f"ri-{n}", "musique") for n in numbers],
        [
            _log(now - timedelta(minutes=n), f"Titre {n}", item=f"ri-{n}")
            for n in numbers
        ],
    )
    site = _interface_client(app_configration, beets_integration)

    async def titles(query: str = "") -> list[str]:
        response = await site.get(f"/public/historique.json{query}")
        payload = await response.get_json()
        assert response.status_code == 200, payload
        return [item["title"] for item in payload["items"]]

    first_twenty = [f"Titre {n}" for n in range(1, 21)]
    assert await titles() == first_twenty
    assert await titles("?limit=") == first_twenty
    assert await titles("?limit=3") == ["Titre 1", "Titre 2", "Titre 3"]
    assert len(await titles("?limit=500")) == 50

    for wrong in ("abc", "0", "-2", "2.5"):
        response = await site.get(f"/public/historique.json?limit={wrong}")
        body = await response.get_json()
        assert response.status_code == 400, body
        assert body["code"] == "validation_error"
        assert body["field"] == "limit"
        assert body["message"] == "Entre 1 et 50 titres."
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        assert response.headers["Cache-Control"] == "no-store"


async def test_the_history_keeps_the_last_seven_days(
    container_tz: str,
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
):
    # metadata_log keeps the container's wall clock, and so does the bound.
    now = datetime.now().replace(microsecond=0)
    await _seed(
        dbsession,
        [_item("ri-old", "musique"), _item("ri-week", "musique")],
        [
            _log(now - timedelta(days=7, hours=1), "Trop ancien", item="ri-old"),
            _log(now - timedelta(days=6, hours=23), "De la semaine", item="ri-week"),
        ],
    )
    site = _interface_client(app_configration, beets_integration)
    response = await site.get("/public/historique.json")
    payload = await response.get_json()
    assert response.status_code == 200, payload
    assert [item["title"] for item in payload["items"]] == ["De la semaine"]


SITE_ROUTES = ("/public/programme.json", "/public/historique.json")
CLOSED = "Cette station ne publie ni son programme ni ses derniers titres."


async def test_the_site_routes_answer_while_the_switch_is_absent_or_on(
    container_tz: str,
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
):
    site = _interface_client(app_configration, beets_integration)
    for value in (None, "1", "true"):
        if value is not None:
            await Setting.upsert(dbsession, SETTING_SITE_ROUTES, value)
            await dbsession.commit()
        for path in SITE_ROUTES:
            response = await site.get(path)
            payload = await response.get_json()
            assert response.status_code == 200, (value, path, payload)
            assert "items" in payload


async def test_the_site_routes_answer_404_when_the_switch_is_off(
    container_tz: str,
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
):
    site = _interface_client(app_configration, beets_integration)
    for value in ("0", "false", "off", ""):
        await Setting.upsert(dbsession, SETTING_SITE_ROUTES, value)
        await dbsession.commit()
        # The switch comes first: a wrong limit does not make it a 400.
        for path in (*SITE_ROUTES, "/public/historique.json?limit=abc"):
            response = await site.get(path)
            body = await response.get_json()
            assert response.status_code == 404, (value, path, body)
            assert body == {"error": CLOSED, "code": "not_found", "message": CLOSED}
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Access-Control-Allow-Origin"] == "*"
    # The switch closes the website's routes only.
    station = await site.get("/public/station.json")
    assert station.status_code == 200
