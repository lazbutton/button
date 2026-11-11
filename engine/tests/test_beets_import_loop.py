"""
`deploy/scripts/beets-import-loop.sh` with the real Beets, on the import settings
that `deploy/scripts/init-radiotomate.sh` writes: a track dropped in a folder
that is already indexed enters the library, a library indexed folder by folder,
as the loop did before, is not imported again, a file that is still being
copied waits, and a WAV that holds MP3 stays as it is. The library follows
the disk: a removed file leaves it, and comes back when put back at the same
path, and a changed file is read again, under the same Beets id.
The loop also runs against a fake `beet` in
`services/catalog/test_beets_import_loop.py`, which the CI runs when the script
changes.

One run of the script is one turn: the fake sleep ends the loop. The loop only
indexes a folder that has not moved while it slept, so a track takes two turns:
seen, then indexed.
"""

import os
import secrets
import shutil
import sqlite3
import struct
import subprocess
import time
from contextlib import closing
from pathlib import Path

from mediafile import MediaFile

SCRIPTS = Path(__file__).parents[2] / "deploy" / "scripts"
TRACK = Path(__file__).parent / "assets" / "ohradiotomateoh.mp3"
MACHINE_SECRETS = [
    "ICECAST_SOURCE_PASSWORD",
    "ICECAST_ADMIN_PASSWORD",
    "RT_NOWPLAYING_SECRET",
    "MEILI_MASTER_KEY",
]
# exit code of the fake sleep
ONE_TURN = 7
# the date of a file copied with its own, older than the one Beets noted
OLD = 1_600_000_000
# The fake sleep ends the loop. When the test left something to happen between
# two turns, it runs it first, once, and the loop takes a second turn.
FAKE_SLEEP = """#!/bin/sh
between="{root}/between-two-turns"
if [ -f "$between" ]; then
  mv "$between" "$between.done"
  . "$between.done"
  exit 0
fi
exit {one_turn}
"""


def _env(tmp_path: Path) -> dict[str, str]:
    return {
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "RADIOTOMATE_DATA": str(tmp_path / "data"),
        "BEETSDIR": str(tmp_path / "data" / "Beets"),
        "MEDIA_ROOT": str(tmp_path / "media"),
        # where the loop keeps the state of each folder before it sleeps
        "TMPDIR": str(tmp_path / "tmp"),
    }


def _run(tmp_path: Path, *command: str, **extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        env={**_env(tmp_path), **extra},
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )


def _station(tmp_path: Path) -> Path:
    """A new station, set up by the real init. Returns its media bank."""
    beetsdir = tmp_path / "data" / "Beets"
    beetsdir.mkdir(parents=True)
    # the init keeps a list of plugins that is already there: without
    # replaygain, the import does not need ffmpeg
    (beetsdir / "config.yaml").write_text("plugins: info\n", encoding="utf-8")
    init = _run(
        tmp_path,
        "sh",
        str(SCRIPTS / "init-radiotomate.sh"),
        RT_ADMIN_USER="admin",
        RT_ADMIN_PASSWORD="un mot de passe",
        **{name: secrets.token_hex(24) for name in MACHINE_SECRETS},
    )
    assert init.returncode == 0, init.stderr
    config = (beetsdir / "config.yaml").read_text(encoding="utf-8")
    assert "incremental: true" in config
    # From Beets 2.7, the import skips a track with the artist and the title of
    # one already indexed: every track of these tests is the same file.
    assert "duplicate_action: keep" in config
    # From Beets 2.10, it replaces a WAV that holds MP3 with an .mp3.
    assert "remux_mp3_in_wav: false" in config
    (tmp_path / "bin").mkdir()
    (tmp_path / "tmp").mkdir()
    sleep = tmp_path / "bin" / "sleep"
    sleep.write_text(
        FAKE_SLEEP.format(root=tmp_path, one_turn=ONE_TURN), encoding="utf-8"
    )
    sleep.chmod(0o755)
    media = tmp_path / "media"
    (media / "10-rotation").mkdir(parents=True)
    (media / "20-archives" / "jazz").mkdir(parents=True)
    return media


