"""Corriger la fiche d'un titre ou d'un lot (FON-66), sur de vrais fichiers.

Les fichiers de `tests/assets/formats` sont un demi-seconde de silence, un par format
que la console accepte (`BANK_FORMATS`, console/src/api/soundsView.ts), faits par
ffmpeg sans aucun tag :

    ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 0.5 -map_metadata -1 \
        -fflags +bitexact -flags:a +bitexact <codec> silence.<format>

Les tags se relisent par mediafile, la couche de Beets sur mutagen.
"""

from __future__ import annotations

import os
import shutil
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import mutagen
import pytest
from beets.library import Item, Library, WriteError
from mediafile import MediaFile
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainConflict, DomainValidationError
from radiotomate.models import (
    JournalChange,
    JournalEntry,
    MusicCategory,
    ProgrammingVersion,
    RundownItem,
    Setting,
)
from radiotomate.services import bank_titles, title_edits
from radiotomate.services.title_edits import (
    MAX_TITLES,
    TitleEdit,
    TitleEditsOff,
    TitlesRefused,
    apply_waiting,
    clean_value,
    edit_titles,
    undo_entry,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

ASSETS = Path(__file__).parent.parent / "assets" / "formats"
FORMATS = ("mp3", "flac", "ogg", "opus", "m4a", "wav", "aif", "aiff")


def _bank(tmp_path: Path, formats=FORMATS) -> tuple[BeetsIntegration, list[int]]:
    """Une bibliothèque Beets temporaire, un titre par format, importé comme le
    ferait Beets : le fichier porte ses tags, la bibliothèque sa date."""
    media = tmp_path / "media" / "10-rotation"
    media.mkdir(parents=True)
    lib = Library(str(tmp_path / "library.db"), directory=str(tmp_path / "media"))
    ids = []
    for index, ext in enumerate(formats):
        path = media / f"titre-{index}.{ext}"
        shutil.copy(ASSETS / f"silence.{ext}", path)
        item = Item.from_path(str(path))
        item.update(
            {
                "title": f"Titre {ext}",
                "artist": "Les Marées Hautes",
                "album": "Estuaire",
                "year": 2019,
                # Beets 2.14 keeps the genres in a list: genre= is a flexible field
                "genres": ["Jazz"],
            }
        )
        item.write()
        lib.add(item)
        ids.append(item.id)
    beets = object.__new__(BeetsIntegration)
    beets.lib = lib
    return beets, ids


async def _open(dbsession: ormSession, *, own: str | None = None) -> None:
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
    if own is not None:
        dbsession.add(Setting(key=title_edits.SETTING_TITLE_EDITS, value=own))
    await dbsession.commit()


def _tags(beets: BeetsIntegration, beets_id: int) -> MediaFile:
    return MediaFile(beets.lib.get_item(beets_id).path)


def _raw_keys(beets: BeetsIntegration, beets_id: int) -> str:
    """Tout ce que mutagen voit dans le fichier, en minuscules."""
    tags = mutagen.File(beets.lib.get_item(beets_id).path).tags
    return " ".join(str(key) for key in (tags or {})).lower()


async def _line(dbsession: ormSession, beets_id: int, status: str) -> RundownItem:
    dbsession.add(ProgrammingVersion(id=f"pv-{beets_id}", source="test"))
    await dbsession.flush()
    line = RundownItem(
        id=f"ri-{beets_id}",
        programming_version_id=f"pv-{beets_id}",
        sequence=0,
        planned_at=datetime.now(),
        duration=200,
        kind="music",
        when_mode="sequential",
        queue="autodj",
        resource="Rotation",
        beets_id=beets_id,
        status=status,
    )
    dbsession.add(line)
    await dbsession.commit()
    return line


async def _entries(dbsession: ormSession) -> list[JournalEntry]:
    return list(await dbsession.scalars(select(JournalEntry).order_by(JournalEntry.id)))


async def _changes(dbsession: ormSession, entry_id: int) -> list[JournalChange]:
    return list(
        await dbsession.scalars(
            select(JournalChange)
            .where(JournalChange.entry_id == entry_id)
            .order_by(JournalChange.id)
            .execution_options(populate_existing=True)
        )
    )


@pytest.mark.parametrize("ext", FORMATS)
async def test_each_format_takes_the_correction(raw_app, dbsession, tmp_path, ext):
    beets, (beets_id,) = _bank(tmp_path, (ext,))
    await _open(dbsession)

    outcome = await edit_titles(
        dbsession,
        beets,
        [
            TitleEdit(
                beets_id,
                {
                    "title": "Été indien",
                    "artist": "Orage",
                    "album": "Ciel",
                    "year": "2021",
                    "genre": "Soul",
                    "famille": "soul-funk",
                },
            )
        ],
        username="programmatrice",
    )

    assert outcome.written == [beets_id]
    tags = _tags(beets, beets_id)
    assert (tags.title, tags.artist, tags.album, tags.year, tags.genre) == (
        "Été indien",
        "Orage",
        "Ciel",
        2021,
        "Soul",
    )
    item = beets.lib.get_item(beets_id)
    assert (item.title, item.artist, item.year, item["famille"]) == (
        "Été indien",
        "Orage",
        2021,
        "soul-funk",
    )
    # la famille reste dans la bibliothèque, jamais dans le fichier
    assert "famille" not in _raw_keys(beets, beets_id)
    # la bibliothèque a noté la nouvelle date : la boucle ne le relit pas
    assert item.mtime == item.current_mtime()

    (entry,) = await _entries(dbsession)
    assert (entry.gesture, entry.username, entry.titles) == (
        "edit",
        "programmatrice",
        1,
    )
    changes = {change.field: change for change in await _changes(dbsession, entry.id)}
    assert set(changes) == {"title", "artist", "album", "year", "genre", "famille"}
    assert (changes["title"].old_value, changes["title"].new_value) == (
        f"Titre {ext}",
        "Été indien",
    )
    assert (changes["year"].old_value, changes["year"].new_value) == (2019, 2021)
    assert (changes["famille"].old_value, changes["famille"].new_value) == (
        "",
        "soul-funk",
    )
    assert {change.status for change in changes.values()} == {"done"}


async def test_a_title_in_queue_waits_then_is_written(raw_app, dbsession, tmp_path):
    beets, (queued, free) = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    line = await _line(dbsession, queued, "in_queue")

    outcome = await edit_titles(
        dbsession,
        beets,
        [TitleEdit(queued, {"album": "Ciel"}), TitleEdit(free, {"album": "Ciel"})],
        username="programmatrice",
    )

    assert outcome.written == [free]
    assert [(issue.beets_id, issue.code) for issue in outcome.waiting] == [
        (queued, "queued")
    ]
    assert _tags(beets, queued).album == "Estuaire"
    assert beets.lib.get_item(queued).album == "Estuaire"
    assert _tags(beets, free).album == "Ciel"
    statuses = {c.beets_id: c.status for c in await _changes(dbsession, 1)}
    assert statuses == {queued: "waiting", free: "done"}

    # toujours en file : rien ne bouge
    assert await apply_waiting(dbsession, beets) == 0
    assert _tags(beets, queued).album == "Estuaire"

    line.status = "played"
    await dbsession.commit()
    assert await apply_waiting(dbsession, beets) == 1
    assert _tags(beets, queued).album == "Ciel"
    assert beets.lib.get_item(queued).album == "Ciel"
    statuses = {c.beets_id: c.status for c in await _changes(dbsession, 1)}
    assert statuses == {queued: "done", free: "done"}


async def test_a_title_on_air_waits(raw_app, dbsession, tmp_path):
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    await _line(dbsession, beets_id, "on_air")

    outcome = await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"title": "Brume"})],
        username="programmatrice",
    )

    assert outcome.written == []
    assert outcome.waiting[0].code == "on_air"
    assert "à l'antenne" in outcome.waiting[0].reason
    assert _tags(beets, beets_id).title == "Titre mp3"


