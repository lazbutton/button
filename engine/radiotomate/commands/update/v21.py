"""The journal of the gestures on the bank (FON-66): one row per lot, one per change.

Instants in these tables are naive UTC (see radiotomate.models.journal).
"""

from sqlalchemy import text


async def upgrade(conn):
    await conn.execute(
        text(
            """
            CREATE TABLE journal_entries (
                id INTEGER NOT NULL PRIMARY KEY,
                gesture VARCHAR NOT NULL,
                username VARCHAR NOT NULL,
                created DATETIME NOT NULL,
                titles INTEGER NOT NULL DEFAULT 0,
                undo_of INTEGER REFERENCES journal_entries (id) ON DELETE SET NULL,
                details JSON NOT NULL DEFAULT '{}'
            )
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE TABLE journal_changes (
                id INTEGER NOT NULL PRIMARY KEY,
                entry_id INTEGER NOT NULL
                    REFERENCES journal_entries (id) ON DELETE CASCADE,
                beets_id INTEGER,
                path VARCHAR NOT NULL DEFAULT '',
                label VARCHAR NOT NULL DEFAULT '',
                field VARCHAR NOT NULL,
                old_value JSON,
                new_value JSON,
                status VARCHAR NOT NULL DEFAULT 'pending',
                reason VARCHAR,
                applied_at DATETIME
            )
            """
        )
    )
    for column in ("gesture", "username", "created", "undo_of"):
        await conn.execute(
            text(
                f"CREATE INDEX ix_journal_entries_{column} "
                f"ON journal_entries ({column})"
            )
        )
    for column in ("entry_id", "beets_id", "status"):
        await conn.execute(
            text(
                f"CREATE INDEX ix_journal_changes_{column} "
                f"ON journal_changes ({column})"
            )
        )


async def downgrade(conn):
    await conn.execute(text("DROP TABLE journal_changes"))
    await conn.execute(text("DROP TABLE journal_entries"))
