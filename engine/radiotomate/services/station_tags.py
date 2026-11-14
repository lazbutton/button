"""Les étiquettes de la station (FON-74). Sans Quart, sans Beets.

Une étiquette dit ce que la station pense d'un titre : une ambiance, une langue,
un moment de la journée. Elle vit dans un champ flexible de Beets, `etiquettes` :
la bibliothèque seulement, jamais le fichier, comme la famille. Un titre déplacé
hors de BUTTON, par le dossier de la station, revient donc sans elles.

Le champ garde ses étiquettes triées, chacune entourée du séparateur :
`|instrumental|nuit|`. Une sélection de titres en prend une par `etiquettes:|nuit|`,
qui ne prend ni « minuit » ni « nuitamment ». La virgule, d'abord proposée, ne
tient pas : Beets coupe une requête à toute virgule qui finit un mot, et
`etiquettes:,nuit,` y devenait une requête vide, qui prend toute la bibliothèque.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from radiotomate.domain.errors import DomainValidationError

if TYPE_CHECKING:
    from collections.abc import Iterable

FIELD = "etiquettes"
SEPARATOR = "|"
MAX_TAG = 40
# Une étiquette se tape dans une requête : ni séparateur, ni virgule, que Beets
# lit comme une fin de requête, ni guillemet, ni signe de contrôle.
_REFUSED = re.compile(r"[|,\"\\\x00-\x1f\x7f]")


def clean_tag(raw: object, *, field: str = "tag") -> str:
    """Une étiquette telle qu'elle s'écrit : en minuscules, ses espaces tassés.
    Lève `DomainValidationError`."""
    if not isinstance(raw, str):
        raise DomainValidationError("Une étiquette est un texte.", field=field)
    tag = " ".join(unicodedata.normalize("NFC", raw).split()).lower()
    if not tag:
        raise DomainValidationError("Une étiquette a au moins une lettre.", field=field)
    if _REFUSED.search(tag):
        raise DomainValidationError(
            "Une étiquette ne prend ni barre droite, ni virgule, ni guillemet : "
            "ils couperaient une sélection de titres.",
            field=field,
        )
    if len(tag) > MAX_TAG:
        raise DomainValidationError(
            f"Une étiquette tient en {MAX_TAG} signes.", field=field
        )
    return tag


def parse_tags(value: object) -> list[str]:
    """Les étiquettes d'un champ, dans son ordre."""
    if not value:
        return []
    return [part for part in str(value).split(SEPARATOR) if part.strip()]


def format_tags(tags: Iterable[str]) -> str:
    """Le champ de ces étiquettes, triées et sans doublon ; vide sans étiquette."""
    kept = sorted(set(tags))
    return f"{SEPARATOR}{SEPARATOR.join(kept)}{SEPARATOR}" if kept else ""


def with_tags(current: object, add: Iterable[str], remove: Iterable[str]) -> str:
    """Le champ d'un titre, ces étiquettes posées et celles-là retirées."""
    removed = set(remove)
    tags = [tag for tag in parse_tags(current) if tag not in removed]
    return format_tags([*tags, *add])


def clean_field(raw: object) -> str:
    """Un champ entier, relu et récrit : ce que le service d'écriture garde."""
    if raw in (None, ""):
        return ""
    if not isinstance(raw, str):
        raise DomainValidationError("Les étiquettes sont un texte.", field=FIELD)
    return format_tags(clean_tag(tag, field=FIELD) for tag in parse_tags(raw))


def tag_query(tag: str) -> str:
    """La requête Beets des titres qui portent cette étiquette."""
    return f"{FIELD}:{SEPARATOR}{tag}{SEPARATOR}"
