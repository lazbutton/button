"""Reconnaître un titre à la lettre près, d'après son artiste et son titre.

Les règles de `radio.ts` et du conflit de versions de `score.ts`, dans Hopper :

1. Les variantes. Un catalogue écrit des noms de fichier, pas des fiches : « Artiste -
   Album - 06 - Titre », « A2 », « Copie de », « - HD master », « L_oreille d_un »,
   une compilation ou une émission en guise d'artiste, des octets perdus en route.
   Chaque titre donne quelques requêtes, essayées dans l'ordre.
2. À la lettre près. Un candidat ne vaut que s'il a le même titre de base et les mêmes
   artistes, un invité cité d'un seul côté mis à part, aux accents, à la casse, aux
   espaces et à la ponctuation près, sans version, remix ni mention d'un seul côté.
   Pas de nom au même squelette (« KOYAKI » n'est pas Kayak), pas de titre contenu
   dans un autre, pas de faute d'une lettre : un lien faux est pire qu'un lien absent.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from radiotomate.fiches.normalize import (
    ParsedTitle,
    is_upper,
    js_regex,
    js_trim,
    normalize_text,
    parse_title,
    split_artists,
    squash,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


@dataclass(frozen=True)
class RadioTrack:
    """L'artiste et le titre d'un fichier, tels que ses tags les écrivent."""

    artist: str
    title: str


@dataclass(frozen=True)
class RadioVariant:
    """Une requête tirée du texte d'un titre.

    `artist` est celui qu'on cherche, `credited` celui que le candidat doit avoir :
    tous les artistes du fichier, quand la requête n'en cherche que le premier.
    """

    artist: str
    title: str
    credited: str
    why: tuple[str, ...]


@dataclass(frozen=True)
class Meta:
    """Un morceau, du fichier ou d'une source : son titre, ses artistes, sa durée."""

    title: str
    artists: tuple[str, ...]
    duration_ms: float | None = None
    album: str | None = None
    explicit: bool | None = None


# ===== Les variantes du texte =====


def _collapse(text: str) -> str:
    return js_trim(js_regex(r"\s+").sub(" ", text))


_ELISION = js_regex(r"(^|[\s_])([cdjlmnst]|qu)_(?=[^\W\d_])", re.IGNORECASE)


def _underscores(text: str) -> str:
    """Les soulignés d'un nom de fichier : « C_est » → « C'est », le reste → espace."""
    if "_" not in text:
        return text
    return _collapse(js_regex(r"_+").sub(" ", _ELISION.sub(r"\1\2'", text)))


# Les rangs de piste et de face qu'un nom de fichier garde : « A2 », « B1 - », « 3A »,
# « 1-12 », « 03-03 », « 017 », « 01E - », « 10The », « TRLP9111_09 ». Un nombre nu
# (« 11 Magic Circle ») peut faire partie du titre, un nombre suivi d'un trait d'union
# en fait partie (« 72-Hour Sweat »). Hopper n'a qu'une regex : `re` ne connaît pas
# `\p{Lu}`, et le rang collé à une capitale (« 10The ») se vérifie à part.
_TRACK_PREFIX = js_regex(
    r"(?:[A-Za-z]{2,5}[0-9]{3,5}[\s_-]+(?:[A-D]?[0-9]{1,2}[\s_-]+)?"
    r"|[A-D][0-9]{1,2}(?:\s*[-\u2013.:]\s*|\s+)"
    r"|[0-9]{1,2}[A-D](?:\s*[-\u2013.:]\s*|\s+)"
    r"|[0-9]{1,2}-[0-9]{1,2}(?:\s*[-\u2013.:_]\s*|\s+)"
    r"|[0-9]{1,3}[A-Z]?\s*[-\u2013.:]\s+)(?=\S)"
)
_TRACK_BEFORE_LETTER = js_regex(r"[0-9]{1,3}(?!-)\.?\s*(?:[-\u2013]\s*)?(?=[^\W\d_])")
_TRACK_BEFORE_SPACE = js_regex(r"[0-9]{1,3}\s+(?=\S)")


def _without_track_prefix(text: str) -> str:
    match = _TRACK_PREFIX.match(text)
    if not match:
        number = _TRACK_BEFORE_LETTER.match(text)
        if number and is_upper(text[number.end()]):
            match = number
        else:
            match = _TRACK_BEFORE_SPACE.match(text)
    return text[match.end() :] if match else text


