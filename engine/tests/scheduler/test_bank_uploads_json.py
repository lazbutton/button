"""Reconnaître un fichier dès l'envoi (FON-82) : `POST /fiches/envois.json`, sur une
bibliothèque de Beets temporaire.

Un doublon se range comme les autres, et se signale : la route ne fait que lire. Le
doublon est celui que la santé de la banque compte (FON-72).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from beets.library import Item, Library

from radiotomate.beets import BeetsIntegration
from radiotomate.fiches.evidence import to_json
from radiotomate.fiches.proposals import DeezerDetails, Details, Match, SearchResult
from radiotomate.models import Fiche, Setting
from radiotomate.services.bank_health import duplicates
from radiotomate.services.bank_titles import title_of
from radiotomate.services.fiches import SETTING_ENABLED
from tests.scheduler.test_fiches_json import _client

# (chemin sous /media, artiste, titre, durée)
TITLES = [
    ("10-rotation/Nina Simone - Feeling Good.mp3", "Nina Simone", "Feeling Good", 172),
    # Envoyé dans la collection « jazz », en wav : rangé en flac.
    ("20-archives/jazz/feeling good.flac", "NINA SIMONE", "Feeling good", 173.5),
    # Le même texte, une autre prise : 20 s de plus, pas un doublon.
    ("20-archives/jazz/Feeling Good (live).mp3", "Nina Simone", "Feeling Good", 192),
    (
        "10-rotation/Les Marées Hautes - Estuaire.mp3",
        "les marees hautes",
        "estuaire",
        201,
    ),
]


def _beets(tmp_path) -> BeetsIntegration:
    lib = Library(str(tmp_path / "library.db"))
    for path, artist, title, length in TITLES:
        lib.add(
            Item(
                path=f"/media/{path}".encode(),
                artist=artist,
                title=title,
                length=length,
            )
        )
    beets = object.__new__(BeetsIntegration)
    beets.lib = lib
    return beets


def _found(title: str, artists: str) -> dict:
    match = Match(
        source="deezer",
        platform="deezer",
        id="1",
        url="https://www.deezer.com/track/1",
        title=title,
        artists=(artists,),
        duration_s=201.0,
    )
    details = Details(deezer=DeezerDetails(track_id="1", title=title))
    return to_json(SearchResult("trouvé", match, details), {})


async def _uploads(client, *files) -> dict:
    body = {"files": [{"dest": dest, "name": name} for dest, name in files]}
    response = await client.post("/fiches/envois.json", json=body)
    assert response.status_code == 200, await response.get_data()
    return await response.get_json()


async def test_a_duplicate_sent_is_said_as_the_health_of_the_bank_says_it(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets = _beets(tmp_path)
    client = await _client(app_configration, beets, dbsession, users_password)

    report = await _uploads(client, ("jazz", "feeling good.wav"))

    (sent,) = report["files"]
    assert (sent["in_bank"], sent["id"]) == (True, 2)
    assert sent["path"] == "20-archives/jazz/feeling good.flac"
    assert [one["path"] for one in sent["duplicates"]] == [
        "10-rotation/Nina Simone - Feeling Good.mp3"
    ]
    assert sent["duplicates"][0]["collection"] == "rotation"
    # La santé de la banque lit le même doublon, ni plus ni moins.
    entries = [title_of(row, "/media") for row in await beets.title_rows()]
    (group,) = duplicates(entries)["groups"]
    assert sorted(one["id"] for one in group["titles"]) == sorted(
        [sent["id"], *(one["id"] for one in sent["duplicates"])]
    )
    # L'autre prise, 20 s plus longue, n'en est pas un.
    report = await _uploads(client, ("jazz", "Feeling Good (live).mp3"))
    assert report["files"][0]["duplicates"] == []


async def test_a_file_not_yet_in_the_library_waits(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    report = await _uploads(
        client,
        ("rotation", "Inconnu - Pas encore.mp3"),
        # Le même nom, dans une autre destination : pas lui.
        ("jazz", "Nina Simone - Feeling Good.mp3"),
    )
    assert [one["in_bank"] for one in report["files"]] == [False, False]
    assert report["fiches"] is False


async def test_a_title_recognized_by_the_search_says_what_it_is(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    dbsession.add(Setting(key=SETTING_ENABLED, value="1"))
    dbsession.add(
        Fiche(
            beets_id=4,
            key="texte:4",
            text_key="texte:4",
            status="trouvé",
            level="sûr",
            reasons=[],
            source="Deezer",
            url="https://www.deezer.com/track/1",
            rules_version=1,
            evidence=_found("Estuaire", "Les Marées Hautes"),
            searched_at=datetime(2026, 11, 15, 12, 0),
        )
    )
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )

    report = await _uploads(
        client,
        ("rotation", "Les Marées Hautes - Estuaire.wav"),
        ("rotation", "Nina Simone - Feeling Good.mp3"),
    )

    assert report["fiches"] is True
    recognized, waiting = report["files"]
    assert recognized["recognized"] == {
        "artist": "Les Marées Hautes",
        "title": "Estuaire",
        "level": "sûr",
        "source": "Deezer",
    }
    assert recognized["searched"] is True
    # Pas encore cherché : la console attend.
    assert (waiting["recognized"], waiting["searched"]) == (None, False)


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"files": "a.mp3"},
        {"files": [{"dest": "rotation", "name": "../x.mp3"}]},
        {"files": [{"dest": "../10-rotation", "name": "x.mp3"}]},
        {"files": [{"dest": "rotation", "name": ".cache"}]},
        {"files": [{"dest": "rotation", "name": f"{n}.mp3"} for n in range(101)]},
    ],
)
async def test_a_wrong_list_is_refused(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, body
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    response = await client.post("/fiches/envois.json", json=body)
    assert response.status_code == 400


async def test_behind_the_tidying(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    body = {"files": [{"dest": "rotation", "name": "a.mp3"}]}
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password, on=False
    )
    response = await client.post("/fiches/envois.json", json=body)
    assert response.status_code == 409


async def test_behind_the_programming_right(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    body = {"files": [{"dest": "rotation", "name": "a.mp3"}]}
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password, permissions={}
    )
    assert (await client.post("/fiches/envois.json", json=body)).status_code == 403
