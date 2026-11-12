from collections import Counter, defaultdict
from pathlib import Path
from typing import NamedTuple

import pytest
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


# What a station writes at each version, once its database reached it: each migration
# finds a full database at the version before. Every column of every table holds a
# value that is neither NULL nor its default, as the tests check, so that losing it
# shows. The rows that an upgrade changes go under a version before it, where its case
# starts: their comment says which upgrade. Each ";" ends a statement: no value holds
# one.
STATION_DATA = {
    1: """
        update settings set value = 'Radio Exemple' where key = 'INTERFACE_NAME';
        insert into users (id, username, password, notes, created, modified,
            permissions)
        values (1, 'animateur', 'change-me', 'mardi', '2026-01-05 10:00:00',
            '2026-01-06 11:00:00', '{"carts": true}');
        insert into sessions (id, user_id, user_agent, active, latest_address,
            created, latest_action)
        values ('session', 1, 'Firefox', FALSE, '192.0.2.10', '2026-01-05 10:00:00',
            '2026-01-05 10:30:00');
        insert into carts (id, title, path, average_duration, notes, mode,
            schedule_mode, schedule_correct, schedule_year, schedule_month,
            schedule_day, schedule_week, schedule_day_of_week, schedule_hour,
            schedule_minute, schedule_second, created, modified)
        values
            (1, 'Jingles', 'carts/jingles', 8, 'habillage', 'RANDOM', 'JINGLES', TRUE,
            '*', '*', '*', '*', '*', '*', '*/15', '0', '2026-01-05 10:00:00',
            '2026-01-06 11:00:00'),
            -- the default cron, every hour at :00, that v13 moves to the clock mode
            (2, 'Pubs', 'carts/pubs', 30, '', 'PLAYLIST', 'TIMED', FALSE, '*', '*',
            '*', '*', '*', '*', '0', '0', '2026-01-05 10:00:00',
            '2026-01-05 10:00:00'),
            -- a cron of its own, that v14 moves to the clock mode
            (3, 'Chronique', 'carts/chronique', 300, '', 'PLAYLIST_LOOP', 'TIMED',
            FALSE, '*', '*', '*', '*', '0-4', '8', '30', '0', '2026-01-05 10:00:00',
            '2026-01-05 10:00:00');
        insert into sounds (id, cart_id, rank, path, duration, title, active, created,
            last_played)
        values
            (1, 1, 2, 'carts/jingles/indicatif.mp3', 7, 'Indicatif', TRUE,
            '2026-01-05 10:00:00', '2026-01-06 08:00:00'),
            (2, 3, 1, 'carts/chronique/lundi.mp3', 290, 'Lundi', FALSE,
            '2026-01-05 10:00:00', NULL);
        insert into metadata_log (id, on_air, source, source_url, cart_id, artist,
            title, album, extra)
        values (1, '2026-01-06 08:00:00', 'cart', 'https://radio.example/jingles', 1,
            'BUTTON', 'Indicatif', 'Habillage', '{"rank": 2}');
        -- APScheduler, gone with v14, kept the job of each timed cart in its tables
        create table apscheduler_schedules (
            id VARCHAR NOT NULL PRIMARY KEY,
            task_id VARCHAR NOT NULL
        );
        insert into apscheduler_schedules (id, task_id)
        values ('2', 'play_cart'), ('3', 'play_cart');
    """,
    2: "update carts set max_duration = 600 where id = 3;",
    3: """
        -- v7 changes the slots at midnight, and adds its own at 10:00 and 18:00,
        -- where a slot of the station would stop it: (day_of_week, minute) is unique
        update autodj_slots
        set title = 'Nuit', color = '#1d3557', constraints = '{"genre": "ambient"}'
        where day_of_week = 0 and minute = 0;
        insert into autodj_slots (day_of_week, minute, color, title, constraints,
            created, modified)
        values (2, 420, '#e9c46a', 'Matinale', '{}', '2026-01-05 10:00:00',
            '2026-01-06 11:00:00');
    """,
    4: "update carts set url = 'https://radio.example/pubs' where id = 2;",
    5: "update sounds set gain = -6.5, peak = 0.89 where id = 1;",
    6: "update sounds set uploader_id = 1 where id = 1;",
    7: """
        insert into music_categories (name, query, empty_query)
        values ('Nouveautés', 'grouping:nouveautes', '');
        insert into clocks (name, fallback_cart_title) values ('Soirée', '');
        insert into clock_positions (clock_id, sort_order, kind, when_mode, minute,
            sync, category_id, cart_title, fallback_cart_title)
        values
            ((select id from clocks where name = 'Soirée'), 0, 'son', 'anchored', 30,
            'molle', NULL, 'Chronique', 'Jingles'),
            ((select id from clocks where name = 'Soirée'), 1, 'musique',
            'sequential', NULL, NULL,
            (select id from music_categories where name = 'Nouveautés'), NULL, NULL);
        update autodj_slots set clock_id = (select id from clocks where name = 'Soirée')
        where day_of_week = 2 and minute = 420;
    """,
    8: """
        update carts set version = 3 where id = 1;
        update clocks set version = 2 where name = 'Soirée';
        update autodj_slots set version = 2 where day_of_week = 2 and minute = 420;
        insert into programming_versions (id, created, source, description)
        values ('programmation', '2026-01-07 00:00:00', 'console', 'semaine 2');
        insert into rundown_items (id, programming_version_id, sequence, planned_at,
            duration, kind, when_mode, sync, queue, resource, path, clock_name,
            daypart, details, status, reason, origin, clock_id, clock_position_id,
            cart_id, sound_id, beets_id, fallback_used, created, reserved_at, sent_at,
            accepted_at, queued_at, started_at, closed_at, version)
        values ('ligne', 'programmation', 1, '2026-01-07 18:30:00', 290.5, 'son',
            'anchored', 'molle', 'sons', 'cart:3', 'carts/chronique/lundi.mp3',
            'Soirée', 'soir', '{"note": 1}', 'played', 'joué', 'desk',
            (select id from clocks where name = 'Soirée'),
            (select id from clock_positions where cart_title = 'Chronique'), 3, 2, 42,
            TRUE, '2026-01-07 18:00:00', '2026-01-07 18:29:00', '2026-01-07 18:29:30',
            '2026-01-07 18:29:31', '2026-01-07 18:29:32', '2026-01-07 18:30:00',
            '2026-01-07 18:35:00', 2);
        insert into playout_commands (id, rundown_item_id, action, queue, payload,
            idempotency_key, status, attempts, available_at, lease_until, last_error,
            response, created, sent_at, acknowledged_at)
        values ('commande', 'ligne', 'queue', 'sons', '{"uri": "lundi.mp3"}',
            'ligne:queue', 'acknowledged', 2, '2026-01-07 18:29:00',
            '2026-01-07 18:29:40', 'timeout', '{"rid": 7}', '2026-01-07 18:29:00',
            '2026-01-07 18:29:30', '2026-01-07 18:29:31');
        update metadata_log
        set rundown_item_id = 'ligne', playout_command_id = 'commande'
        where id = 1;
    """,
    10: """
        insert into emissions (id, scope, title, artist, day_of_week, start_minute,
            end_minute, starts_at, ends_at, version, created, modified)
        values
            (1, 'weekly', 'QG', 'Collectif', 2, 1200, 1320, NULL, NULL, 2,
            '2026-01-08 09:00:00', '2026-01-08 10:00:00'),
            (2, 'session', 'Concert', '', NULL, NULL, NULL, '2026-02-01 20:00:00',
            '2026-02-01 22:00:00', 1, '2026-01-08 09:00:00', '2026-01-08 09:00:00');
    """,
    15: "update emissions set host_username = 'animateur' where id = 1;",
    17: """
        insert into agenda_guests (id, name, contact, token, token_created,
            opened_at, created, version)
        values (1, 'Invitée', 'invitee@radio.example', 'jeton', '2026-01-08 09:00:00',
            '2026-01-08 10:00:00', '2026-01-08 09:00:00', 2);
        insert into agenda_diffusions (id, kind, title, starts_at, ends_at, guest_id,
            host_username, set_title, tracklist, rights_at, deadline_at, series_id,
            air_status, air_reason, air_item_id, aired_start, aired_end,
            stop_requested_at, created_by, created, modified, version)
        values (1, 'set', 'Mix du jeudi', '2026-01-15 18:00:00', '2026-01-15 19:00:00',
            1, 'animateur', 'Mix', '1. Titre', '2026-01-09 10:00:00',
            '2026-01-14 18:00:00', 'série', 'aired', 'fini', 'ligne',
            '2026-01-15 18:00:02', '2026-01-15 19:00:00', '2026-01-15 18:59:00',
            'animateur', '2026-01-08 09:00:00', '2026-01-09 10:00:00', 3);
        insert into agenda_files (id, diffusion_id, path, origin, original_name,
            duration, gain, report, late, created, replaced_at)
        values (1, 1, 'agenda/1/mix.mp3', 'depot', 'mix final.mp3', 3600.5, -3.2,
            '{"lufs": -16}', 1, '2026-01-14 18:00:00', '2026-01-14 19:00:00');
        insert into agenda_exceptions (id, emission_id, day, created)
        values (1, 1, '2026-01-21', '2026-01-10 09:00:00');
    """,
    18: """
        update users
        set stream_token_hash = 'sha256-hex',
            stream_token_created_at = '2026-10-30 13:05:00'
        where id = 1;
    """,
}

