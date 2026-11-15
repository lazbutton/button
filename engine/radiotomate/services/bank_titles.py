"""Le tableau de la banque (FON-64) : les titres de la bibliothèque de Beets, triés,
filtrés et rangés par collection, artiste, famille, album ou étiquette de la
station (FON-74). Sans Quart.

La bibliothèque de Beets est la source du tableau : elle a l'album, le genre,
l'année et les champs flexibles, que l'index de la recherche n'a pas
(docs/decisions/0020-la-banque-se-range-par-ses-fiches.md). Elle ne connaît que
la rotation et les collections.

Tout le chantier « Ranger la banque » tient derrière un interrupteur général,
``features.bank_tidy``, allumé depuis FON-85. Coupé, le tableau reste en lecture,
et rien du chantier n'écrit plus dans les fichiers.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from radiotomate.domain.errors import DomainError, DomainValidationError
from radiotomate.fiches.rules import FAMILIES
from radiotomate.models import Setting
from radiotomate.services.media_bank import (
    BANK_ZONES,
    COLLECTIONS_TOP,
    ROTATION_TOP,
    media_root,
)
from radiotomate.services.station_tags import parse_tags

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy.orm import Session as ormSession

# L'interrupteur général du chantier. Une clé absente le laisse allumé (FON-85).
# Coupé, les lectures du tableau répondent, et ses gestes sont refusés.
SETTING_BANK_TIDY = "features.bank_tidy"
SETTING_OFF = {"0", "false", "off", "no", "non", ""}

ZONES = {ROTATION_TOP: "rotation", COLLECTIONS_TOP: "collections", **BANK_ZONES}
ROTATION = "rotation"
FAMILY_LABELS = {family.name: family.label for family in FAMILIES}
# Les champs d'une fiche complète, dans l'ordre des colonnes.
FICHE_FIELDS = ("title", "artist", "album", "year", "genre", "famille")
# Les colonnes qui se trient, et les filtres qui prennent une valeur exacte.
SORTS = ("title", "artist", "album", "famille", "genre", "year", "duration")
FILTERS = ("collection", "artist", "famille", "album", "genre", "year", "etiquette")
# What the table ranges by; the genre is no ranking, but a selection picks it (FON-73).
RANKINGS = ("collection", "artist", "famille", "album", "etiquette")
FACETS = (*RANKINGS, "genre")
# The verdict (FON-80), a column, a filter and a ranking only once switched on.
VERDICT = "fmg"
VERDICT_LABELS = {"oui": "Oui", "mixte": "Mixte", "non": "Non"}
PAGE = 100
MAX_PAGE = 500
# Beets garde les valeurs d'un champ multiple, comme les genres de Beets 2.14,
# séparées ainsi.
_MULTI_SEPARATORS = ("\\␀", "␀")


class BankTidyOff(DomainError):  # noqa: N818
    status_code = 409
    code = "bank_tidy_off"


async def bank_tidy_enabled(session: ormSession) -> bool:
    """Whether the bank's tidying writes: on, unless a station turns it off."""
    row = await Setting.from_key(session, SETTING_BANK_TIDY)
    return row is None or str(row.value).strip().lower() not in SETTING_OFF


async def require_bank_tidy(session: ormSession) -> None:
    if not await bank_tidy_enabled(session):
        raise BankTidyOff(
            "Le rangement de la banque est coupé sur cette station : "
            "le tableau reste en lecture."
        )


def fold(text: str) -> str:
    """« Été » and « ete » are the same word to a search, as in the catalogue."""
    plain = unicodedata.normalize("NFD", text)
    return "".join(char for char in plain if not unicodedata.combining(char)).casefold()


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "surrogateescape")
    return " ".join(str(value).split())


def _genre(value: object) -> str:
    text = _text(value)
    for separator in _MULTI_SEPARATORS:
        text = text.replace(separator, ", ")
    return text


def bank_rel(raw: object, root: str | None = None) -> str:
    """The path of a title below the bank, as the station's folder shows it.

    Beets keeps absolute paths, `/media/…` in the station's containers. A path
    outside MEDIA_ROOT, such as the demo's, is read from its first bank folder.
    """
    if isinstance(raw, bytes):
        path = raw.decode("utf-8", "surrogateescape")
    else:
        path = str(raw or "")
    bases = [root] if root is not None else [media_root_text(), str(media_root())]
    for raw_base in bases:
        base = raw_base.rstrip("/")
        if base and path.startswith(base + "/"):
            return path[len(base) + 1 :]
    parts = PurePosixPath(path).parts
    for index, part in enumerate(parts):
        if part in ZONES:
            return "/".join(parts[index:])
    return path.lstrip("/")


