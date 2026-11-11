"""Le texte d'un titre ou d'un artiste, normalisé avant toute comparaison.

Les règles de `normalize.ts`, dans Hopper :

- NFKD, accents retirés, minuscules, ponctuation remplacée par des espaces ; les
  écritures non latines restent ;
- les artistes séparés sur « , & + / ; feat. ft. featuring with avec x vs. and et » ;
  un « (feat. X) » du titre rejoint les artistes ;
- les mentions de version extraites du titre, pas retirées : live, remix et son
  remixeur, acoustic, instrumental, radio edit, extended, club mix, dub, vip, sped
  up, slowed, karaoke, demo, remaster, reprise, une langue (« English Version ») ou
  une version nommée (« Piano Version »), qui sont d'autres enregistrements ;
- « Original Mix », « Album Version », « Explicit »… désignent la version de base :
  ignorés.

Les deux côtés d'une comparaison passent par les mêmes règles : « Simon & Garfunkel »
devient { simon, garfunkel } partout, et la comparaison reste juste.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def js_regex(pattern: str, flags: int = 0) -> re.Pattern[str]:
    r"""Compile une regex de Hopper, écrite pour JavaScript.

    Son `\b` n'y connaît que les lettres ASCII, comme en JavaScript : « Søet » a un
    « et » pour Hopper, pas pour le `\b` de Python. Le reste de la regex s'écrit en
    Python : `[0-9]` pour le `\d` de JavaScript, `\Z` pour son `$`, et `[^\W\d_]`
    pour une lettre (`\p{L}`), qui y prend aussi un nombre comme « ² ».
    """
    return re.compile(pattern.replace(r"\b", r"(?a:\b)"), flags)


def is_mark(char: str) -> bool:
    """Un accent combinant, ou une autre marque (`\\p{M}`)."""
    return unicodedata.category(char).startswith("M")


def is_upper(char: str) -> bool:
    """Une lettre capitale (`\\p{Lu}`)."""
    return unicodedata.category(char) == "Lu" if char else False


def without_marks(text: str) -> str:
    return "".join(char for char in text if not is_mark(char))


_APOSTROPHES = re.compile(r"[\u2019'`\u00b4\u02bc]")
# Tout ce qui n'est ni une lettre ni un chiffre (`[^\p{L}\p{N}]`).
_NOT_ALNUM = re.compile(r"[\W_]+")
_SPACES = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Accents et ponctuation retirés, minuscules ; une autre écriture reste.

    « L'amour   toujours » → « lamour toujours », « Rock & Roll » → « rock and roll ».
    """
    text = without_marks(unicodedata.normalize("NFKD", text)).lower()
    text = _APOSTROPHES.sub("", text).replace("&", " and ")
    return _SPACES.sub(" ", _NOT_ALNUM.sub(" ", text).strip())


def squash(text: str) -> str:
    """Le texte normalisé, sans ses espaces : « Hush Puppies » et « HUSHPUPPIES »."""
    return normalize_text(text).replace(" ", "")


_ARTIST_SEPARATORS = js_regex(
    r"\s*(?:,|&|\+|/|;|\bfeat\.?(?=\s)|\bft\.?(?=\s)|\bfeaturing\b|\bwith\b"
    r"|\bavec\b|\s[x\u00d7]\s|\bvs\.?(?=\s)|\band\b|\bet\b)\s*",
    re.IGNORECASE,
)


def split_artists(names: str | Iterable[str]) -> list[str]:
    """Les artistes normalisés, dédoublonnés, dans l'ordre."""
    if isinstance(names, str):
        names = [names]
    parts = (part for name in names for part in _ARTIST_SEPARATORS.split(name))
    return list(dict.fromkeys(filter(None, map(normalize_text, parts))))


_LANGUAGES = {
    "english": "en",
    "anglaise": "en",
    "french": "fr",
    "francaise": "fr",
    "spanish": "es",
    "espanol": "es",
    "espagnole": "es",
    "italian": "it",
    "italiano": "it",
    "italienne": "it",
    "german": "de",
    "deutsch": "de",
    "allemande": "de",
    "portuguese": "pt",
    "japanese": "ja",
    "korean": "ko",
}

