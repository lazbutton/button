"""Les fiches pour la console (FON-26) : `GET /fiches.json`, `GET /fiches/<id>.json`
et `/fiches/reglages.json`, sur une bibliothèque de Beets temporaire."""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import quote

import pytest
from beets.library import Item, Library

from radiotomate.beets import BeetsIntegration
from radiotomate.fiches.evidence import to_json
from radiotomate.fiches.proposals import DeezerDetails, Details, Match, SearchResult
from radiotomate.models import Fiche, FicheProposition, Setting, User
from radiotomate.services import bank_titles
from radiotomate.services.fiches import SETTING_ACOUSTID_KEY, SETTING_ENABLED
from tests.scheduler.test_studio_json import _interface_client, _login

NOW = datetime(2026, 11, 14, 12, 0)

# (chemin sous /media, titre, artiste, niveau, statut, propositions)
TITLES = [
    ("10-rotation/a.mp3", "feeling good", "Nina Simone", "sûr", "trouvé", ["title"]),
    ("10-rotation/b.mp3", "sinnerman", "Nina Simone", "à revoir", "trouvé", ["year"]),
    ("20-archives/jazz/c.mp3", "so what", "Miles", "rapproché", "rapproché", ["title"]),
    ("20-archives/jazz/d.mp3", "rare", "Nobody", "introuvable", "introuvable", []),
    ("10-rotation/e.mp3", "panne", "Nobody", "erreur", "erreur", []),
]


def _beets(tmp_path) -> BeetsIntegration:
    lib = Library(str(tmp_path / "library.db"))
    for path, title, artist, *_ in TITLES:
        lib.add(
            Item(
                path=f"/media/{path}".encode(),
                title=title,
                artist=artist,
                length=172.0,
            )
        )
    beets = object.__new__(BeetsIntegration)
    beets.lib = lib
    return beets


def _evidence(title: str, artist: str) -> dict:
    match = Match(
        source="deezer",
        platform="deezer",
        id="1",
        url="https://www.deezer.com/track/1",
        title=title.title(),
        artists=(artist,),
        duration_s=170.0,
    )
    details = Details(deezer=DeezerDetails(track_id="1", title=title.title()))
    return to_json(SearchResult("trouvé", match, details), {})


async def _fiches(dbsession) -> None:
    for index, (_path, title, artist, level, status, fields) in enumerate(TITLES):
        fiche = Fiche(
            beets_id=index + 1,
            key=f"texte:{index}",
            text_key=f"texte:{index}",
            status=status,
            level=level,
            reasons=["une raison"] if level == "à revoir" else [],
            source="Deezer" if status != "erreur" else "",
            url="https://www.deezer.com/track/1" if fields else "",
            rules_version=1,
            evidence=_evidence(title, artist) if fields else None,
            error="MusicBrainz : 503" if status == "erreur" else "",
            searched_at=NOW + timedelta(seconds=10 * index),
            propositions=[
                FicheProposition(
                    field=field,
                    before=title if field == "title" else "0",
                    value=title.title() if field == "title" else "1965",
                    level=level,
                    state="proposée",
                )
                for field in fields
            ],
        )
        dbsession.add(fiche)
    await dbsession.commit()


async def _client(  # noqa: PLR0913
    app_configration,
    beets,
    dbsession,
    users_password,
    *,
    permissions: dict | None = None,
    on: bool = True,
):
    user = User(username="relire-json")
    user.update_password(users_password)
    user.permissions = {"autodj": True} if permissions is None else permissions
    dbsession.add(user)
    # On by default since FON-85: off, a station says so.
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1" if on else "0"))
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "relire-json", users_password)
    return client


async def _get(client, path: str) -> dict:
    response = await client.get(path)
    assert response.status_code == 200, await response.get_data()
    return await response.get_json()


def _titles(payload: dict) -> list[str]:
    return [row["title"] for row in payload["titles"]]


