from sqlalchemy import text


async def upgrade(conn):
    await conn.execute(
        text(
            "ALTER TABLE carts ADD COLUMN ident_pads INTEGER NOT NULL DEFAULT 0"
        )
    )
    await conn.execute(
        text("UPDATE carts SET ident_pads = 1 WHERE title = 'Jingles' AND ident_pads = 0")
    )


async def downgrade(conn):
    await conn.execute(text("ALTER TABLE carts DROP COLUMN ident_pads"))