# Les fins de fichier de master : « - HD master », « MSTR 8824 HD », « Main Master
# (2496) », « DIGI MASTER 44.1-16 »…
_JUNK_END = (
    js_regex(r"\s*[-\u2013]\s*digi master\b.*\Z", re.IGNORECASE),
    js_regex(r"\s*[-\u2013]?\s*\bmain master\b.*\Z", re.IGNORECASE),
    js_regex(r"\s*[-\u2013]\s*(?:hd\s+)?master\Z", re.IGNORECASE),
    js_regex(r"\s+z?mstr\b.*\Z", re.IGNORECASE),
    js_regex(r"\s*[-\u2013]\s*[0-9]{4}\s+remaster(?:ed)?\Z", re.IGNORECASE),
    js_regex(r"\s*\bextrait\b.*\Z", re.IGNORECASE),
    js_regex(r"\s+mp3(?:\s+[0-9]+)?\Z", re.IGNORECASE),
    js_regex(r"\s+v[0-9]\Z", re.IGNORECASE),
    js_regex(r"\s+sf[0-9]\Z", re.IGNORECASE),
    js_regex(r"\s+hd\Z", re.IGNORECASE),
    js_regex(r"\s*\[[A-Z]{2,}[0-9]*\]\Z"),
    js_regex(r"\s*\(released [^)]*\)\Z", re.IGNORECASE),
    js_regex(r"\s*\([0-9]{2,3}\s*bpm\)\Z", re.IGNORECASE),
    js_regex(r"\s*\(prod(?:uced)?\.? by [^)]*\)\Z", re.IGNORECASE),
    js_regex(r"\s*\([^)]*\b(?:ep|lp)[0-9]*\b[^)]*\)\Z", re.IGNORECASE),
    js_regex(r"\s*\(single\)", re.IGNORECASE),
)


def _strip_end(text: str) -> str:
    out = text
    for _ in range(4):
        before = out
        for junk in _JUNK_END:
            out = js_trim(junk.sub("", out, count=1))
        if out == before:
            break
    return out or text


# Hopper compile les deux regex qui s'en servent avec le drapeau `u`, qui rapproche
# le « s » long de « s » et le signe kelvin de « k » : ils sont écrits ici.
_VERSION_WORD = "(?:remix|rmx|mix|ver[s\u017f]ion|edit|rewor[k\u212a])"
_TWO_WORD_VERSION = js_regex(rf"(.+?\S)\s+(\S+\s+{_VERSION_WORD})\Z", re.IGNORECASE)
_ONE_WORD_VERSION = js_regex(rf"(.+?\S)\s+({_VERSION_WORD})\Z", re.IGNORECASE)


def _wrap_version(text: str) -> str:
    """« Going places Zemix version » : la version, mise entre parenthèses.

    « dub » reste : c'est aussi un nom.
    """
    if js_regex(r"[()\[\]]").search(text):
        return text
    two = _TWO_WORD_VERSION.match(text)
    if two:
        return f"{two.group(1)} ({two.group(2)})"
    one = _ONE_WORD_VERSION.match(text)
    return f"{one.group(1)} ({one.group(2)})" if one else text


# Des caractères perdus en route, réduits à leur octet bas : « Ne\x01gationnistes »
# était « Négationnistes » (accent combinant U+0301), « TM \x13 Die Uhr » un tiret
# (U+2013).
_LOW_BYTE = {
    "\x00": "\u0300",
    "\x01": "\u0301",
    "\x02": "\u0302",
    "\x03": "\u0303",
    "\x08": "\u0308",
    "\x13": "\u2013",
    "\x14": "\u2014",
    "\x18": "\u2018",
    "\x19": "\u2019",
    "\x1c": "\u201c",
    "\x1d": "\u201d",
}


def _repair_bytes(text: str) -> str:
    repaired = js_regex(r"[\x00-\x1f]").sub(
        lambda char: _LOW_BYTE.get(char[0], " "), text
    )
    return unicodedata.normalize("NFC", repaired)


_THE = js_regex(r"^the(?=.{3})")


def _same_name(a: str, b: str) -> bool:
    """Le nom de l'artiste en tête d'un titre (« Coilguns - Carbon Magic »), « The »
    en tête ou pas."""
    x, y = _THE.sub("", squash(a), count=1), _THE.sub("", squash(b), count=1)
    return bool(x) and bool(y) and (x == y or x.startswith(y) or y.startswith(x))