def _turn(tmp_path: Path) -> subprocess.CompletedProcess:
    """One turn of the real loop, up to its sleep."""
    loop = _run(tmp_path, "sh", str(SCRIPTS / "beets-import-loop.sh"))
    assert loop.returncode == ONE_TURN, loop.stderr
    return loop


def _between_two_turns(tmp_path: Path, script: str) -> None:
    """What happens during the sleep of the next run, which then takes two turns."""
    (tmp_path / "between-two-turns").write_text(script, encoding="utf-8")


def _beet(tmp_path: Path, *args: str) -> None:
    done = _run(tmp_path, "beet", *args)
    assert done.returncode == 0, done.stderr


def _index_by_folder(tmp_path: Path, folder: Path) -> None:
    """What the loop ran before it imported track by track."""
    _beet(tmp_path, "import", "-A", "-q", str(folder))
    _beet(tmp_path, "modify", "-y", "grouping=rotation", f"path:{folder}")


def _odd_name(folder: Path) -> list[str]:
    """A track whose name is not UTF-8, where the file system takes one."""
    name = os.fsdecode(b"Caf\xe9 - Noir.mp3")
    try:
        shutil.copy(TRACK, folder / name)
    except OSError:
        # macOS refuses the name
        return []
    return [name]


def _items(
    tmp_path: Path, fields: str = "id, album_id, grouping, genre, rg_track_gain, title"
) -> dict[str, tuple]:
    """The library, by file name: Beets id, album, grouping, genre, gain and title."""
    library = tmp_path / "data" / "Beets" / "library.db"
    if not library.exists():
        return {}
    with closing(sqlite3.connect(library)) as con:
        rows = con.execute(f"select path, {fields} from items").fetchall()
    return {Path(os.fsdecode(path)).name: tuple(values) for path, *values in rows}


def _retag(path: Path, when: int, **tags: str) -> None:
    """Tags fixed in place, by hand, with a date of their own."""
    track = MediaFile(path)
    for tag, value in tags.items():
        setattr(track, tag, value)
    track.save()
    os.utime(path, (when, when))


def test_a_track_dropped_in_an_indexed_folder_is_indexed(tmp_path: Path):
    media = _station(tmp_path)
    shutil.copy(TRACK, media / "10-rotation" / "Ada - Un.mp3")
    shutil.copy(TRACK, media / "20-archives" / "jazz" / "Cy - Live à Orléans.mp3")
    _turn(tmp_path)
    assert _items(tmp_path) == {}
    _turn(tmp_path)
    first = _items(tmp_path)
    assert sorted(first) == ["Ada - Un.mp3", "Cy - Live à Orléans.mp3"]

    # the next ones land flat, in folders that are already indexed
    shutil.copy(TRACK, media / "10-rotation" / "Bea - Deux.mp3")
    shutil.copy(TRACK, media / "20-archives" / "jazz" / "Dan - Live deux.mp3")
    _turn(tmp_path)
    assert _items(tmp_path) == first
    _turn(tmp_path)

    items = _items(tmp_path)
    assert {name: fields[2:4] for name, fields in items.items()} == {
        "Ada - Un.mp3": ("rotation", ""),
        "Bea - Deux.mp3": ("rotation", ""),
        "Cy - Live à Orléans.mp3": ("jazz", "Archive"),
        "Dan - Live deux.mp3": ("jazz", "Archive"),
    }
    assert {name: items[name] for name in first} == first

    # beet modify has just written its tags into the new files: what the loop
    # writes during its own turn does not make the next track wait
    shutil.copy(TRACK, media / "10-rotation" / "Eve - Trois.mp3")
    _turn(tmp_path)
    assert _items(tmp_path) == items
    _turn(tmp_path)
    assert _items(tmp_path).pop("Eve - Trois.mp3")[2] == "rotation"

    # nothing new: nothing moves
    indexed = _items(tmp_path)
    _turn(tmp_path)
    _turn(tmp_path)
    assert _items(tmp_path) == indexed


