"""La santé de la banque (FON-72).

Une banque semée de chaque défaut : un artiste écrit de trois façons, un doublon,
des fichiers mal nommés, des fiches incomplètes, le genre « Archive », des
fichiers que la bibliothèque n'a pas. Chaque compte, puis la route, qui compte à
part et recompte après un geste, et une correction qui fait baisser le compte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainValidationError
from radiotomate.interface import bank_health as route
from radiotomate.models import JournalEntry, Setting
from radiotomate.services.bank_health import (
    MAX_TITLES,
    bank_health,
    check_model,
    duplicates,
    health_on,
    misnamed,
    spellings,
)
from radiotomate.services.bank_titles import title_of
from radiotomate.services.title_renames import plan_renames, rename_titles
from tests.scheduler.test_bank_moves import media, place  # noqa: F401
from tests.scheduler.test_bank_moves_journal import tidying  # noqa: F401
from tests.scheduler.test_media_titles_json import _beets, _client
from tests.scheduler.test_title_renames import _ada

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session as ormSession

    from radiotomate.services.bank_lock import BeetsPlace

ROOT = "/media"

# (id, path below the bank, title, artist, album, year, genre, length, famille)
SEEDED = [
    (
        1,
        "10-rotation/estuaire.mp3",
        "Estuaire",
        "Les Marées Hautes",
        "Delta",
        2020,
        "Jazz",
        200.0,
        "jazz",
    ),
    (
        2,
        "10-rotation/Les Marées Hautes - Delta.mp3",
        "Delta",
        "Les Marées Hautes",
        "Delta",
        2020,
        "Jazz",
        190.0,
        "jazz",
    ),
    (
        3,
        "20-archives/nuit/ressac.mp3",
        "Ressac",
        "les marees hautes",
        "Delta",
        2020,
        "Jazz",
        210.0,
        "jazz",
    ),
    (
        4,
        "20-archives/nuit/estuaire-bis.flac",
        "Estuaire",
        "LES MARÉES HAUTES",
        "Delta",
        2020,
        "Jazz",
        201.5,
        "jazz",
    ),
    (
        5,
        "20-archives/nuit/estuaire-live.mp3",
        "Estuaire (live)",
        "Les Marées Hautes",
        "Live",
        2021,
        "Jazz",
        260.0,
        "jazz",
    ),
    (
        6,
        "20-archives/vieux/a.mp3",
        "Avant",
        "Orage",
        "Ciel",
        1999,
        "Archive",
        180.0,
        "rock",
    ),
    (
        7,
        "20-archives/vieux/b.mp3",
        "Bientôt",
        "Orage",
        "Ciel",
        1999,
        "Rock\\␀Archive",
        181.0,
        "rock",
    ),
    (8, "10-rotation/c.mp3", "Comète", "Zéphyr", "", 0, "", 150.0, ""),
]


def _rows(seeded=SEEDED) -> list[tuple]:
    return [
        (beets_id, f"{ROOT}/{rel}".encode(), *rest) for beets_id, rel, *rest in seeded
    ]


def _entries(seeded=SEEDED) -> list[dict]:
    return [title_of(row, ROOT) for row in _rows(seeded)]


def _ids(titles: list[dict]) -> list[int]:
    return [title["id"] for title in titles]


def test_an_artist_written_three_ways_is_one_group():
    found = spellings(_entries())
    assert found["count"] == 1
    assert found["titles"] == 5
    group = found["groups"][0]
    assert group["suggested"] == "Les Marées Hautes"
    assert group["spellings"] == [
        {"value": "Les Marées Hautes", "count": 3},
        {"value": "LES MARÉES HAUTES", "count": 1},
        {"value": "les marees hautes", "count": 1},
    ]
    assert sorted(_ids(group["titles"])) == [1, 2, 3, 4, 5]


def test_a_tie_goes_to_the_spelling_with_accents_and_capitals():
    seeded = [
        (1, "10-rotation/a.mp3", "A", "les marees hautes", "", 0, "", 100.0, ""),
        (2, "10-rotation/b.mp3", "B", "Les Marées Hautes", "", 0, "", 100.0, ""),
    ]
    assert spellings(_entries(seeded))["groups"][0]["suggested"] == "Les Marées Hautes"


def test_a_duplicate_is_the_same_title_within_two_seconds():
    found = duplicates(_entries())
    assert found["count"] == 1
    assert [_ids(group["titles"]) for group in found["groups"]] == [[1, 4]]
    # 3 s apart: another take.
    seeded = [
        (9, "10-rotation/x.mp3", "Estuaire", "Les Marées Hautes", "", 0, "", 204.0, "")
    ]
    assert [
        _ids(group["titles"])
        for group in duplicates(_entries([SEEDED[0], *seeded]))["groups"]
    ] == []


def test_a_title_without_duration_is_no_duplicate():
    seeded = [
        (1, "10-rotation/a.mp3", "Un", "Ada", "", 0, "", 0.0, ""),
        (2, "10-rotation/b.mp3", "Un", "Ada", "", 0, "", 0.0, ""),
    ]
    assert duplicates(_entries(seeded))["count"] == 0


@pytest.mark.parametrize(
    ("model", "ids"),
    [
        # 2 already says « Les Marées Hautes - Delta.mp3 ».
        ("artiste-titre", [6, 7, 8, 1, 4, 5, 3]),
        ("titre", [6, 7, 8, 1, 2, 4, 5, 3]),
    ],
)
def test_misnamed_files_follow_the_model(model, ids):
    found = misnamed(_entries(), model)
    assert sorted(_ids(found["titles"])) == sorted(ids)
    named = {title["id"]: title["to"] for title in found["titles"]}
    if model == "artiste-titre":
        assert named[3] == "les marees hautes - Ressac.mp3"
        assert 2 not in named


def test_a_name_with_decomposed_accents_is_well_named():
    nfd = "10-rotation/Zéphyr - Comète.mp3"
    seeded = [(1, nfd, "Comète", "Zéphyr", "", 0, "", 100.0, "")]
    assert misnamed(_entries(seeded), "artiste-titre")["count"] == 0


def test_every_count_of_the_seeded_bank(tmp_path: Path):
    root = tmp_path / "media"
    for rel in [
        "10-rotation/estuaire.mp3",
        "20-archives/nuit/ressac.mp3",
        "20-archives/nuit/orphelin.flac",
        "20-archives/nuit/sous/perdu.MP3",
        "10-rotation/.cache.mp3",
        "10-rotation/envoi.mp3.partial",
        "20-archives/nuit/pochette.jpg",
        "20-archives/.Trash/vieux.mp3",
        "30-habillage/jingle.mp3",
    ]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(b"")
    rows = [
        (beets_id, f"{root}/{rel}".encode(), *rest) for beets_id, rel, *rest in SEEDED
    ]

    health = bank_health(rows, root, "artiste-titre")

    assert health["figures"]["titles"] == 8
    # 8 has neither album, year, genre nor family; 6 and 7 are complete.
    assert health["figures"]["complete"] == 7
    assert health["figures"]["without_family"] == 1
    assert [(row["value"], row["count"]) for row in health["figures"]["families"]] == [
        ("jazz", 5),
        ("rock", 2),
    ]
    assert health["spellings"]["count"] == 1
    assert health["duplicates"]["count"] == 1
    assert health["misnamed"]["count"] == 7
    assert health["incomplete"]["count"] == 1
    assert {row["field"]: row["count"] for row in health["incomplete"]["fields"]} == {
        "title": 0,
        "artist": 0,
        "album": 1,
        "year": 1,
        "genre": 1,
        "famille": 1,
    }
    assert [
        (title["id"], title["genre_without"]) for title in health["archive"]["titles"]
    ] == [(6, ""), (7, "Rock")]
    assert health["unindexed"] == {
        "count": 2,
        "paths": ["20-archives/nuit/orphelin.flac", "20-archives/nuit/sous/perdu.MP3"],
    }


def test_a_lot_lists_no_more_than_a_lot_takes():
    seeded = [
        (
            i,
            f"10-rotation/{i}.mp3",
            f"T{i}",
            "Ada",
            "A",
            2000,
            "Jazz",
            100.0 + i,
            "jazz",
        )
        for i in range(1, MAX_TITLES + 20)
    ]
    found = misnamed(_entries(seeded), "artiste-titre")
    assert found["count"] == MAX_TITLES + 19
    assert len(found["titles"]) == MAX_TITLES


def test_the_model_is_checked():
    assert check_model(None) == "artiste-titre"
    with pytest.raises(DomainValidationError):
        check_model("n'importe")


async def test_a_renaming_takes_the_title_out_of_the_count(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
    tidying: None,  # noqa: F811
):
    ada = _ada(place, media)
    _ada(place, media, "Ada - Deux.mp3", title="Deux")
    beets = object.__new__(BeetsIntegration)
    beets.lib = place.lib

    before = bank_health(beets._title_rows(), media, "artiste-titre")
    assert _ids(before["misnamed"]["titles"]) == [ada.id]

    plans = await plan_renames(dbsession, place, [ada.id], "artiste-titre")
    await rename_titles(dbsession, place, plans, username="prog")

    after = bank_health(beets._title_rows(), media, "artiste-titre")
    assert after["misnamed"]["count"] == 0
    assert after["unindexed"]["count"] == 0


@pytest.fixture(autouse=True)
def _fresh_counts():
    route.forget()
    yield
    route.forget()


async def _health(client, query: str = "") -> dict:
    response = await client.get(f"/media/health.json{query}")
    assert response.status_code == 200, await response.get_data()
    return await response.get_json()


async def test_the_route_counts_apart_then_again_after_a_gesture(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, monkeypatch
):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )

    first = await _health(client)
    assert first["computing"] is True
    assert first["health"] is None
    await route.settle()

    counted = await _health(client)
    assert counted["computing"] is False
    assert counted["computed_at"] is not None
    assert counted["error"] is None
    assert counted["health"]["figures"]["titles"] == 5
    assert counted["health"]["model"] == "artiste-titre"
    # Nothing has changed: the count stands.
    assert (await _health(client))["computing"] is False

    dbsession.add(JournalEntry(gesture="edit", username="prog", titles=1))
    await dbsession.commit()
    assert (await _health(client))["computing"] is True
    await route.settle()

    # Each model has its own count, and « Recompter » counts again.
    assert (await _health(client, "?model=titre"))["computing"] is True
    await route.settle()
    assert (await _health(client, "?model=titre&refresh=1"))["computing"] is True
    await route.settle()


async def test_the_route_checks_its_model_and_its_switches(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    response = await client.get("/media/health.json?model=autre")
    assert response.status_code == 400

    dbsession.add(Setting(key="features.bank_health", value="0"))
    await dbsession.commit()
    assert not await health_on(dbsession)
    response = await client.get("/media/health.json")
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_health_off"


async def test_the_route_waits_for_the_general_switch(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password, on=False
    )
    response = await client.get("/media/health.json")
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_tidy_off"
    assert not await health_on(dbsession)
