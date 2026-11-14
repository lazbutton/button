"""A selection of titles composed by filters (FON-73), written as a Beets query.

The console clicks filters; the engine writes the query that says the same, so
that only it knows the paths of the bank and the version of Beets. The query is
checked by ``beets_query.validate_selection_query``, as one typed by hand.

- An artist, an album or a genre is that value alone, whatever its case:
  ``artist:=~Orage`` does not take « Madame Orage ».
- The family is a flexible field, its short name: ``famille:=jazz``.
- A collection is its folder, ``path:`` and the folder under MEDIA_ROOT, as the
  table reads it; the rotation its own folder, as the Rotation selection. The
  bank is MEDIA_ROOT, ``/media`` on a station.
- The genre is ``genres``, the list of Beets 2.14 (ARC-06), whose ``genre:`` the
  check refuses; ``genre`` still, for a library of Beets 2.5.
- A tag of the station (FON-74) is that tag between its separators,
  ``etiquettes:|nuit|``, which takes neither « minuit » nor « nuitamment ».
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from radiotomate.domain.errors import DomainValidationError
from radiotomate.services.bank_titles import media_root_text
from radiotomate.services.media_bank import COLLECTIONS_TOP, ROTATION_TOP
from radiotomate.services.station_tags import clean_tag, tag_query

ROTATION = "rotation"
YEAR_MIN = 1000
YEAR_MAX = 2999


@dataclass(frozen=True)
class SelectionFilters:
    famille: str = ""
    collection: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    etiquette: str = ""
    year_from: int | None = None
    year_to: int | None = None

    @classmethod
    def from_args(cls, args) -> SelectionFilters:
        def text(name: str) -> str:
            return " ".join(str(args.get(name) or "").split())

        def year(name: str) -> int | None:
            raw = text(name)
            if not raw:
                return None
            if not raw.isdigit() or not YEAR_MIN <= int(raw) <= YEAR_MAX:
                raise DomainValidationError(
                    "Une année s'écrit en quatre chiffres.", field=name
                )
            return int(raw)

        made = cls(
            famille=text("famille"),
            collection=text("collection"),
            artist=text("artist"),
            album=text("album"),
            genre=text("genre"),
            etiquette=clean_tag(text("etiquette"), field="etiquette")
            if text("etiquette")
            else "",
            year_from=year("year_from"),
            year_to=year("year_to"),
        )
        if made.year_from and made.year_to and made.year_from > made.year_to:
            raise DomainValidationError(
                "L'année de début vient après celle de fin.", field="year_to"
            )
        if "/" in made.collection or made.collection.startswith("."):
            raise DomainValidationError("Collection inconnue.", field="collection")
        return made

    def empty(self) -> bool:
        return not any(
            (
                self.famille,
                self.collection,
                self.artist,
                self.album,
                self.genre,
                self.etiquette,
                self.year_from,
                self.year_to,
            )
        )


def _exact(field: str, value: str) -> str:
    # A value that ends with a comma would split the query (beets_query.py): a
    # regular expression says the same without one at its end.
    if value.endswith(","):
        escaped = "".join(f"\\{char}" if not char.isalnum() else char for char in value)
        return f"{field}::(?i)^{escaped}$"
    return f"{field}:=~{value}"


def selection_query(filters: SelectionFilters, *, genre_field: str = "genres") -> str:
    """The Beets query of these filters, each part quoted for Beets' shell split."""
    if filters.empty():
        raise DomainValidationError(
            "Choisis au moins un filtre : sans filtre, la sélection prendrait toute la "
            "bibliothèque."
        )
    parts: list[str] = []
    if filters.famille:
        parts.append(f"famille:={filters.famille}")
    root = media_root_text().rstrip("/")
    if filters.collection == ROTATION:
        parts.append(f"path:{root}/{ROTATION_TOP}")
    elif filters.collection:
        parts.append(f"path:{root}/{COLLECTIONS_TOP}/{filters.collection}")
    if filters.artist:
        parts.append(_exact("artist", filters.artist))
    if filters.album:
        parts.append(_exact("album", filters.album))
    if filters.genre:
        parts.append(_exact(genre_field, filters.genre))
    if filters.etiquette:
        parts.append(tag_query(filters.etiquette))
    if filters.year_from or filters.year_to:
        # A title without a year has 0 in Beets: « until 1999 » does not take it.
        start = filters.year_from or 1
        end = filters.year_to or ""
        parts.append(f"year:{start}..{end}")
    return " ".join(_quoted(part) for part in parts)


def _quoted(part: str) -> str:
    """A part as Beets' shell split reads it back: quoted only when it must be."""
    if any(char.isspace() or char in "'\"\\" for char in part):
        return shlex.quote(part)
    return part
