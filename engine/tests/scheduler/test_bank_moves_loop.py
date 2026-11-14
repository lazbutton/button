"""Un titre déplacé par le moteur, puis la vraie boucle d'import (ARC-09).

La station est montée par le vrai `init-radiotomate.sh`, et indexée par la vraie
boucle (`deploy/scripts/beets-import-loop.sh`), comme dans
`tests/test_beets_import_loop.py`. Après un déplacement par le moteur, les tours
suivants de la boucle ne retirent rien et n'importent rien : le titre garde son
identifiant, son gain et ses champs flexibles, et prend le regroupement de sa
nouvelle collection.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from beets.library import Library

from radiotomate.services.bank_lock import BeetsPlace
from radiotomate.services.bank_moves import library_paths, move_titles
from tests.test_beets_import_loop import TRACK, _items, _station, _turn

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession


@pytest.fixture
def station(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    tmp_path = tmp_path.resolve()
    media = _station(tmp_path)
    monkeypatch.setenv("MEDIA_ROOT", str(media))
    return tmp_path, media


def _library(tmp_path: Path, media: Path) -> BeetsPlace:
    beetsdir = tmp_path / "data" / "Beets"
    # As init-radiotomate.sh sets it: the root is Beets's folder (ARC-06).
    lib = Library(str(beetsdir / "library.db"), str(beetsdir))
    return BeetsPlace(lib, beetsdir / "state.pickle", beetsdir / "banque.lock")


async def test_the_next_turns_neither_remove_nor_import(
    dbsession: ormSession, station: tuple[Path, Path]
):
    tmp_path, media = station
    shutil.copy(TRACK, media / "10-rotation" / "Ada - Un.mp3")
    shutil.copy(TRACK, media / "10-rotation" / "Bea - Deux.mp3")
    shutil.copy(TRACK, media / "20-archives" / "jazz" / "Cy - Live.mp3")
    _turn(tmp_path)
    _turn(tmp_path)
    before = _items(tmp_path)
    assert sorted(before) == ["Ada - Un.mp3", "Bea - Deux.mp3", "Cy - Live.mp3"]
    place = _library(tmp_path, media)
    ada = before["Ada - Un.mp3"][0]
    with library_paths(place.lib):
        item = place.lib.get_item(ada)
        item["rg_track_gain"] = -6.5
        item["famille"] = "Jazz"
        # In the file too, as the import writes the gain: otherwise the loop
        # reads the file again, which has none.
        item.try_write()
        item.store()

    report = await move_titles(
        dbsession,
        place,
        [
            ("10-rotation/Ada - Un.mp3", "20-archives/jazz/live/Ada - Un.mp3"),
            ("20-archives/jazz/Cy - Live.mp3", "10-rotation/Cy - Live.mp3"),
        ],
        username="prog",
    )
    assert report.failed == []

    turns = [_turn(tmp_path) for _ in range(3)]

    output = "".join(turn.stdout + turn.stderr for turn in turns)
    assert "retiré" not in output, output
    after = _items(tmp_path)
    assert {name: fields[0] for name, fields in after.items()} == {
        name: fields[0] for name, fields in before.items()
    }
    with library_paths(place.lib):
        moved = place.lib.get_item(ada)
        assert (
            Path(os.fsdecode(moved.path))
            == media / "20-archives" / "jazz" / "live" / "Ada - Un.mp3"
        )
        assert moved["rg_track_gain"] == -6.5
        assert moved["famille"] == "Jazz"
        # Its new collection's grouping, which the loop gives every title of the folder.
        assert moved["grouping"] == "jazz"
        cy = place.lib.get_item(before["Cy - Live.mp3"][0])
        assert Path(os.fsdecode(cy.path)) == media / "10-rotation" / "Cy - Live.mp3"
        assert cy["grouping"] == "rotation"
    assert len(after) == 3
    place.lib._close()