_NAME_REVERSED = js_regex(
    r"((?:[^\W\d_]|['-])+),\s*((?:[^\W\d_]|[.'-])+(?:\s(?:[^\W\d_]|[.'-])+)?)\Z"
)


def _clean_artist(artist: str) -> str:
    """« Porter, Nolan » → « Nolan Porter », « A | B | C » → A, « J.P. Bimeni _ The
    Black Belts » → « … & … »."""
    name = js_trim(js_regex(r"^\*+|\*+\Z").sub("", artist))
    name = js_regex(r"\s_\s").sub(" & ", name)
    if "_" in name:
        # « Tristan Honsinger-…_What Are You Talki » : le nom, puis celui de l'album.
        head, *rest = name.split("_")
        album_after = (
            len(rest) == 1
            and js_regex(r"\s").search(head)
            and js_regex(r"\s").search(rest[0])
        )
        name = head if album_after else _underscores(name)
    if js_regex(r"\s\|\s").search(name):
        name = js_regex(r"\s\|\s").split(name)[0]
    reversed_name = _NAME_REVERSED.match(name)
    if reversed_name:
        name = f"{reversed_name.group(2)} {reversed_name.group(1)}"
    return _collapse(js_regex(r"\s+aka\s+.*\Z", re.IGNORECASE).sub("", name, count=1))


_ANNOUNCEMENT = js_regex(r"\bcontacte nous\b|\bjingle\b")


def is_announcement(track: RadioTrack) -> bool:
    """Une publicité, un jingle ou un indicatif : rien à chercher."""
    text = normalize_text(f"{track.artist} {track.title}")
    return bool(_ANNOUNCEMENT.search(text)) or bool(
        js_regex(r"pub [0-9]+").fullmatch(normalize_text(track.title))
    )


# Le nom de la station en guise d'artiste : « Radio-campus-france |
# Ville-en-flamme_l-etrangleuse ».
_STATION = js_regex(r"^radio campus\b")
_VER = js_regex(r"\bVer\.(?=\)|\s|\Z)")
_FIRST_ARTIST = js_regex(
    r"\s*(?:,|&|\+|/|\\|\bfeat\.?(?=\s)|\bft\.?(?=\s)|\bfeaturing\b|\s[x\u00d7]\s"
    r"|\band\b|\bet\b|\s-\s)\s*",
    re.IGNORECASE,
)
_FEAT_MENTION = js_regex(
    r"\s*[(\[]?\s*\b(?:feat\.?|ft\.?|featuring)\s+[^)\]]*[)\]]?", re.IGNORECASE
)


def _clean(text: str) -> str:
    return js_regex(r"^[-\u2013:/\s]+|[-\u2013:/\s\\|]+\Z").sub(
        "", _collapse(js_regex(r"\?+").sub(" ", text))
    )


