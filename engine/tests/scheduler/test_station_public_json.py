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
)
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


async def test_the_programme_gives_titles_times_and_kinds_only(
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


async def test_a_weekly_show_cancelled_or_replaced_leaves_the_programme(
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


async def test_the_programme_is_empty_when_the_agenda_is_off(
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
    await _create(
        admin,
        kind="set",
        title="Carte blanche",
        start=_wall(_day(2), 22),
        end=_wall(_day(2), 23),
    )
    site = _interface_client(app_configration, beets_integration)
    before = await (await site.get("/public/programme.json")).get_json()
    assert len(before["items"]) == 2

    off = await admin.put("/agenda/settings.json", json={"enabled": False})
    assert off.status_code == 200
    response = await site.get("/public/programme.json")
    payload = await response.get_json()
    assert response.status_code == 200, payload
    assert payload["items"] == []
    assert payload["from"] == _day(0).isoformat()
    assert payload["to"] == _day(6).isoformat()


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
    """A local time of metadata_log as the history gives it: offset, seconds."""
    return at.replace(tzinfo=PARIS).isoformat()


async def test_the_history_gives_music_only_newest_first(
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
            _log(
                ago(16), "En attente de métadonnées", artist="BUTTON", item="ri-empty"
            ),
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
