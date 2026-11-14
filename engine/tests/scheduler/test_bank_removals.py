"""Un titre retiré par le moteur, noté au journal, puis remis (FON-71).

Sur une bibliothèque Beets temporaire, comme les tests d'ARC-09 : le fichier part
dans la corbeille, le titre sort de Beets, et « Annuler » le remet à sa place,
sous son identifiant, avec son gain et ses champs flexibles.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from radiotomate.beets import BeetsIntegration
from radiotomate.models import JournalChange, JournalEntry, User
from radiotomate.models.setting import Setting
from radiotomate.services import bank_removals, journal
from radiotomate.services.bank_moves import ON_AIR
from radiotomate.services.bank_removals import (
    NOT_IN_TRASH,
    PLACE_TAKEN,
    removals_on,
    remove_titles,
)
from radiotomate.services.bank_titles import SETTING_BANK_TIDY
from tests.scheduler.test_bank_moves import (
    _history,
    _library,
    _line,
    _title,
    _version,
)
from tests.scheduler.test_studio_json import _interface_client, _login

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = (tmp_path / "media").resolve()
    (root / "10-rotation").mkdir(parents=True)
    (root / "20-archives" / "jazz").mkdir(parents=True)
    monkeypatch.setenv("MEDIA_ROOT", str(root))
    return root


@pytest.fixture
def place(tmp_path: Path, media: Path):
    """La bibliothèque d'une station, comme dans les tests d'ARC-09."""
    place = _library(tmp_path, tmp_path / "Beets")
    yield place
    place.lib._close()


async def _open(dbsession) -> None:
    dbsession.add(Setting(key=SETTING_BANK_TIDY, value="1"))
    await dbsession.commit()


def _beets(place) -> BeetsIntegration:
    beets = object.__new__(BeetsIntegration)
    beets.lib = place.lib
    return beets


def _trash(media: Path) -> list[str]:
    folder = media / "90-trash"
    return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []


async def _remove(dbsession, place, paths):
    return await remove_titles(dbsession, place, paths, username="prog")


async def test_a_removal_is_noted_then_undone_with_the_same_identity(
    raw_app, dbsession, media, place
):
    await _open(dbsession)
    first = _title(place, media / "10-rotation" / "a.mp3", famille="jazz")
    second = _title(place, media / "20-archives" / "jazz" / "b.mp3")

    report = await _remove(
        dbsession, place, ["10-rotation/a.mp3", "20-archives/jazz/b.mp3"]
    )

    assert report.removed == ["10-rotation/a.mp3", "20-archives/jazz/b.mp3"]
    assert report.failed == []
    assert not (media / "10-rotation" / "a.mp3").exists()
    assert _trash(media) == ["a.mp3", "b.mp3"]
    # le titre sort de Beets lui-même : la boucle ne retire rien de la corbeille
    assert place.lib.get_item(first.id) is None
    assert place.lib.get_item(second.id) is None
    entry = await JournalEntry.from_id(dbsession, report.entry)
    assert (entry.gesture, entry.username, entry.titles) == ("remove", "prog", 2)
    snapshot = entry.details["items"][str(first.id)]
    assert (snapshot["famille"], snapshot["rg_track_gain"]) == ("jazz", -7.25)

    outcome = await journal.undo(dbsession, _beets(place), entry.id, username="prog")

    assert outcome.written == sorted([first.id, second.id])
    assert outcome.kept == []
    assert (media / "10-rotation" / "a.mp3").is_file()
    assert (media / "20-archives" / "jazz" / "b.mp3").is_file()
    assert _trash(media) == []
    back = place.lib.get_item(first.id)
    assert back is not None
    assert os.fsdecode(back.path) == str(media / "10-rotation" / "a.mp3")
    assert (back["famille"], back.rg_track_gain, back.title) == (
        "jazz",
        -7.25,
        first.title,
    )
    # l'historique d'import le connaît : la boucle ne le réimporte pas
    assert (os.fsencode(media / "10-rotation" / "a.mp3"),) in _history(place)

    undo = await JournalEntry.from_id(dbsession, outcome.entry_id)
    assert (undo.gesture, undo.undo_of) == ("undo", entry.id)
    assert journal.why_not_undoable(undo, None) == (
        "Une remise ne s'annule pas : retire ces titres de nouveau."
    )
    again = await journal.journal_page(dbsession)
    removal = next(item for item in again["entries"] if item["id"] == entry.id)
    assert removal["gesture_label"] == "Retrait"
    assert removal["undone_by"]["id"] == undo.id


async def test_a_title_on_air_stays(raw_app, dbsession, media, place):
    await _open(dbsession)
    title = _title(place, media / "10-rotation" / "a.mp3")
    await _version(dbsession)
    dbsession.add(
        _line(
            "ri",
            status="on_air",
            path=media / "10-rotation" / "a.mp3",
            beets_id=title.id,
        )
    )
    await dbsession.commit()

    report = await _remove(dbsession, place, ["10-rotation/a.mp3"])

    assert report.failed == [{"from": "10-rotation/a.mp3", "reason": ON_AIR}]
    assert (media / "10-rotation" / "a.mp3").is_file()
    assert place.lib.get_item(title.id) is not None
    assert report.entry is None
    assert _trash(media) == []


async def test_a_place_taken_since_keeps_the_title_in_the_trash(
    raw_app, dbsession, media, place
):
    await _open(dbsession)
    _title(place, media / "10-rotation" / "a.mp3")
    gone = _title(place, media / "10-rotation" / "b.mp3")
    report = await _remove(dbsession, place, ["10-rotation/a.mp3", "10-rotation/b.mp3"])
    # un autre fichier prend la place de « a » ; « b » sort de la corbeille
    (media / "10-rotation" / "a.mp3").write_bytes(b"autre")
    (media / "90-trash" / "b.mp3").unlink()

    outcome = await journal.undo(
        dbsession, _beets(place), report.entry, username="prog"
    )

    assert outcome.written == []
    reasons = {issue.label: issue.reason for issue in outcome.kept}
    assert set(reasons.values()) == {PLACE_TAKEN, NOT_IN_TRASH}
    assert (media / "10-rotation" / "a.mp3").read_bytes() == b"autre"
    assert _trash(media) == ["a.mp3"]
    assert place.lib.get_item(gone.id) is None
    statuses = {
        change.status
        for change in await dbsession.scalars(
            select(JournalChange).where(JournalChange.entry_id == outcome.entry_id)
        )
    }
    assert statuses == {"kept"}


async def test_an_identity_taken_since_comes_back_under_a_new_one(
    raw_app, dbsession, media, place
):
    await _open(dbsession)
    title = _title(place, media / "10-rotation" / "a.mp3", famille="jazz")
    report = await _remove(dbsession, place, ["10-rotation/a.mp3"])
    # Beets donne l'identifiant libéré au titre indexé ensuite
    newcomer = _title(place, media / "10-rotation" / "c.mp3")
    assert newcomer.id == title.id

    outcome = await journal.undo(
        dbsession, _beets(place), report.entry, username="prog"
    )

    (back_id,) = outcome.written
    assert back_id != title.id
    back = place.lib.get_item(back_id)
    assert (os.fsdecode(back.path), back["famille"]) == (
        str(media / "10-rotation" / "a.mp3"),
        "jazz",
    )
    assert place.lib.get_item(title.id).path == os.fsencode(
        media / "10-rotation" / "c.mp3"
    )


async def test_a_file_not_indexed_yet_goes_and_comes_back(
    raw_app, dbsession, media, place
):
    await _open(dbsession)
    (media / "10-rotation" / "neuf.mp3").write_bytes(b"son")
    report = await _remove(dbsession, place, ["10-rotation/neuf.mp3"])
    (change,) = await dbsession.scalars(
        select(JournalChange).where(JournalChange.entry_id == report.entry)
    )
    assert (change.beets_id, change.label) == (None, "neuf.mp3")

    await journal.undo(dbsession, _beets(place), report.entry, username="prog")

    assert (media / "10-rotation" / "neuf.mp3").read_bytes() == b"son"
    assert len(list(place.lib.items())) == 0


async def test_the_switches(raw_app, dbsession, media, place):
    assert await removals_on(dbsession) is False
    await _open(dbsession)
    assert await removals_on(dbsession) is True
    dbsession.add(Setting(key=bank_removals.SETTING_REMOVALS, value="0"))
    await dbsession.commit()
    assert await removals_on(dbsession) is False


async def test_remove_json(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, media, place
):
    _title(place, media / "10-rotation" / "a.mp3")
    user = User(username="prog", permissions={"carts": True})
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, _beets(place))
    await _login(client, "prog", users_password)
    body = {"paths": ["10-rotation/a.mp3"]}

    # le rangement fermé : le catalogue retire comme avant
    closed = await client.post("/media/remove.json", json=body)
    assert closed.status_code == 409
    assert (await closed.get_json())["code"] == "bank_removals_off"
    await _open(dbsession)
    assert (await client.post("/media/remove.json", json={})).status_code == 400

    response = await client.post("/media/remove.json", json=body)

    assert response.status_code == 200, await response.get_data()
    payload = await response.get_json()
    assert payload["removed"] == ["10-rotation/a.mp3"]
    assert payload["entry"] is not None
    account = await (await client.get("/account.json")).get_json()
    assert account["features"]["bank_removals"] is True


async def test_remove_json_refuses_an_animateur(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, media, place
):
    user = User(username="anim", permissions={"live": True})
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, _beets(place))
    await _login(client, "anim", users_password)
    response = await client.post(
        "/media/remove.json", json={"paths": ["10-rotation/a.mp3"]}
    )
    assert response.status_code == 403
