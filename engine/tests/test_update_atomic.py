"""
Each schema change of `radiotomate update` runs in its own transaction: one that fails
leaves nothing behind, and rebuilding a table keeps the rows of its child tables.
"""

import sqlite3
from contextlib import closing
from functools import partial
from importlib import import_module
from pathlib import Path

import pytest
from sqlalchemy import text

from radiotomate.commands.update import do_update
from radiotomate.db import QuartAlchemy
from tests.test_migrations import _latest_schema_version, _schema_version

# parent rows, and child rows that a cascade would delete or detach from them
STATION = [
    "insert into carts (id, title) values (1, 'Jingles')",
    "insert into sounds (cart_id, path, title) values (1, 'a.mp3', 'A')",
    "insert into sounds (cart_id, path, title) values (1, 'b.mp3', 'B')",
    "insert into metadata_log (cart_id, title) values (1, 'A')",
    "insert into users (id, username, password) values (1, 'admin', 'change-me')",
    "insert into sessions (id, user_id) values ('session', 1)",
]
CHILD_ROWS = {
    "sounds": "select count(*) from sounds",
    "sessions": "select count(*) from sessions",
    "clock_positions": "select count(*) from clock_positions",
    "metadata_log": "select count(*) from metadata_log where cart_id = 1",
}


class _FailsAt:
    """A connection whose statement number `n` fails, as on a full disk."""

    def __init__(self, conn, n):
        self.conn = conn
        self.n = n

    async def execute(self, *args, **kwargs):
        self.n -= 1
        if not self.n:
            raise sqlite3.OperationalError("database or disk is full")
        return await self.conn.execute(*args, **kwargs)


def _dump(db_path: Path) -> list[str]:
    """The database as SQL, schema and rows: two equal dumps, two equal databases."""
    with closing(sqlite3.connect(db_path)) as con:
        return list(con.iterdump())


def _query(db_path: Path, sql: str):
    with closing(sqlite3.connect(db_path)) as con:
        return con.execute(sql).fetchall()


async def _foreign_keys(engine) -> int:
    # the only connection of the pool: the one the update used
    async with engine.connect() as conn:
        return (await conn.exec_driver_sql("PRAGMA foreign_keys")).scalar()


async def _rebuild(conn, table):
    """
    Rebuild `table` as SQLite says to, for what ALTER TABLE can't do: create the new
    table under another name, copy the rows, drop the old table, rename the new one,
    then create the indexes again.
    """
    # without the indexes SQLite makes for UNIQUE, which have no SQL
    result = await conn.execute(
        text("select type, sql from sqlite_master where tbl_name = :t and sql > ''"),
        {"t": table},
    )
    schema = result.all()
    (create,) = [sql for kind, sql in schema if kind == "table"]
    new = create.replace(f"CREATE TABLE {table}", f"CREATE TABLE new_{table}", 1)
    await conn.exec_driver_sql(new)
    await conn.exec_driver_sql(f"INSERT INTO new_{table} SELECT * FROM {table}")
    await conn.exec_driver_sql(f"DROP TABLE {table}")
    await conn.exec_driver_sql(f"ALTER TABLE new_{table} RENAME TO {table}")
    for sql in (sql for kind, sql in schema if kind == "index"):
        await conn.exec_driver_sql(sql)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "radiotomate.db"


@pytest.fixture
async def engine(db_path: Path):
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{db_path}"}, {})
    yield db.engine
    await db.after_serving()


@pytest.fixture
async def station(engine) -> None:
    """
    A database at v16, with a cart and its sounds, a user and their session. The
    clocks and their positions come with v7.
    """
    await do_update(engine, target_version=16)
    async with engine.connect() as conn:
        for sql in STATION:
            await conn.exec_driver_sql(sql)
        await conn.commit()


