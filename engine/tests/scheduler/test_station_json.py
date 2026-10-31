"""The station's settings: GET /public/station.json, GET and PUT /station.json."""

import re

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.commands.install.installer import YAML_TEMPLATE
from radiotomate.domain.errors import DomainValidationError
from radiotomate.domain.station import KEYS, PUBLIC_KEYS, clean_value
from radiotomate.interface.csrf import HEADER_NAME
from radiotomate.models import Setting
from radiotomate.services.station import station_timezone
from tests.scheduler.test_admin_json import _admin_client
from tests.scheduler.test_agenda_public import _setup
from tests.scheduler.test_csrf import _csrf_config
from tests.scheduler.test_studio_json import _interface_client

STATION = {
    "name": "Radio Exemple",
    "short": "REX",
    "tagline": "La radio du quartier",
    "locale": "fr-FR",
    "public_stream_url": "https://radio.example/live.mp3",
    "now_url": "https://radio.example/now.json",
    "status_url": "https://radio.example/status-json.xsl",
    "harbor_host": "radio.example",
    "harbor_port": 6800,
    "harbor_mount": "/stream",
    "source_url": "https://code.radio.example/button",
}
UNSET = dict.fromkeys(KEYS)


async def _stored(dbsession: ormSession) -> dict:
    await dbsession.rollback()  # a fresh read, after the interface's writes
    rows = await dbsession.scalars(
        select(Setting).where(Setting.key.startswith("station."))
    )
    return {row.key: row.value for row in rows}


def test_the_yaml_has_no_station_section(app_configration: dict):
    # A dotted key of the settings table would mix with a YAML section.
    assert not re.search(r"^station\s*:", YAML_TEMPLATE, re.MULTILINE)
    assert "station" not in app_configration


@pytest.mark.parametrize(
    ("key", "raw", "stored"),
    [
        ("name", "  Radio Exemple ", "Radio Exemple"),
        ("name", "", None),
        ("name", "   ", None),
        ("name", None, None),
        ("locale", "fr", "fr"),
        ("locale", "fr-FR", "fr-FR"),
        (
            "now_url",
            "http://radio.example:8000/now.json ",
            "http://radio.example:8000/now.json",
        ),
        ("source_url", "HTTPS://radio.example/code", "HTTPS://radio.example/code"),
        ("harbor_host", "radio.example", "radio.example"),
        ("harbor_host", "192.0.2.10", "192.0.2.10"),
        ("harbor_host", "2001:db8::10", "2001:db8::10"),
        ("harbor_port", 6800, "6800"),
        ("harbor_port", " 8005 ", "8005"),
        ("harbor_port", "", None),
        ("harbor_port", None, None),
        ("harbor_mount", "/stream", "/stream"),
        ("harbor_mount", "/live.mp3", "/live.mp3"),
    ],
)
def test_a_value_is_trimmed_and_an_empty_one_unset(key, raw, stored):
    assert clean_value(key, raw) == stored


@pytest.mark.parametrize(
    ("key", "raw", "message"),
    [
        ("name", "x" * 81, "80 caractères au plus."),
        ("short", "x" * 17, "16 caractères au plus."),
        ("tagline", "Une\nradio", "Une seule ligne de texte."),
        ("name", 12, "Du texte attendu."),
        ("locale", "français", "Une langue comme fr ou fr-FR."),
        ("public_stream_url", "radio.example/live.mp3", "Une adresse complète"),
        ("now_url", "ftp://radio.example/now.json", "Une adresse complète"),
        ("status_url", "https://radio.example/status json", "Une adresse complète"),
        ("source_url", "https://radio.example:99999/", "Une adresse complète"),
        ("source_url", "https://", "Une adresse complète"),
        ("source_url", "https://radio.example/" + "x" * 500, "500 caractères"),
        # Served without a session: no account in an address.
        (
            "public_stream_url",
            "https://source:change-me@radio.example:8000/live.mp3",
            "sans identifiant ni mot de passe",
        ),
        (
            "status_url",
            "https://admin@radio.example/status-json.xsl",
            "sans identifiant",
        ),
        ("harbor_host", "https://radio.example", "sans http:// ni chemin"),
        ("harbor_host", "radio.example:6800", "le port a son propre champ"),
        ("harbor_host", "[2001:db8::10]", "sans crochets"),
        ("harbor_host", "radio example", "Un nom d'hôte comme radio.example"),
        ("harbor_port", 0, "Un port entre 1 et 65535."),
        ("harbor_port", 65536, "Un port entre 1 et 65535."),
        ("harbor_port", "6800a", "Un port entre 1 et 65535."),
        ("harbor_port", True, "Un port entre 1 et 65535."),
        ("harbor_port", 6800.5, "Un port entre 1 et 65535."),
        ("harbor_mount", "stream", "Un mount qui commence par /"),
        ("harbor_mount", "/", "Un mount qui commence par /"),
        ("harbor_mount", "/mon flux", "Un mount qui commence par /"),
    ],
)
def test_a_wrong_value_is_refused_on_its_field(key, raw, message):
    with pytest.raises(DomainValidationError) as refused:
        clean_value(key, raw)
    assert refused.value.field == key
    assert message in refused.value.message