def radio_variants(track: RadioTrack) -> list[RadioVariant]:  # noqa: PLR0912, PLR0915
    """Les requêtes d'un titre, la plus fidèle à son texte d'abord."""
    out: list[RadioVariant] = []
    raw_title = _repair_bytes(js_trim(track.title))
    raw_artist = _repair_bytes(js_trim(track.artist))

    def push(
        artist: str, title: str, why: Sequence[str], credited: str | None = None
    ) -> None:
        credited = _clean(artist if credited is None else credited)
        artist, title = _clean(artist), _clean(title)
        if not artist or not js_regex(r"[^\W_]").search(title):
            return
        if any(
            squash(other.artist) == squash(artist)
            and squash(other.title) == squash(title)
            for other in out
        ):
            return
        out.append(RadioVariant(artist, title, credited, tuple(why)))

    if is_announcement(RadioTrack(raw_artist, raw_title)):
        return out
    if _STATION.search(normalize_text(raw_artist)):
        parts = js_regex(r"(.+?)\s+[-\u2013]\s+(.+)\Z").match(raw_title) or js_regex(
            r"([^_]+)_([^_]+)\Z"
        ).match(raw_title)
        if parts:
            a, b = (
                _underscores(js_regex(r"([^\W\d_])-(?=[^\W\d_])").sub(r"\1 ", part))
                for part in (parts.group(1), _strip_end(parts.group(2)))
            )
            push(a, b, ["artiste lu dans le titre"])
            push(b, a, ["titre - artiste"])
        return out

    artist = _clean_artist(raw_artist)
    why: list[str] = []
    title = js_trim(js_regex(r"^\*+|\*+\Z").sub("", raw_title))
    # « Station17 & Schneider TM  Die Uhr spricht » : deux espaces entre les invités
    # et le titre.
    spaced = js_regex(r"(.+?)\s{2,}(.+)\Z").match(title)
    if spaced and _same_name(js_regex(r"\s+&\s+").split(spaced.group(1))[0], artist):
        guests = js_regex(r"\s+&\s+").split(spaced.group(1))[1:]
        title = spaced.group(2)
        if guests:
            artist = " & ".join([artist, *guests])
        why.append("invités lus dans le titre")
    if js_regex(r"copie de\s", re.IGNORECASE).match(title):
        title = js_regex(r"^copie de\s+", re.IGNORECASE).sub("", title)
        why.append("« Copie de »")
    if "_" in title:
        title = _underscores(title)
        why.append("soulignés")
    title = _VER.sub("Version", title)
    # « Artiste - Album - 06 - Titre », « Titre - Artiste - from Album », « Artiste
    # + Invité - Titre », « Artiste / Titre ».
    album = js_regex(
        r"(.+?)\s+[-\u2013]\s+(.+?)\s+[-\u2013]\s+[0-9]{1,2}\s+[-\u2013]\s+(.+)\Z"
    ).match(title)
    if album and _same_name(album.group(1), artist):
        title = album.group(3)
        why.append("« Artiste - Album - N° - »")
    origin = js_regex(
        r"(.+?)\s+[-\u2013]\s+(.+?)\s+[-\u2013]\s+from\s+.+\Z", re.IGNORECASE
    ).match(title)
    if origin and _same_name(origin.group(2), artist):
        title = origin.group(1)
        why.append("« Titre - Artiste - from Album »")
    guest = js_regex(r"(.+?)\s\+\s(.+?)\s[-\u2013]\s(.+)\Z").match(title)
    if guest and _same_name(guest.group(1), artist):
        title = guest.group(3)
        artist = f"{artist} & {guest.group(2)}"
        why.append("invité lu dans le titre")
    prefixed = js_regex(r"(.+?)\s*(?:\s[-\u2013]\s|\s?/\s?|-(?=\S))\s*(.+)\Z").match(
        title
    )
    if prefixed and _same_name(prefixed.group(1), artist):
        title = prefixed.group(2)
        why.append("artiste retiré du titre")
    before_number = title
    title = _without_track_prefix(title)
    # Un nombre nu peut faire partie du titre : le texte tel quel d'abord, puis
    # sans lui.
    bare = (
        title != before_number
        and bool(js_regex(r"[1-9][0-9]{0,2}\s+\S").match(before_number))
        and not js_regex(r"[1-9][0-9]{0,2}\s+[-\u2013.:_]").match(before_number)
    )
    if title != before_number and not bare:
        why.append("numéro de piste")
    after_number = js_regex(r"(.+?)\s+[-\u2013]\s+(.+)\Z").match(title)
    if after_number and _same_name(after_number.group(1), artist):
        title = after_number.group(2)
        why.append("artiste retiré du titre")
    main = _wrap_version(_strip_end(title))
    if bare:
        push(artist, _wrap_version(_strip_end(before_number)), why)
    push(artist, main, [*why, "nombre de tête retiré"] if bare else why)

    # Une compilation, une émission ou un interprète : « Various Artists | Umeme
    # Afrorave - Agama », « Combat dub | Zion Train - … ».
    other = js_regex(r"(.+?)\s+[-\u2013]\s+(.+)\Z").match(main)
    if other and not _same_name(other.group(1), artist):
        push(
            _without_track_prefix(other.group(1)),
            _strip_end(other.group(2)),
            [*why, "artiste lu dans le titre"],
        )
    if js_regex(r"[^\W\d_]\s+[0-9]\Z").search(main):
        push(
            artist,
            js_regex(r"\s+[0-9]\Z").sub("", main, count=1),
            [*why, "chiffre de fin retiré"],
        )
    # Le premier artiste seul, pour chercher ; le candidat doit tout de même les
    # créditer tous.
    first = _FIRST_ARTIST.split(artist)[0]
    no_feat = js_trim(_FEAT_MENTION.sub("", main))
    if first and first != artist:
        push(first, no_feat, [*why, "premier artiste cherché"], artist)
    # Un titre coupé (« Dance Sucker (Francois Kevorki », « Je ne veux pa ») ne donne
    # aucune requête de plus : il ne sera jamais celui du candidat. Dernier recours :
    # l'artiste et le titre inversés (« THE_ANSWER | THE_BLACK_SEEDS »).
    push(main, artist, [*why, "artiste et titre inversés"])
    return out