async def test_a_title_known_by_its_path_waits(raw_app, dbsession, tmp_path):
    """Une ligne du pupitre peut ne porter que le chemin du fichier."""
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    line = await _line(dbsession, beets_id, "sent")
    line.beets_id = None
    line.path = str(beets.lib.get_item(beets_id).filepath)
    await dbsession.commit()

    outcome = await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"title": "Brume"})],
        username="programmatrice",
    )

    assert [issue.code for issue in outcome.waiting] == ["queued"]


async def test_the_family_alone_never_waits_nor_touches_the_file(
    raw_app, dbsession, tmp_path
):
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    await _line(dbsession, beets_id, "on_air")
    path = beets.lib.get_item(beets_id).filepath
    path.chmod(0o444)
    before = path.read_bytes()

    outcome = await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"famille": "jazz"})],
        username="programmatrice",
    )

    assert outcome.written == [beets_id]
    assert beets.lib.get_item(beets_id)["famille"] == "jazz"
    assert path.read_bytes() == before


async def test_a_read_only_file_changes_nothing(raw_app, dbsession, tmp_path):
    beets, ids = _bank(tmp_path, ("mp3", "flac", "ogg"))
    await _open(dbsession)
    locked = beets.lib.get_item(ids[1]).filepath
    locked.chmod(0o444)

    with pytest.raises(TitlesRefused) as refused:
        await edit_titles(
            dbsession,
            beets,
            [TitleEdit(beets_id, {"artist": "Orage"}) for beets_id in ids],
            username="programmatrice",
        )

    assert [(issue.beets_id, issue.code) for issue in refused.value.titles] == [
        (ids[1], "read_only")
    ]
    assert "Rien n'a été écrit" in refused.value.message
    for beets_id in ids:
        assert _tags(beets, beets_id).artist == "Les Marées Hautes"
        assert beets.lib.get_item(beets_id).artist == "Les Marées Hautes"
    assert await _entries(dbsession) == []