# Les mentions qui ne changent pas l'enregistrement, ou désignent la version de base.
_NEUTRAL = re.compile(
    r"(?:(?:original|album|single|main|lp|full|explicit|clean|censored|edited|dirty"
    r"|uncensored|bonus track|mono|stereo)(?: mix| version| edit)?|from .+"
    r"|bonus track|explicit version|clean version)"
)

# Les étiquettes de version, dans l'ordre où Hopper les relève.
_TAGS = (
    (
        "radio edit",
        js_regex(r"\b(?:radio|single|short)(?: edit| version| mix)\b|^edit\Z|^radio\Z"),
    ),
    ("club mix", js_regex(r"\bclub mix\b")),
    ("extended", js_regex(r"\bextended\b")),
    ("sped up", js_regex(r"\bsped up\b|\bspeed up\b|\bnightcore\b")),
    ("slowed", js_regex(r"\bslowed\b")),
    ("instrumental", js_regex(r"\binstrumental\b")),
    ("acoustic", js_regex(r"\bacoustic\b|\bacoustique\b|\bunplugged\b|\bstripped\b")),
    ("karaoke", js_regex(r"\bkaraoke\b")),
    ("demo", js_regex(r"\bdemo\b")),
    ("dub", js_regex(r"\bdub\b")),
    ("vip", js_regex(r"\bvip\b")),
    ("live", js_regex(r"\blive\b|\ben (?:direct|concert|public)\b")),
    ("remaster", js_regex(r"\bremaster")),
    ("reprise", js_regex(r"\breprise\b")),
)
_LANGUAGE = js_regex(r"\b([^\W\d_]+) version\b|\bversion ([^\W\d_]+)\b")
_REMIX = js_regex(r"(.*?)\s*\b(?:remix(?:ed)?|rmx|rework|bootleg)\b")
_NOT_A_REMIXER_EDIT = re.compile(
    r"(?:radio|single|short|extended|club|album|clean|explicit)"
)
_NOT_A_REMIXER_MIX = re.compile(
    r"(?:original|radio|club|extended|dub|album|single|main|vocal)"
)
_MIXED = js_regex(r"\bmixed\b")
_REMIXER_NOISE = js_regex(r"\b(?:the|official|feat .+)\b")


@dataclass(frozen=True)
class _Label:
    """Ce qu'un libellé entre parenthèses, ou après un tiret, dit de la version."""

    tags: tuple[str, ...] = ()
    remixer: str | None = None
    featuring: tuple[str, ...] = ()


def _classify(label: str) -> _Label | None:  # noqa: PLR0912
    """Les étiquettes de version d'un libellé ; None si ce n'est pas une version."""
    text = normalize_text(label)
    if not text:
        return None
    # Une année seule accompagne une autre mention (« Live at Wembley - 1986 »,
    # « Remastered / 2011 »).
    if _NEUTRAL.fullmatch(text) or re.fullmatch(r"[0-9]{4}", text):
        return _Label()

    tags: list[str] = []

    def add(tag: str) -> None:
        if tag not in tags:
            tags.append(tag)

    for tag, pattern in _TAGS:
        if pattern.search(text):
            add(tag)

    language = _LANGUAGE.search(text)
    lang = None
    if language:
        word = language.group(1) if language.group(1) is not None else language.group(2)
        lang = _LANGUAGES.get(word)
    if lang:
        add(f"langue:{lang}")

    remixer = None
    remix = _REMIX.match(text)
    named_edit = re.fullmatch(r"(.+?) edit", text)
    named_mix = re.fullmatch(r"(.+?) mix", text)
    if remix:
        add("remix")
        remixer = remix.group(1)
    elif named_edit and not _NOT_A_REMIXER_EDIT.fullmatch(named_edit.group(1)):
        add("remix")
        remixer = named_edit.group(1)
    elif (
        named_mix and not tags and not _NOT_A_REMIXER_MIX.fullmatch(named_mix.group(1))
    ):
        add("remix")
        remixer = named_mix.group(1)
    elif _MIXED.search(text):
        add("remix")

    # « Piano Version », « Orchestral Version » : une autre interprétation.
    named = re.fullmatch(r"(.+?) version", text)
    if named and not tags and not lang:
        add(f"version:{named.group(1)}")

    if not tags:
        return None
    if remixer is not None:
        remixer = _REMIXER_NOISE.sub("", remixer).strip()
    return _Label(tuple(tags), remixer or None)