# ===== Le jugement à la lettre près =====

_COVER = js_regex(
    r"\b(?:karaoke|tribute|made famous|in the style of|cover|originally performed)\b",
    re.IGNORECASE,
)
_ANY_FEAT_MENTION = js_regex(
    r"\s*[(\[]?\s*\b(?:feat\.?|ft\.?|featuring|with)\s+[^)\]]*[)\]]?", re.IGNORECASE
)


def _names(names: Iterable[str]) -> set[str]:
    return {name for name in map(squash, names) if name}


def _same_credits(
    variant: RadioVariant, candidate: Meta, radio: ParsedTitle, found: ParsedTitle
) -> bool:
    """Les mêmes artistes, des deux côtés, comme artiste ou comme invité du titre.

    Un invité cité d'un seul côté ne compte pas : un fichier l'écrit souvent dans le
    titre (« Better For My Heart feat. Judith Little D »), et la recherche de Deezer
    ne donne que l'artiste principal.
    """
    mine = _names(split_artists(variant.credited))
    theirs = _names(split_artists(candidate.artists))
    mine_all = mine | _names(radio.featuring)
    theirs_all = theirs | _names(found.featuring)
    return bool(mine) and mine <= theirs_all and theirs <= mine_all


def same_radio_track(variant: RadioVariant, candidate: Meta) -> bool:
    """Le candidat est-il, à la lettre près, le titre du fichier ?"""
    cover = any(_COVER.search(text) for text in (candidate.title, *candidate.artists))
    if cover and not _COVER.search(f"{variant.credited} {variant.title}"):
        return False
    radio, found = parse_title(variant.title), parse_title(candidate.title)
    same_base = bool(radio.base) and squash(radio.base) == squash(found.base)
    if not same_base and squash(_ANY_FEAT_MENTION.sub("", variant.title)) != squash(
        _ANY_FEAT_MENTION.sub("", candidate.title)
    ):
        return False
    if not _same_credits(variant, candidate, radio, found):
        return False
    # Une version, un remixeur, une mention d'un seul côté (« Crypto (Mix) » n'est
    # pas « Crypto »), un live sans album : refusés.
    source = Meta(title=variant.title, artists=(variant.credited,))
    return not compare(source, candidate).conflict


# ===== Le conflit de versions, et le score de `score.ts` =====

ACCEPT = 0.88
REMASTER_PENALTY = 0.1
EXPLICIT_PENALTY = 0.05


def levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y))
            )
        previous = current
    return previous[-1]


def ratio(a: str, b: str) -> float:
    """La similarité de deux textes, de 0 à 1 : la distance d'édition, rapportée à la
    plus longue."""
    length = max(len(a), len(b))
    return 1.0 if length == 0 else 1 - levenshtein(a, b) / length


def token_set_similarity(a: str, b: str) -> float:
    """L'ordre des mots ne compte pas, un mot en plus d'un côté coûte peu."""
    left = {token for token in a.split(" ") if token}
    right = {token for token in b.split(" ") if token}
    if not left or not right:
        return 1.0 if len(left) == len(right) else 0.0
    base = " ".join(sorted(left & right))
    with_left = " ".join(filter(None, [base, *sorted(left - right)]))
    with_right = " ".join(filter(None, [base, *sorted(right - left)]))
    return max(
        ratio(base, with_left) if base else 0.0,
        ratio(base, with_right) if base else 0.0,
        ratio(with_left, with_right),
    )


def duration_score(a: float | None, b: float | None) -> float:
    """1 sous 2 s d'écart, 0 au-delà de 12 s, linéaire entre ; 0,5 sans durée."""
    if a is None or b is None:
        return 0.5
    delta = abs(a - b) / 1000
    return 1.0 if delta <= 2 else 0.0 if delta >= 12 else 1 - (delta - 2) / 10