async def test_failed_change_leaves_the_database_as_it_was(
    engine,
    station,
    db_path: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    before = _dump(db_path)
    v17 = import_module("radiotomate.commands.update.v17")
    upgrade = v17.upgrade

    async def fails_midway(conn):
        # once agenda_guests, agenda_diffusions and two of their indexes are created
        await upgrade(_FailsAt(conn, 5))

    monkeypatch.setattr(v17, "upgrade", fails_midway)
    with pytest.raises(sqlite3.OperationalError, match="disk is full"):
        await do_update(engine, target_version=17)

    assert _dump(db_path) == before
    assert await _schema_version(engine) == 16
    assert "Applying schema change #17... rolled back" in capsys.readouterr().out
    assert await _foreign_keys(engine) == 1

    # nothing left of the first try: no "table agenda_guests already exists"
    monkeypatch.setattr(v17, "upgrade", upgrade)
    await do_update(engine, target_version=17)
    assert await _schema_version(engine) == 17


async def test_every_schema_change_is_undone_whole(
    engine,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    Each upgrade, then each downgrade, fails once done: none of them may end the
    transaction on its own, with a commit or a VACUUM.
    """

    async def then_fail(change, conn):
        await change(conn)
        raise RuntimeError("failed once done")

    latest = _latest_schema_version()
    steps = [(version, "upgrade", version) for version in range(1, latest + 1)]
    steps += [(version, "downgrade", version - 1) for version in range(latest, 0, -1)]
    for version, name, target in steps:
        migration = import_module(f"radiotomate.commands.update.v{version}")
        before = _dump(db_path)
        with monkeypatch.context() as patch:
            patch.setattr(migration, name, partial(then_fail, getattr(migration, name)))
            with pytest.raises(RuntimeError, match="failed once done"):
                await do_update(engine, target_version=target)
        assert _dump(db_path) == before, f"v{version} {name}"
        await do_update(engine, target_version=target)


async def test_table_rebuild_keeps_child_rows(
    engine,
    station,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    counts = {table: _query(db_path, sql) for table, sql in CHILD_ROWS.items()}
    assert all(count != [(0,)] for count in counts.values()), counts

    async def rebuild_parents(conn):
        for table in ("carts", "users", "clocks"):
            await _rebuild(conn, table)

    v17 = import_module("radiotomate.commands.update.v17")
    monkeypatch.setattr(v17, "upgrade", rebuild_parents)
    await do_update(engine, target_version=17)

    assert await _schema_version(engine) == 17
    assert {table: _query(db_path, sql) for table, sql in CHILD_ROWS.items()} == counts
    assert _query(db_path, "PRAGMA foreign_key_check") == []
    assert await _foreign_keys(engine) == 1


async def test_change_that_breaks_foreign_keys_is_refused(
    engine,
    station,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    before = _dump(db_path)

    async def delete_cart(conn):
        # foreign keys are off: its sounds stay, pointing at nothing
        await conn.execute(text("delete from carts where id = 1"))

    v17 = import_module("radiotomate.commands.update.v17")
    monkeypatch.setattr(v17, "upgrade", delete_cart)
    with pytest.raises(sqlite3.IntegrityError, match="2 sounds -> carts"):
        await do_update(engine, target_version=17)

    assert _dump(db_path) == before
    assert await _schema_version(engine) == 16


async def test_older_broken_foreign_keys_dont_stop_a_change(
    engine,
    station,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # deleted by hand with the sqlite3 shell, where foreign keys are off
    with closing(sqlite3.connect(db_path)) as con:
        con.execute("delete from carts where id = 1")
        con.commit()

    async def rename_sounds(conn):
        # its orphan rows go with it
        await conn.execute(text("alter table sounds rename to cart_sounds"))

    v17 = import_module("radiotomate.commands.update.v17")
    monkeypatch.setattr(v17, "upgrade", rename_sounds)
    await do_update(engine, target_version=17)

    assert await _schema_version(engine) == 17
    assert len(_query(db_path, "PRAGMA foreign_key_check")) == 3
