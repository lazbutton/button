"""The fiches of the library (FON-25): what the search found for each title, the
fields it proposes, and the decisions taken on them.

- `fiches`: a title searched, by its Beets id. Its key finds it again under another
  Beets id: its fingerprint when `fpcalc` took it, else its artist, title and
  length, normalized (`text_key`, kept to see a tag changed). Where its search is,
  its level and why, the source and its link, the version of the rules, the
  evidence (JSON, what the sources said, nothing about a person), and when to
  search it again.
- `fiche_propositions`: a field proposed for a fiche: the value before, the value
  proposed, its level, why, where from, and its state. They go with their fiche.
- `fiche_decisions`: each acceptance and refusal, by the key of the title, the field
  and the value proposed, with who and when. They outlive the title.

Times are naive UTC, like the new tables.
"""

from sqlalchemy import text


async def upgrade(conn):
    await conn.execute(
        text(
            """
            CREATE TABLE fiches (
                id INTEGER NOT NULL PRIMARY KEY,
                beets_id INTEGER NOT NULL,
                key VARCHAR NOT NULL,
                text_key VARCHAR NOT NULL,
                status VARCHAR NOT NULL,
                level VARCHAR NOT NULL,
                reasons JSON NOT NULL,
                source VARCHAR NOT NULL DEFAULT '',
                url VARCHAR NOT NULL DEFAULT '',
                rules_version INTEGER NOT NULL,
                evidence JSON,
                attempts INTEGER NOT NULL DEFAULT 0,
                error VARCHAR NOT NULL DEFAULT '',
                searched_at DATETIME NOT NULL,
                next_at DATETIME,
                created DATETIME NOT NULL,
                modified DATETIME NOT NULL,
                CONSTRAINT uq_fiches_beets_id UNIQUE (beets_id)
            )
            """
        )
    )
    await conn.execute(text("CREATE INDEX ix_fiches_key ON fiches (key)"))
    await conn.execute(text("CREATE INDEX ix_fiches_text_key ON fiches (text_key)"))
    await conn.execute(text("CREATE INDEX ix_fiches_next_at ON fiches (next_at)"))
    await conn.execute(
        text(
            """
            CREATE TABLE fiche_propositions (
                id INTEGER NOT NULL PRIMARY KEY,
                fiche_id INTEGER NOT NULL REFERENCES fiches (id) ON DELETE CASCADE,
                field VARCHAR NOT NULL,
                before VARCHAR NOT NULL,
                value VARCHAR NOT NULL,
                level VARCHAR NOT NULL,
                why VARCHAR NOT NULL DEFAULT '',
                source VARCHAR NOT NULL DEFAULT '',
                state VARCHAR NOT NULL,
                error VARCHAR NOT NULL DEFAULT '',
                created DATETIME NOT NULL,
                modified DATETIME NOT NULL
            )
            """
        )
    )
    await conn.execute(
        text(
            "CREATE INDEX ix_fiche_propositions_fiche_id "
            "ON fiche_propositions (fiche_id)"
        )
    )
    await conn.execute(
        text(
            """
            CREATE TABLE fiche_decisions (
                id INTEGER NOT NULL PRIMARY KEY,
                key VARCHAR NOT NULL,
                field VARCHAR NOT NULL,
                value VARCHAR NOT NULL,
                decision VARCHAR NOT NULL,
                username VARCHAR NOT NULL,
                decided_at DATETIME NOT NULL,
                CONSTRAINT uq_fiche_decisions_key_field_value
                    UNIQUE (key, field, value)
            )
            """
        )
    )
    await conn.execute(
        text("CREATE INDEX ix_fiche_decisions_key ON fiche_decisions (key)")
    )


async def downgrade(conn):
    await conn.execute(text("DROP INDEX ix_fiche_decisions_key"))
    await conn.execute(text("DROP TABLE fiche_decisions"))
    await conn.execute(text("DROP INDEX ix_fiche_propositions_fiche_id"))
    await conn.execute(text("DROP TABLE fiche_propositions"))
    await conn.execute(text("DROP INDEX ix_fiches_next_at"))
    await conn.execute(text("DROP INDEX ix_fiches_text_key"))
    await conn.execute(text("DROP INDEX ix_fiches_key"))
    await conn.execute(text("DROP TABLE fiches"))
