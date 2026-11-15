"""Les arrivées de la banque (FON-81).

Des titres arrivés depuis 30 jours et d'autres plus vieux : la fiche proposée, le
nom d'après le modèle une fois les propositions sûres acceptées, un doublon dans
toute la banque, et ce qui est prêt à ranger ou attend une relecture. Puis la
route, pour le Programmateur, derrière ses interrupteurs.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING

from beets.library import Item, Library

from radiotomate.beets import BeetsIntegration
from radiotomate.models import Setting
from radiotomate.models.fiche import PROPOSED, REFUSED
from radiotomate.services.bank_arrivals import DAYS, arrivals, arrivals_on, since
from tests.scheduler.test_admin_json import _admin_client

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session as ormSession

ROOT = "/media"
NOW = 1_800_000_000.0
OLD = NOW - 40 * 86400

# (id, path below the bank, title, artist, album, year, genre, length, famille)
BANK = [
    (1, "10-rotation/new1.mp3", "estuaire", "les marees hautes", "", 0, "", 200.0, ""),
    (2, "10-rotation/new2.mp3", "Delta", "Orage", "Ciel", 2020, "Jazz", 190.0, ""),
    (3, "10-rotation/Ada - Avant.mp3", "Avant", "Ada", "", 0, "", 181.0, ""),
    (4, "20-archives/nuit/ressac.mp3", "Ressac", "Zéphyr", "", 0, "", 210.0, ""),
    (5, "20-archives/nuit/Zéphyr - Brume.mp3", "Brume", "Zéphyr", "", 0, "", 220.0, ""),
    (6, "20-archives/nuit/avant.mp3", "Avant", "Ada", "", 0, "", 180.0, ""),
    (7, "30-habillage/jingle.mp3", "Jingle", "Station", "", 0, "", 5.0, ""),
]
ADDED = {
    1: NOW - 60,
    2: NOW - 120,
    4: NOW - 3600,
    5: NOW - 7200,
    6: NOW - 86400,
    7: NOW,
}


def _rows() -> list[tuple]:
    return [(i, f"{ROOT}/{rel}".encode(), *rest) for i, rel, *rest in BANK]


def _one(pid, field, before, value, level="sûr", state=PROPOSED):  # noqa: PLR0913
    return SimpleNamespace(
        id=pid,
        field=field,
        before=before,
        value=value,
        level=level,
        why="",
        source="deezer",
        state=state,
        error="",
    )


def _fiche(*propositions, level="sûr"):
    return SimpleNamespace(
        status="trouvé", level=level, propositions=list(propositions)
    )


FICHES = {
    1: _fiche(
        _one(11, "artist", "les marees hautes", "Les Marées Hautes"),
        _one(12, "title", "estuaire", "Estuaire"),
        _one(13, "year", "", "2019", state=REFUSED),
    ),
    2: _fiche(
        _one(21, "album", "Ciel", "Ciel bleu"),
        _one(22, "artist", "Orage", "Madame Orage", level="à revoir"),
        level="à revoir",
    ),
}


def _by_id(payload: dict) -> dict[int, dict]:
    return {title["id"]: title for title in payload["titles"]}


def test_the_arrivals_are_the_new_titles_of_the_rotation_and_the_collections():
    payload = arrivals(_rows(), ADDED, FICHES, "artiste-titre", ROOT)
    # Newest first; neither the old title nor the station's sound.
    assert [title["id"] for title in payload["titles"]] == [1, 2, 4, 5, 6]
    assert payload["days"] == DAYS
    assert payload["titles"][0]["added"] == "2027-01-15T08:59+01:00"


def test_a_sure_fiche_gives_the_name_it_will_take():
    title = _by_id(arrivals(_rows(), ADDED, FICHES, "artiste-titre", ROOT))[1]
    assert [one["id"] for one in title["propositions"]] == [11, 12]
    assert title["sure"] == [11, 12]
    assert title["review"] is False
    assert title["to"] == "Les Marées Hautes - Estuaire.mp3"
    assert title["ready"] is True
    assert title["searched"] is True


def test_a_fiche_to_review_is_not_ready():
    title = _by_id(arrivals(_rows(), ADDED, FICHES, "artiste-titre", ROOT))[2]
    assert title["review"] is True
    assert title["ready"] is False
    # The name takes only the sure propositions: the artist waits for a person.
    assert title["to"] == "Orage - Delta.mp3"


def test_a_title_not_searched_yet_is_renamed_after_its_own_fiche():
    titles = _by_id(arrivals(_rows(), ADDED, FICHES, "artiste-titre", ROOT))
    assert titles[4]["searched"] is False
    assert titles[4]["to"] == "Zéphyr - Ressac.mp3"
    assert titles[4]["ready"] is True
    # Already named after its fiche: nothing to tidy.
    assert titles[5]["to"] is None
    assert titles[5]["ready"] is False


def test_a_duplicate_is_found_in_the_whole_bank():
    titles = _by_id(arrivals(_rows(), ADDED, FICHES, "artiste-titre", ROOT))
    assert [twin["id"] for twin in titles[6]["duplicates"]] == [3]
    assert titles[6]["duplicates"][0]["path"] == "10-rotation/Ada - Avant.mp3"
    assert titles[4]["duplicates"] == []


def test_the_counts():
    payload = arrivals(_rows(), ADDED, FICHES, "titre", ROOT)
    assert (
        payload["total"],
        payload["ready"],
        payload["review"],
        payload["waiting"],
        payload["duplicates"],
    ) == (5, 4, 1, 3, 1)
    assert payload["model"] == "titre"


def test_since_counts_thirty_days_back():
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    assert since(now) == now.timestamp() - 30 * 86400


def _library(tmp_path: Path) -> BeetsIntegration:
    lib = Library(str(tmp_path / "library.db"))
    for rel, title, artist, added in [
        ("10-rotation/nouveau.mp3", "Nouveau", "Ada", None),
        ("10-rotation/vieux.mp3", "Vieux", "Ada", time.time() - 40 * 86400),
    ]:
        item = Item(
            path=f"/media/{rel}".encode(), title=title, artist=artist, length=100.0
        )
        lib.add(item)
        if added is not None:
            item.added = added
            item.store()
    beets = object.__new__(BeetsIntegration)
    beets.lib = lib
    return beets


async def test_the_route_is_for_the_programmateur_behind_its_switches(
    raw_app, app_configration, dbsession: ormSession, users_password, tmp_path
):
    dbsession.add(Setting(key="features.bank_tidy", value="1"))
    await dbsession.commit()
    beets = _library(tmp_path)
    client = await _admin_client(
        app_configration, beets, dbsession, users_password, "prog", {"autodj": True}
    )

    response = await client.get("/media/arrivals.json")
    assert response.status_code == 200, await response.get_data()
    payload = await response.get_json()
    assert [title["path"] for title in payload["titles"]] == ["10-rotation/nouveau.mp3"]
    assert payload["titles"][0]["to"] == "Ada - Nouveau.mp3"
    assert (await client.get("/media/arrivals.json?model=autre")).status_code == 400

    dbsession.add(Setting(key="features.bank_arrivals", value="0"))
    await dbsession.commit()
    assert not await arrivals_on(dbsession)
    response = await client.get("/media/arrivals.json")
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_arrivals_off"


async def test_the_route_refuses_whoever_does_not_program(
    raw_app, app_configration, dbsession: ormSession, users_password, tmp_path
):
    dbsession.add(Setting(key="features.bank_tidy", value="1"))
    await dbsession.commit()
    client = await _admin_client(
        app_configration,
        _library(tmp_path),
        dbsession,
        users_password,
        "anim",
        {"live": True},
    )
    assert (await client.get("/media/arrivals.json")).status_code == 403