# What one database cannot hold with STATION_DATA: another state of a station before a
# migration, tried as a case of its own, on top of the database at the version before.
# A downgrade that picks its rows by the value its upgrade writes needs one, where a
# row had that value before the upgrade.
STATION_VARIANTS = {
    # the Rotation set by hand where v9 points it, as the examples of the forms say
    "v9-rotation-set-by-hand": (
        9,
        "update music_categories set query = 'path:/media/10-rotation'"
        " where name = 'Rotation';",
    ),
}

# Each case: the migration it takes up and down, and the variant of the station.
CASES = {
    f"v{version}": (version, "") for version in range(1, _latest_schema_version() + 1)
} | STATION_VARIANTS

# The published downgrades that lose what was there before their upgrade, by case, and
# why. A published migration never changes (engine/AGENTS.md): the test lets these
# losses through, and only these. One that no longer happens fails the test, like a
# new one. A migration not yet published has no place here: its downgrade is fixed.
LOSSY_DOWNGRADES = {
    "v7": (
        {"autodj_slots.title", "autodj_slots.color"},
        "the upgrade gives the slots at midnight the title and color of the 24/24 "
        "clock, and the downgrade puts back those of v3, not those they had",
    ),
    "v9-rotation-set-by-hand": (
        {"music_categories.query"},
        "the downgrade puts grouping:rotation back on a Rotation that searched "
        "path:/media/10-rotation, also when the upgrade didn't set it",
    ),
    "v13": (
        {"carts.schedule_correct", "apscheduler_schedules"},
        "the upgrade moves the carts left on the default cron to the clock mode, sets "
        "their schedule_correct and deletes their APScheduler job: the downgrade only "
        "puts back their timed mode",
    ),
    "v14": (
        {"carts.schedule_mode", "carts.schedule_correct", "apscheduler_schedules"},
        "the upgrade moves the timed carts to the clock mode, sets their "
        "schedule_correct and drops the APScheduler tables: the downgrade does nothing",
    ),
}


