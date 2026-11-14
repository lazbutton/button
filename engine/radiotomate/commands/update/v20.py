"""Beets 2.14 (ARC-06): the music categories search `genres`, no longer `genre`.

Beets 2.14 keeps the genres of a track in a list field, `genres`. It still reads
`genre:` in a query, but through an alias that writes a warning in the log at each
query, and that Beets 3.0 removes. The upgrade rewrites the field in the queries of
the categories, `query` and `empty_query`, and the downgrade puts `genre` back, for
the Beets 2.5 of the engine before.

A field starts a term: at the start of the query, or after a space, a comma or a
quote, behind a `-` or `^` that negates it. It ends with `:`, as in `genre:Jazz`,
`genre::^Jazz$` or `genre:=Jazz`, or with the `+` or `-` of a sort, as in `genre+`.
A value that holds ` genre:` itself, between quotes, is rewritten too: Beets reads it
as a value, but no station writes one. A query that searched `genres:` before the
upgrade, which found nothing in Beets 2.5, goes down as `genre:`.

This module has its own copy of the rule: a published migration never changes, while
the check of the queries (`radiotomate/services/beets_query.py`) may.
"""

import re

from sqlalchemy import text


def _field(name: str) -> re.Pattern:
    return re.compile(rf"""(^|[\s,"'])([-^]?){name}(?=:|[+-](?:$|[\s,"']))""")


GENRE = _field("genre")
GENRES = _field("genres")


async def _rewrite(conn, pattern: re.Pattern, field: str) -> None:
    rows = await conn.execute(
        text("SELECT id, query, empty_query FROM music_categories")
    )
    for category_id, query, empty_query in rows.all():
        new_query = pattern.sub(rf"\1\2{field}", query)
        new_empty = pattern.sub(rf"\1\2{field}", empty_query or "")
        if (new_query, new_empty) != (query, empty_query or ""):
            await conn.execute(
                text(
                    "UPDATE music_categories SET query = :query, empty_query = :empty "
                    "WHERE id = :id"
                ),
                {"query": new_query, "empty": new_empty, "id": category_id},
            )


async def upgrade(conn):
    await _rewrite(conn, GENRE, "genres")


async def downgrade(conn):
    await _rewrite(conn, GENRES, "genre")
