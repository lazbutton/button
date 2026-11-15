"""Renommer des fichiers d'après leur fiche (FON-68).

Sur une bibliothèque Beets temporaire : l'aperçu de chaque modèle, un nom pris,
des accents décomposés, un dossier par artiste, une fiche incomplète, un titre
à l'antenne ; puis le renommage, qui garde l'identité de chaque titre, se note
au journal et s'annule.
"""

from __future__ import annotations

import os
import unicodedata
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from radiotomate.domain.errors import DomainValidationError
from radiotomate.interface import bank_moves as route
from radiotomate.models import JournalChange, JournalEntry
from radiotomate.models.setting import Setting
from radiotomate.services import journal
from radiotomate.services.title_renames import (
    MAX_TITLES,
    STATE_BUSY,
    STATE_INCOMPLETE,
    STATE_MISSING,
    STATE_RENAME,
    STATE_RENAMED,
    STATE_SAME,
    STATE_TAKEN,
    parse_lot,
    plan_renames,
    rename_titles,
    renames_on,
)
from tests.scheduler.test_admin_json import _admin_client
from tests.scheduler.test_bank_moves import (  # noqa: F401
    _line,
    _path_of,
    _title,
    _version,
    media,
    place,
)
from tests.scheduler.test_bank_moves_journal import tidying  # noqa: F401

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration
    from radiotomate.services.bank_lock import BeetsPlace


def _ada(place: BeetsPlace, media: Path, name: str = "03_un.mp3", **fiche):  # noqa: F811
    fiche = {"artist": "Ada", "album": "Nuits", "title": "Un", **fiche}
    return _title(place, media / "20-archives" / "jazz" / name, **fiche)


async def _plan(dbsession, place, ids, model="artiste-titre", **more):  # noqa: F811
    plans = await plan_renames(dbsession, place, ids, model, **more)
    return [(plan.state, plan.to, plan.reason) for plan in plans]


@pytest.mark.parametrize(
    ("model", "name"),
    [
        ("artiste-titre", "Ada - Un.mp3"),
        ("artiste-album-titre", "Ada - Nuits - Un.mp3"),
        ("titre", "Un.mp3"),
    ],
)
async def test_each_model(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
    model: str,
    name: str,
):
    item = _ada(place, media)

    assert await _plan(dbsession, place, [item.id], model) == [
        (STATE_RENAME, f"20-archives/jazz/{name}", "")
    ]


async def test_a_folder_per_artist_stays_on_its_shelf(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
):
    item = _ada(place, media, "live/03_un.mp3")

    plans = await _plan(dbsession, place, [item.id], by_artist=True)

    assert plans == [(STATE_RENAME, "20-archives/jazz/Ada/Ada - Un.mp3", "")]


async def test_decomposed_accents_are_composed(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
):
    item = _ada(
        place,
        media,
        artist=unicodedata.normalize("NFD", "Élodie"),
        title=unicodedata.normalize("NFD", "Été"),
    )

    (plan,) = await _plan(dbsession, place, [item.id])

    assert plan[1] == unicodedata.normalize("NFC", "20-archives/jazz/Élodie - Été.mp3")


async def test_what_keeps_its_name_and_why(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
):
    same = _ada(place, media, "Ada - Un.mp3")
    no_artist = _ada(place, media, "sans.mp3", artist="")
    taken = _ada(place, media, "pris.mp3", artist="Bea", title="Deux")
    (media / "20-archives" / "jazz" / "Bea - Deux.mp3").write_bytes(b"un autre son")
    first = _ada(place, media, "a.mp3", artist="Cy", title="Trois")
    twin = _ada(place, media, "b.mp3", artist="Cy", title="Trois")
    gone = _ada(place, media, "parti.mp3", artist="Dan")
    (media / "20-archives" / "jazz" / "parti.mp3").unlink()
    # promote-inbox.sh took the track number for the artist.
    numbered = _ada(place, media, "01 - Ada - Un.mp3", artist="01", title="Un")

    plans = await _plan(
        dbsession,
        place,
        [
            *(same.id, no_artist.id, numbered.id, taken.id),
            *(first.id, twin.id, gone.id, 9999),
        ],
    )

    assert plans == [
        (STATE_SAME, "20-archives/jazz/Ada - Un.mp3", "Il porte déjà ce nom."),
        (STATE_INCOMPLETE, None, "La fiche n'a pas d'artiste."),
        (STATE_INCOMPLETE, None, "L'artiste de la fiche est un numéro de piste."),
        (
            STATE_TAKEN,
            "20-archives/jazz/Bea - Deux.mp3",
            "Ce nom est déjà pris : rien n'est remplacé.",
        ),
        (STATE_RENAME, "20-archives/jazz/Cy - Trois.mp3", ""),
        (
            STATE_TAKEN,
            "20-archives/jazz/Cy - Trois.mp3",
            "Ce nom est déjà pris : rien n'est remplacé.",
        ),
        (STATE_MISSING, None, "Son fichier a disparu du disque."),
        (STATE_MISSING, None, "Ce titre n'est plus dans la bibliothèque."),
    ]


async def test_a_title_on_air_keeps_its_name(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
):
    item = _ada(place, media)
    await _version(dbsession)
    dbsession.add(
        _line("antenne", status="on_air", path=media / "x.mp3", beets_id=item.id)
    )
    await dbsession.commit()

    assert await _plan(dbsession, place, [item.id]) == [
        (STATE_BUSY, "20-archives/jazz/Ada - Un.mp3", "À l'antenne en ce moment.")
    ]