class _Table(NamedTuple):
    columns: dict[str, tuple]  # by name: type, NOT NULL, default, rank in the key
    indexes: set[tuple]
    foreign_keys: set[tuple]
    rows: dict[tuple, dict]


@pytest.fixture
async def engine(tmp_path: Path):
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{tmp_path / 'station.db'}"}, {})
    yield db.engine
    await db.after_serving()


async def _execute(engine, script: str) -> None:
    """Each statement of `script`, one after the other."""
    async with engine.connect() as conn:
        for sql in script.split(";"):
            if sql.strip():
                await conn.exec_driver_sql(sql)
        await conn.commit()


async def _station_at(engine, version: int) -> None:
    """A database at `version`, with what a station wrote at each version on its way."""
    for reached in range(1, version + 1):
        await do_update(engine, target_version=reached)
        await _execute(engine, STATION_DATA.get(reached, ""))


async def _tables(conn) -> dict[str, list[tuple]]:
    """Each table, with its columns as `PRAGMA table_info` gives them."""
    result = await conn.exec_driver_sql(
        "select name from sqlite_master where type = 'table' order by name"
    )
    tables = {}
    for (name,) in result.all():
        if not name.startswith("sqlite_"):
            info = await conn.exec_driver_sql(f'PRAGMA table_info("{name}")')
            tables[name] = info.all()
    return tables


async def _columns_without_data(engine) -> list[str]:
    """
    The columns where no row holds a value but NULL or the column's default: losing
    them would not show. Where the default is the time, like CURRENT_TIMESTAMP, a value
    must be older than a day: one written by the test itself would come back the same
    from a downgrade that drops the column and adds it back.
    """
    empty = []
    async with engine.connect() as conn:
        for table, columns in (await _tables(conn)).items():
            for _, column, _, _, default, _ in columns:
                where = f'"{column}" is not null'
                if default is not None and default.upper().startswith("CURRENT_"):
                    where += f""" and "{column}" < datetime('now', '-1 day')"""
                elif default is not None:
                    where += f' and "{column}" is not ({default})'
                count = await conn.exec_driver_sql(
                    f'select count(*) from "{table}" where {where}'
                )
                if not count.scalar():
                    empty.append(f"{table}.{column}")
    return empty


async def _indexes(conn, table: str) -> set[tuple]:
    """Its indexes: by name when CREATE INDEX made them, else by what made them."""
    indexes = set()
    result = await conn.exec_driver_sql(f'PRAGMA index_list("{table}")')
    for _, name, unique, origin, partial in result.all():
        info = await conn.exec_driver_sql(f'PRAGMA index_info("{name}")')
        columns = tuple(column for *_, column in info)
        indexes.add((name if origin == "c" else origin, unique, partial, columns))
    return indexes


