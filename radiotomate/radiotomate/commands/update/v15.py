from sqlalchemy import text


async def upgrade(conn):
    await conn.execute(
        text(
            "ALTER TABLE emissions ADD COLUMN host_username VARCHAR NOT NULL DEFAULT ''"
        )
    )


async def downgrade(conn):
    await conn.execute(text("ALTER TABLE emissions DROP COLUMN host_username"))
