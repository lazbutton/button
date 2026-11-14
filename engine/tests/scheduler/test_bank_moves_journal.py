"""Un déplacement se note au journal des gestes, et s'annule (ARC-09, FON-66, FON-71).

Et le verrou de la bibliothèque tient aussi la correction d'une fiche : la boucle
d'import ne relit pas un fichier à moitié écrit.
"""

from __future__ import annotations

import fcntl
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from mediafile import MediaFile
from sqlalchemy import select

from radiotomate.models import JournalChange, JournalEntry
from radiotomate.models.setting import Setting
from radiotomate.services import bank_lock, journal, title_edits
from radiotomate.services.bank_lock import BankBusyError
from radiotomate.services.bank_moves import (
    MOVED_SINCE,
    move_titles,
)
from tests.scheduler.test_bank_moves import (  # noqa: F401
    _history,
    _path_of,
    _title,
    media,
    place,
)

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session as ormSession

    from radiotomate.services.bank_lock import BeetsPlace

ADA = ("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")
BEA = ("10-rotation/Bea - Deux.mp3", "20-archives/jazz/live/Bea - Deux.mp3")


@pytest.fixture
async def tidying(dbsession: ormSession) -> None:
    dbsession.add_all(
        [
            Setting(key="features.bank_tidy", value="1"),
            Setting(key="features.title_edits", value="1"),
        ]
    )
    await dbsession.commit()


async def _changes(dbsession: ormSession, entry_id: int) -> list[JournalChange]:
    return list(
        await dbsession.scalars(
            select(JournalChange)
            .where(JournalChange.entry_id == entry_id)
            .order_by(JournalChange.id)
        )
    )


async def _undo(dbsession: ormSession, place: BeetsPlace, entry_id: int):  # noqa: F811
    return await journal.undo(
        dbsession, SimpleNamespace(lib=place.lib), entry_id, username="cam"
    )


async def test_a_lot_of_moves_is_noted_in_the_journal(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
):
    ada = _title(place, media / ADA[0], artist="Ada", title="Un")
    bea = _title(place, media / BEA[0], artist="Bea", title="Deux")

    report = await move_titles(dbsession, place, [ADA, BEA], username="prog")

    entry = await JournalEntry.from_id(dbsession, report.entry)
    assert (entry.gesture, entry.username, entry.titles) == ("move", "prog", 2)
    assert entry.details["fields"] == ["path"]
    assert [
        (c.beets_id, c.label, c.field, c.old_value, c.new_value, c.status)
        for c in await _changes(dbsession, entry.id)
    ] == [
        (
            ada.id,
            "Ada \N{EN DASH} Un",
            "path",
            str(media / ADA[0]),
            str(media / ADA[1]),
            "done",
        ),
        (
            bea.id,
            "Bea \N{EN DASH} Deux",
            "path",
            str(media / BEA[0]),
            str(media / BEA[1]),
            "done",
        ),
    ]
    assert journal.why_not_undoable(entry, None) is None


async def test_nothing_moved_notes_nothing(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
):
    report = await move_titles(dbsession, place, [ADA], username="prog")

    assert report.entry is None
    assert list(await dbsession.scalars(select(JournalEntry))) == []


async def test_undo_brings_each_title_back_with_its_identity(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
    tidying: None,
):
    ada = _title(place, media / ADA[0], artist="Ada", title="Un")
    bea = _title(place, media / BEA[0], artist="Bea", title="Deux")
    report = await move_titles(dbsession, place, [ADA, BEA], username="prog")

    outcome = await _undo(dbsession, place, report.entry)

    assert outcome.written == sorted([ada.id, bea.id])
    assert outcome.kept == []
    assert _path_of(place, ada.id) == media / ADA[0]
    assert _path_of(place, bea.id) == media / BEA[0]
    assert not (media / "20-archives" / "jazz" / "live").exists() or not any(
        (media / "20-archives" / "jazz" / "live").iterdir()
    )
    assert _history(place) == {
        (os.fsencode(media / ADA[0]),),
        (os.fsencode(media / BEA[0]),),
    }
    undo = await JournalEntry.from_id(dbsession, outcome.entry_id)
    assert (undo.gesture, undo.undo_of, undo.username) == ("undo", report.entry, "cam")
    assert [
        (c.old_value, c.new_value, c.status) for c in await _changes(dbsession, undo.id)
    ] == [
        (str(media / ADA[1]), str(media / ADA[0]), "done"),
        (str(media / BEA[1]), str(media / BEA[0]), "done"),
    ]
    entry = await JournalEntry.from_id(dbsession, report.entry)
    assert journal.why_not_undoable(entry, undo) == "Ce lot a déjà été défait."

    # Undoing the undo moves them again.
    again = await _undo(dbsession, place, undo.id)
    assert again.written == sorted([ada.id, bea.id])
    assert _path_of(place, ada.id) == media / ADA[1]


