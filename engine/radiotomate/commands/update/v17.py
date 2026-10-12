"""Agenda: dated broadcasts, their guests and files, cancelled weekly days.

Instants in these tables are naive UTC (see radiotomate.models.agenda).
"""

from sqlalchemy import text


async def upgrade(conn):
    await conn.execute(
        text(
            """
            CREATE TABLE agenda_guests (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR NOT NULL,
                contact VARCHAR NOT NULL DEFAULT '',
                token VARCHAR NOT NULL UNIQUE,
                token_created DATETIME NOT NULL,
                opened_at DATETIME,
                created DATETIME NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE TABLE agenda_diffusions (
                id INTEGER NOT NULL PRIMARY KEY,
                kind VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                starts_at DATETIME NOT NULL,
                ends_at DATETIME NOT NULL,
                guest_id INTEGER REFERENCES agenda_guests (id) ON DELETE SET NULL,
                host_username VARCHAR NOT NULL DEFAULT '',
                set_title VARCHAR NOT NULL DEFAULT '',
                tracklist TEXT NOT NULL DEFAULT '',
                rights_at DATETIME,
                deadline_at DATETIME,
                series_id VARCHAR,
                air_status VARCHAR NOT NULL DEFAULT 'upcoming',
                air_reason VARCHAR NOT NULL DEFAULT '',
                air_item_id VARCHAR,
                aired_start DATETIME,
                aired_end DATETIME,
                stop_requested_at DATETIME,
                created_by VARCHAR NOT NULL DEFAULT '',
                created DATETIME NOT NULL,
                modified DATETIME NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
    )
    for column in ("starts_at", "ends_at", "series_id", "air_status"):
        await conn.execute(
            text(
                f"CREATE INDEX ix_agenda_diffusions_{column} "
                f"ON agenda_diffusions ({column})"
            )
        )
    await conn.execute(
        text(
            """
            CREATE TABLE agenda_files (
                id INTEGER NOT NULL PRIMARY KEY,
                diffusion_id INTEGER NOT NULL
                    REFERENCES agenda_diffusions (id) ON DELETE CASCADE,
                path VARCHAR NOT NULL,
                origin VARCHAR NOT NULL,
                original_name VARCHAR NOT NULL DEFAULT '',
                duration FLOAT NOT NULL DEFAULT 0,
                gain FLOAT,
                report JSON NOT NULL DEFAULT '{}',
                late INTEGER NOT NULL DEFAULT 0,
                created DATETIME NOT NULL,
                replaced_at DATETIME
            )
            """
        )
    )
    await conn.execute(
        text("CREATE INDEX ix_agenda_files_diffusion_id ON agenda_files (diffusion_id)")
    )
    await conn.execute(
        text(
            """
            CREATE TABLE agenda_exceptions (
                id INTEGER NOT NULL PRIMARY KEY,
                emission_id INTEGER NOT NULL
                    REFERENCES emissions (id) ON DELETE CASCADE,
                day DATE NOT NULL,
                created DATETIME NOT NULL,
                UNIQUE (emission_id, day)
            )
            """
        )
    )


async def downgrade(conn):
    await conn.execute(text("DROP TABLE IF EXISTS agenda_exceptions"))
    await conn.execute(text("DROP INDEX IF EXISTS ix_agenda_files_diffusion_id"))
    await conn.execute(text("DROP TABLE IF EXISTS agenda_files"))
    for column in ("starts_at", "ends_at", "series_id", "air_status"):
        await conn.execute(text(f"DROP INDEX IF EXISTS ix_agenda_diffusions_{column}"))
    await conn.execute(text("DROP TABLE IF EXISTS agenda_diffusions"))
    await conn.execute(text("DROP TABLE IF EXISTS agenda_guests"))