def test_the_time_zone_is_the_containers_tz(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TZ", "America/Montreal")
    assert station_timezone() == "America/Montreal"
    monkeypatch.setenv("TZ", ":Europe/Paris")
    assert station_timezone() == "Europe/Paris"
    # Without TZ, the zone the C library reads.
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(
        "os.path.realpath", lambda _: "/usr/share/zoneinfo/Europe/Brussels"
    )
    assert station_timezone() == "Europe/Brussels"
    monkeypatch.setattr("os.path.realpath", lambda path: path)
    assert station_timezone() == "UTC"


async def test_a_listener_reads_the_public_part_without_a_session(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    listener = _interface_client(app_configration, beets_integration)
    response = await listener.get("/public/station.json")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert await response.get_json() == dict.fromkeys(PUBLIC_KEYS)

    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "st-pub"
    )
    assert (await admin.put("/station.json", json=STATION)).status_code == 200

    payload = await (await listener.get("/public/station.json")).get_json()
    assert payload == {key: STATION[key] for key in PUBLIC_KEYS}
    assert not [key for key in payload if key.startswith("harbor")]


async def test_the_station_settings_need_an_admin(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    anonymous = _interface_client(app_configration, beets_integration)
    for response in (
        await anonymous.get("/station.json"),
        await anonymous.put("/station.json", json={"name": "Pirate"}),
    ):
        assert response.status_code == 401
        assert (await response.get_json())["error"] == "unauthenticated"

    programmer = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "st-prog",
        {"live": True, "stream": True, "carts": True, "autodj": True},
    )
    for response in (
        await programmer.get("/station.json"),
        await programmer.put("/station.json", json={"name": "Pirate"}),
    ):
        assert response.status_code == 403
        assert (await response.get_json())["error"] == "forbidden"
    assert await _stored(dbsession) == {}


async def test_an_admin_reads_and_sets_the_station(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "st-admin"
    )
    empty = await admin.get("/station.json")
    assert empty.status_code == 200
    # The tests run with TZ=Europe/Paris, like the CI.
    assert await empty.get_json() == {**UNSET, "timezone": "Europe/Paris"}

    saved = await admin.put("/station.json", json=STATION)
    assert saved.status_code == 200, await saved.get_data(as_text=True)
    assert await saved.get_json() == {**STATION, "timezone": "Europe/Paris"}
    assert await (await admin.get("/station.json")).get_json() == {
        **STATION,
        "timezone": "Europe/Paris",
    }
    stored = await _stored(dbsession)
    assert stored["station.name"] == "Radio Exemple"
    assert stored["station.harbor_port"] == "6800"
    assert len(stored) == len(KEYS)


async def test_a_put_keeps_absent_keys_and_unsets_empty_ones(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "st-part"
    )
    await admin.put("/station.json", json=STATION)

    response = await admin.put(
        "/station.json",
        json={"name": "Radio Autre", "tagline": "", "short": None, "unknown": 1},
    )
    assert response.status_code == 200, await response.get_data(as_text=True)
    payload = await response.get_json()
    assert payload["name"] == "Radio Autre"
    assert payload["tagline"] is None
    assert payload["short"] is None
    assert payload["public_stream_url"] == STATION["public_stream_url"]
    assert payload["harbor_port"] == 6800
    stored = await _stored(dbsession)
    assert "station.tagline" not in stored
    assert "station.short" not in stored
    assert "station.unknown" not in stored


async def test_a_wrong_value_writes_nothing(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "st-wrong"
    )
    response = await admin.put(
        "/station.json",
        json={"name": "Radio Exemple", "public_stream_url": "radio.example/live"},
    )
    assert response.status_code == 400
    assert await response.get_json() == {
        "error": "Une adresse complète, en http:// ou https://.",
        "code": "validation_error",
        "message": "Une adresse complète, en http:// ou https://.",
        "field": "public_stream_url",
    }
    assert await _stored(dbsession) == {}


async def test_the_time_zone_is_read_only(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "st-tz"
    )
    # Sending back what was read changes nothing.
    same = await admin.put(
        "/station.json", json={"name": "Radio Exemple", "timezone": "Europe/Paris"}
    )
    assert same.status_code == 200
    assert (await same.get_json())["timezone"] == "Europe/Paris"

    other = await admin.put(
        "/station.json", json={"name": "Autre", "timezone": "America/Montreal"}
    )
    assert other.status_code == 400
    payload = await other.get_json()
    assert payload["field"] == "timezone"
    assert "TZ" in payload["message"]
    assert (await _stored(dbsession))["station.name"] == "Radio Exemple"


async def test_setting_the_station_needs_the_csrf_token(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        _csrf_config(app_configration),
        beets_integration,
        dbsession,
        users_password,
        "st-csrf",
    )
    denied = await admin.put("/station.json", json={"name": "Radio Exemple"})
    assert denied.status_code == 403
    assert (await denied.get_json())["error"] == "csrf_invalid"

    csrf = (await (await admin.get("/csrf.json")).get_json())["csrf_token"]
    allowed = await admin.put(
        "/station.json", json={"name": "Radio Exemple"}, headers={HEADER_NAME: csrf}
    )
    assert allowed.status_code == 200


async def test_a_guest_sees_the_station_name(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin, row = await _setup(
        app_configration, beets_integration, dbsession, users_password, "st-guest"
    )
    guest = _interface_client(app_configration, beets_integration)
    path = f"/public/guest/{row['guest']['token']}.json"
    # Unset, the name of the brand.
    assert (await (await guest.get(path)).get_json())["station"] == "BUTTON"

    await admin.put("/station.json", json={"name": "Radio Exemple"})
    assert (await (await guest.get(path)).get_json())["station"] == "Radio Exemple"