def test_a_bank_named_like_a_beets_query_keeps_its_name_and_its_own_tracks(
    tmp_path: Path,
):
    media = _station(tmp_path)
    shutil.copy(TRACK, media / "10-rotation" / "Ada - Un.mp3")
    # Beets reads a query and a value its own way. With path:, a trailing comma
    # adds an empty query, which takes the whole library, and a trailing space
    # goes. In a value, $title and %upper{} are a template, and a lone } ends it.
    names = ["jazz", "Foo,", "Bar ", "Prix $title", "Bio %upper{x}", "Live}$2024"]
    for name in names:
        bank = media / "20-archives" / name
        bank.mkdir(exist_ok=True)
        shutil.copy(TRACK, bank / f"{name} - Live.mp3")
    _turn(tmp_path)
    _turn(tmp_path)

    expected = {
        "Ada - Un.mp3": ("rotation", ""),
        **{f"{name} - Live.mp3": (name, "Archive") for name in names},
    }
    assert {name: fields[2:4] for name, fields in _items(tmp_path).items()} == expected

    # nothing new: nothing moves, and no file is written again
    tracks = list(media.rglob("*.mp3"))
    dates = {track: track.stat().st_mtime_ns for track in tracks}
    _turn(tmp_path)
    _turn(tmp_path)
    assert {name: fields[2:4] for name, fields in _items(tmp_path).items()} == expected
    assert {track: track.stat().st_mtime_ns for track in tracks} == dates


def test_a_file_still_being_copied_waits(tmp_path: Path):
    media = _station(tmp_path)
    song = media / "10-rotation" / "Ada - Un.mp3"
    track = TRACK.read_bytes()
    half = len(track) // 2
    song.write_bytes(track[:half])
    _turn(tmp_path)
    # the copy ends: the folder has moved while the loop slept
    with song.open("ab") as copy:
        copy.write(track[half:])
    _turn(tmp_path)

    assert _items(tmp_path) == {}
    # Beets would have measured half a track, and written its tags into it
    assert song.read_bytes() == track

    _turn(tmp_path)
    assert _items(tmp_path)["Ada - Un.mp3"][2] == "rotation"


def test_a_library_indexed_by_folder_takes_the_skipped_track_and_keeps_its_items(
    tmp_path: Path,
):
    media = _station(tmp_path)
    rotation = media / "10-rotation"
    shutil.copy(TRACK, rotation / "Ada - Un.mp3")
    shutil.copy(TRACK, rotation / "Bea - Deux.mp3")
    indexed = ["Ada - Un.mp3", "Bea - Deux.mp3", *_odd_name(rotation)]
    _index_by_folder(tmp_path, rotation)
    _beet(tmp_path, "modify", "-y", "rg_track_gain=-3.25", f"path:{rotation}")
    # the defect: dropped later, this track never got in
    shutil.copy(TRACK, rotation / "Cy - Trois.mp3")
    _index_by_folder(tmp_path, rotation)
    before = _items(tmp_path)
    assert sorted(before) == sorted(indexed)
    assert {fields[4] for fields in before.values()} == {-3.25}

    seen = _turn(tmp_path)
    _turn(tmp_path)

    after = _items(tmp_path)
    assert "Cy - Trois.mp3" in after
    assert after.pop("Cy - Trois.mp3")[2] == "rotation"
    # imported again, they would get new ids, and lose their album and their gain
    assert after == before
    assert f"{len(indexed)} fichier(s) déjà indexé(s) repris" in seen.stdout


def test_a_lost_history_does_not_import_the_library_again(tmp_path: Path):
    media = _station(tmp_path)
    shutil.copy(TRACK, media / "10-rotation" / "Ada - Un.mp3")
    shutil.copy(TRACK, media / "10-rotation" / "Bea - Deux.mp3")
    # a second folder: SQLite gives a lone folder imported again its old ids
    shutil.copy(TRACK, media / "20-archives" / "jazz" / "Cy - Live.mp3")
    _turn(tmp_path)
    _turn(tmp_path)
    before = _items(tmp_path)
    assert len(before) == 3

    # lost between two turns of the same run, not only when the loop starts
    for lose in (
        'rm "$BEETSDIR/state.pickle"',
        'printf unreadable > "$BEETSDIR/state.pickle"',
    ):
        _between_two_turns(tmp_path, lose + "\n")
        both = _turn(tmp_path)
        # two turns, two folders: Beets went through them all, and skipped them
        assert both.stderr.count("No files imported") == 4, both.stderr
        assert _items(tmp_path) == before


