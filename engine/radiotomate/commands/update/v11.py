"""
Renamed the previous brand's carts, clocks, settings and sound titles to BUTTON.

Every database in service passed this version before the old labels were
removed from the code: it is kept empty so the schema numbering stays intact.
A fresh database has nothing to rename.
"""


async def upgrade(_conn):
    return


async def downgrade(_conn):
    return