async def test_a_title_moved_again_since_stays_where_it_is(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
    tidying: None,
):
    ada = _title(place, media / ADA[0], artist="Ada", title="Un")
    bea = _title(place, media / BEA[0], artist="Bea", title="Deux")
    first = await move_titles(dbsession, place, [ADA, BEA], username="prog")
    await move_titles(
        dbsession,
        place,
        [(ADA[1], "10-rotation/ailleurs/Ada - Un.mp3")],
        username="prog",
    )

    outcome = await _undo(dbsession, place, first.entry)

    assert outcome.written == [bea.id]
    assert [issue.payload() for issue in outcome.kept] == [
        {
            "id": ada.id,
            "label": "Ada \N{EN DASH} Un",
            "code": "changed",
            "reason": MOVED_SINCE,
        }
    ]
    assert (
        _path_of(place, ada.id) == media / "10-rotation" / "ailleurs" / "Ada - Un.mp3"
    )
    assert _path_of(place, bea.id) == media / BEA[0]
    statuses = [c.status for c in await _changes(dbsession, outcome.entry_id)]
    assert sorted(statuses) == ["done", "kept"]


async def test_an_undo_waits_for_a_title_on_air(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
    tidying: None,
):
    from tests.scheduler.test_bank_moves import _line, _version

    ada = _title(place, media / ADA[0], artist="Ada", title="Un")
    first = await move_titles(dbsession, place, [ADA], username="prog")
    await _version(dbsession)
    dbsession.add(
        _line("antenne", status="on_air", path=media / ADA[1], beets_id=ada.id)
    )
    await dbsession.commit()

    outcome = await _undo(dbsession, place, first.entry)

    assert outcome.written == []
    assert [issue.reason for issue in outcome.kept] == [
        "Il reste où il est : à l'antenne en ce moment."
    ]
    assert _path_of(place, ada.id) == media / ADA[1]


async def test_a_fiche_is_not_written_while_the_loop_holds_the_library(
    dbsession: ormSession,
    media: Path,  # noqa: F811
    place: BeetsPlace,  # noqa: F811
    tidying: None,
    monkeypatch: pytest.MonkeyPatch,
):
    """FON-66 prend le même verrou, avant la base : rien ne s'écrit, rien ne reste."""
    ada = _title(place, media / ADA[0], artist="Ada", title="Un")
    monkeypatch.setattr(bank_lock, "LOCK_WAIT", 0.3)
    fd = os.open(place.lock, os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(BankBusyError):
            await title_edits.edit_titles(
                dbsession,
                SimpleNamespace(lib=place.lib),
                [title_edits.TitleEdit(ada.id, {"title": "Nouveau"})],
                username="prog",
            )
    finally:
        os.close(fd)
    assert MediaFile(str(media / ADA[0])).title != "Nouveau"
    assert place.lib.get_item(ada.id).title == "Un"
    assert list(await dbsession.scalars(select(JournalChange))) == []

    outcome = await title_edits.edit_titles(
        dbsession,
        SimpleNamespace(lib=place.lib),
        [title_edits.TitleEdit(ada.id, {"title": "Nouveau"})],
        username="prog",
    )
    assert outcome.written == [ada.id]
    assert MediaFile(str(media / ADA[0])).title == "Nouveau"