async def test_a_lot_renamed_keeps_its_identity_and_undoes(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
    tidying: None,  # noqa: F811
):
    ada = _ada(place, media, famille="jazz")
    bea = _ada(place, media, "04_deux.flac.mp3", artist="Bea", title="Deux")
    plans = await plan_renames(dbsession, place, [ada.id, bea.id], "artiste-titre")

    outcome = await rename_titles(dbsession, place, plans, username="prog")

    assert [plan.state for plan in outcome.titles] == [STATE_RENAMED, STATE_RENAMED]
    assert _path_of(place, ada.id) == media / "20-archives" / "jazz" / "Ada - Un.mp3"
    assert place.lib.get_item(ada.id)["famille"] == "jazz"
    assert sorted(os.listdir(media / "20-archives" / "jazz")) == [
        "Ada - Un.mp3",
        "Bea - Deux.mp3",
    ]
    entry = await JournalEntry.from_id(dbsession, outcome.entry)
    assert (entry.gesture, entry.titles) == ("rename", 2)
    assert journal.why_not_undoable(entry, None) is None

    undone = await journal.undo(
        dbsession, SimpleNamespace(lib=place.lib), entry.id, username="prog"
    )

    assert undone.written == sorted([ada.id, bea.id])
    assert _path_of(place, ada.id) == media / "20-archives" / "jazz" / "03_un.mp3"
    assert sorted(os.listdir(media / "20-archives" / "jazz")) == [
        "03_un.mp3",
        "04_deux.flac.mp3",
    ]
    changes = list(await dbsession.scalars(select(JournalChange.status)))
    assert changes.count("done") == 4


async def test_only_the_renameable_titles_move(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
    tidying: None,  # noqa: F811
):
    same = _ada(place, media, "Ada - Un.mp3")
    plans = await plan_renames(dbsession, place, [same.id], "artiste-titre")

    outcome = await rename_titles(dbsession, place, plans, username="prog")

    assert outcome.entry is None
    assert [plan.state for plan in outcome.titles] == [STATE_SAME]


def test_a_lot_is_checked():
    assert parse_lot({"ids": [1, 2, 1], "model": "titre"}) == (
        [1, 2],
        "titre",
        False,
        False,
    )
    assert parse_lot(
        {"ids": [1], "model": "titre", "by_artist": True, "dry_run": True}
    )[2:] == (
        True,
        True,
    )
    for data in (
        {"ids": [], "model": "titre"},
        {"ids": ["1"], "model": "titre"},
        {"ids": [True], "model": "titre"},
        {"ids": list(range(MAX_TITLES + 1)), "model": "titre"},
        {"ids": [1], "model": "autre"},
        {"ids": [1], "model": "titre", "by_artist": "oui"},
    ):
        with pytest.raises(DomainValidationError):
            parse_lot(data)


async def test_the_renaming_waits_for_its_switches(dbsession: ormSession):
    # On by default since FON-85, under the general switch.
    assert await renames_on(dbsession) is True
    tidy = Setting(key="features.bank_tidy", value="0")
    dbsession.add(tidy)
    await dbsession.commit()
    assert await renames_on(dbsession) is False
    tidy.value = "1"
    await dbsession.commit()
    assert await renames_on(dbsession) is True
    dbsession.add(Setting(key="features.title_renames", value="0"))
    await dbsession.commit()
    assert await renames_on(dbsession) is False


@pytest.fixture
def engine_library(place: BeetsPlace, monkeypatch: pytest.MonkeyPatch) -> BeetsPlace:  # noqa: F811
    monkeypatch.setattr(route.BeetsPlace, "of", classmethod(lambda cls, lib: place))
    return place


async def test_the_route_tries_then_renames(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    media: Path,  # noqa: F811
    engine_library: BeetsPlace,
    tidying: None,  # noqa: F811
):
    item = _ada(engine_library, media)
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "prog",
        {"autodj": True},
    )
    body = {"ids": [item.id], "model": "artiste-titre"}

    tried = await client.post(
        "/media/titles/rename.json", json={**body, "dry_run": True}
    )

    assert tried.status_code == 200
    assert await tried.get_json() == {
        "dry_run": True,
        "titles": [
            {
                "id": item.id,
                "label": "Ada \N{EN DASH} Un",
                "path": "20-archives/jazz/03_un.mp3",
                "to": "20-archives/jazz/Ada - Un.mp3",
                "state": "rename",
                "reason": "",
            }
        ],
        "entry": None,
        "left": [],
    }
    assert (
        _path_of(engine_library, item.id)
        == media / "20-archives" / "jazz" / "03_un.mp3"
    )

    done = await client.post("/media/titles/rename.json", json=body)

    payload = await done.get_json()
    assert payload["titles"][0]["state"] == "renamed"
    assert payload["entry"] is not None
    assert (
        _path_of(engine_library, item.id)
        == media / "20-archives" / "jazz" / "Ada - Un.mp3"
    )


async def test_the_route_is_for_the_programmateur_and_its_switch(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    media: Path,  # noqa: F811
    engine_library: BeetsPlace,
):
    item = _ada(engine_library, media)
    body = {"ids": [item.id], "model": "titre", "dry_run": True}
    voice = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "voix",
        {"carts": True},
    )
    assert (await voice.post("/media/titles/rename.json", json=body)).status_code == 403

    prog = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "prog",
        {"autodj": True},
    )
    dbsession.add(Setting(key="features.bank_tidy", value="0"))
    await dbsession.commit()
    off = await prog.post("/media/titles/rename.json", json=body)
    assert off.status_code == 409
    assert (await off.get_json())["code"] == "title_renames_off"
    bad = await prog.post("/media/titles/rename.json", json={**body, "model": "autre"})
    assert bad.status_code == 400
