"""Les preuves gardées d'une recherche, et la clé d'un titre (FON-25).

Les preuves sont ce que les sources ont dit d'un titre, réduit aux champs utiles,
sans le genre d'une personne ni les membres d'un groupe (`Search.evidence`). Elles
se gardent en JSON dans la base du moteur, et refont les propositions sans réseau :
quand les règles changent (`RULES_VERSION`), et quand un fichier déplacé revient
sous un autre identifiant de Beets.

La clé d'un titre le reconnaît d'un identifiant de Beets à l'autre : l'empreinte
quand `fpcalc` l'a prise, sinon l'artiste, le titre et la durée, normalisés. Les
décisions se gardent par clé : une valeur refusée ne se propose plus, même au titre
revenu sous un autre identifiant.

Sans réseau, sans Quart, sans Beets.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import hashlib
import sys
import types
import typing
from collections.abc import Mapping
from typing import Any

from radiotomate.fiches.normalize import normalize_text
from radiotomate.fiches.proposals import SearchResult, Track, WikidataArtist

if typing.TYPE_CHECKING:
    from radiotomate.fiches.fingerprint import Print

# La version des règles. La monter quand une règle change ce qu'elle propose : la
# tâche refait alors, d'après les preuves gardées, les propositions qui attendent.
RULES_VERSION = 1


def text_key(track: Track) -> str:
    """La clé d'un titre sans empreinte : l'artiste, le titre et la durée, à la
    seconde, normalisés."""
    seconds = round(track.length) if track.length else 0
    artist, title = normalize_text(track.artist), normalize_text(track.title)
    return f"texte:{artist}|{title}|{seconds}"


def print_key(fingerprint: Print) -> str:
    """La clé d'un titre par son empreinte : son condensé, l'empreinte entière
    faisant plusieurs kilo-octets."""
    digest = hashlib.sha256(fingerprint.fingerprint.encode("ascii", "replace"))
    return f"empreinte:{digest.hexdigest()[:40]}"


def to_json(
    result: SearchResult, wikidata: Mapping[str, WikidataArtist]
) -> dict[str, Any]:
    """Les preuves d'une recherche, en JSON : son résultat et ses fiches Wikidata,
    déjà réduits par `Search.evidence`."""
    return {
        "result": _dump(result),
        "wikidata": {key: _dump(value) for key, value in wikidata.items()},
    }


def from_json(
    data: Mapping[str, Any],
) -> tuple[SearchResult, dict[str, WikidataArtist]]:
    """Les preuves relues, telles que `to_json` les a écrites."""
    result = _load(SearchResult, data.get("result") or {"status": "erreur"})
    wikidata = {
        key: _load(WikidataArtist, value)
        for key, value in (data.get("wikidata") or {}).items()
    }
    return result, wikidata


def _dump(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _dump(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.compare
        }
    if isinstance(value, Mapping):
        return {str(key): _dump(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump(item) for item in value]
    return value


def _hints(kind: type) -> dict[str, Any]:
    """The annotations of a dataclass, read with the names of its module, and those
    of `collections.abc` that a module imports for typing only."""
    names = {**vars(collections.abc), **vars(sys.modules[kind.__module__])}
    return typing.get_type_hints(kind, globalns=names)


def _load(kind: Any, value: Any) -> Any:  # noqa: PLR0911
    """Une valeur JSON relue selon son type annoté."""
    if value is None:
        return None
    origin = typing.get_origin(kind)
    if origin in (typing.Union, types.UnionType):
        options = [arg for arg in typing.get_args(kind) if arg is not type(None)]
        return _load(options[0], value) if len(options) == 1 else value
    if dataclasses.is_dataclass(kind):
        hints = _hints(kind)
        known = {field.name for field in dataclasses.fields(kind) if field.init}
        return kind(
            **{
                name: _load(hints[name], item)
                for name, item in value.items()
                if name in known
            }
        )
    if origin is tuple:
        args = typing.get_args(kind)
        item = args[0] if args else Any
        return tuple(_load(item, one) for one in value)
    if origin is list:
        (item,) = typing.get_args(kind) or (Any,)
        return [_load(item, one) for one in value]
    if origin in (dict, Mapping) or kind is Mapping:
        args = typing.get_args(kind)
        item = args[1] if len(args) == 2 else Any
        return {key: _load(item, one) for key, one in value.items()}
    return value
