"""
`deploy/scripts/beets-import-loop.sh` with the real Beets, on the import settings
that `deploy/scripts/init-radiotomate.sh` writes: a track dropped in a folder
that is already indexed enters the library, a library indexed folder by folder,
as the loop did before, is not imported again, and a file that is still being
copied waits.
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
import subprocess
from contextlib import closing
from pathlib import Path

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
    assert "incremental: true" in (beetsdir / "config.yaml").read_text(encoding="utf-8")
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


def _items(tmp_path: Path) -> dict[str, tuple]:
    """The library, by file name: Beets id, album, grouping, genre and gain."""
    library = tmp_path / "data" / "Beets" / "library.db"
    if not library.exists():
        return {}
    with closing(sqlite3.connect(library)) as con:
        rows = con.execute(
            "select path, id, album_id, grouping, genre, rg_track_gain from items"
        ).fetchall()
    return {Path(os.fsdecode(path)).name: tuple(fields) for path, *fields in rows}


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
