"""Les requêtes Beets des sélections de titres, saisies par un admin.

Beets 2.5.1 coupe une requête à ses virgules (`parse_sorted_query`, dans
`beets/dbcore/queryparse.py`) : chaque partie devient une requête à part, et un
titre est pris s'il répond à l'une d'elles. Une partie sans filtre prend toute la
bibliothèque : sous `grouping:jazz,`, l'auto-DJ jouerait n'importe quel titre.

La requête est lue par Beets lui-même, pour voir les parties comme il les voit.
"""

from __future__ import annotations

from beets.dbcore.query import (
    AndQuery,
    InvalidQueryArgumentValueError,
    OrQuery,
    ParsingError,
    Query,
    TrueQuery,
)
from beets.library import Item, parse_query_string

from radiotomate.domain.errors import DomainValidationError

EXTRA_COMMA = (
    "Il y a une virgule en trop dans la requête : Beets lirait à côté une partie "
    "vide, qui prend toute la bibliothèque. Retire-la."
)
UNCLOSED_QUOTE = "Un guillemet n'est pas fermé dans la requête."
TRAILING_BACKSLASH = "La requête finit par une barre oblique inverse : retire-la."
BAD_VALUE = (
    "Beets ne sait pas lire une valeur de la requête : vérifie les nombres, "
    "les durées, les dates et les expressions régulières."
)


def _parse(query: str) -> Query:
    return parse_query_string(query, Item)[0]


def _takes_everything(query: Query) -> bool:
    """Une partie sans filtre, que Beets lit comme « tous les titres »."""
    if isinstance(query, AndQuery):
        return all(_takes_everything(sub) for sub in query.subqueries)
    return isinstance(query, TrueQuery)


def validate_selection_query(query: str, *, field: str = "query") -> None:
    """Refuse une requête que Beets ne sait pas lire, ou dont une partie prend tout.

    Une requête sans virgule qui prend tout, comme un tri seul (`year+`), reste
    permise : elle le dit d'elle-même.
    """
    try:
        parsed = _parse(query)
    except InvalidQueryArgumentValueError as exc:
        raise DomainValidationError(BAD_VALUE, field=field) from exc
    except ParsingError as exc:
        # shlex : un guillemet ouvert, ou une barre oblique inverse à la fin.
        quote = "quotation" in str(exc)
        message = UNCLOSED_QUOTE if quote else TRAILING_BACKSLASH
        raise DomainValidationError(message, field=field) from exc
    if isinstance(parsed, OrQuery) and any(
        _takes_everything(sub) for sub in parsed.subqueries
    ):
        raise DomainValidationError(EXTRA_COMMA, field=field)


def playable_query(query: str) -> str | Query:
    """La requête que l'auto-DJ passe à Beets : sans ses parties vides.

    Une sélection enregistrée avant la règle peut encore avoir une virgule en
    trop : seules ses parties qui filtrent restent. Une requête que Beets ne sait
    pas lire est rendue telle quelle, et Beets la refuse comme avant.
    """
    try:
        parsed = _parse(query)
    except ParsingError:
        return query
    if not isinstance(parsed, OrQuery):
        return query
    kept = [sub for sub in parsed.subqueries if not _takes_everything(sub)]
    if not kept or len(kept) == len(parsed.subqueries):
        return query
    return kept[0] if len(kept) == 1 else OrQuery(kept)