def test_nothing_is_indexed_while_the_history_cannot_be_resumed(tmp_path: Path):
    media = _station(tmp_path)
    rotation = media / "10-rotation"
    shutil.copy(TRACK, rotation / "Ada - Un.mp3")
    shutil.copy(TRACK, rotation / "Bea - Deux.mp3")
    _index_by_folder(tmp_path, rotation)
    shutil.copy(TRACK, rotation / "Cy - Trois.mp3")
    before = _items(tmp_path)
    # the file that the loop writes before it replaces the history
    obstacle = tmp_path / "data" / "Beets" / ".state.partial.pickle"
    obstacle.mkdir()

    _turn(tmp_path)
    blocked = _turn(tmp_path)

    assert "reprise impossible" in blocked.stderr
    assert _items(tmp_path) == before

    # once it can, the loop goes on by itself, with no restart
    obstacle.rmdir()
    _turn(tmp_path)
    _turn(tmp_path)

    after = _items(tmp_path)
    assert after.pop("Cy - Trois.mp3")[2] == "rotation"
    assert after == before


def test_a_removed_track_leaves_the_library_and_comes_back_when_put_back(
    tmp_path: Path,
):
    media = _station(tmp_path)
    rotation = media / "10-rotation"
    jazz = media / "20-archives" / "jazz"
    soul = media / "20-archives" / "soul"
    soul.mkdir()
    shutil.copy(TRACK, rotation / "Ada - Un.mp3")
    shutil.copy(TRACK, rotation / "Bea - Deux.mp3")
    shutil.copy(TRACK, jazz / "Cy - Live.mp3")
    shutil.copy(TRACK, soul / "Dan - Live.mp3")
    _turn(tmp_path)
    _turn(tmp_path)
    before = _items(tmp_path)
    assert sorted(before) == [
        "Ada - Un.mp3",
        "Bea - Deux.mp3",
        "Cy - Live.mp3",
        "Dan - Live.mp3",
    ]

    (rotation / "Bea - Deux.mp3").unlink()
    (jazz / "Cy - Live.mp3").unlink()
    removed = _turn(tmp_path)

    # on the next turn, with no wait for the folders to settle
    kept = ["Ada - Un.mp3", "Dan - Live.mp3"]
    assert _items(tmp_path) == {name: before[name] for name in kept}
    assert "2 titre(s) retiré(s)" in removed.stdout
    # beet update would have pruned the emptied bank, and 20-archives with it
    assert jazz.is_dir()

    # put back at the same path: the history has forgotten them
    shutil.copy(TRACK, rotation / "Bea - Deux.mp3")
    shutil.copy(TRACK, jazz / "Cy - Live.mp3")
    _turn(tmp_path)
    _turn(tmp_path)

    items = _items(tmp_path)
    assert {name: items.pop(name) for name in kept} == {
        name: before[name] for name in kept
    }
    assert {name: fields[2:4] for name, fields in items.items()} == {
        "Bea - Deux.mp3": ("rotation", ""),
        "Cy - Live.mp3": ("jazz", "Archive"),
    }


