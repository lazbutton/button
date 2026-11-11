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

import functools
import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


# Les espaces de JavaScript, ceux de son `\s` et de son `trim`. Python y met en plus
# les signes de contrôle 0x1C à 0x1F et 0x85, qu'un texte abîmé à l'import peut porter
# (« ğ » y devient 0x1F), et pas U+FEFF.
JS_SPACES = (
    "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_SPACE_CLASS = (
    r"\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
# Le `.` de JavaScript ne prend aucun saut de ligne.
_DOT = r"[^\n\r\u2028\u2029]"


def js_trim(text: str) -> str:
    """Le `trim` de JavaScript : ses espaces, pas ceux de Python."""
    return text.strip(JS_SPACES)


# Un drapeau écrit dans le motif, comme `(?i)` : la règle de casse ne le verrait pas.
_INLINE_FLAGS = re.compile(r"\?([a-zA-Z-]*)[:)]")


def _js_pattern(pattern: str) -> tuple[str, bool]:  # noqa: PLR0912
    r"""Une regex de JavaScript, dite pour Python : son `\b`, son `\B`, son `\s`, son
    `\S` et son `.`, hors des classes et dedans.

    Dit aussi si elle a des classes d'Unicode (`\w`, `\W`, `\d`, `\D`), celles d'une
    regex écrite pour le drapeau `u` de JavaScript.
    """
    out: list[str] = []
    unicode = False
    # `first` : la place, dans `out`, du premier signe de la classe ouverte.
    at, inside, first = 0, False, 0
    while at < len(pattern):
        char = pattern[at]
        if char == "\\":
            escape = pattern[at : at + 2]
            at += 2
            unicode = unicode or escape in (r"\w", r"\W", r"\d", r"\D")
            # Dans une classe, `\S` n'a pas de liste, et `\s` ne borne pas une plage.
            if inside and escape in (r"\s", r"\S"):
                after = pattern[at : at + 1] == "-" and pattern[at + 1 : at + 2] != "]"
                before = out[-1:] == ["-"] and len(out) - 1 > first
                if escape == r"\S" or after or before:
                    msg = f"une classe d'espaces ne se traduit pas ici : {pattern}"
                    raise ValueError(msg)
            if escape == r"\s":
                out.append(_SPACE_CLASS if inside else f"[{_SPACE_CLASS}]")
            elif escape == r"\S":
                out.append(f"[^{_SPACE_CLASS}]")
            elif escape in (r"\b", r"\B") and not inside:
                out.append(f"(?a:{escape})")
            else:
                out.append(escape)
            continue
        at += 1
        if inside:
            inside = char != "]"
        elif char == "[":
            inside = True
            # « ^ », puis « ] », en tête de classe, sont des signes comme les autres.
            head = "^" if pattern[at : at + 1] == "^" else ""
            at += len(head)
            if pattern[at : at + 1] == "]":
                head += "]"
                at += 1
            out.append(char + head)
            first = len(out)
            continue
        elif char == "(":
            flags = _INLINE_FLAGS.match(pattern, at)
            if flags and "i" in flags[1]:
                msg = f"un drapeau dans le motif : passer re.IGNORECASE ({pattern})"
                raise ValueError(msg)
        elif char == ".":
            char = _DOT
        out.append(char)
    return "".join(out), unicode


@functools.cache
def js_regex(pattern: str, flags: int = 0) -> re.Pattern[str]:
    r"""Compile une regex de Hopper, écrite pour JavaScript, avec les règles de
    JavaScript. Toutes les regex des fiches passent par elle.

    - `\b` et `\B` n'y connaissent que les lettres ASCII : « Søet » a un « et » pour
      Hopper, pas pour le `\b` de Python ;
    - `\s` et `\S` y ont les espaces de JavaScript (`JS_SPACES`), comme `js_trim` ;
    - `.` n'y prend aucun saut de ligne : ni `\n`, ni `\r`, ni U+2028, ni U+2029 ;
    - sous `re.IGNORECASE`, seules les lettres ASCII y changent de casse : le « i »
      turc, avec ou sans point, n'est pas un « i », comme pour JavaScript, alors que
      Python les rapproche. Le motif s'écrit donc en lettres ASCII : JavaScript
      rapprocherait aussi « é » de « É ». Avec son drapeau `u`, JavaScript rapproche
      en plus le « s » long de « s » et le signe kelvin de « k » : le motif les écrit
      lui-même (`_VERSION_WORD`, dans `variants.py`). Un motif aux classes d'Unicode
      (`\w`, `\W`, `\d`), écrit pour le drapeau `u`, garde la casse de Python, qui
      est celle de JavaScript tant que le motif n'a pas de « i ».

    Le reste s'écrit en Python : `[0-9]` pour le `\d` de JavaScript, `\Z` pour son
    `$`, et `[^\W\d_]` pour une lettre (`\p{L}`), qui y prend aussi un nombre comme
    « ² ». Ce qui n'a pas de traduction est refusé : `\S` dans une classe, `\s` qui
    borne une plage, un drapeau écrit dans le motif. Une regex compilée est gardée :
    écrite dans un appel, elle ne se compile qu'une fois.
    """
    translated, unicode = _js_pattern(pattern)
    if flags & re.IGNORECASE and not unicode:
        flags |= re.ASCII
    return re.compile(translated, flags)


def is_mark(char: str) -> bool:
    """Un accent combinant, ou une autre marque (`\\p{M}`)."""
    return unicodedata.category(char).startswith("M")


def is_upper(char: str) -> bool:
    """Une lettre capitale (`\\p{Lu}`)."""
    return unicodedata.category(char) == "Lu" if char else False


def without_marks(text: str) -> str:
    return "".join(char for char in text if not is_mark(char))


_APOSTROPHES = js_regex(r"[\u2019'`\u00b4\u02bc]")
# Tout ce qui n'est ni une lettre ni un chiffre (`[^\p{L}\p{N}]`).
_NOT_ALNUM = js_regex(r"[\W_]+")
_SPACES = js_regex(r"\s+")


def normalize_text(text: str) -> str:
    """Accents et ponctuation retirés, minuscules ; une autre écriture reste.

    « L'amour   toujours » → « lamour toujours », « Rock & Roll » → « rock and roll ».
    """
    text = without_marks(unicodedata.normalize("NFKD", text)).lower()
    text = _APOSTROPHES.sub("", text).replace("&", " and ")
    return _SPACES.sub(" ", js_trim(_NOT_ALNUM.sub(" ", text)))


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
_NEUTRAL = js_regex(
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
_NOT_A_REMIXER_EDIT = js_regex(
    r"(?:radio|single|short|extended|club|album|clean|explicit)"
)
_NOT_A_REMIXER_MIX = js_regex(
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
    if _NEUTRAL.fullmatch(text) or js_regex(r"[0-9]{4}").fullmatch(text):
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
    named_edit = js_regex(r"(.+?) edit").fullmatch(text)
    named_mix = js_regex(r"(.+?) mix").fullmatch(text)
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
    named = js_regex(r"(.+?) version").fullmatch(text)
    if named and not tags and not lang:
        add(f"version:{named.group(1)}")

    if not tags:
        return None
    if remixer is not None:
        remixer = js_trim(_REMIXER_NOISE.sub("", remixer))
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


_GROUPS = js_regex(r"\(([^()]*)\)|\[([^\[\]]*)\]")
_LABEL_PARTS = js_regex(r"\s*[/|]\s*|\s+[-\u2013\u2014]\s+")
_FEAT = js_regex(r"(?:feat\.?|ft\.?|featuring|with|avec)\s+(.+)\Z", re.IGNORECASE)
_YEARS = js_regex(r"\b(?:19|20)[0-9]{2}\b")
_DASH_SUFFIX = js_regex(r"\s[-\u2013\u2014]\s([^-\u2013\u2014]+)\Z")
_INLINE_FEAT = js_regex(r"\s(?:feat\.?|ft\.?|featuring)\s+(.+)\Z", re.IGNORECASE)


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
            feat = _FEAT.match(js_trim(part))
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


def _pairs(text: str) -> dict[str, str]:
    words = text.split(" ")
    return {words[at]: words[at + 1].replace("_", "") for at in range(0, len(words), 2)}


def _jamo(first: int, text: str) -> dict[str, str]:
    return {
        chr(first + at): latin.replace("_", "")
        for at, latin in enumerate(text.split(" "))
    }


# Les lettres d'autres écritures, en latin : un artiste écrit en cyrillique chez l'un,
# en latin chez l'autre (Кино, Kino). Ces lettres ressemblent aux nôtres : ruff le
# signale, à tort ici.
_LATIN = {
    **_pairs("ß ss ł l đ d ð d þ th ħ h ı i ø o æ ae œ oe ŋ ng"),  # noqa: RUF001
    # Cyrillique (russe, ukrainien, serbe) : « Группа крови » → gruppa krovi.
    **_pairs(
        "а a б b в v г g д d е e ё yo ж zh з z и i й y к k л l м m н n о o п p "  # noqa: RUF001
        "р r с s т t у u ф f х kh ц ts ч ch ш sh щ shch ъ _ ы i ь _ э e ю yu "  # noqa: RUF001
        "я ya є ye і i ї yi ґ g ђ dj ј j љ lj њ nj ћ c џ dz ў u"  # noqa: RUF001
    ),
    # Grec, accents retirés au passage (NFKD).
    **_pairs(
        "α a β v γ g δ d ε e ζ z η i θ th ι i κ k λ l μ m ν n ξ x ο o π p ρ r "  # noqa: RUF001
        "σ s ς s τ t υ i φ f χ ch ψ ps ω o"  # noqa: RUF001
    ),
    # Coréen : chaque syllabe se décompose (NFKD) en consonne initiale, voyelle (21,
    # notées a) et consonne finale.
    **_jamo(0x1100, "g kk n d tt r m b pp s ss _ j jj ch k t p h"),
    **_jamo(0x1161, " ".join(["a"] * 21)),
    **_jamo(0x11A8, "k k k n n n t l k m l l l p l m p p t t ng t t k t p t"),
}


def latin_words(text: str) -> list[str]:
    """Le texte en latin, mot par mot : les lettres connues de `_LATIN`, les autres
    décomposées, puis privées de leurs accents.

    « Από λιμάνι σε λιμάνι » → apo, limani, se, limani.
    """
    out: list[str] = []
    for char in unicodedata.normalize("NFC", text.lower()):
        latin = _LATIN.get(char)
        if latin is None:
            parts = without_marks(unicodedata.normalize("NFKD", char))
            latin = "".join(_LATIN.get(part, part) for part in parts)
        out.append(latin)
    joined = _APOSTROPHES.sub("", "".join(out))
    return [word for word in js_regex(r"[^a-z0-9]+").split(joined) if word]


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
    return js_trim(" ".join([parsed.base, *parsed.remixers, *version]))