async def test_a_vanished_file_says_so(raw_app, dbsession, tmp_path):
    beets, (gone, kept) = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    beets.lib.get_item(gone).filepath.unlink()

    with pytest.raises(TitlesRefused) as refused:
        await edit_titles(
            dbsession,
            beets,
            [TitleEdit(gone, {"title": "x"}), TitleEdit(kept, {"title": "x"})],
            username="programmatrice",
        )

    assert [issue.code for issue in refused.value.titles] == ["missing"]
    assert "disparu" in refused.value.titles[0].reason
    assert _tags(beets, kept).title == "Titre flac"


async def test_a_failure_midway_leaves_nothing_half_done(
    raw_app, dbsession, tmp_path, monkeypatch
):
    beets, ids = _bank(tmp_path, ("mp3", "flac", "ogg"))
    await _open(dbsession)
    real_write = Item.write

    def write(item, *args, **kwargs):
        if item.id == ids[2] and item.album == "Ciel":
            raise WriteError(item.path, OSError("disque plein"))
        return real_write(item, *args, **kwargs)

    monkeypatch.setattr(Item, "write", write)

    with pytest.raises(TitlesRefused) as refused:
        await edit_titles(
            dbsession,
            beets,
            [TitleEdit(beets_id, {"album": "Ciel"}) for beets_id in ids],
            username="programmatrice",
        )

    assert [issue.code for issue in refused.value.titles] == ["failed"]
    assert "ont repris leurs tags d'avant" in refused.value.message
    for beets_id in ids:
        assert _tags(beets, beets_id).album == "Estuaire"
        assert beets.lib.get_item(beets_id).album == "Estuaire"
    assert await _entries(dbsession) == []


