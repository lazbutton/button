"""
The copy of the database that `radiotomate update` makes before a migration (MAJ-02),
and `restore-radiotomate.sh`, which puts it back.
"""

import os
import re
import shutil
import sqlite3
import stat
import subprocess
from contextlib import closing
from importlib import import_module
from pathlib import Path

import click
import pytest
from sqlalchemy import text

from radiotomate.commands.update import do_update
from radiotomate.db import QuartAlchemy
from tests.test_migrations import _latest_schema_version, _schema_version

RESTORE = Path(__file__).parents[2] / "deploy" / "scripts" / "restore-radiotomate.sh"
needs_sqlite3 = pytest.mark.skipif(
    shutil.which("sqlite3") is None,
    reason="restore-radiotomate.sh needs the sqlite3 command",
)
# by name, v9 would come after v13: the date in the name decides
OLDER_COPIES = [
    "avant-v9-20250101T000000Z.db",
    "avant-v10-20250102T000000Z.db",
    "avant-v11-20250103T000000Z.db",
    "avant-v12-20250104T000000Z.db",
    "avant-v13-20250105T000000Z.db",
]


def _version_in(path: Path) -> int:
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as con:
        (value,) = con.execute(
            "select value from settings where key='SCHEMA_VERSION'",
        ).fetchone()
    return int(value)