@dataclass(frozen=True)
class ParsedTitle:
    """Un titre découpé : sa base, et ce qui fait de lui une version."""

    # Le titre sans ses étiquettes, ses invités ni ses mentions, normalisé.
    base: str
    tags: tuple[str, ...] = ()
    # Les remixeurs nommés (« Eric Prydz Remix » → eric prydz), normalisés.
    remixers: tuple[str, ...] = ()
    # Les artistes invités cités dans le titre, normalisés.
    featuring: tuple[str, ...] = ()
    # Les mentions entre parenthèses qui ne sont pas des versions connues
    # (« Drumless Edition », « Part 2 ») : d'un seul côté, un autre enregistrement.
    extras: tuple[str, ...] = ()
    # Les années citées dans les mentions de version (« Live at Wembley, 1986 »).
    years: tuple[str, ...] = ()


_GROUPS = re.compile(r"\(([^()]*)\)|\[([^\[\]]*)\]")
_LABEL_PARTS = re.compile(r"\s*[/|]\s*|\s+[-\u2013\u2014]\s+")
_FEAT = re.compile(r"(?:feat\.?|ft\.?|featuring|with|avec)\s+(.+)\Z", re.IGNORECASE)
_YEARS = js_regex(r"\b(?:19|20)[0-9]{2}\b")
_DASH_SUFFIX = re.compile(r"\s[-\u2013\u2014]\s([^-\u2013\u2014]+)\Z")
_INLINE_FEAT = re.compile(r"\s(?:feat\.?|ft\.?|featuring)\s+(.+)\Z", re.IGNORECASE)


def parse_title(title: str) -> ParsedTitle:
    """« Get Lucky (Radio Edit) [feat. Pharrell Williams] » : get lucky, radio edit."""
    tags: list[str] = []
    remixers: list[str] = []
    featuring: list[str] = []
    extras: list[str] = []
    years: list[str] = []

    def absorb(label: str) -> bool:
        """Vrai si le libellé est une version ou un invité, retiré du titre de base.

        Un libellé peut en mêler plusieurs : « Radio Edit - feat. Pharrell
        Williams », « Remastered 2011 / Radio Edit ».
        """
        found: list[_Label | None] = []
        for part in filter(None, _LABEL_PARTS.split(label)):
            feat = _FEAT.match(part.strip())
            if feat:
                found.append(_Label(featuring=tuple(split_artists(feat.group(1)))))
            else:
                found.append(_classify(part))
        labels = [item for item in found if item is not None]
        if len(labels) < len(found):
            return False
        years.extend(_YEARS.findall(normalize_text(label)))
        for item in labels:
            featuring.extend(item.featuring)
            tags.extend(tag for tag in item.tags if tag not in tags)
            if item.remixer:
                remixers.append(item.remixer)
        return True

    def group(match: re.Match[str]) -> str:
        # Une mention inconnue sort aussi du titre de base, mais reste à part.
        label = match.group(1) if match.group(1) is not None else match.group(2)
        if not absorb(label):
            extra = normalize_text(label)
            if extra:
                extras.append(extra)
        return " "

    rest = _GROUPS.sub(group, title)
    # « Titre - Remastered 2011 », « Titre - Live at Wembley », autant qu'il y en a.
    while (dash := _DASH_SUFFIX.search(rest)) and absorb(dash.group(1)):
        rest = rest[: dash.start()]
    # « Titre feat. X », hors parenthèses.
    inline = _INLINE_FEAT.search(rest)
    if inline:
        featuring.extend(split_artists(inline.group(1)))
        rest = rest[: inline.start()]
    return ParsedTitle(
        base=normalize_text(rest),
        tags=tuple(tags),
        remixers=tuple(dict.fromkeys(remixers)),
        featuring=tuple(dict.fromkeys(featuring)),
        extras=tuple(extras),
        years=tuple(dict.fromkeys(years)),
    )


def search_terms(title: str) -> str:
    """Les mots qui cherchent un titre : sa base et sa version, pour trouver la bonne.

    « Get Lucky (Radio Edit) » → « get lucky radio edit ».
    """
    parsed = parse_title(title)
    version = [
        f"{tag.removeprefix('version:')} version" if tag.startswith("version:") else tag
        for tag in parsed.tags
        if tag != "remaster" and not tag.startswith("langue:")
    ]
    return " ".join([parsed.base, *parsed.remixers, *version]).strip()