def place_of(rel: str) -> tuple[str, str]:
    """The zone of a title, and its collection: `rotation`, or the folder's name."""
    parts = rel.split("/")
    zone = ZONES.get(parts[0], "")
    if zone == "rotation":
        return zone, ROTATION
    if zone == "collections" and len(parts) > 2:
        return zone, parts[1]
    return zone, ""


def title_of(row: tuple, root: str | None = None, *, verdict: bool = False) -> dict:
    """One row of the table, from one row of `BeetsIntegration.title_rows`.

    The verdict « femme ou minorité de genre » (FON-80) is there only when asked,
    the switch `features.fiches_fmg` on: switched off, it leaves no trace."""
    beets_id, path, title, artist, album, year, genre, length, famille, *more = row
    rel = bank_rel(path, root)
    zone, collection = place_of(rel)
    try:
        year_value = int(year or 0) or None
    except (TypeError, ValueError):
        year_value = None
    try:
        duration = float(length) if length else None
    except (TypeError, ValueError):
        duration = None
    family = _text(famille)
    entry = {
        "id": int(beets_id),
        "title": _text(title),
        "artist": _text(artist),
        "album": _text(album),
        "year": year_value,
        "genre": _genre(genre),
        "famille": family,
        "famille_label": FAMILY_LABELS.get(family, family),
        # The station's tags (FON-74), a flexible field: |instrumental|nuit|.
        "etiquettes": parse_tags(more[0] if more else None),
        "duration": duration,
        "zone": zone,
        "collection": collection,
        "path": rel,
    }
    if verdict:
        value = _text(more[1] if len(more) > 1 else None)
        entry["fmg"] = value if value in VERDICT_LABELS else ""
    entry["missing"] = [name for name in FICHE_FIELDS if not entry[name]]
    return entry


@dataclass
class TitleQuery:
    """What the table asks for: a text, exact filters, an order and a page."""

    q: str = ""
    filters: dict[str, str] = field(default_factory=dict)
    sort: str = "artist"
    descending: bool = False
    offset: int = 0
    limit: int = PAGE
    facets: tuple[str, ...] = ()
    # From and to, both kept: a title without a year is in neither.
    years: tuple[int | None, int | None] = (None, None)

    @classmethod
    def from_args(cls, args: Mapping[str, str], *, verdict: bool = False) -> TitleQuery:
        """A filter given empty takes the titles where that field is empty. The
        verdict sorts, filters and ranges only switched on: off, it is a name the
        table does not know."""
        extra = (VERDICT,) if verdict else ()
        sorts, filters_known, facets_known = (
            (*SORTS, *extra),
            (*FILTERS, *extra),
            (*FACETS, *extra),
        )
        sort = str(args.get("sort") or "artist")
        if sort not in sorts:
            raise DomainValidationError(f"Tri inconnu : {sort}.", field="sort")
        order = str(args.get("order") or "asc")
        if order not in ("asc", "desc"):
            raise DomainValidationError(f"Ordre inconnu : {order}.", field="order")
        facets = tuple(
            name for name in str(args.get("facets") or "").split(",") if name.strip()
        )
        unknown = [name for name in facets if name not in facets_known]
        if unknown:
            raise DomainValidationError(
                f"Facette inconnue : {unknown[0]}.", field="facets"
            )
        filters = {
            name: " ".join(str(args[name]).split())
            for name in filters_known
            if name in args
        }
        for name in ("year", "year_from", "year_to"):
            if args.get(name) and not str(args[name]).strip().isdigit():
                raise DomainValidationError("L'année est un nombre.", field=name)
        return cls(
            q=str(args.get("q") or ""),
            filters=filters,
            sort=sort,
            descending=order == "desc",
            offset=_bounded(args.get("offset"), 0, 0, 10**9, "offset"),
            limit=_bounded(args.get("limit"), PAGE, 1, MAX_PAGE, "limit"),
            facets=facets,
            years=(
                int(args["year_from"]) if args.get("year_from") else None,
                int(args["year_to"]) if args.get("year_to") else None,
            ),
        )


def _bounded(raw: object, default: int, low: int, high: int, name: str) -> int:
    if raw in (None, ""):
        return default
    try:
        value = int(str(raw))
    except ValueError as exc:
        raise DomainValidationError(f"{name} est un nombre.", field=name) from exc
    return max(low, min(high, value))


def _value(entry: dict, name: str) -> str:
    value = entry[name]
    return "" if value is None else str(value)