async def test_a_busy_base_midway_leaves_nothing_half_done(
    raw_app, dbsession, tmp_path, monkeypatch
):
    """Une erreur qui n'est pas celle d'un fichier, comme une base occupée, rend
    aussi leurs tags d'avant aux fichiers déjà écrits."""
    beets, ids = _bank(tmp_path, ("mp3", "flac", "ogg"))
    await _open(dbsession)
    real_busy = title_edits.busy_status

    async def busy(session, beets_id, path):
        if beets_id == ids[2]:
            raise OperationalError("select", {}, Exception("database is locked"))
        return await real_busy(session, beets_id, path)

    monkeypatch.setattr(title_edits, "busy_status", busy)

    with pytest.raises(OperationalError):
        await edit_titles(
            dbsession,
            beets,
            [TitleEdit(beets_id, {"album": "Ciel"}) for beets_id in ids],
            username="programmatrice",
        )

    for beets_id in ids:
        assert _tags(beets, beets_id).album == "Estuaire"
        assert beets.lib.get_item(beets_id).album == "Estuaire"
    assert await _entries(dbsession) == []


async def test_a_lot_of_501_titles_is_refused(raw_app, dbsession, tmp_path):
    beets, _ids = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    edits = [TitleEdit(beets_id, {"album": "Ciel"}) for beets_id in range(1, 502)]

    with pytest.raises(DomainValidationError) as refused:
        await edit_titles(dbsession, beets, edits, username="programmatrice")

    assert "500 titres au plus" in refused.value.message
    assert MAX_TITLES == 500
    assert _tags(beets, 1).album == "Estuaire"


async def test_a_title_changed_since_it_was_seen_refuses_the_lot(
    raw_app, dbsession, tmp_path
):
    beets, (seen, other) = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)

    with pytest.raises(TitlesRefused) as refused:
        await edit_titles(
            dbsession,
            beets,
            [
                TitleEdit(seen, {"album": "Ciel"}, {"album": "Autre chose"}),
                TitleEdit(other, {"album": "Ciel"}, {"album": "Estuaire"}),
            ],
            username="programmatrice",
        )

    assert [issue.code for issue in refused.value.titles] == ["changed"]
    assert _tags(beets, other).album == "Estuaire"


async def test_a_file_written_by_another_tool_is_read_first(
    raw_app, dbsession, tmp_path
):
    """Beets récrit tous les tags qu'il connaît : un fichier changé depuis sa
    dernière lecture est relu, pour ne pas écraser ce qu'un autre outil a mis."""
    beets, (beets_id,) = _bank(tmp_path, ("flac",))
    await _open(dbsession)
    item = beets.lib.get_item(beets_id)
    other = MediaFile(item.path)
    other.composer = "Quelqu'un"
    other.save()
    later = item.mtime + 10
    os.utime(item.path, (later, later))

    await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"album": "Ciel"})],
        username="programmatrice",
    )

    tags = _tags(beets, beets_id)
    assert (tags.album, tags.composer) == ("Ciel", "Quelqu'un")


async def test_revenir_gives_back_the_values_before(raw_app, dbsession, tmp_path):
    beets, ids = _bank(tmp_path, ("mp3", "flac", "ogg"))
    await _open(dbsession)
    outcome = await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"album": "Ciel", "year": 2001}) for beets_id in ids],
        username="programmatrice",
    )
    # quelqu'un change l'album du deuxième titre depuis
    await edit_titles(
        dbsession,
        beets,
        [TitleEdit(ids[1], {"album": "Autre"})],
        username="autre",
    )

    undo = await undo_entry(
        dbsession, beets, outcome.entry_id, username="programmatrice"
    )

    assert (_tags(beets, ids[0]).album, _tags(beets, ids[0]).year) == ("Estuaire", 2019)
    assert (_tags(beets, ids[2]).album, _tags(beets, ids[2]).year) == ("Estuaire", 2019)
    # le titre changé depuis garde sa valeur, et l'annulation le dit
    assert _tags(beets, ids[1]).album == "Autre"
    assert [(issue.beets_id, issue.code) for issue in undo.kept] == [
        (ids[1], "changed")
    ]
    entries = await _entries(dbsession)
    assert (entries[-1].gesture, entries[-1].undo_of) == ("undo", outcome.entry_id)
    kept = [c for c in await _changes(dbsession, entries[-1].id) if c.status == "kept"]
    assert {c.field for c in kept} == {"album", "year"}

    with pytest.raises(DomainConflict):
        await undo_entry(dbsession, beets, outcome.entry_id, username="programmatrice")