async def test_the_fiches_ask_for_the_programming_right(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password, permissions={}
    )
    for path in ("/fiches.json", "/fiches/1.json", "/fiches/reglages.json"):
        assert (await client.get(path)).status_code == 403
    response = await client.put("/fiches/reglages.json", json={"enabled": True})
    assert response.status_code == 403


async def test_switch_off_keeps_the_fiches_closed(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password, on=False
    )
    response = await client.get("/fiches.json")
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_tidy_off"


async def test_the_titles_to_read_their_counts_and_filters(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    await _fiches(dbsession)
    beets = _beets(tmp_path)
    client = await _client(app_configration, beets, dbsession, users_password)

    payload = await _get(client, "/fiches.json")
    # À relire : les titres qui ont une proposition qui attend, les plus sûrs d'abord.
    assert _titles(payload) == ["feeling good", "sinnerman", "so what"]
    assert payload["total"] == 3
    assert payload["next"] is None
    assert payload["enabled"] is False
    assert payload["progress"] == {"library": 5, "searched": 5, "remaining_hours": None}
    assert payload["statuses"] == {
        "trouvé": 2,
        "rapproché": 1,
        "introuvable": 1,
        "erreur": 1,
    }
    assert payload["levels"] == [
        {"value": "sûr", "count": 1},
        {"value": "à revoir", "count": 1},
        {"value": "rapproché", "count": 1},
    ]
    assert payload["fields"] == [
        {"value": "title", "count": 2},
        {"value": "year", "count": 1},
    ]
    assert payload["banks"] == [
        {"value": "rotation", "count": 3},
        {"value": "jazz", "count": 2},
    ]
    assert payload["failures"] == [{"error": "MusicBrainz : 503", "count": 1}]
    first = payload["titles"][0]
    assert (first["level"], first["zone"], first["path"]) == (
        "sûr",
        "rotation",
        "10-rotation/a.mp3",
    )
    assert first["propositions"] == [
        {
            "id": first["propositions"][0]["id"],
            "field": "title",
            "before": "feeling good",
            "value": "Feeling Good",
            "level": "sûr",
            "why": "",
            "source": "",
            "state": "proposée",
            "error": "",
        }
    ]

    level = quote("à revoir")
    assert _titles(await _get(client, f"/fiches.json?level={level}")) == ["sinnerman"]
    assert _titles(await _get(client, "/fiches.json?field=year")) == ["sinnerman"]
    assert _titles(await _get(client, "/fiches.json?bank=jazz")) == ["so what"]
    assert _titles(await _get(client, "/fiches.json?q=SINNER")) == ["sinnerman"]
    # Un niveau sans proposition : les introuvables, les titres en erreur.
    assert _titles(await _get(client, "/fiches.json?level=introuvable")) == ["rare"]
    assert _titles(await _get(client, "/fiches.json?level=erreur")) == ["panne"]
    assert _titles(await _get(client, f"/fiches.json?state={quote('écrite')}")) == []

    page = await _get(client, "/fiches.json?limit=2")
    assert (_titles(page), page["next"]) == (["feeling good", "sinnerman"], 2)
    rest = await _get(client, "/fiches.json?limit=2&offset=2")
    assert (_titles(rest), rest["next"]) == (["so what"], None)

    response = await client.get("/fiches.json?level=parfait")
    assert response.status_code == 400
    assert (await response.get_json())["field"] == "level"


async def test_the_search_says_how_long_is_left(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    await _fiches(dbsession)
    dbsession.add(Setting(key=SETTING_ENABLED, value="1"))
    await dbsession.commit()
    beets = _beets(tmp_path)
    for number in range(360):
        beets.lib.add(Item(path=f"/media/10-rotation/n{number}.mp3".encode()))
    client = await _client(app_configration, beets, dbsession, users_password)

    payload = await _get(client, "/fiches.json")

    # Dix secondes par titre, 360 titres pas encore cherchés : une heure.
    assert payload["enabled"] is True
    assert payload["progress"] == {
        "library": 365,
        "searched": 5,
        "remaining_hours": 1.0,
    }


async def test_one_title_with_its_evidence(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    await _fiches(dbsession)
    beets = _beets(tmp_path)
    client = await _client(app_configration, beets, dbsession, users_password)

    detail = await _get(client, "/fiches/1.json")

    assert detail["title"]["title"] == "feeling good"
    assert detail["title"]["duration"] == 172.0
    assert detail["fiche"]["level"] == "sûr"
    assert detail["fiche"]["searched_at"] == "2026-11-14T13:00+01:00"
    assert detail["fiche"]["next_at"] is None
    assert [one["field"] for one in detail["propositions"]] == ["title"]
    assert detail["evidence"]["found_at"] == "Deezer"
    assert detail["evidence"]["url"] == "https://www.deezer.com/track/1"
    assert detail["evidence"]["title"] == "Feeling Good"
    assert detail["evidence"]["duration"] == 170.0
    assert detail["listen"] == "/autodj/beets/1"
    # Sans preuves, un titre en erreur se lit aussi.
    failed = await _get(client, "/fiches/5.json")
    assert (failed["fiche"]["error"], failed["evidence"]) == ("MusicBrainz : 503", None)

    missing = await client.get("/fiches/99.json")
    assert missing.status_code == 404


async def test_the_settings_say_whether_a_key_is_set_never_its_value(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration,
        _beets(tmp_path),
        dbsession,
        users_password,
        permissions={"admin": True},
    )
    settings = await _get(client, "/fiches/reglages.json")
    assert settings["enabled"] is False
    assert settings["verdict"] is False
    assert settings["acoustid_key_set"] is False
    assert settings["sources"] == {
        "tidal": False,
        "apple_music": False,
        "bandcamp": False,
        "tidal_key_set": False,
    }
    assert "MusicBrainz" in settings["sent"]

    response = await client.put(
        "/fiches/reglages.json",
        json={
            "enabled": True,
            "verdict": True,
            "acoustid_key": "  cle-station  ",
            "tidal": True,
            "tidal_client_id": "id",
            "tidal_client_secret": "secret",
        },
    )
    assert response.status_code == 200, await response.get_data()
    written = await response.get_json()
    assert (written["enabled"], written["verdict"], written["acoustid_key_set"]) == (
        True,
        True,
        True,
    )
    assert written["sources"]["tidal"] is True
    assert written["sources"]["tidal_key_set"] is True
    body = (await response.get_data()).decode()
    assert "cle-station" not in body
    assert "secret" not in body
    row = await Setting.from_key(dbsession, SETTING_ACOUSTID_KEY)
    await dbsession.refresh(row)
    assert row.value == "cle-station"

    # Vidée, la clé de la station s'en va : celle de BUTTON revient.
    cleared = await client.put("/fiches/reglages.json", json={"acoustid_key": ""})
    assert (await cleared.get_json())["acoustid_key_set"] is False


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"enabled": "oui"}, "enabled"),
        ({"acoustid_key": 12}, "acoustid_key"),
        ({"tidal_client_secret": "x" * 201}, "tidal_client_secret"),
        ({"tidal_client_id": "deux mots"}, "tidal_client_id"),
        ({"acoustid_key": "cle\nX-Autre: 1"}, "acoustid_key"),
    ],
)
async def test_a_wrong_setting_is_refused_and_nothing_written(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, body, field
):
    client = await _client(
        app_configration,
        _beets(tmp_path),
        dbsession,
        users_password,
        permissions={"admin": True},
    )
    response = await client.put("/fiches/reglages.json", json={"verdict": True, **body})
    assert response.status_code == 400
    assert (await response.get_json())["field"] == field
    assert (await _get(client, "/fiches/reglages.json"))["verdict"] is False


async def test_only_an_admin_writes_the_settings(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets = _beets(tmp_path)
    client = await _client(app_configration, beets, dbsession, users_password)
    assert (await client.get("/fiches/reglages.json")).status_code == 200
    response = await client.put("/fiches/reglages.json", json={"enabled": True})
    assert response.status_code == 403
