"""GET /media/titles.json: the bank's table, in a temporary Beets library (FON-64)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from beets.library import Item, Library

from radiotomate.beets import BeetsIntegration
from radiotomate.models import Setting, User
from radiotomate.services import bank_titles
from tests.scheduler.test_studio_json import _interface_client, _login

if TYPE_CHECKING:
    from pathlib import Path

# (path below /media, title, artist, album, year, genre, length, famille)
TITLES = [
    ("10-rotation/a.mp3", "Été indien", "Orage", "Ciel", 2019, "Jazz", 200.0, "jazz"),
    ("10-rotation/b.mp3", "Brume", "Madame Orage", "", 0, "Pop", 180.0, ""),
    ("20-archives/nuit/c.mp3", "Comète", "Orage", "Ciel", 2015, "Jazz", 240.0, "jazz"),
    (
        "20-archives/nuit/sub/d.flac",
        "Dune",
        "Zéphyr",
        "Sable",
        2021,
        "",
        0.0,
        "electro",
    ),
    ("20-archives/concerts/e.mp3", "Écho", "", "Live", 2003, "Rock", 300.0, ""),
]


def _beets(tmp_path: Path) -> BeetsIntegration:
    lib = Library(str(tmp_path / "library.db"))
    for rel, title, artist, album, year, genre, length, famille in TITLES:
        item = Item(
            path=f"/media/{rel}".encode(),
            title=title,
            artist=artist,
            album=album,
            year=year,
            genre=genre,
            length=length,
        )
        lib.add(item)
        if famille:
            item["famille"] = famille
            item.store()
    beets = object.__new__(BeetsIntegration)
    beets.lib = lib
    return beets


async def _client(app_configration, beets, dbsession, users_password, *, on=True):
    user = User(username="banque-json")
    user.update_password(users_password)
    dbsession.add(user)
    if on:
        dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "banque-json", users_password)
    return client


async def _titles(client, query: str = "") -> dict:
    response = await client.get(f"/media/titles.json{query}")
    assert response.status_code == 200, await response.get_data()
    return await response.get_json()


def _names(payload: dict) -> list[str]:
    return [row["title"] for row in payload["titles"]]


async def test_titles_ask_for_a_session(raw_app, app_configration, tmp_path):
    client = _interface_client(app_configration, _beets(tmp_path))
    response = await client.get("/media/titles.json")
    assert response.status_code == 401


async def test_switch_off_keeps_the_table_closed(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password, on=False
    )
    response = await client.get("/media/titles.json")
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_tidy_off"
    account = await (await client.get("/account.json")).get_json()
    assert account["features"] == {"bank_tidy": False, "title_edits": False}


@pytest.mark.parametrize("value", ["0", "false", "off", ""])
async def test_switch_turned_off_by_value(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, value
):
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value=value))
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password, on=False
    )
    assert (await client.get("/media/titles.json")).status_code == 409


async def test_a_row_says_everything_the_table_shows(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    account = await (await client.get("/account.json")).get_json()
    assert account["features"] == {"bank_tidy": True, "title_edits": True}
    payload = await _titles(client, "?q=dune")
    assert payload["total"] == len(TITLES)
    assert payload["matched"] == 1
    (row,) = payload["titles"]
    assert isinstance(row.pop("id"), int)
    assert row == {
        "title": "Dune",
        "artist": "Zéphyr",
        "album": "Sable",
        "year": 2021,
        "genre": "",
        "famille": "electro",
        "famille_label": "Électro",
        "duration": None,
        "zone": "collections",
        "collection": "nuit",
        "path": "20-archives/nuit/sub/d.flac",
        "missing": ["genre"],
    }


async def test_the_table_filters_by_each_column(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    sort = "&sort=title"
    assert _names(await _titles(client, f"?collection=nuit{sort}")) == [
        "Comète",
        "Dune",
    ]
    assert _names(await _titles(client, f"?collection=rotation{sort}")) == [
        "Brume",
        "Été indien",
    ]
    # An artist is that artist alone, not a name that holds it.
    assert _names(await _titles(client, f"?artist=orage{sort}")) == [
        "Comète",
        "Été indien",
    ]
    assert _names(await _titles(client, f"?famille=jazz{sort}")) == [
        "Comète",
        "Été indien",
    ]
    # Given empty, a filter takes the titles where the field is empty.
    assert _names(await _titles(client, f"?famille={sort}")) == ["Brume", "Écho"]
    assert _names(await _titles(client, "?artist=")) == ["Écho"]
    assert _names(await _titles(client, f"?album=ciel{sort}")) == [
        "Comète",
        "Été indien",
    ]
    assert _names(await _titles(client, f"?genre=Jazz&year=2015{sort}")) == ["Comète"]
    # The text search forgets accents and case, and reads the path too.
    assert _names(await _titles(client, f"?q=%C3%89T%C3%89%20INDIEN{sort}")) == [
        "Été indien"
    ]
    assert _names(await _titles(client, f"?q=concerts{sort}")) == ["Écho"]
    assert _names(await _titles(client, f"?q=orage ciel{sort}")) == [
        "Comète",
        "Été indien",
    ]


async def test_the_table_sorts_and_pages(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    # By artist by default; an empty artist goes last, then title within an artist.
    assert _names(await _titles(client)) == [
        "Brume",
        "Comète",
        "Été indien",
        "Dune",
        "Écho",
    ]
    # Empty values stay last, whichever the order.
    years = await _titles(client, "?sort=year&order=desc")
    assert [row["year"] for row in years["titles"]] == [2021, 2019, 2015, 2003, None]
    durations = await _titles(client, "?sort=duration")
    assert [row["duration"] for row in durations["titles"]][-1] is None
    page = await _titles(client, "?sort=title&offset=2&limit=2")
    assert _names(page) == ["Dune", "Écho"]
    assert (page["offset"], page["limit"], page["matched"]) == (2, 2, len(TITLES))


async def test_the_facets_count_the_whole_bank(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    payload = await _titles(client, "?q=dune&facets=collection,artist,famille,album")
    facets = payload["facets"]
    assert facets["collection"] == [
        {"value": "concerts", "label": "concerts", "count": 1},
        {"value": "nuit", "label": "nuit", "count": 2},
        {"value": "rotation", "label": "rotation", "count": 2},
    ]
    assert facets["artist"] == [
        {"value": "Madame Orage", "label": "Madame Orage", "count": 1},
        {"value": "Orage", "label": "Orage", "count": 2},
        {"value": "Zéphyr", "label": "Zéphyr", "count": 1},
        {"value": "", "label": "", "count": 1},
    ]
    assert facets["famille"] == [
        {"value": "electro", "label": "Électro", "count": 1},
        {"value": "jazz", "label": "Jazz", "count": 2},
        {"value": "", "label": "", "count": 2},
    ]
    assert [row["value"] for row in facets["album"]] == ["Ciel", "Live", "Sable", ""]
    assert "facets" not in payload or (await _titles(client))["facets"] == {}


@pytest.mark.parametrize(
    "query", ["?sort=size", "?order=up", "?facets=genre", "?limit=x", "?year=deux"]
)
async def test_a_wrong_query_is_refused(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, query
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    response = await client.get(f"/media/titles.json{query}")
    assert response.status_code == 400
    assert (await response.get_json())["code"] == "validation_error"


def test_a_path_is_read_below_the_bank():
    assert (
        bank_titles.bank_rel(b"/srv/m/10-rotation/a.mp3", "/srv/m")
        == "10-rotation/a.mp3"
    )
    # Outside MEDIA_ROOT, as the demo's: from its first bank folder.
    assert (
        bank_titles.bank_rel("/x/radio_data/20-archives/n/a.mp3", "/media")
        == "20-archives/n/a.mp3"
    )
    assert bank_titles.place_of("20-archives/nuit/a.mp3") == ("collections", "nuit")
    assert bank_titles.place_of("20-archives/a.mp3") == ("collections", "")
    assert bank_titles.place_of("30-habillage/jingles/a.mp3") == ("habillage", "")


def test_the_genres_of_beets_2_14_read_as_one_text():
    row = (1, b"/media/10-rotation/a.mp3", "T", "A", "B", 0, "Jazz\\␀Soul", 1.0, None)
    assert bank_titles.title_of(row, "/media")["genre"] == "Jazz, Soul"


def test_seven_thousand_titles_read_fast():
    """The page itself, without Beets: well under the half-second of the fiche."""
    import time

    rows = [
        (
            index,
            f"/media/20-archives/c{index % 40}/{index}.mp3".encode(),
            f"Titre {index}",
            f"Artiste {index % 900}",
            f"Album {index % 1500}",
            1960 + index % 60,
            "Jazz",
            180.0,
            "jazz" if index % 3 else None,
        )
        for index in range(7000)
    ]
    query = bank_titles.TitleQuery(sort="famille", facets=("artist",))
    started = time.perf_counter()
    payload = bank_titles.titles_page(rows, query, "/media")
    assert time.perf_counter() - started < 0.5
    assert payload["matched"] == 7000