def _matches(entry: dict, query: TitleQuery, words: list[str]) -> bool:
    for name, wanted in query.filters.items():
        if name == "etiquette":
            # One tag among those of the title; given empty, the titles without any.
            tags = [fold(tag) for tag in entry["etiquettes"]]
            if (fold(wanted) not in tags) if wanted else bool(tags):
                return False
        elif fold(_value(entry, name)) != fold(wanted):
            return False
    start, end = query.years
    if start is not None or end is not None:
        year = entry["year"]
        if year is None or (start is not None and year < start):
            return False
        if end is not None and year > end:
            return False
    if words:
        haystack = fold(
            " ".join((entry["title"], entry["artist"], entry["album"], entry["path"]))
        )
        return all(word in haystack for word in words)
    return True


def _sort_key(name: str):
    """Empty values go last, whatever the order: they are what is left to fill."""
    if name == VERDICT:
        order = list(VERDICT_LABELS)
        return lambda entry: not entry[name], lambda entry: (
            order.index(entry[name]) if entry[name] in order else len(order)
        )
    if name in ("year", "duration"):
        return lambda entry: entry[name] is None, lambda entry: entry[name] or 0
    return lambda entry: not entry[name], lambda entry: fold(_value(entry, name))


def _ordered(entries: list[dict], query: TitleQuery) -> list[dict]:
    # Ties: artist, then title, then id, so that a page never shifts.
    ordered = sorted(
        entries,
        key=lambda entry: (fold(entry["artist"]), fold(entry["title"]), entry["id"]),
    )
    empty, value = _sort_key(query.sort)
    ordered.sort(key=value, reverse=query.descending)
    ordered.sort(key=empty)
    return ordered


def _facet_values(entry: dict, name: str) -> list[str]:
    """What a title counts for in a facet: its value, or each of its tags."""
    if name == "etiquette":
        return entry["etiquettes"] or [""]
    return [_value(entry, name)]


def facet_counts(entries: Iterable[dict], name: str) -> list[dict]:
    """The values of a column, each with its number of titles; the empty one last.
    A title with several tags counts for each."""
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for entry in entries:
        for value in _facet_values(entry, name):
            key = fold(value)
            counts[key] = counts.get(key, 0) + 1
            labels.setdefault(key, value)
    rows = [
        {
            "value": labels[key],
            "label": FAMILY_LABELS.get(labels[key], labels[key])
            if name == "famille"
            else VERDICT_LABELS.get(labels[key], labels[key])
            if name == VERDICT
            else labels[key],
            "count": count,
        }
        for key, count in counts.items()
    ]
    rows.sort(key=lambda row: (not row["value"], fold(row["label"])))
    return rows


def titles_page(
    rows: Iterable[tuple],
    query: TitleQuery,
    root: str | None = None,
    carts: Mapping[str, list[dict]] | None = None,
    *,
    verdict: bool = False,
) -> dict:
    """One page of the table, and the facets it asked for, over the whole bank.

    `carts` names, by path below the bank, the carts that play a title without a
    copy (FON-69): the console says so before the title leaves the bank.
    """
    entries = [title_of(row, root, verdict=verdict) for row in rows]
    for entry in entries:
        entry["carts"] = (carts or {}).get(entry["path"], [])
    words = [word for word in fold(query.q).split() if word]
    kept = [entry for entry in entries if _matches(entry, query, words)]
    ordered = _ordered(kept, query)
    return {
        "titles": ordered[query.offset : query.offset + query.limit],
        "total": len(entries),
        "matched": len(kept),
        "offset": query.offset,
        "limit": query.limit,
        "sort": query.sort,
        "order": "desc" if query.descending else "asc",
        "facets": {name: facet_counts(entries, name) for name in query.facets},
    }


async def carts_by_title(session: ormSession, root: str | None = None) -> dict:
    """The carts that play each title of the bank, by its path below the bank."""
    from sqlalchemy import select

    from radiotomate.models import Cart, Sound

    rows = await session.execute(
        select(Sound.path, Cart.id, Cart.title)
        .join(Cart, Cart.id == Sound.cart_id)
        .order_by(Cart.title, Cart.id)
    )
    found: dict[str, list[dict]] = {}
    for path, cart_id, title in rows:
        rel = bank_rel(str(path), root)
        listed = found.setdefault(rel, [])
        if not any(cart["id"] == cart_id for cart in listed):
            listed.append({"id": cart_id, "title": title})
    return found


def title_label(artist: object, title: object, path: Path) -> str:
    """How a cart names a title of the bank: « Artiste - Titre », as its sounds."""
    artist_text, title_text = _text(artist), _text(title)
    if artist_text and title_text:
        return f"{artist_text} - {title_text}"
    return title_text or path.name


def media_root_text() -> str:
    """MEDIA_ROOT as Beets writes it, without resolving a link (the demo has none)."""
    return os.environ.get("MEDIA_ROOT", "/media")