def test_a_changed_track_is_read_again_once_and_keeps_its_id(tmp_path: Path):
    media = _station(tmp_path)
    rotation = media / "10-rotation"
    jazz = media / "20-archives" / "jazz"
    for name in ("Ada - Un.mp3", "Bea - Deux.mp3", "Cy - Trois.mp3"):
        shutil.copy(TRACK, rotation / name)
    shutil.copy(TRACK, jazz / "Dan - Live.mp3")
    _turn(tmp_path)
    _turn(tmp_path)
    # the gain that Beets measures at import, and writes into the files
    _beet(tmp_path, "modify", "-y", "rg_track_gain=-3.25", f"path:{media}")
    _turn(tmp_path)
    before = _items(tmp_path)

    later = int(time.time()) + 60
    # a tag fixed in place, a while later
    _retag(rotation / "Ada - Un.mp3", later, title="Un, corrigé", genre="Jazz")
    # a bank sets its own genre
    _retag(jazz / "Dan - Live.mp3", later, title="Live, remasterisé", genre="Rock")
    # a file replaced by another one, copied with its own date, older than the
    # one Beets noted: no gain in its tags
    shutil.copy(TRACK, rotation / "Bea - Deux.mp3")
    os.utime(rotation / "Bea - Deux.mp3", (OLD, OLD))
    _turn(tmp_path)
    # the folders moved while the loop slept: nothing is read yet
    assert _items(tmp_path) == before
    _turn(tmp_path)

    items = _items(tmp_path)
    ada, bea, cy, dan = (before[name] for name in sorted(before))
    assert items == {
        "Ada - Un.mp3": (*ada[:3], "Jazz", -3.25, "Un, corrigé"),
        # the engine measures a gain that is missing
        "Bea - Deux.mp3": (*bea[:4], None, ""),
        "Cy - Trois.mp3": cy,
        "Dan - Live.mp3": (*dan[:5], "Live, remasterisé"),
    }
    # Beets 2.5.1 does not note the date of what it reads: the loop does, so a
    # file is read once, and not at every turn
    files = [*rotation.iterdir(), *jazz.iterdir()]
    assert _items(tmp_path, "mtime") == {
        path.name: (int(path.stat().st_mtime),) for path in files
    }
    assert _items(tmp_path, "mtime")["Bea - Deux.mp3"] == (OLD,)


def test_a_changed_track_of_a_folder_album_leaves_the_others_alone(tmp_path: Path):
    media = _station(tmp_path)
    rotation = media / "10-rotation"
    for name, genre, year in (
        ("Ada - Un.mp3", "Rock", 1990),
        ("Bea - Deux.mp3", "Jazz", 2001),
        ("Cy - Trois.mp3", "Funk", 2010),
    ):
        shutil.copy(TRACK, rotation / name)
        _retag(rotation / name, OLD, genre=genre, year=year)
    # as the loop did before: the folder is one album
    _index_by_folder(tmp_path, rotation)
    fields = "id, album_id, genre, year, title"
    before = _items(tmp_path, fields)
    assert len({values[1] for values in before.values()}) == 1

    _retag(rotation / "Cy - Trois.mp3", int(time.time()) + 60, title="Trois, corrigé")
    _turn(tmp_path)
    _turn(tmp_path)

    # beet update would give the album fields of its first track to all of them
    after = _items(tmp_path, fields)
    assert after["Ada - Un.mp3"] == before["Ada - Un.mp3"]
    assert after["Bea - Deux.mp3"] == before["Bea - Deux.mp3"]
    # read out of its album, under the same id
    cy_id = before["Cy - Trois.mp3"][0]
    assert after["Cy - Trois.mp3"] == (cy_id, None, "Funk", 2010, "Trois, corrigé")


def _mp3_in_wav(path: Path) -> None:
    """A WAV that holds an MP3 stream (WAVE_FORMAT_MPEGLAYER3)."""
    mp3 = TRACK.read_bytes()
    # format, channels, rate, bytes per second, block align, bits per sample
    fmt = struct.pack("<HHIIHH", 0x55, 2, 44100, 16000, 1, 0)
    chunks = (
        b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt))
        + fmt
        + b"data"
        + struct.pack("<I", len(mp3))
        + mp3
        + b"\0" * (len(mp3) % 2)
    )
    path.write_bytes(b"RIFF" + struct.pack("<I", len(chunks)) + chunks)


def test_a_wav_that_holds_mp3_stays_a_wav(tmp_path: Path):
    media = _station(tmp_path)
    rotation = media / "10-rotation"
    _mp3_in_wav(rotation / "Ada - Un.wav")
    _turn(tmp_path)
    _turn(tmp_path)

    # Beets 2.10 and later would write an .mp3 next to it, and delete the WAV
    assert sorted(path.name for path in rotation.iterdir()) == ["Ada - Un.wav"]
    assert _items(tmp_path)["Ada - Un.wav"][2] == "rotation"
