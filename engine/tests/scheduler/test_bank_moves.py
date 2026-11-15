"""Un titre déplacé par le moteur garde son identité (ARC-09).

Sur une bibliothèque Beets temporaire, par l'API de Beets : le même identifiant,
le même gain, les mêmes champs flexibles, l'historique d'import qui suit ; puis
un son de bac, un fichier de l'Agenda et une ligne prévue du conducteur qui
suivent. Un titre à l'antenne ou en file ne bouge pas, un nom pris non plus, et
un échec en route rend tout comme avant.
"""

from __future__ import annotations

import errno
import fcntl
import os
import pickle
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from beets.library import Item, Library
from sqlalchemy import select

from radiotomate.enums import CartMode, RundownStatus, ScheduleMode
from radiotomate.models import Cart, Sound
from radiotomate.models.agenda import AgendaDiffusion, AgendaFile
from radiotomate.models.execution import ProgrammingVersion, RundownItem
from radiotomate.models.setting import Setting
from radiotomate.services import bank_lock, bank_moves
from radiotomate.services.bank_lock import BankBusyError, BeetsPlace
from radiotomate.services.bank_moves import (
    GONE,
    LINK,
    ON_AIR,
    QUEUED,
    TAKEN,
    move_titles,
    moves_on,
)
from tests.scheduler.test_admin_json import ASSETS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

MP3 = ASSETS / "ohradiotomateoh.mp3"


async def _move(dbsession, place, moves, **more):
    return await move_titles(dbsession, place, moves, username="prog", **more)


ROOT = os.geteuid() == 0


@pytest.fixture
def media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = (tmp_path / "media").resolve()
    (root / "10-rotation").mkdir(parents=True)
    (root / "20-archives" / "jazz").mkdir(parents=True)
    monkeypatch.setenv("MEDIA_ROOT", str(root))
    return root


def _library(tmp_path: Path, root: Path):
    beetsdir = tmp_path / "Beets"
    beetsdir.mkdir(exist_ok=True)
    lib = Library(str(beetsdir / "library.db"), str(root))
    return BeetsPlace(lib, beetsdir / "state.pickle", beetsdir / "banque.lock")


@pytest.fixture
def place(tmp_path: Path, media: Path):
    """La bibliothèque d'une station : sa racine (`directory`) est le dossier de
    Beets, hors de la banque, comme le pose init-radiotomate.sh (ARC-06)."""
    place = _library(tmp_path, tmp_path / "Beets")
    yield place
    place.lib._close()


def _title(place: BeetsPlace, path: Path, **fields) -> Item:
    """Un titre de la banque, indexé comme par la boucle, avec son historique."""
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(MP3, path)
    os.utime(path, (1_600_000_000, 1_600_000_000))
    item = Item.from_path(str(path))
    item["rg_track_gain"] = -7.25
    item["grouping"] = "rotation"
    for key, value in fields.items():
        item[key] = value
    place.lib.add(item)
    history = _history(place) | {(os.fsencode(path),)}
    place.statefile.write_bytes(
        pickle.dumps({"taghistory": history, "tagprogress": {}})
    )
    return item


def _history(place: BeetsPlace) -> set:
    if not place.statefile.exists():
        return set()
    return pickle.loads(place.statefile.read_bytes())["taghistory"]


def _stored(place: BeetsPlace) -> str:
    """The path of the only title, as library.db keeps it."""
    with sqlite3.connect(place.lib.path) as con:
        (stored,) = con.execute("select path from items").fetchone()
    return os.fsdecode(stored)


def _path_of(place: BeetsPlace, beets_id: int) -> Path:
    return Path(os.fsdecode(place.lib.get_item(beets_id).path))


async def _version(dbsession: ormSession) -> str:
    dbsession.add(ProgrammingVersion(id="pv", source="t", description="t"))
    await dbsession.flush()
    return "pv"


def _line(
    line_id: str, *, status: str, path: Path, beets_id: int | None = None
) -> RundownItem:
    return RundownItem(
        id=line_id,
        programming_version_id="pv",
        sequence=0,
        planned_at=datetime.now() + timedelta(minutes=10),
        duration=180,
        kind="musique",
        when_mode="sequential",
        queue="autodj",
        resource="x",
        path=str(path),
        beets_id=beets_id,
        status=status,
    )