def _restore(copy: Path, data_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(RESTORE), str(copy), str(data_root)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
async def engine(tmp_path: Path):
    db = QuartAlchemy()
    db.init_from_config(
        {"url": f"sqlite+aiosqlite:///{tmp_path / 'radiotomate.db'}"}, {}
    )
    yield db.engine
    await db.after_serving()


@pytest.fixture
async def previous_version(engine) -> int:
    """
    A database one version behind, with a row of our own: one migration is due.
    """
    version = _latest_schema_version() - 1
    await do_update(engine, target_version=version)
    async with engine.connect() as conn:
        await conn.execute(
            text("insert into settings (key, value) values ('test_backup', 'kept')"),
        )
        await conn.commit()
    return version


async def test_no_copy_unless_upgrading(engine, tmp_path: Path):
    # a blank database, then an up-to-date one
    await do_update(engine)
    await do_update(engine)
    # a downgrade: the documentation says to back up by hand first
    await do_update(engine, target_version=_latest_schema_version() - 1)
    assert not (tmp_path / "backups").exists()


async def test_copy_before_migration_is_readable(
    engine,
    previous_version: int,
    tmp_path: Path,
):
    await do_update(engine)

    backups = tmp_path / "backups"
    copies = list(backups.iterdir())
    assert len(copies) == 1
    copy = copies[0]
    assert re.fullmatch(
        rf"avant-v{previous_version + 1}-\d{{8}}T\d{{6}}Z\.db", copy.name
    )
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    with closing(sqlite3.connect(f"file:{copy}?mode=ro", uri=True)) as con:
        assert con.execute("pragma integrity_check").fetchall() == [("ok",)]
        settings = dict(con.execute("select key, value from settings"))
    assert settings["SCHEMA_VERSION"] == str(previous_version)
    assert settings["test_backup"] == "kept"
    # nothing left beside the copy, no -wal nor -shm
    assert [path.name for path in backups.iterdir()] == [copy.name]
    assert await _schema_version(engine) == previous_version + 1


async def test_rotation_keeps_the_last_five_copies(
    engine,
    previous_version: int,
    tmp_path: Path,
):
    backups = tmp_path / "backups"
    backups.mkdir()
    # backup-radiotomate.sh writes its archives in the same folder
    others = ["radiotomate-20250101T000000Z.tar.gz", "notes.txt"]
    # what a copy killed midway left behind
    leftovers = [
        "avant-v13-20250106T000000Z.db.part",
        "avant-v13-20250106T000000Z.db.part-journal",
    ]
    for name in OLDER_COPIES + others + leftovers:
        (backups / name).touch()

    await do_update(engine)

    names = {path.name for path in backups.iterdir()}
    new = {name for name in names if name.startswith(f"avant-v{previous_version + 1}-")}
    assert len(new) == 1
    assert names == set(OLDER_COPIES[1:]) | set(others) | new


async def test_rotation_never_deletes_the_new_copy(
    engine,
    previous_version: int,
    tmp_path: Path,
):
    backups = tmp_path / "backups"
    backups.mkdir()
    # made while the clock was ahead
    future = [name.replace("2025", "2099") for name in OLDER_COPIES]
    for name in future:
        (backups / name).touch()

    await do_update(engine)

    names = {path.name for path in backups.iterdir()}
    new = {name for name in names if name.startswith(f"avant-v{previous_version + 1}-")}
    assert len(new) == 1
    assert names == set(future[1:]) | new


async def test_failed_migration_deletes_no_copy(
    engine,
    previous_version: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    backups = tmp_path / "backups"
    backups.mkdir()
    for name in OLDER_COPIES:
        (backups / name).touch()

    async def broken(conn):
        raise RuntimeError("bug in the migration")

    migration = import_module(f"radiotomate.commands.update.v{previous_version + 1}")
    monkeypatch.setattr(migration, "upgrade", broken)
    with pytest.raises(RuntimeError, match="bug in the migration"):
        await do_update(engine)

    # the copy made before it, and every older one, until a migration succeeds
    names = {path.name for path in backups.iterdir()}
    assert set(OLDER_COPIES) < names
    assert len(names) == len(OLDER_COPIES) + 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes in a read-only folder")
async def test_no_migration_without_copy(
    engine,
    previous_version: int,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
):
    backups = tmp_path / "backups"
    backups.mkdir()
    backups.chmod(0o500)
    try:
        with pytest.raises(click.exceptions.Exit) as exit_info:
            await do_update(engine)
    finally:
        backups.chmod(0o700)

    assert exit_info.value.exit_code == 1
    assert await _schema_version(engine) == previous_version
    assert list(backups.iterdir()) == []
    out = capsys.readouterr().out
    assert "Database backup failed, no schema change applied" in out
    assert "Permission denied" in out


async def test_copy_goes_to_the_database_owner_under_root(
    engine,
    previous_version: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # radiotomate-init runs as root
    chowned = []
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        os, "chown", lambda path, uid, gid: chowned.append((Path(path).name, uid, gid))
    )

    await do_update(engine)

    owner = (tmp_path / "radiotomate.db").stat()
    (copy,) = (tmp_path / "backups").glob("avant-v*.db")
    assert chowned == [
        ("backups", owner.st_uid, owner.st_gid),
        (copy.name, owner.st_uid, owner.st_gid),
    ]


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes in a read-only folder")
def test_install_keeps_an_existing_instance(tmp_path: Path):
    """
    On an existing instance, `radiotomate install` only updates it: when that fails,
    reverting would delete the database.
    """

    def radiotomate(*args):
        return subprocess.run(
            ["radiotomate", *args], capture_output=True, text=True, check=False
        )

    config = str(tmp_path / "radiotomate.yaml")
    previous = str(_latest_schema_version() - 1)
    assert radiotomate("install", "-d", str(tmp_path)).returncode == 0
    assert (
        radiotomate("-c", config, "update", "--target-version", previous).returncode
        == 0
    )
    backups = tmp_path / "backups"
    backups.mkdir()
    backups.chmod(0o500)
    try:
        result = radiotomate("install", "-d", str(tmp_path))
    finally:
        backups.chmod(0o700)

    assert result.returncode == 1
    assert "Database backup failed" in result.stdout
    assert (tmp_path / "radiotomate.db").exists()
    assert (tmp_path / "radiotomate.yaml").exists()


@needs_sqlite3
async def test_restore_script_puts_the_copy_back(
    engine,
    previous_version: int,
    tmp_path: Path,
):
    (tmp_path / "radiotomate.yaml").touch()
    await do_update(engine)
    backups = tmp_path / "backups"
    (copy,) = backups.glob("avant-v*.db")

    # the engine's pool still holds the database open
    refused = _restore(copy, tmp_path)
    assert refused.returncode == 1
    assert "database in use" in refused.stderr

    await engine.dispose()
    restored = _restore(copy, tmp_path)
    assert restored.returncode == 0, restored.stderr
    assert _version_in(tmp_path / "radiotomate.db") == previous_version
    (aside,) = backups.glob("avant-restauration-*.db")
    assert _version_in(aside) == previous_version + 1

    # once the copy is in place, running it again changes nothing
    again = _restore(copy, tmp_path)
    assert again.returncode == 0
    assert "already in place" in again.stderr
    assert list(backups.glob("avant-restauration-*.db")) == [aside]


@needs_sqlite3
def test_restore_script_rerun_sees_writes_in_the_wal(tmp_path: Path):
    (tmp_path / "radiotomate.yaml").touch()
    # in WAL mode, like the database of a backup-radiotomate.sh archive
    copy = tmp_path / "copy.db"
    with closing(sqlite3.connect(copy)) as con:
        con.execute("pragma journal_mode=wal")
        con.execute("create table settings (key, value)")
        con.execute("insert into settings values ('SCHEMA_VERSION', '16')")
        con.commit()
    assert _restore(copy, tmp_path).returncode == 0

    with closing(sqlite3.connect(tmp_path / "radiotomate.db")) as engine_like:
        engine_like.execute("insert into settings values ('written', 'since')")
        engine_like.commit()
        # the main file still equals the copy, the write sits in the -wal
        again = _restore(copy, tmp_path)

    assert again.returncode == 1
    assert "database in use" in again.stderr


@needs_sqlite3
def test_restore_script_refuses_a_wal_left_alone(tmp_path: Path):
    (tmp_path / "radiotomate.yaml").touch()
    copy = tmp_path / "copy.db"
    with closing(sqlite3.connect(copy)) as con:
        con.execute("create table settings (key, value)")
        con.execute("insert into settings values ('SCHEMA_VERSION', '16')")
        con.commit()
    # the database was moved away by hand, not its WAL, which SQLite would replay
    (tmp_path / "radiotomate.db-wal").write_bytes(b"frames of another database")

    result = _restore(copy, tmp_path)

    assert result.returncode == 1
    assert "left without its database" in result.stderr
    assert not (tmp_path / "radiotomate.db").exists()