async def _foreign_keys(conn, table: str) -> set[tuple]:
    """Its foreign keys: the parent table, the actions, then the pairs of columns."""
    keys = defaultdict(list)
    result = await conn.exec_driver_sql(f'PRAGMA foreign_key_list("{table}")')
    for number, _, parent, column, parent_column, on_update, on_delete, _ in result:
        keys[number, parent, on_update, on_delete].append((column, parent_column))
    return {(*key[1:], tuple(pairs)) for key, pairs in keys.items()}


async def _rows_by_key(conn, table: str, columns: list[tuple]) -> dict[tuple, dict]:
    """Its rows by primary key. Without one, a row is its values, once per copy."""
    names = [name for _, name, *_ in columns]
    # pk: the column's rank in the primary key, 0 out of it
    key = [name for _, name in sorted((pk, name) for _, name, *_, pk in columns if pk)]
    selected = ", ".join(f'"{name}"' for name in names)
    copies = Counter()
    rows = {}
    for row in await conn.exec_driver_sql(f'select {selected} from "{table}"'):
        values = dict(zip(names, row, strict=True))
        if key:
            rows[tuple(values[name] for name in key)] = values
        else:
            copies[tuple(row)] += 1
            rows[(*row, copies[tuple(row)])] = values
    return rows


async def _snapshot(engine) -> dict[str, _Table]:
    """Each table: its columns as declared, its indexes, its foreign keys, its rows."""
    snapshot = {}
    async with engine.connect() as conn:
        for table, columns in (await _tables(conn)).items():
            snapshot[table] = _Table(
                {name: tuple(declared) for _, name, *declared in columns},
                await _indexes(conn, table),
                await _foreign_keys(conn, table),
                await _rows_by_key(conn, table, columns),
            )
    return snapshot


def _losses(before: dict[str, _Table], after: dict[str, _Table]) -> dict[str, list]:
    """
    What of `before` is not in `after`, by table or by column: a table, a column or its
    declaration, an index, a foreign key, a row or a value. What `after` has more is no
    loss.
    """
    losses = defaultdict(list)
    for name, table in before.items():
        if name not in after:
            losses[name].append("table dropped")
            continue
        now = after[name]
        for column, declared in table.columns.items():
            if column not in now.columns:
                losses[f"{name}.{column}"].append("column dropped")
            elif now.columns[column] != declared:
                losses[f"{name}.{column}"].append(
                    f"declared {declared} -> {now.columns[column]}"
                )
        for index in sorted(table.indexes - now.indexes, key=repr):
            losses[name].append(f"index {index} dropped")
        for key in sorted(table.foreign_keys - now.foreign_keys, key=repr):
            losses[name].append(f"foreign key {key} dropped")
        for key, values in table.rows.items():
            if key not in now.rows:
                losses[name].append(f"row {key} deleted")
                continue
            for column, value in values.items():
                then = now.rows[key].get(column, value)
                if then != value:
                    losses[f"{name}.{column}"].append(
                        f"row {key}: {value!r} -> {then!r}"
                    )
    return dict(losses)


async def test_station_data_fills_the_latest_schema(engine):
    """At the latest version too: the next migration finds a value in every column."""
    await _station_at(engine, _latest_schema_version())
    assert await _columns_without_data(engine) == [], "to fill in STATION_DATA"


def test_lossy_downgrades_are_cases():
    """An exception that names no case would let nothing through, and fail nothing."""
    assert LOSSY_DOWNGRADES.keys() - CASES.keys() == set()


@pytest.mark.parametrize("case", list(CASES))
async def test_downgrade_gives_back_what_was_there(engine, case: str):
    """
    A full database at the version before goes up to the case's version, then down:
    all that was there before the upgrade is back, but what LOSSY_DOWNGRADES lists.
    What the upgrade added is not looked at: the migration's own test checks that the
    downgrade takes it away, so that the upgrade can run again.
    """
    version, variant = CASES[case]
    await _station_at(engine, version - 1)
    await _execute(engine, variant)
    assert await _columns_without_data(engine) == [], "to fill in STATION_DATA"
    before = await _snapshot(engine)

    await do_update(engine, target_version=version)
    await do_update(engine, target_version=version - 1)

    assert await _schema_version(engine) == version - 1
    losses = _losses(before, await _snapshot(engine))
    known, _ = LOSSY_DOWNGRADES.get(case, (set(), ""))
    unlisted = {what: losses[what] for what in losses.keys() - known}
    assert unlisted == {}, "lost by the downgrade"
    assert known - losses.keys() == set(), "no longer lost: out of LOSSY_DOWNGRADES"