async def test_revenir_cancels_what_still_waits(raw_app, dbsession, tmp_path):
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    line = await _line(dbsession, beets_id, "in_queue")
    outcome = await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"title": "Brume"})],
        username="programmatrice",
    )

    await undo_entry(dbsession, beets, outcome.entry_id, username="programmatrice")
    line.status = "played"
    await dbsession.commit()

    assert await apply_waiting(dbsession, beets) == 0
    assert _tags(beets, beets_id).title == "Titre mp3"
    (change,) = await _changes(dbsession, outcome.entry_id)
    assert change.status == "cancelled"


async def test_a_waiting_title_changed_meanwhile_keeps_its_value(
    raw_app, dbsession, tmp_path
):
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    line = await _line(dbsession, beets_id, "in_queue")
    await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"title": "Brume"})],
        username="programmatrice",
    )
    item = beets.lib.get_item(beets_id)
    item.title = "Changé par la boucle"
    item.write()
    item.store()
    line.status = "played"
    await dbsession.commit()

    assert await apply_waiting(dbsession, beets) == 0
    assert _tags(beets, beets_id).title == "Changé par la boucle"
    (change,) = await _changes(dbsession, 1)
    assert change.status == "kept"


async def test_the_try_names_the_selections_touched(raw_app, dbsession, tmp_path):
    beets, ids = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    dbsession.add_all(
        [
            MusicCategory(name="Jazz", query="genres:Jazz"),
            MusicCategory(name="Soul", query="genres:Soul"),
            MusicCategory(name="Orage", query="artist:Orage"),
        ]
    )
    await dbsession.commit()

    outcome = await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"genre": "Soul"}) for beets_id in ids],
        username="programmatrice",
        dry_run=True,
    )

    assert {(s.name, s.gained, s.lost) for s in outcome.selections} == {
        ("Jazz", 0, 2),
        ("Soul", 2, 0),
    }
    assert _tags(beets, ids[0]).genre == "Jazz"
    assert await _entries(dbsession) == []


async def test_the_switches(raw_app, dbsession, tmp_path):
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    edit = [TitleEdit(beets_id, {"title": "Brume"})]

    # le chantier coupé : rien ne s'écrit
    tidy = Setting(key=bank_titles.SETTING_BANK_TIDY, value="0")
    dbsession.add(tidy)
    await dbsession.commit()
    with pytest.raises(TitleEditsOff):
        await edit_titles(dbsession, beets, edit, username="programmatrice")
    # le chantier ouvert, ce service coupé
    tidy.value = "1"
    dbsession.add(Setting(key=title_edits.SETTING_TITLE_EDITS, value="0"))
    await dbsession.commit()
    with pytest.raises(TitleEditsOff):
        await edit_titles(dbsession, beets, edit, username="programmatrice")
    assert _tags(beets, beets_id).title == "Titre mp3"

    row = await Setting.from_key(dbsession, title_edits.SETTING_TITLE_EDITS)
    await dbsession.delete(row)
    await dbsession.commit()
    await edit_titles(dbsession, beets, edit, username="programmatrice")
    assert _tags(beets, beets_id).title == "Brume"


async def test_waiting_writes_stop_when_the_switch_is_cut(raw_app, dbsession, tmp_path):
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    line = await _line(dbsession, beets_id, "in_queue")
    await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"title": "Brume"})],
        username="programmatrice",
    )
    line.status = "played"
    await Setting.upsert(dbsession, title_edits.SETTING_TITLE_EDITS, "0")
    await dbsession.commit()

    assert await apply_waiting(dbsession, beets) == 0
    assert _tags(beets, beets_id).title == "Titre mp3"


