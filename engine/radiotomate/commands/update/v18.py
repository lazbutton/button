"""Encoder tokens: what an encoder sends to the harbor, instead of the account password.

Only the token's hash is kept. Its creation time is naive UTC, like the new tables.
"""

from sqlalchemy import text


async def upgrade(conn):
    await conn.execute(text("ALTER TABLE users ADD COLUMN stream_token_hash VARCHAR"))
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN stream_token_created_at DATETIME")
    )


async def downgrade(conn):
    await conn.execute(text("ALTER TABLE users DROP COLUMN stream_token_created_at"))
    await conn.execute(text("ALTER TABLE users DROP COLUMN stream_token_hash"))
