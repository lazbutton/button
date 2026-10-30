from pathlib import Path

from sqlalchemy import text

from radiotomate.commands.update import do_update
from radiotomate.db import QuartAlchemy

ESSENTIAL_TABLES = {
    "settings",
    "users",
    "carts",
    "clocks",
    "autodj_slots",
    "rundown_items",
    "playout_commands",
    "emissions",
}


def _latest_schema_version() -> int:
    from importlib import import_module
    from pkgutil import iter_modules

    updates = import_module("radiotomate.commands.update")
    latest = 0
    for modinfo in iter_modules(updates.__path__):
        if modinfo.name.startswith("v"):
            latest = max(latest, int(modinfo.name[1:]))
    return latest


async def _schema_version(engine) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("select value from settings where key=:key"),
            {"key": "SCHEMA_VERSION"},
        )
        return int(result.scalars().first())


async def _table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("select name from sqlite_master where type='table'"),
        )
        return {row[0] for row in result}


async def _columns(engine, table: str) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        return {row[1] for row in result}


async def _rows(engine, sql: str) -> list[tuple]:
    async with engine.connect() as conn:
        return [tuple(row) for row in await conn.execute(text(sql))]


async def test_migrations_blank_database_then_idempotent(tmp_path: Path):
    db_path = tmp_path / "fresh.db"
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{db_path}"}, {})
    latest = _latest_schema_version()
    assert latest >= 1

    await do_update(db.engine)
    assert await _schema_version(db.engine) == latest
    names = await _table_names(db.engine)
    missing = ESSENTIAL_TABLES - names
    assert not missing, missing
    async with db.engine.connect() as conn:
        result = await conn.execute(
            text("select query from music_categories where name='Rotation'")
        )
        assert result.scalar_one() == "path:/media/10-rotation"

    await do_update(db.engine)
    assert await _schema_version(db.engine) == latest
    await db.after_serving()


async def test_v18_encoder_token_up_then_down(tmp_path: Path):
    """
    v18 gives each account an encoder token: an existing account has none, and going
    back to v17 takes the token away without touching the accounts nor their sessions.
    """
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{tmp_path / 'v17.db'}"}, {})
    await do_update(db.engine, target_version=17)
    async with db.engine.connect() as conn:
        for sql in (
            "insert into users (id, username, password, notes, permissions) "
            """values (1, 'animateur', 'argon2-hash', 'mardi', '{"stream": true}')""",
            "insert into sessions (id, user_id) values ('session', 1)",
        ):
            await conn.execute(text(sql))
        await conn.commit()
    users = "select * from users order by id"
    sessions = "select * from sessions order by id"
    before = (await _rows(db.engine, users), await _rows(db.engine, sessions))
    token_columns = {"stream_token_hash", "stream_token_created_at"}

    await do_update(db.engine, target_version=18)
    assert await _schema_version(db.engine) == 18
    assert token_columns <= await _columns(db.engine, "users")
    assert await _rows(
        db.engine, "select stream_token_hash, stream_token_created_at from users"
    ) == [(None, None)]
    async with db.engine.connect() as conn:
        await conn.execute(
            text(
                "update users set stream_token_hash = 'sha256-hex', "
                "stream_token_created_at = '2026-10-30 13:05:00.000000' where id = 1"
            )
        )
        await conn.commit()

    await do_update(db.engine, target_version=17)
    assert await _schema_version(db.engine) == 17
    assert not token_columns & await _columns(db.engine, "users")
    assert (await _rows(db.engine, users), await _rows(db.engine, sessions)) == before
    await db.after_serving()