async def test_a_proposition_never_writes_the_genre(raw_app, dbsession, tmp_path):
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)

    with pytest.raises(DomainValidationError):
        await edit_titles(
            dbsession,
            beets,
            [TitleEdit(beets_id, {"genre": "Soul"})],
            username="programmatrice",
            gesture="accept",
        )
    outcome = await edit_titles(
        dbsession,
        beets,
        [TitleEdit(beets_id, {"label": "Disques du Port", "isrc": "FR-Z03-98-00212"})],
        username="programmatrice",
        gesture="accept",
    )
    assert outcome.written == [beets_id]
    tags = _tags(beets, beets_id)
    assert (tags.label, tags.isrc) == ("Disques du Port", "FRZ039800212")


async def test_an_interrupted_write_is_settled(raw_app, dbsession, tmp_path):
    beets, (beets_id,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    entry = JournalEntry(gesture="edit", username="programmatrice", created=old)
    entry.changes = [
        JournalChange(
            beets_id=beets_id, field="title", old_value="x", new_value="Titre mp3"
        ),
        JournalChange(
            beets_id=beets_id, field="album", old_value="Estuaire", new_value="Ciel"
        ),
    ]
    dbsession.add(entry)
    await dbsession.commit()

    await apply_waiting(dbsession, beets)

    statuses = {c.field: c.status for c in await _changes(dbsession, entry.id)}
    assert statuses == {"title": "done", "album": "failed"}


@pytest.mark.parametrize(
    ("name", "raw", "value"),
    [
        # la forme décomposée des accents, comme un Mac l'envoie
        ("title", f" {unicodedata.normalize('NFD', 'Été indien')} ", "Été indien"),
        ("year", "", 0),
        ("year", "1987", 1987),
        ("famille", "", ""),
        ("famille", "jazz", "jazz"),
        ("isrc", "fr-z03-98-00212", "FRZ039800212"),
    ],
)
def test_clean_value(name, raw, value):
    assert clean_value(name, raw) == value


@pytest.mark.parametrize(
    ("name", "raw"),
    [
        ("title", "deux\nlignes"),
        ("title", ["liste"]),
        ("year", "87"),
        ("year", 20190),
        ("year", True),
        ("famille", "variété"),
        ("isrc", "123"),
        ("artist", "x" * 1001),
    ],
)
def test_clean_value_refuses(name, raw):
    with pytest.raises(DomainValidationError) as refused:
        clean_value(name, raw)
    assert refused.value.field == name


async def test_a_gesture_notes_itself_in_the_journal(raw_app, dbsession):
    """Ce qu'ARC-09 et FON-68 écrivent au journal pour un déplacement."""
    entry = JournalEntry.note(
        "move",
        "programmatrice",
        [
            JournalChange(
                beets_id=7,
                path="/media/10-rotation/a.mp3",
                label="Orage \u2013 Comète",
                field="path",
                old_value="/media/10-rotation/a.mp3",
                new_value="/media/20-archives/nuit/a.mp3",
                status="done",
            ),
            JournalChange(
                beets_id=8,
                path="/media/10-rotation/b.mp3",
                field="path",
                old_value="/media/10-rotation/b.mp3",
                new_value="/media/20-archives/nuit/b.mp3",
                status="done",
            ),
        ],
    )
    dbsession.add(entry)
    await dbsession.commit()

    (saved,) = await _entries(dbsession)
    assert (saved.gesture, saved.titles) == ("move", 2)
    assert saved.details == {"fields": ["path"]}
    assert [c.new_value for c in await _changes(dbsession, saved.id)] == [
        "/media/20-archives/nuit/a.mp3",
        "/media/20-archives/nuit/b.mp3",
    ]