def _skeleton(name: str) -> str:
    """Le squelette d'un nom : deux translittérations ne diffèrent que par leurs
    voyelles."""
    return js_regex(r"(.)\1+").sub(r"\1", js_regex(r"[aeiouy]").sub("", name))


def same_artist(a: str, b: str) -> bool:
    """« fairuz », « fairouz » et « fayrouz » : le même nom. « Daft Funk » n'est pas
    « Daft Punk » : une consonne différente suffit à les séparer."""
    return a == b or (
        len(a) >= 5
        and len(b) >= 5
        and _skeleton(a) == _skeleton(b)
        and ratio(a, b) >= 0.65
    )


def _jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    """Les artistes communs sur tous les artistes, les translittérations d'un nom
    comptant pour un seul."""
    if not a and not b:
        return 1.0
    pool = list(b)
    common = 0
    for name in a:
        index = next(
            (at for at, other in enumerate(pool) if same_artist(name, other)), -1
        )
        if index >= 0:
            common += 1
            del pool[index]
    return common / (len(a) + len(b) - common)


def _artist_set(meta: Meta, parsed: ParsedTitle) -> list[str]:
    return list(dict.fromkeys([*split_artists(meta.artists), *parsed.featuring]))


@dataclass(frozen=True)
class VersionConflict:
    """Ce qui sépare deux versions ; à défaut, la pénalité d'une différence tolérée."""

    conflict: str | None
    penalty: float


def version_conflict(a: ParsedTitle, b: ParsedTitle) -> VersionConflict:
    different = [tag for tag in a.tags if tag not in b.tags]
    different += [tag for tag in b.tags if tag not in a.tags]
    penalty = 0.0
    if different:
        if any(tag != "remaster" for tag in different):
            tags = ", ".join(dict.fromkeys(different))
            return VersionConflict(f"version différente : {tags}", penalty)
        penalty += REMASTER_PENALTY
    if (
        a.remixers
        and b.remixers
        and not any(
            token_set_similarity(left, right) >= 0.85
            for left in a.remixers
            for right in b.remixers
        )
    ):
        return VersionConflict("remixeurs différents", penalty)
    # Deux concerts datés d'années différentes ne sont pas le même enregistrement.
    if "live" in a.tags and a.years and b.years and not set(a.years) & set(b.years):
        return VersionConflict("concert différent", penalty)
    return VersionConflict(None, penalty)


@dataclass(frozen=True)
class Comparison:
    """Le score d'un candidat, de 0 à 1, et ce qui l'écarte d'office.

    Le score pèse le titre pour 0,40, les artistes pour 0,30, la durée pour 0,20 et
    l'album pour 0,10, moins les pénalités : un remaster d'un seul côté (0,10),
    explicit contre clean (0,05).
    """

    score: float
    title: float
    artists: float
    duration: float
    album: float
    conflict: str | None
    accepted: bool


def compare(source: Meta, candidate: Meta) -> Comparison:
    a, b = parse_title(source.title), parse_title(candidate.title)
    title = token_set_similarity(a.base, b.base)
    artists = _jaccard(_artist_set(source, a), _artist_set(candidate, b))
    duration = duration_score(source.duration_ms, candidate.duration_ms)
    album = (
        token_set_similarity(
            parse_title(source.album).base, parse_title(candidate.album).base
        )
        if source.album and candidate.album
        else 0.5
    )
    version = version_conflict(a, b)
    explicit = (
        EXPLICIT_PENALTY
        if source.explicit is not None
        and candidate.explicit is not None
        and source.explicit != candidate.explicit
        else 0.0
    )
    score = max(
        0.0,
        0.4 * title
        + 0.3 * artists
        + 0.2 * duration
        + 0.1 * album
        - version.penalty
        - explicit,
    )
    # Une mention inconnue d'un seul côté (« Drumless Edition ») désigne un autre
    # enregistrement ; un live se reconnaît aussi à son album, le concert.
    extras = [extra for extra in a.extras if extra not in b.extras]
    extras += [extra for extra in b.extras if extra not in a.extras]
    conflict = (
        version.conflict
        or (f"mention différente : {', '.join(extras)}" if extras else None)
        or ("autre album live" if "live" in a.tags and album < 0.6 else None)
    )
    return Comparison(
        score,
        title,
        artists,
        duration,
        album,
        conflict,
        not conflict and score >= ACCEPT,
    )
