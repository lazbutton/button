"""La troisième passe : d'autres lectures du texte, d'autres règles d'artiste.

Les règles de `third.ts`, dans Hopper, pour un titre que ni la recherche à la lettre
près ni la seconde passe n'ont trouvé : le texte du fichier relu (annotation entre
crochets, numéro de piste collé, parenthèse coupée, version hors parenthèses), un texte
abîmé à l'import ou écrit dans une autre écriture, un artiste coupé à 30 signes, écrit
par ses noms de famille, ou remixeur. Toujours confirmée par la durée du fichier, à 7 s
près, dans la même version : le titre est « rapproché », à relire.

Hopper l'a mesurée sur 100 introuvables tirés au hasard : 26 trouvés, tous justes.

La recherche, chez Deezer, dans l'album du fichier et dans MusicBrainz en recherche
floue, est dans `search.py`.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from radiotomate.fiches.loose import (
    CLEANED,
    LOOSE_TOLERANCE_S,
    ONE_SIDED,
    SAME_FILE_S,
    Found,
    LooseCandidate,
    close_artist,
    close_title,
    foreign_cover,
    generic_title,
    loose_match,
    loose_variants,
    nearly_same,
    versions,
)
from radiotomate.fiches.normalize import (
    js_regex,
    js_trim,
    latin_words,
    normalize_text,
    parse_title,
    split_artists,
    squash,
)
from radiotomate.fiches.rules import js_falsy, js_round

if TYPE_CHECKING:
    from collections.abc import Sequence

    from radiotomate.fiches.loose import ArtistAndTitle
    from radiotomate.fiches.variants import RadioTrack


# ===== Le texte du fichier, relu =====


@dataclass(frozen=True)
class Reading:
    """Une lecture du texte d'un fichier : l'artiste et le titre à chercher.

    `fix` : ce que la lecture a changé au texte. `swapped` : l'artiste et le titre lus
    à l'envers (« THE WORLD », de « THE ACHIEVEMENT », cherché comme « THE
    ACHIEVEMENT », de « THE WORLD »).
    """

    artist: str
    title: str
    fix: str = ""
    swapped: bool = False


SWAPPED = "artiste et titre inversés"

# Les mots d'une version écrite hors parenthèses (« I'm gonna leave you the cinematic
# orchestra rmx »).
_VERSION_WORD = js_regex(
    r"(?:rmx|remix|edit|mix|dub|version|rework|bootleg|refix|reedit)", re.IGNORECASE
)
_CAMPUS = js_regex(r"radio.?campus.?france", re.IGNORECASE)
_ANNOTATION = js_regex(r"\s*\[([^\]]*)\]")
_GLUED_NUMBER = js_regex(r"[0-9]{1,2}\s*[-.]\s*(?=\S)")
_EXTRA_DIGIT = js_regex(r"\)\s+[0-9]{1,2}\Z")
_LAST_DIGITS = js_regex(r"\s+[0-9]{1,2}\Z")
_CUT_PARENTHESIS = js_regex(r"\s*\([^)]*\Z")


def _without_notes(title: str) -> str:
    """Le titre sans ses annotations entre crochets, sauf une version (« [Live] »)."""

    def note(match: re.Match[str]) -> str:
        return "" if parse_title(f"x ({match[1]})").extras else match[0]

    return js_trim(_ANNOTATION.sub(note, title))


def readings(item: RadioTrack, album: str = "") -> list[Reading]:
    """Les requêtes de la seconde passe, plus d'autres lectures du texte du fichier.

    Une annotation entre crochets retirée (« My Melody ['We Can Get Down'] »,
    « [FREEDOWNLOAD] », mais pas « [Live] », une version), un numéro de piste collé
    (« 02-MOVE TAN »), un chiffre en trop après une parenthèse, une parenthèse coupée
    (« (Los Amparit »), une version hors parenthèses remise entre parenthèses,
    l'artiste d'un titre de « Radio Campus France » (« FANFARE FOR 7.83Hz | PHOTAY »).
    """
    radio_artist, radio_title = squash(item.artist), squash(item.title)
    base = [
        Reading(
            variant.artist,
            variant.title,
            swapped=squash(variant.title) in radio_artist
            and squash(variant.title) not in radio_title,
        )
        for variant in loose_variants(item)[:2]
    ]
    if _CAMPUS.fullmatch(js_trim(item.artist)):
        parts = js_regex(r"\s*\|\s*").split(item.title)
        if len(parts) > 1 and parts[1]:
            base.insert(0, Reading(parts[1], parts[0], "artiste lu dans le titre"))
        elif js_trim(album):
            base.insert(
                0, Reading(js_trim(album), item.title, "artiste lu dans l'album")
            )
    out = list(base)
    for reading in base:
        title = reading.title
        fixes = [reading.fix] if reading.fix else []
        notes = _without_notes(title)
        if notes != title:
            title = notes
            fixes.append("annotation entre crochets retirée")
        if _GLUED_NUMBER.match(title):
            title = _GLUED_NUMBER.sub("", title, count=1)
            fixes.append("numéro de piste collé")
        if _EXTRA_DIGIT.search(title):
            title = _LAST_DIGITS.sub("", title, count=1)
            fixes.append("chiffre en trop")
        if _CUT_PARENTHESIS.search(title):
            title = _CUT_PARENTHESIS.sub("", title, count=1)
            fixes.append("parenthèse coupée retirée")
        if title and title != reading.title:
            out.append(replace(reading, title=title, fix=", ".join(fixes)))
        # La recherche à la lettre près met déjà le dernier mot entre parenthèses (« the
        # cinematic (orchestra rmx) ») : le remixeur peut en compter plus.
        words = js_regex(r"\s+").split(js_trim(js_regex(r"[()]").sub(" ", title)))
        at = next(
            (
                index
                for index, word in enumerate(words)
                if index > 0 and _VERSION_WORD.fullmatch(word)
            ),
            -1,
        )
        if at > 0 and not js_regex(r"[()\[\]]").search(item.title):
            fix = ", ".join([*fixes, "version hors parenthèses"])
            for size in range(1, min(4, at) + 1):
                cut = at - size + 1
                wrapped = f"{' '.join(words[:cut])} ({' '.join(words[cut:])})"
                out.append(replace(reading, title=wrapped, fix=fix))

    # Les parenthèses comptent : « you the cinematic (orchestra rmx) » n'est pas « you
    # (the cinematic orchestra rmx) ».
    def key(reading: Reading) -> str:
        title = js_trim(js_regex(r"\s+").sub(" ", reading.title.lower()))
        return f"{squash(reading.artist)}|{title}"

    keys = [key(reading) for reading in out]
    return [
        reading
        for at, reading in enumerate(out)
        if reading.title and keys.index(keys[at]) == at
    ]


# ===== Le morceau trouvé est-il le bon ? =====


def damaged(text: str) -> str:
    """Le texte tel que l'import l'a parfois abîmé : chaque signe hors ASCII réduit à
    ses 7 bits de poids faible.

    « è » → « h », « ś » → « [ », « ł » → « B » : « Marie-Thirhse », « W[rsd
    Pampassw », « Gra|yna Aobaszewska ».
    """
    return "".join(
        chr(ord(char) & 0x7F) if ord(char) > 0x7F else char
        for char in unicodedata.normalize("NFC", text)
    )


def _latin(text: str) -> str:
    return "".join(latin_words(text))


_MENTIONS = js_regex(r"\s*[(\[][^()\[\]]*[)\]]")


def _bare(title: str) -> str:
    """Le titre sans ses mentions entre parenthèses ou crochets, sans rien normaliser :
    les accents d'origine comptent."""
    return js_trim(_MENTIONS.sub("", title)) or title


# Les plages du script latin (`Script=Latin`), d'après Unicode 17, telles que Node 24
# les lit ; le `\p{Script=Latin}` de Hopper n'a pas d'équivalent dans `re`.
_LATIN_SCRIPT = (
    (0x0041, 0x005A), (0x0061, 0x007A), (0x00AA, 0x00AA), (0x00BA, 0x00BA),
    (0x00C0, 0x00D6), (0x00D8, 0x00F6), (0x00F8, 0x02B8), (0x02E0, 0x02E4),
    (0x1D00, 0x1D25), (0x1D2C, 0x1D5C), (0x1D62, 0x1D65), (0x1D6B, 0x1D77),
    (0x1D79, 0x1DBE), (0x1E00, 0x1EFF), (0x2071, 0x2071), (0x207F, 0x207F),
    (0x2090, 0x209C), (0x212A, 0x212B), (0x2132, 0x2132), (0x214E, 0x214E),
    (0x2160, 0x2188), (0x2C60, 0x2C7F), (0xA722, 0xA787), (0xA78B, 0xA7DC),
    (0xA7F1, 0xA7FF), (0xAB30, 0xAB5A), (0xAB5C, 0xAB64), (0xAB66, 0xAB69),
    (0xFB00, 0xFB06), (0xFF21, 0xFF3A), (0xFF41, 0xFF5A), (0x10780, 0x10785),
    (0x10787, 0x107B0), (0x107B2, 0x107BA), (0x1DF00, 0x1DF1E), (0x1DF25, 0x1DF2A),
)  # fmt: skip
_LATIN_STARTS = tuple(start for start, _ in _LATIN_SCRIPT)


def _other_script(text: str) -> bool:
    """Une lettre d'une autre écriture que le latin."""

    def latin(char: str) -> bool:
        at = bisect.bisect_right(_LATIN_STARTS, ord(char)) - 1
        return at >= 0 and ord(char) <= _LATIN_SCRIPT[at][1]

    return any(char.isalpha() and not latin(char) for char in text)


def _other_spelling(radio: str, found: str, what: str) -> str | None:
    """Le même nom abîmé à l'import (« Marie-Thirhse »), écrit dans une autre écriture
    (« Skiouroi ») ou autrement (« Lotte Kaersa », « Lotte Kærså » ; « REDDS THE
    BOYS », « Redds & the Boys ») : la raison, ou None."""
    if damaged(found) != unicodedata.normalize("NFC", found) and nearly_same(
        damaged(found), radio
    ):
        return f"{what} aux accents perdus"
    theirs = _latin(found)
    if not theirs or theirs == squash(found) or not nearly_same(theirs, _latin(radio)):
        return None
    if _other_script(found):
        return f"{what} dans une autre écriture"
    return f"{what} écrit autrement"


# Les mots qu'un nom d'ensemble ajoute sans changer de qui il s'agit (« Super Rail Band
# de Bamako », « Fruko y sus Tesos »).
_FILLER = frozenset(
    "and et y e the le la les los las el de do da des du of his her their sus ses son"
    " band orchestra orchestre orquesta group groupe ensemble combo trio quartet"
    " quintet sextet".split(" ")
)


def any_artist(radio: str, found: Sequence[str], found_title: str) -> str | None:
    """L'artiste du fichier parmi ceux trouvés : la raison, ou None.

    Les règles de la seconde passe, et cinq de plus : un nom abîmé ou écrit dans une
    autre écriture ; coupé à 30 signes (« GILAD AZMON AND THE ORIENT HOU ») ; des noms
    de famille (« Zorn Lewis Frisell » pour John Zorn, George Lewis et Bill Frisell) ;
    le remixeur nommé dans le titre trouvé (« KMTR » pour « Sorarim (KMTR Edit) »).
    """
    close = close_artist(radio, found)
    if close:
        return close
    names = [*found, " & ".join(found)]
    for name in names:
        other = _other_spelling(radio, name, "artiste")
        if other:
            return other
    mine = normalize_text(radio)
    words = mine.split(" ")
    if len(js_trim(radio)) >= 28:
        # Le dernier mot, coupé, ne compte pas.
        head = "".join(words[:-1])
        if len(head) >= 8 and any(
            squash(name).startswith(head)
            or nearly_same(head, squash(name)[: len(head)])
            for name in names
        ):
            return "artiste coupé à 30 signes"
    # Chaque nom du fichier est celui d'un des artistes crédités (« Zorn Lewis
    # Frisell ») ; tous dans un seul nom, seulement avec des mots d'ensemble en plus :
    # « Lonnie Smith » n'est pas Lonnie Liston Smith.
    people = [person.split(" ") for name in found for person in split_artists(name)]
    surnames = [word for word in words if len(word) >= 4]
    homes = [
        next((at for at, person in enumerate(people) if word in person), -1)
        for word in surnames
    ]
    if len(surnames) >= 2 and all(home >= 0 for home in homes):
        single = all(home == homes[0] for home in homes)
        extra = (
            [word for word in people[homes[0]] if word not in words] if single else []
        )
        if all(
            word in _FILLER or len(word) <= 2 or js_regex(r"[0-9]+").fullmatch(word)
            for word in extra
        ):
            return "artistes par leur nom"
    if any(
        squash(remixer) == squash(radio)
        for remixer in parse_title(found_title).remixers
    ):
        return "artiste remixeur"
    return None


def any_title(radio: str, found: str) -> str | None:
    """Le titre du fichier et celui trouvé : les règles de la seconde passe, ou le même
    titre abîmé, ou dans une autre écriture."""
    close = close_title(radio, found)
    if close is not None:
        return close
    return _other_spelling(_bare(radio), _bare(found), "titre")


@dataclass(frozen=True)
class ThirdCandidate(LooseCandidate):
    """Un candidat, et s'il vient de l'album du fichier, retrouvé chez Deezer : une
    compilation, souvent."""

    from_album: bool = False


# Les titres assez sûrs pour se passer de l'artiste, dans l'album du fichier.
_STRONG_TITLES = frozenset(
    {
        "même titre",
        "titre à une faute près",
        "titre aux accents perdus",
        "titre dans une autre écriture",
    }
)


def third_match(
    reading: Reading,
    candidate: ThirdCandidate,
    radio_seconds: float | None,
    album_ok: bool = False,
) -> Found | None:
    """Le candidat est-il le morceau du fichier ?

    D'abord les règles de la seconde passe ; sinon l'artiste et le titre de la
    troisième, à 7 s près et dans la même version (une version d'un seul côté, à
    2 s). Un morceau de l'album du fichier peut se passer de l'artiste, qui y est
    parfois écrit dans une autre langue, avec un titre sûr, à 5 s. `album_ok` : cet
    album en est un vrai, pas un nom vide ni celui de l'artiste.
    """
    fix = (reading.fix,) if reading.fix else ()
    loose = loose_match(reading, candidate, radio_seconds)
    if loose:
        return replace(loose, why=(*loose.why, *fix))
    if (
        js_falsy(radio_seconds)
        or js_falsy(candidate.duration_ms)
        or generic_title(reading.title)
        or foreign_cover(reading, candidate)
    ):
        return None
    gap = abs(candidate.duration_ms / 1000 - radio_seconds)
    if gap > LOOSE_TOLERANCE_S:
        return None
    title = any_title(reading.title, candidate.title)
    if not title:
        return None
    # Sans l'artiste, seulement le titre lu à sa place (pas l'artiste pris pour un
    # titre), dans une compilation.
    from_album = (
        candidate.from_album
        and album_ok
        and not reading.swapped
        and gap <= 5
        and title in _STRONG_TITLES
    )
    artist = any_artist(reading.artist, candidate.artists, candidate.title)
    if artist is None and from_album:
        artist = "dans l'album de la radio"
    agreement = versions(reading.title, candidate.title)
    if (
        not artist
        or agreement == "contraires"
        or (agreement == "d'un seul côté" and gap > SAME_FILE_S)
    ):
        return None
    one_sided = agreement != "mêmes"
    why = (artist, title, f"durée à {js_round(gap)} s")
    return Found((*why, *((ONE_SIDED,) if one_sided else ()), *fix), gap, one_sided)


def third_judge(
    item: ArtistAndTitle,
    reading: Reading,
    candidate: ThirdCandidate,
    radio_seconds: float | None,
    album_ok: bool = False,
) -> Found | None:
    """Le candidat d'une lecture du fichier, jugé par la troisième passe, et ce que la
    lecture a fait du texte du fichier.

    Le titre cherché n'est plus celui du fichier (« A3 The Broken Shoe ») : le titre
    trouvé le remplacera (`CLEANED`) ; l'artiste et le titre cherchés à l'envers :
    chacun reprendra sa place (`SWAPPED`).
    """
    verdict = third_match(reading, candidate, radio_seconds, album_ok)
    if not verdict:
        return None
    radio_title = squash(item.title.replace("_", " "))
    cleaned = (
        not reading.fix and not reading.swapped and squash(reading.title) != radio_title
    )
    notes = (CLEANED,) if cleaned else (SWAPPED,) if reading.swapped else ()
    return Found((*verdict.why, *notes), verdict.gap, verdict.one_sided)


# ===== Ce que la recherche en tire =====

# Un album bidon : « title », « no title », ou un marqueur de langue (« |Anglais »).
PLACEHOLDER = js_regex(r"(?:title|no title|\|.*)", re.IGNORECASE)


def album_ok(album: str, artist: str) -> bool:
    """L'album du fichier en est-il un vrai, qui peut se passer de l'artiste ?

    Pas un nom bidon, pas le nom de l'artiste (« THE WORLD », album « THE WORLD ») :
    un album au nom de l'artiste n'est pas une compilation. Et assez long pour ne pas
    en rencontrer un autre.
    """
    album = js_trim(album)
    return (
        len(squash(album)) >= 8
        and not PLACEHOLDER.fullmatch(album)
        and squash(album) != squash(artist)
    )


def fuzzy(text: str) -> str:
    """Les mots d'une requête floue de MusicBrainz : une faute permise dès quatre
    lettres."""
    words = [word for word in normalize_text(text).split(" ") if len(word) > 1]
    return " ".join(f"{word}~" if len(word) >= 4 else word for word in words)
