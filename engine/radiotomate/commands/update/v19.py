"""The saved views of the bank's table (FON-65): each account keeps its own.

A view is a name and what the table shows: its columns, its order, its ranking and
its filters, as JSON. It goes with its account. Its times are naive UTC, like the new
tables.
"""

from sqlalchemy import text


async def upgrade(conn):
    await conn.execute(
        text(
            """
            CREATE TABLE bank_views (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                name VARCHAR NOT NULL,
                state JSON NOT NULL,
                created DATETIME NOT NULL,
                modified DATETIME NOT NULL,
                CONSTRAINT uq_bank_views_user_name UNIQUE (user_id, name)
            )
            """
        )
    )
    await conn.execute(
        text("CREATE INDEX ix_bank_views_user_id ON bank_views (user_id)")
    )


async def downgrade(conn):
    await conn.execute(text("DROP INDEX ix_bank_views_user_id"))
    await conn.execute(text("DROP TABLE bank_views"))