async def test_a_title_moved_keeps_its_id_gain_fields_and_history(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    source = media / "10-rotation" / "Ada - Un.mp3"
    item = _title(place, source, famille="Jazz", etiquettes="nuit")

    report = await _move(
        dbsession,
        place,
        [("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")],
    )

    target = media / "20-archives" / "jazz" / "Ada - Un.mp3"
    assert report.payload() == {
        "moved": [
            {
                "from": "10-rotation/Ada - Un.mp3",
                "to": "20-archives/jazz/Ada - Un.mp3",
                "beets_ids": [item.id],
            }
        ],
        "failed": [],
        "left": [],
        "entry": 1,
    }
    assert not source.exists()
    assert target.is_file()
    assert target.stat().st_mtime == 1_600_000_000
    moved = place.lib.get_item(item.id)
    assert Path(os.fsdecode(moved.path)) == target
    assert moved["rg_track_gain"] == -7.25
    assert moved["famille"] == "Jazz"
    assert moved["etiquettes"] == "nuit"
    assert moved.mtime == item.mtime
    assert len(list(place.lib.items())) == 1
    assert _history(place) == {(os.fsencode(target),)}
    # Absolute, as the import loop reads it.
    assert _stored(place) == str(target)


async def test_a_library_rooted_on_the_bank_follows_too(
    dbsession: ormSession, tmp_path: Path, media: Path
):
    """Une racine sur la banque : Beets 2.14 y range les chemins relatifs, et
    ne les lit justes, dans un fil de l'exécuteur, que la racine nommée."""
    place = _library(tmp_path, media)
    try:
        item = _title(place, media / "10-rotation" / "Ada - Un.mp3")

        report = await _move(
            dbsession,
            place,
            [("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")],
        )

        target = media / "20-archives" / "jazz" / "Ada - Un.mp3"
        assert report.failed == []
        assert _path_of(place, item.id) == target
        relative = hasattr(place.lib, "music_dir_context")
        assert _stored(place) == (
            "20-archives/jazz/Ada - Un.mp3" if relative else str(target)
        )
    finally:
        place.lib._close()


async def test_the_subfolder_stays_with_the_title(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    item = _title(place, media / "20-archives" / "jazz" / "live" / "Cy - Live.mp3")

    report = await _move(
        dbsession,
        place,
        [("20-archives/jazz/live/Cy - Live.mp3", "10-rotation/live/Cy - Live.mp3")],
    )

    assert [move["to"] for move in report.moved] == ["10-rotation/live/Cy - Live.mp3"]
    assert _path_of(place, item.id) == media / "10-rotation" / "live" / "Cy - Live.mp3"


async def test_a_cart_sound_the_agenda_and_a_planned_line_follow(
    raw_app, dbsession: ormSession, media: Path, place: BeetsPlace
):
    source = media / "10-rotation" / "Ada - Un.mp3"
    target = media / "20-archives" / "jazz" / "Ada - Un.mp3"
    item = _title(place, source)
    cart = Cart(
        title="Soirée",
        path=raw_app.config["DATA_ROOT"] / "soiree",
        mode=CartMode.RANDOM,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(cart)
    await dbsession.flush()
    dbsession.add(
        Sound(
            cart_id=cart.id, path=source, duration=8, title="Un", gain=-1.0, peak=-0.5
        )
    )
    diffusion = AgendaDiffusion(
        kind="set",
        title="Carte blanche",
        starts_at=datetime(2030, 1, 1, 20),
        ends_at=datetime(2030, 1, 1, 21),
    )
    dbsession.add(diffusion)
    await dbsession.flush()
    dbsession.add(
        AgendaFile(
            diffusion_id=diffusion.id, path="10-rotation/Ada - Un.mp3", origin="banque"
        )
    )
    await _version(dbsession)
    dbsession.add_all(
        [
            _line(
                "prevue",
                status=RundownStatus.PLANNED.value,
                path=source,
                beets_id=item.id,
            ),
            _line(
                "jouee",
                status=RundownStatus.PLAYED.value,
                path=source,
                beets_id=item.id,
            ),
        ]
    )
    await dbsession.commit()

    report = await _move(
        dbsession,
        place,
        [("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")],
    )

    assert report.failed == []
    dbsession.expire_all()
    assert [sound.path for sound in await dbsession.scalars(select(Sound))] == [target]
    assert list(await dbsession.scalars(select(AgendaFile.path))) == [
        "20-archives/jazz/Ada - Un.mp3"
    ]
    lines = dict(
        (await dbsession.execute(select(RundownItem.id, RundownItem.path))).all()
    )
    # What has played keeps what it played.
    assert lines == {"prevue": str(target), "jouee": str(source)}


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (RundownStatus.ON_AIR.value, ON_AIR),
        (RundownStatus.IN_QUEUE.value, QUEUED),
        (RundownStatus.SENT.value, QUEUED),
        (RundownStatus.RESERVED.value, QUEUED),
    ],
)
async def test_a_title_on_air_or_in_a_queue_stays(
    dbsession: ormSession, media: Path, place: BeetsPlace, status: str, reason: str
):
    source = media / "10-rotation" / "Ada - Un.mp3"
    item = _title(place, source)
    await _version(dbsession)
    dbsession.add(
        _line("antenne", status=status, path=media / "ailleurs.mp3", beets_id=item.id)
    )
    await dbsession.commit()

    report = await _move(
        dbsession,
        place,
        [("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")],
    )

    assert report.failed == [{"from": "10-rotation/Ada - Un.mp3", "reason": reason}]
    assert source.is_file()
    assert not (media / "20-archives" / "jazz" / "Ada - Un.mp3").exists()
    assert _path_of(place, item.id) == source


async def test_a_set_of_the_agenda_on_air_stays_by_its_path(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    source = media / "20-archives" / "jazz" / "set.mp3"
    source.write_bytes(MP3.read_bytes())
    await _version(dbsession)
    dbsession.add(_line("set", status=RundownStatus.ON_AIR.value, path=source))
    await dbsession.commit()

    report = await _move(
        dbsession, place, [("20-archives/jazz/set.mp3", "10-rotation/set.mp3")]
    )

    assert report.failed == [{"from": "20-archives/jazz/set.mp3", "reason": ON_AIR}]
    assert source.is_file()


async def test_a_name_already_taken_is_never_replaced(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    source = media / "10-rotation" / "Ada - Un.mp3"
    item = _title(place, source)
    taken = media / "20-archives" / "jazz" / "Ada - Un.mp3"
    taken.write_bytes(b"un autre son")

    report = await _move(
        dbsession,
        place,
        [("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")],
    )

    assert report.failed == [{"from": "10-rotation/Ada - Un.mp3", "reason": TAKEN}]
    assert taken.read_bytes() == b"un autre son"
    assert source.is_file()
    assert _path_of(place, item.id) == source


async def test_a_name_the_library_still_holds_is_taken(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    """Un fichier parti depuis le dernier tour de la boucle : son titre y est encore."""
    source = media / "10-rotation" / "Ada - Un.mp3"
    item = _title(place, source)
    gone = _title(place, media / "20-archives" / "jazz" / "Ada - Un.mp3")
    (media / "20-archives" / "jazz" / "Ada - Un.mp3").unlink()

    report = await _move(
        dbsession,
        place,
        [("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")],
    )

    assert report.failed == [{"from": "10-rotation/Ada - Un.mp3", "reason": TAKEN}]
    assert _path_of(place, item.id) == source
    assert gone.id != item.id


async def test_a_file_not_indexed_yet_moves_too(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    """Déposé depuis moins d'un tour de la boucle : Beets l'indexera à sa place."""
    (media / "10-rotation" / "neuf.mp3").write_bytes(MP3.read_bytes())

    report = await _move(
        dbsession, place, [("10-rotation/neuf.mp3", "20-archives/jazz/neuf.mp3")]
    )

    assert report.moved == [
        {
            "from": "10-rotation/neuf.mp3",
            "to": "20-archives/jazz/neuf.mp3",
            "beets_ids": [],
        }
    ]
    assert (media / "20-archives" / "jazz" / "neuf.mp3").is_file()
    assert _history(place) == set()


async def test_to_another_disk_a_copy_then_the_removal(
    dbsession: ormSession,
    media: Path,
    place: BeetsPlace,
    monkeypatch: pytest.MonkeyPatch,
):
    source = media / "10-rotation" / "Ada - Un.mp3"
    item = _title(place, source)
    real_link = os.link

    def across_disks(src, dst, *args, **kwargs):
        if Path(src) == source:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(bank_moves.os, "link", across_disks)

    report = await _move(
        dbsession,
        place,
        [("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")],
    )

    target = media / "20-archives" / "jazz" / "Ada - Un.mp3"
    assert report.failed == []
    assert not source.exists()
    assert target.read_bytes() == MP3.read_bytes()
    assert target.stat().st_mtime == 1_600_000_000
    assert sorted(os.listdir(target.parent)) == ["Ada - Un.mp3"]
    assert _path_of(place, item.id) == target


@pytest.mark.skipif(ROOT, reason="root removes a file from a folder it may not write")
async def test_a_title_that_cannot_leave_its_folder_stays_whole(
    raw_app, dbsession: ormSession, media: Path, place: BeetsPlace
):
    source = media / "20-archives" / "jazz" / "live" / "Cy - Live.mp3"
    item = _title(place, source)
    cart = Cart(
        title="Soirée",
        path=raw_app.config["DATA_ROOT"] / "soiree",
        mode=CartMode.RANDOM,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(cart)
    await dbsession.flush()
    dbsession.add(
        Sound(
            cart_id=cart.id, path=source, duration=8, title="Live", gain=-1.0, peak=-0.5
        )
    )
    await dbsession.commit()
    source.parent.chmod(0o555)
    try:
        report = await _move(
            dbsession,
            place,
            [("20-archives/jazz/live/Cy - Live.mp3", "10-rotation/a/b/Cy - Live.mp3")],
        )
    finally:
        source.parent.chmod(0o755)

    assert report.failed == [
        {
            "from": "20-archives/jazz/live/Cy - Live.mp3",
            "reason": "déplacement impossible",
        }
    ]
    assert source.is_file()
    assert not (media / "10-rotation" / "a").exists()
    assert _path_of(place, item.id) == source
    assert _history(place) == {(os.fsencode(source),)}
    dbsession.expire_all()
    assert [sound.path for sound in await dbsession.scalars(select(Sound))] == [source]


async def test_names_outside_what_beets_indexes_are_refused(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    _title(place, media / "10-rotation" / "Ada - Un.mp3")
    (media / "30-habillage" / "jingles").mkdir(parents=True)

    report = await _move(
        dbsession,
        place,
        [
            ("../10-rotation/Ada - Un.mp3", "20-archives/jazz/a.mp3"),
            ("10-rotation/Ada - Un.mp3", "30-habillage/jingles/a.mp3"),
            ("10-rotation/Ada - Un.mp3", "20-archives/inconnue/a.mp3"),
            ("10-rotation/Ada - Un.mp3", "20-archives/jazz/.cache/a.mp3"),
            ("10-rotation/absent.mp3", "20-archives/jazz/absent.mp3"),
        ],
    )

    assert report.moved == []
    assert [entry["reason"] for entry in report.failed] == [
        GONE,
        "destination refusée",
        "destination refusée",
        "destination refusée",
        GONE,
    ]


async def test_a_link_is_moved_on_the_machine(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    real = media / "10-rotation" / "Ada - Un.mp3"
    real.write_bytes(MP3.read_bytes())
    (media / "10-rotation" / "lien.mp3").symlink_to(real)

    report = await _move(
        dbsession, place, [("10-rotation/lien.mp3", "20-archives/jazz/lien.mp3")]
    )

    assert report.failed == [{"from": "10-rotation/lien.mp3", "reason": LINK}]


async def test_nothing_moves_while_the_loop_holds_the_library(
    dbsession: ormSession,
    media: Path,
    place: BeetsPlace,
    monkeypatch: pytest.MonkeyPatch,
):
    source = media / "10-rotation" / "Ada - Un.mp3"
    _title(place, source)
    monkeypatch.setattr(bank_lock, "LOCK_WAIT", 0.3)
    fd = os.open(place.lock, os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(BankBusyError):
            await _move(
                dbsession,
                place,
                [("10-rotation/Ada - Un.mp3", "20-archives/jazz/Ada - Un.mp3")],
            )
    finally:
        os.close(fd)
    assert source.is_file()


async def test_past_its_time_a_request_says_what_is_left(
    dbsession: ormSession, media: Path, place: BeetsPlace
):
    for name in ("a.mp3", "b.mp3"):
        _title(place, media / "10-rotation" / name)

    report = await _move(
        dbsession,
        place,
        [
            ("10-rotation/a.mp3", "20-archives/jazz/a.mp3"),
            ("10-rotation/b.mp3", "20-archives/jazz/b.mp3"),
        ],
        budget=-1,
    )

    assert [move["from"] for move in report.moved] == ["10-rotation/a.mp3"]
    assert report.left == ["10-rotation/b.mp3"]


async def test_the_engine_moves_only_while_the_tidying_is_on(dbsession: ormSession):
    # On unless said off, as the console reads it (FON-85).
    assert await moves_on(dbsession) is True
    tidy = Setting(key="features.bank_tidy", value="non")
    dbsession.add(tidy)
    await dbsession.commit()
    assert await moves_on(dbsession) is False
    tidy.value = "oui"
    await dbsession.commit()
    assert await moves_on(dbsession) is True
    dbsession.add(Setting(key="features.bank_moves_keep_identity", value="0"))
    await dbsession.commit()
    assert await moves_on(dbsession) is False
