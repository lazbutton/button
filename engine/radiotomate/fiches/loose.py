"""La seconde passe : un artiste et un titre proches, confirmés par la durée.

Les règles de `loose.ts`, dans Hopper, pour un titre que la recherche à la lettre près
n'a pas trouvé : une faute de frappe, « The » ou « & His Orchestra » en plus ou en
moins, un titre coupé, des mots en plus ou en moins. La durée du fichier est toujours
exigée, à 7 s près, et la version doit être la même : jamais un autre remix. Un titre
rapproché est toujours à relire.

Hopper l'a mesurée sur 80 introuvables tirés au hasard : la moitié environ existent
quelque part, chez Deezer sous une autre graphie (« Gonnas Pedro » pour Gnonnas Pedro),
dans MusicBrainz seulement, sur Bandcamp ou sur SoundCloud. Seul faux de la mesure, un
autre remix à 5 s près, d'où la règle des versions.

La recherche elle-même, chez Deezer puis dans MusicBrainz, est dans `search.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypeVar

from radiotomate.fiches.normalize import (
    js_regex,
    js_trim,
    normalize_text,
    parse_title,
    squash,
)
from radiotomate.fiches.rules import js_falsy, js_round
from radiotomate.fiches.variants import RadioTrack, levenshtein, radio_variants

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from radiotomate.fiches.normalize import ParsedTitle


class ArtistAndTitle(Protocol):
    """Le texte cherché : l'artiste et le titre d'un fichier, ou une lecture."""

    @property
    def artist(self) -> str: ...

    @property
    def title(self) -> str: ...


# ===== Les règles =====

# L'écart de durée toléré : plus serré qu'à la lettre près (10 s), le texte l'étant
# moins.
LOOSE_TOLERANCE_S = 7
# Une version ou une mention d'un seul côté (« Part 1, Part 2 & Part 3 », « Male ») :
# la même durée, à 2 s.
SAME_FILE_S = 2


def edit_distance(a: str, b: str) -> int:
    """La distance d'édition : insertions, suppressions et substitutions.

    Hopper l'écrit deux fois, ici et dans `score.ts` (`levenshtein`). La seconde
    compte les lettres, la première les unités UTF-16 de JavaScript : elles ne
    diffèrent que pour un signe hors du plan de base d'Unicode.
    """
    return levenshtein(a, b)


def nearly_same(a: str, b: str) -> bool:
    """Une ou deux fautes de frappe : aucune sous 5 signes, une jusqu'à 9, deux
    au-delà."""
    x, y = squash(a), squash(b)
    if not x or not y or x == y:
        return bool(x) and x == y
    shorter = min(len(x), len(y))
    allowed = 0 if shorter < 5 else 1 if shorter < 10 else 2
    return abs(len(x) - len(y)) <= allowed and edit_distance(x, y) <= allowed


# « The » en tête, un ensemble en fin (« Orchestra », « Sextette », « & His
# Orchestra ») : le nom sans eux.
_THE = js_regex(r"^the\s+(?=\S{3})")
_ENSEMBLE = js_regex(
    r"\s+(?:and\s+)?(?:(?:his|her|their|y su|e seu|e sua|et son|et ses)\s+)?"
    r"(?:big band|orchestra|orchestre|orquesta|orquestra|band|combo|group|ensemble"
    r"|all stars|sextet|sextette|quintet|quintette|quartet|quartette|trio)\Z"
)


def _core_name(name: str) -> str:
    text = _THE.sub("", normalize_text(name), count=1)
    return js_trim(_ENSEMBLE.sub("", text, count=1))


def _words(outer: str, inner: str) -> bool:
    """`inner` est-il fait de mots entiers de `outer` ?"""
    return f" {inner} " in f" {outer} "


_CREDIT_SEPARATORS = js_regex(
    r"\s*(?:,|&|/|\+|\bfeat\.?(?=\s)|\bft\.?(?=\s)|\bfeaturing\b)\s*", re.IGNORECASE
)


def close_artist(radio: str, found: Sequence[str]) -> str | None:  # noqa: PLR0911
    """L'artiste du fichier parmi ceux trouvés, à peu près : la raison, ou None.

    Le même nom ; le même nom sans « The » ni ensemble (« Joe Cuba Sextet », « Joe
    Cuba Sextette ») ; une faute de frappe (« Gonnas Pedro », « Gnonnas Pedro ») ; un
    nom de 6 signes ou plus contenu dans l'autre (« Willie Bobo », « Willie Bobo & The
    Bo-Gents » ; « JFX meets Bleubird », « Bleubird »). Un nom court ne vaut que tel
    quel : « Low » n'est pas « Low Leaf ».
    """
    mine = _core_name(radio)
    if not mine:
        return None
    # « Artiste à une faute près » seulement sur le nom entier : c'est la faute que le
    # fichier propose de corriger.
    for name in found:
        theirs = _core_name(name)
        if not theirs:
            continue
        if squash(radio) == squash(name):
            return "même artiste"
        if squash(mine) == squash(theirs):
            return "artiste à « The » ou à l'ensemble près"
        if nearly_same(radio, name):
            return "artiste à une faute près"
        if nearly_same(mine, theirs):
            return "artiste à une faute et à « The » ou à l'ensemble près"
    # L'un des artistes crédités, ou un nom contenu dans l'autre : le crédit diffère,
    # il ne se corrige pas.
    names = [
        *found,
        *(part for name in found for part in _CREDIT_SEPARATORS.split(name)),
    ]
    for name in names:
        theirs = _core_name(name)
        if not theirs:
            continue
        if squash(mine) == squash(theirs) or nearly_same(mine, theirs):
            return "artiste crédité autrement"
        short, longer = (
            (mine, theirs)
            if len(squash(mine)) <= len(squash(theirs))
            else (theirs, mine)
        )
        if len(squash(short)) >= 6 and _words(longer, short):
            return "artiste crédité autrement"
    return None


def _in_order(needles: Sequence[str], haystack: Iterable[str]) -> bool:
    at = 0
    for word in haystack:
        if at < len(needles) and word == needles[at]:
            at += 1
    return at == len(needles)


def close_title(radio: str, found: str) -> str | None:
    """Le titre du fichier et celui trouvé, à peu près : la raison, ou None.

    Le même titre de base ; une ou deux fautes de frappe ; coupé par le fichier (12
    signes ou plus, même début) ; des mots en plus ou en moins d'un côté (au moins
    trois mots et 10 signes, dans l'ordre : « You Keep Turning Me », « You Keep On
    Turning Me On »).
    """
    mine, theirs = parse_title(radio).base, parse_title(found).base
    if not mine or not theirs:
        return None
    x, y = mine.replace(" ", ""), theirs.replace(" ", "")
    if x == y:
        return "même titre"
    if nearly_same(mine, theirs):
        return "titre à une faute près"
    if len(x) >= 12 and y.startswith(x):
        return "titre coupé"
    short, longer = (
        (mine, theirs)
        if len(mine.split(" ")) <= len(theirs.split(" "))
        else (theirs, mine)
    )
    needles = short.split(" ")
    if (
        len(needles) >= 3
        and len(short.replace(" ", "")) >= 10
        and _in_order(needles, longer.split(" "))
    ):
        return "mots en plus ou en moins"
    return None


def _version_words(mine: str, theirs: str) -> ParsedTitle | None:
    """Les mots de `theirs` qui manquent à `mine`, s'ils sont une version."""
    known = set(mine.split(" "))
    extra = " ".join(word for word in theirs.split(" ") if word and word not in known)
    parsed = parse_title(f"x ({extra})") if extra else None
    return parsed if parsed and not parsed.extras else None


def _tags(parsed: ParsedTitle, more: ParsedTitle | None) -> set[str]:
    return {
        tag for tag in (*parsed.tags, *(more.tags if more else ())) if tag != "remaster"
    }


# « Remix by Apparat », « RMX_BY_RECHENZENTRUM » : le remixeur après « by ».
_BY = js_regex(r"\b(?:remix|rmx|edit|mix|rework|version) by ((?:\S+ ?){1,3})")


def _by(title: str) -> str | None:
    match = _BY.search(normalize_text(title.replace("_", " ")))
    return js_trim(match[1]) if match else None


def _remixers(parsed: ParsedTitle, more: ParsedTitle | None, title: str) -> list[str]:
    names = (*parsed.remixers, *(more.remixers if more else ()), _by(title))
    return [squash(name) for name in names if name]


def _same_remixer(one: str, other: str) -> bool:
    """Le même remixeur, à une faute près, ou coupé par le fichier (« rmx by si » pour
    Simbad)."""
    return nearly_same(one, other) or (
        min(len(one), len(other)) >= 2
        and (one.startswith(other) or other.startswith(one))
    )


Agreement = Literal["mêmes", "d'un seul côté", "contraires"]


def versions(radio: str, found: str) -> Agreement:
    """Les versions des deux titres.

    Les mêmes ; une version ou une mention d'un seul côté (« Live at Wembley »,
    « Part 2 ») ; ou deux qui se contredisent : deux remixeurs nommés différents, deux
    versions, deux mentions différentes.
    """
    a, b = parse_title(radio), parse_title(found)
    # Les mots en plus d'un côté, hors parenthèses, peuvent être une version (« Fatty
    # Boom Boom Remix », « Chest Fever Live ») ; d'autres mots (« Scene », « To Turn Me
    # On ») font partie du titre.
    more_a, more_b = _version_words(b.base, a.base), _version_words(a.base, b.base)
    tags_a, tags_b = _tags(a, more_a), _tags(b, more_b)
    remixers_a = _remixers(a, more_a, radio)
    remixers_b = _remixers(b, more_b, found)
    if (
        remixers_a
        and remixers_b
        and not any(
            _same_remixer(one, other) for one in remixers_a for other in remixers_b
        )
    ):
        return "contraires"
    if tags_a and tags_b and tags_a != tags_b:
        return "contraires"
    extras_a, extras_b = set(a.extras), set(b.extras)
    if extras_a and extras_b and not extras_a & extras_b:
        return "contraires"
    if (
        tags_a == tags_b
        and extras_a == extras_b
        and bool(remixers_a) == bool(remixers_b)
    ):
        return "mêmes"
    return "d'un seul côté"


def same_version(radio: str, found: str, gap_s: float) -> bool:
    """Deux versions qui se contredisent, jamais (« Chrome Canyon Remix » n'est pas
    « Little Daylight Remix ») ; une version ou une mention d'un seul côté, seulement
    à la même durée, à 2 s (« Mexican Junkanoo Suite (Part 1, Part 2 & Part 3) »,
    19:03 pour 19:04)."""
    agreement = versions(radio, found)
    return agreement == "mêmes" or (
        agreement == "d'un seul côté" and gap_s <= SAME_FILE_S
    )


_GENERIC = js_regex(
    r"(?:intro|outro|interlude|skit|untitled|sans titre|instrumental|jingle|track"
    r"|piste|pista|titre|title|no title|unknown|inconnu|demo)(?: [0-9]+)?"
)
_COVER = js_regex(
    r"\b(?:karaoke|tribute|made famous|in the style of|cover|originally performed)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LooseCandidate:
    """Un morceau trouvé : son titre, ses artistes et sa durée."""

    title: str
    artists: tuple[str, ...]
    duration_ms: float | None = None


def foreign_cover(radio: ArtistAndTitle, candidate: LooseCandidate) -> bool:
    """Une reprise, un karaoké, que le fichier ne nomme pas : jamais rapproché."""
    return any(
        _COVER.search(text) for text in (candidate.title, *candidate.artists)
    ) and not _COVER.search(f"{radio.artist} {radio.title}")


def generic_title(title: str) -> bool:
    """Trop vague pour un rapprochement : « Intro », « Untitled », « Piste 04 », un
    nombre."""
    base = parse_title(title).base
    return (
        len(base.replace(" ", "")) < 3
        or bool(_GENERIC.fullmatch(base))
        or bool(js_regex(r"[0-9\s]+").fullmatch(base))
    )


def meaningless_title(title: str) -> bool:
    """Un titre vide de sens, que l'empreinte peut remplacer : vide, « Piste 04 »,
    « Untitled », un nombre.

    Plus étroit que `generic_title` : un titre court (« Go ») a un sens, que
    l'empreinte doit retrouver, et ne remplace pas.
    """
    base = parse_title(title).base
    return (
        not base.replace(" ", "")
        or bool(_GENERIC.fullmatch(base))
        or bool(js_regex(r"[0-9\s]+").fullmatch(base))
    )


ONE_SIDED = "version ou mention d'un seul côté"


@dataclass(frozen=True)
class Found:
    """Un candidat rapproché : pourquoi, l'écart de durée en secondes, et s'il a une
    version ou une mention d'un seul côté."""

    why: tuple[str, ...]
    gap: float
    one_sided: bool


def loose_match(
    radio: ArtistAndTitle, candidate: LooseCandidate, radio_seconds: float | None
) -> Found | None:
    """Le candidat est-il, à peu près, le morceau du fichier ?

    La durée est exigée des deux côtés : sans elle, rien ne départage deux morceaux
    proches.
    """
    if (
        js_falsy(radio_seconds)
        or js_falsy(candidate.duration_ms)
        or generic_title(radio.title)
        or foreign_cover(radio, candidate)
    ):
        return None
    gap = abs(candidate.duration_ms / 1000 - radio_seconds)
    if gap > LOOSE_TOLERANCE_S:
        return None
    artist = close_artist(radio.artist, candidate.artists)
    title = close_title(radio.title, candidate.title) if artist else None
    if not artist or not title or not same_version(radio.title, candidate.title, gap):
        return None
    one_sided = versions(radio.title, candidate.title) != "mêmes"
    why = (artist, title, f"durée à {js_round(gap)} s")
    return Found((*why, ONE_SIDED) if one_sided else why, gap, one_sided)


# ===== Ce que la recherche en tire =====

# Un numéro de fichier en fin (« Love_having_you_around_32915 »).
_FILE_NUMBER = js_regex(r"[\s_]+[0-9]{4,}\Z")


def loose_variants(item: ArtistAndTitle) -> list[RadioTrack]:
    """Les requêtes : celles de la recherche à la lettre près (soulignés, numéros de
    piste, artiste lu dans le titre…), plus un numéro de fichier en fin retiré."""
    title = _FILE_NUMBER.sub("", item.title, count=1)
    out: dict[tuple[str, str], RadioTrack] = {}
    for variant in radio_variants(RadioTrack(item.artist, title)):
        key = (squash(variant.artist), squash(variant.title))
        out.setdefault(key, RadioTrack(variant.artist, variant.title))
    return list(out.values())


# Le titre cherché n'est plus celui du fichier (« 01 Perambulator », « Henri Mancini -
# Birdie Num-num ») : le titre trouvé le remplace.
CLEANED = "titre de la radio nettoyé"
# L'artiste du fichier lu comme titre, et l'inverse : le `SWAPPED` de `third.py`.
_SWAPPED = "artiste et titre inversés"


def quoteless(text: str) -> str:
    """Le texte d'une requête entre guillemets, sans guillemet ni barre oblique
    inverse."""
    return js_trim(js_regex(r"\s+").sub(" ", js_regex(r"[\"\\]").sub(" ", text)))


def loose_judge(
    item: ArtistAndTitle,
    variant: ArtistAndTitle,
    candidate: LooseCandidate,
    radio_seconds: float | None,
) -> Found | None:
    """Le candidat d'une variante du fichier, jugé par la seconde passe, et ce que la
    variante a fait du texte du fichier.

    Le titre cherché n'est plus celui du fichier (« 01 Perambulator ») : le titre
    trouvé le remplacera (`CLEANED`). L'artiste du fichier lu comme titre, et
    l'inverse : chacun reprendra sa place.
    """
    verdict = loose_match(variant, candidate, radio_seconds)
    if not verdict:
        return None
    radio_title = squash(item.title.replace("_", " "))
    title = squash(variant.title)
    swapped = title in squash(item.artist) and title not in radio_title
    cleaned = not swapped and title != radio_title
    notes = (CLEANED,) if cleaned else (_SWAPPED,) if swapped else ()
    return Found((*verdict.why, *notes), verdict.gap, verdict.one_sided)


@dataclass(frozen=True)
class MbRelease:
    """Une sortie d'un enregistrement de MusicBrainz.

    `type` : celui de son groupe de sorties (« Album », « Single ») ; `secondary` :
    ses types secondaires (« Compilation », « Live »).
    """

    title: str
    date: str | None = None
    type: str | None = None
    secondary: tuple[str, ...] = ()


def first_release(releases: Iterable[MbRelease]) -> str | None:
    """Le disque d'origine d'un enregistrement : le plus ancien album qui n'est ni une
    compilation ni un live, sinon la plus ancienne sortie.

    Hopper lui passe l'enregistrement ; ici, ses sorties. Les dates de MusicBrainz
    sont ISO (« 1978 », « 2002-05-01 ») : l'ordre de leur texte est celui que
    `localeCompare` donne à Hopper.
    """
    dated = sorted(
        releases, key=lambda release: "9999" if release.date is None else release.date
    )
    first = next(
        (
            release
            for release in dated
            if release.type == "Album" and not release.secondary
        ),
        dated[0] if dated else None,
    )
    return first.title if first else None


_Found = TypeVar("_Found", bound=Found)


def best(found: Iterable[_Found]) -> _Found | None:
    """Le meilleur candidat : la même version d'abord, puis le plus petit écart de
    durée.

    « Bara To Yajuu », 4:24, est plutôt le « Bara To Yaju » de 4:22 que le live de Los
    Angeles de 4:24 : le fichier aurait écrit « Live ».
    """
    return min(found, key=lambda one: (one.one_sided, one.gap), default=None)
