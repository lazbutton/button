"""Ce qu'on propose, d'après quoi, et quand on s'abstient.

Les règles de `rules.ts`, dans Hopper. Un champ faux est pire qu'un champ vide : rien
ne remplace une valeur du fichier, sauf sa graphie (casse, soulignés, accents) ou une
valeur bidon (« title », un ISRC mal formé). Une année, un genre ou un genre d'artiste
qu'aucune source ne déclare restent à vérifier : jamais déduits d'un prénom, d'une
voix, d'une photo ni d'un nom qui ressemble.
"""

from __future__ import annotations

import datetime
import math
import re
import string
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from radiotomate.fiches.normalize import (
    is_mark,
    is_upper,
    js_regex,
    normalize_text,
    parse_title,
    split_artists,
    squash,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


def js_round(value: float) -> int:
    """Le `Math.round` de JavaScript : une demie va vers le haut, -2,5 donne -2."""
    whole = math.floor(value)
    return whole + 1 if value - whole >= 0.5 else whole


# ===== Le morceau trouvé est-il le bon fichier ? =====

# L'écart toléré entre la durée du fichier et celle du morceau trouvé : silences,
# fondus, rips de vinyle.
DURATION_TOLERANCE_S = 10


@dataclass(frozen=True)
class DurationLevel:
    level: str
    gap: int | None = None
    why: str | None = None


def duration_level(
    radio_seconds: float | None, found_seconds: float | None
) -> DurationLevel:
    """Le niveau d'un morceau trouvé à la lettre près, d'après sa durée.

    Le même titre et les mêmes artistes ne suffisent pas : la durée du fichier
    départage un extrait, un edit, une autre version.
    """
    if not radio_seconds or not found_seconds:
        return DurationLevel("à revoir", why="durée du morceau trouvé inconnue")
    gap = js_round(found_seconds - radio_seconds)
    if abs(gap) <= DURATION_TOLERANCE_S:
        return DurationLevel("sûr", gap)
    why = f"durée : {clock(radio_seconds)} ici, {clock(found_seconds)} trouvé"
    return DurationLevel("à revoir", gap, why)


def clock(seconds: float) -> str:
    """244 → « 4:04 »."""
    total = js_round(seconds)
    return f"{total // 60}:{total % 60:02d}"


# ===== Graphies =====


def _edition_only(label: str) -> bool:
    parsed = parse_title(f"x ({label})")
    return (
        not parsed.extras
        and not parsed.featuring
        and not parsed.remixers
        and all(tag == "remaster" for tag in parsed.tags)
    )


_MENTION = re.compile(r"\s*[(\[]([^()\[\]]*)[)\]]")
_DASH_TAIL = re.compile(r"\s[-\u2013\u2014]\s([^-\u2013\u2014]+)\Z")


def without_edition_mentions(title: str) -> str:
    """Le titre sans ses mentions d'édition, qui ne changent pas l'enregistrement.

    « (Remastered 2024) », « (Original Mix) », « - Original », « [Album Version] »
    partent ; les versions (live, remix, edit), les invités et les mentions inconnues
    restent.
    """
    out = _MENTION.sub(lambda match: "" if _edition_only(match[1]) else match[0], title)
    while (dash := _DASH_TAIL.search(out)) and _edition_only(dash[1]):
        out = out[: dash.start()]
    return out.strip() or title.strip()


# Les parenthèses et crochets d'une mention gardée, masqués le temps de relire les
# autres.
_HIDDEN = {"(": "\x01", ")": "\x02", "[": "\x03", "]": "\x04"}
_SHOWN = {hidden: mark for mark, hidden in _HIDDEN.items()}
_FEAT_TAIL = re.compile(r"\s(?:feat\.?|ft\.?|featuring)\s+(.+)\Z", re.IGNORECASE)
_FROM_TAIL = re.compile(r"\sfrom\s+([\"\u201c\u00ab].+)\Z", re.IGNORECASE)


def without_foreign_mentions(found: str, radio: str) -> str:
    """Le titre trouvé sans les mentions que le fichier n'écrit pas.

    Une version (« Live at The Mayan Theatre », « 1969 Mono Single Master »), un
    invité, une précision entre parenthèses ne s'ajoutent pas à son titre en le
    corrigeant. Une suite qui n'est pas une version (« You Got the Power - To Turn Me
    On ») fait partie du titre.
    """
    mine = set(normalize_text(radio.replace("_", " ")).split(" "))

    def written(label: str) -> bool:
        return all(word in mine for word in normalize_text(label).split(" ") if word)

    def hide(match: re.Match[str]) -> str:
        if not written(match[1]):
            return ""
        return re.sub(r"[()\[\]]", lambda mark: _HIDDEN[mark[0]], match[0])

    # Des parenthèses dans des parenthèses (« (Album Version (Explicit)) ») : de
    # l'intérieur vers l'extérieur.
    out, before = found, ""
    while before != out:
        before = out
        out = _MENTION.sub(hide, out)
    out = re.sub(r"[\x01-\x04]", lambda mark: _SHOWN[mark[0]], out)
    while True:
        dash = _DASH_TAIL.search(out)
        if not dash or written(dash[1]) or parse_title(f"x - {dash[1]}").base != "x":
            break
        out = out[: dash.start()]
    # Un invité, ou le film d'une musique de film (« Theme Du Gorille From "Le Gorille
    # Vous Salue Bien" »).
    for inline in (_FEAT_TAIL, _FROM_TAIL):
        mention = inline.search(out)
        if mention and not written(mention[1]):
            out = out[: mention.start()]
    return out.strip() or found.strip()


_GROUP_TAIL = re.compile(r"\s*[(\[][^()\[\]]*[)\]]\Z")
_FEAT_END = re.compile(
    r"\s(?:feat\.?|ft\.?|featuring)\s+(?:(?!\s[-\u2013\u2014]\s).)+\Z", re.IGNORECASE
)


def split_tail(title: str) -> tuple[str, str]:
    """Un titre et ses mentions de fin : parenthèses ou crochets, « - Remix »,
    « feat. X ».

    « Murky Racing - Featuring Mocky » donne « Murky Racing » et « - Featuring
    Mocky » : corriger le premier ne fait pas perdre les secondes.
    """
    whole = title.strip()
    base = whole
    while True:
        group = _GROUP_TAIL.search(base)
        if group and group.start() > 0:
            base = base[: group.start()]
            continue
        dash = _DASH_TAIL.search(base)
        if dash and parse_title(f"x - {dash[1]}").base == "x":
            base = base[: dash.start()]
            continue
        # « feat. X » à la fin seulement : pas « Sleepin Giant ft. Romaine Smith - Hey
        # Girl ».
        feat = _FEAT_END.search(base)
        if feat and feat.start() > 0:
            base = base[: feat.start()]
            continue
        return base.strip(), whole[len(base) :].strip()


def calmed(text: str) -> str:
    """Un texte en capitales, une capitale par mot : « FEAT PRINCE RAPID » → « Feat
    Prince Rapid »."""
    if not _shouting(text):
        return text

    def replace(run: str, offset: int) -> str:
        previous = text[offset - 1] if offset else ""
        return run.lower() if previous in _JOINS else _capitalized(run)

    return _replace_runs(text, replace)


def exotic_letters(text: str) -> bool:
    """Des lettres au-delà de l'alphabet latin étendu (« ḗ », « ượ ») : rares, souvent
    une erreur de saisie de la source."""
    return any(
        char.isalpha() and ord(char) > 0x24F
        for char in unicodedata.normalize("NFC", text)
    )


def plain_punctuation(text: str) -> str:
    """La ponctuation typographique d'une graphie trouvée, ramenée à celle du clavier.

    MusicBrainz écrit « Q-Tip » avec un trait d'union U+2010, qu'un tag tapé au clavier
    n'a pas ; de même une apostrophe courbe. Une parenthèse collée au mot s'en décolle
    (« Now(Dwson Remix) »).
    """
    text = re.sub(r"[\u2019\u2018\u02bc\u201b]", "'", text)
    text = re.sub(r"[\u201c\u201d\u201e]", '"', text)
    text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014]", "-", text)
    text = text.replace("\u2026", "...").replace("\u00a0", " ")
    return re.sub(r"([^\W_])\(", r"\1 (", text)


def _same_spelling(radio: str, found: str) -> bool:
    return squash(radio.replace("_", " ")) == squash(found)


# Une apostrophe ne commence pas un mot : « Who's », « N'Dogoni ».
_JOINS = frozenset("'\u2019\u02bc")


def _starts_word(previous: str) -> bool:
    return not previous.isalpha() and previous not in _JOINS


def _only_letters(text: str) -> str:
    return "".join(char for char in text if char.isalpha())


def _has_letter(text: str) -> bool:
    return any(char.isalpha() for char in text)


@dataclass
class _Letter:
    letter: str
    marks: str
    start: bool
    after_join: bool


def _letters_of(text: str) -> list[_Letter]:
    """Les lettres d'un texte décomposé (NFD), chacune avec ses accents.

    Chacune sait si elle commence un mot, ou suit une apostrophe.
    """
    out: list[_Letter] = []
    last: _Letter | None = None
    previous = ""
    for char in unicodedata.normalize("NFD", text):
        if is_mark(char):
            if last is not None:
                last.marks += char
            continue
        last = None
        if char.isalpha():
            last = _Letter(char, "", _starts_word(previous), previous in _JOINS)
            out.append(last)
        previous = char
    return out


def _accents_of(letter: _Letter) -> str:
    """Le point suscrit du « İ » turc n'est pas un accent : la minuscule « i » l'a."""
    if letter.letter in "ijIJ":
        return letter.marks.replace("\u0307", "")
    return letter.marks


def _accent_count(text: str) -> int:
    """Les accents et lettres particulières (« ø », « œ », « ß »…) d'un texte : ce
    qu'une graphie ne doit pas perdre."""
    return sum(
        len(_accents_of(letter)) + (letter.letter not in string.ascii_letters)
        for letter in _letters_of(text)
    )


def _merged(found: str, radio: str, radio_case: bool) -> str | None:
    """La graphie trouvée lettre à lettre, avec la casse du fichier si `radio_case`.

    Les accents viennent des deux : ceux de la graphie trouvée d'abord, sinon ceux du
    fichier. None si les lettres ne s'alignent pas (« & » face à « and », « œ » face
    à « oe », « ø » face à « o »).
    """
    twins = _letters_of(radio)
    mine = _letters_of(found)
    if len(mine) != len(twins) or any(
        one.letter.lower() != twin.letter.lower() for one, twin in zip(mine, twins)
    ):
        return None
    # Avec la casse du fichier, deux exceptions, chacune pour un mot entier de la
    # graphie trouvée : un mot coupé autrement (« Patanegra », « Pata Negra »), une
    # capitale au milieu d'un mot, ailleurs qu'après une apostrophe (« Sly5thAve »,
    # « FerenDJi », mais pas « D'Amour »). Jamais un mot moitié l'un, moitié l'autre.
    found_case = [False] * len(mine)
    first = 0
    while first < len(mine):
        end = first + 1
        while end < len(mine) and not mine[end].start:
            end += 1
        word = mine[first:end]
        inner = any(
            at > 0
            and not one.after_join
            and one.letter != one.letter.lower()
            and word[at - 1].letter != word[at - 1].letter.upper()
            for at, one in enumerate(word)
        )
        # Une espace du fichier à la place d'une apostrophe (« don t », « Don't »)
        # ne coupe pas le mot.
        split = not twins[first].start or any(
            twin.start and not mine[first + 1 + at].after_join
            for at, twin in enumerate(twins[first + 1 : end])
        )
        for at in range(first, end):
            found_case[at] = not radio_case or inner or split
        first = end
    out: list[str] = []
    index = 0
    for char in unicodedata.normalize("NFD", found):
        if is_mark(char):
            continue
        if not char.isalpha():
            out.append(char)
            continue
        at, index = index, index + 1
        twin = twins[at]
        letter = mine[at].letter if found_case[at] else twin.letter
        # Les accents trouvés, sinon ceux du fichier ; le point suscrit du « İ » turc
        # n'a pas lieu d'être sur une minuscule.
        marks = twin.marks.replace("\u0307", "") if letter in "ij" else twin.marks
        out.append(letter + (mine[at].marks or marks))
    return unicodedata.normalize("NFC", "".join(out))


def _shouting(text: str) -> bool:
    """Un texte en capitales : plus de la moitié de ses mots de trois lettres ou plus
    (« ANNEES SOLAIRES Part I »)."""
    words = [
        word for word in map(_only_letters, re.split(r"\s+", text)) if len(word) > 2
    ]
    return sum(word == word.upper() for word in words) * 2 > len(words)


def _brackets(text: str) -> int:
    return text.count("(") + text.count("[")


def respelling(radio: str, found: str | None, *, sentence: bool = False) -> str | None:
    """La graphie trouvée, si seuls la casse, les accents, les espaces, la ponctuation
    ou les soulignés changent, sans jamais perdre un accent du fichier.

    « GLIMITY_GLAMITY » → « Glimity Glamity » ; « l'éclair » et « L'Eclair » donnent
    « L'Éclair » ; « Les Frères Smith » ne devient pas « Les Freres Smith ». Une casse
    soignée reste, la ponctuation et les accents trouvés s'y ajoutent : des capitales
    ailleurs qu'en tête sans être un texte en capitales (« He's a Superstar » reste,
    « Guess Whos Back » devient « Guess Who's Back »), ou, pour un titre ou un album
    (`sentence`), une phrase (« Je ne bois pas beaucoup » reste). Une graphie trouvée
    en capitales ne remplace pas une casse du fichier. « Vladimir and his orchestra »,
    un nom d'artiste tapé vite, devient « Vladimir And His Orchestra ».
    """
    clean = plain_punctuation(found).strip() if found else found
    if not clean or clean == radio or not _same_spelling(radio, clean):
        return None
    text = re.sub(r"\s+", " ", radio).strip()
    letters = _only_letters(text)
    rest = letters[1:]
    typed = "_" not in radio
    capital = is_upper(letters[:1])
    cased = typed and capital and any(map(is_upper, rest)) and not _shouting(text)
    phrase = (
        sentence
        and typed
        and capital
        and rest == rest.lower()
        and sum(map(_has_letter, text.split(" "))) > 1
    )
    found_letters = _only_letters(clean)
    loud = (
        found_letters == found_letters.upper()
        and len(re.split(r"\s+", clean)) > 1
        and letters != letters.upper()
    )
    radio_case = cased or phrase or loud
    proposal = _merged(clean, radio, radio_case)
    if (
        proposal is None
        and not radio_case
        and _accent_count(clean) >= _accent_count(radio)
    ):
        proposal = clean
    # Les parenthèses d'un titre ou d'un album restent (« Moribiyassa (Daniel Haaksman
    # Edit) », pas « Moribiyassa - Daniel Haaksman Edit ») ; celles d'un nom peuvent
    # partir (« Giorgio (Moroder) » → « Giorgio Moroder »).
    if sentence and proposal and _brackets(proposal) < _brackets(radio):
        return None
    if not proposal or proposal in (radio, plain_punctuation(radio)):
        return None
    return proposal


def _capitalized(word: str) -> str:
    return word[:1].upper() + word[1:].lower()


def _is_run(char: str) -> bool:
    """Une lettre, une marque ou un chiffre (`[\\p{L}\\p{M}\\p{N}]`)."""
    return unicodedata.category(char)[0] in "LMN"


def _runs(text: str) -> list[tuple[int, str]]:
    """Les mots d'un texte, avec leur position : des lettres, marques et chiffres."""
    out: list[tuple[int, str]] = []
    start = None
    for at, char in enumerate(text):
        if _is_run(char):
            if start is None:
                start = at
        elif start is not None:
            out.append((start, text[start:at]))
            start = None
    if start is not None:
        out.append((start, text[start:]))
    return out


def _replace_runs(text: str, replace: Callable[[str, int], str]) -> str:
    out: list[str] = []
    end = 0
    for at, run in _runs(text):
        out.append(text[end:at])
        out.append(replace(run, at))
        end = at + len(run)
    out.append(text[end:])
    return "".join(out)


_RUN_STARTS = frozenset(' \t\n\v\f\r([{"\u00ab/')


def _starts_run(text: str, offset: int) -> bool:
    """Un mot commence au début du texte, après une espace, une parenthèse ou un
    guillemet ; pas après « ' », « - » ou « * »."""
    if offset == 0:
        return True
    previous = text[offset - 1]
    return previous in _RUN_STARTS or previous.isspace()


@dataclass(frozen=True)
class _Word:
    run: str
    start: bool


def _words_of(text: str) -> list[_Word]:
    return [_Word(run, _starts_run(text, at)) for at, run in _runs(text)]


@dataclass(frozen=True)
class _Style:
    # Une casse de titre (« Meet Me At The Roosevelt ») : une capitale à plus de la
    # moitié des mots.
    title: bool
    # Une capitale à chaque mot.
    every: bool


def _style(words: Sequence[_Word]) -> _Style:
    lettered = [word for word in words if word.start and _has_letter(word.run)]
    upper = sum(is_upper(word.run[:1]) for word in lettered)
    return _Style(upper * 2 > len(lettered), upper == len(lettered))


def retyped(
    radio: str, found: str, *, sentence: bool = False, inside: bool = False
) -> str:
    """Une correction écrite comme le fichier écrit.

    Une faute de frappe, un titre coupé, des mots en plus ou en moins, un numéro de
    piste retiré : les mots gardent leurs accents, et leur casse si le fichier la
    soigne (comme pour `respelling`) ; un mot nouveau suit alors son style (« Peaches
    in regalia » et « Peaches En Regalia » donnent « Peaches en regalia »). Sinon
    (soulignés, capitales, minuscules), la casse trouvée, en capitales seulement si
    le fichier l'était.
    """
    clean = re.sub(r"\s+", " ", plain_punctuation(found)).strip()
    text = re.sub(r"\s+", " ", radio).strip()
    letters = _only_letters(text)
    rest = letters[1:]
    typed = "_" not in radio
    capital = is_upper(letters[:1])
    cased = typed and capital and any(map(is_upper, rest)) and not _shouting(text)
    phrase = (
        sentence
        and typed
        and capital
        and rest == rest.lower()
        and sum(map(_has_letter, text.split(" "))) > 1
    )
    careful = cased or phrase
    # Une graphie trouvée en capitales, face à un fichier qui ne l'est pas : une
    # capitale par mot.
    loud = _shouting(clean) and not _shouting(text)

    runs = _words_of(text.replace("_", " "))
    title_case = cased and _style(runs).title
    every = _style(runs).every
    # Les capitales d'une graphie trouvée en casse de titre ne disent rien ; celles
    # d'une phrase, des noms (« Brasil »).
    found_title_case = _style(_words_of(clean)).title
    used: set[int] = set()
    first = True

    def replace(run: str, offset: int) -> str:
        nonlocal first
        if not _has_letter(run):
            return run
        start = _starts_run(clean, offset)
        at = next(
            (
                index
                for index, other in enumerate(runs)
                if index not in used and squash(other.run) == squash(run)
            ),
            -1,
        )
        if at >= 0:
            used.add(at)
        word = run
        if at >= 0 and runs[at].start == start:
            # Le mot du fichier : ses accents, et sa casse s'il la soigne.
            merged = _merged(run, runs[at].run, careful)
            word = run if merged is None else merged
            if loud and not careful:
                word = _capitalized(word) if start else word.lower()
        elif loud and (at >= 0 or not start or not careful):
            # Un mot coupé autrement (« Y'a De La Haine », « Y'a d'la haine »), la
            # suite d'un mot (« F**k », « Who's ») ou un mot sans casse à suivre : la
            # graphie trouvée, sans ses capitales.
            word = _capitalized(run) if start else run.lower()
        elif at >= 0 or not start or not careful:
            word = run
        elif title_case:
            # Une capitale à chaque mot, petits mots compris, si le fichier en met
            # partout (« Say The Truth And Run »).
            if loud or (every and run == run.lower()):
                word = _capitalized(run)
        elif len(run) > 1 and (loud or (found_title_case and run == _capitalized(run))):
            # Une phrase : le mot nouveau en minuscules, sauf un sigle (« DJ ») ou une
            # lettre seule (« I »).
            word = run.lower()
        # En tête de titre, une capitale ; pas dans une mention de fin (`inside`).
        if first and careful and not inside:
            word = word[:1].upper() + word[1:]
        first = False
        return word

    return _replace_runs(clean, replace)


_SEPARATORS = js_regex(
    r"(\s*(?:,|&|\+|/|;|\bfeat\.?(?=\s)|\bft\.?(?=\s)|\bfeaturing\b|\s[x\u00d7]\s"
    r"|\bvs\.?(?=\s))\s*)",
    re.IGNORECASE,
)


def respell_artists(radio: str, found: Sequence[str]) -> str | None:
    """Les artistes du fichier dans la graphie trouvée, ses séparateurs gardés.

    « HUSH_PUPPIES » → « Hushpuppies », « dornik & X » → « Dornik & X ». Un seul nom
    que la source n'a pas, et rien n'est proposé.
    """
    for whole in (" & ".join(found), ", ".join(found), found[0] if found else ""):
        if whole and _same_spelling(radio, whole):
            return respelling(radio, whole)
    names = {squash(name): name for name in found}
    changed = False
    out: list[str] = []
    for index, part in enumerate(_SEPARATORS.split(radio)):
        if index % 2 == 1:
            out.append(part)
            continue
        name = names.get(squash(part.replace("_", " ")))
        if name is None:
            return None
        fixed = respelling(part.strip(), name)
        if fixed:
            changed = True
        out.append(fixed if fixed is not None else part.strip())
    return re.sub(r"\s+", " ", "".join(out)).strip() if changed else None


def same_artist_name(radio_artist: str, name: str | None) -> bool:
    """Le nom d'un artiste rejoint par identifiant (ISRC, page Deezer) est-il l'un de
    ceux du fichier ?

    Une page d'artiste Deezer réunit parfois des homonymes (« Driver » pour le duo
    « Driver&Driver ») : son genre serait celui d'un autre. Le nom ne sert qu'à
    vérifier, jamais à chercher.
    """
    target = squash(name) if name else ""
    if not target:
        return False
    text = radio_artist.replace("_", " ")
    if squash(text) == target:
        return True
    names = split_artists(text)
    # Un seul nom après découpe (« Driver&Driver ») : c'est le nom entier qui compte.
    return len(names) > 1 and any(one.replace(" ", "") == target for one in names)


# ===== Les valeurs bidon =====

_PLACEHOLDER_ALBUM = re.compile(
    r"(?:title|no title|untitled|unknown|inconnu|sans titre|album|n/?a|none|[-?.]+)",
    re.IGNORECASE,
)


def placeholder_album(album: str) -> bool:
    """Un album rempli par défaut : vide, « title », « no title ».

    « |Anglais », « |Français », « |Aucune » ne sont pas des albums vides mais,
    semble-t-il, des marqueurs de langue : gardés, jamais remplacés.
    """
    text = album.strip()
    return not text or bool(_PLACEHOLDER_ALBUM.fullmatch(text))


def clean_isrc(text: str | None) -> str | None:
    """Un ISRC : 2 lettres de pays, 3 signes de déclarant, 2 chiffres d'année, 5
    chiffres ; tirets tolérés."""
    code = re.sub(r"[-\s]", "", text).upper() if text else ""
    return code if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}", code) else None


# ===== L'année =====

# Les mots d'un album qui n'est pas la sortie d'origine.
_REISSUE = js_regex(
    r"\b(?:remaster(?:ed|isee?)?|reissue|reedition|best of|greatest|hits|anthology"
    r"|anthologie|collection|essential|early years|selected|complete|integrale|deluxe"
    r"|anniversary|edition|compilation|vol|volume|years|sessions|rarities|archives?)\b"
)
_COMPILATION_OR_REISSUE = "année d'une compilation ou d'une réédition"
_EDITION_ONLY = "année de l'édition trouvée, peut-être une réédition"


def isrc_year(isrc: str | None) -> str | None:
    """L'année d'un ISRC (6e et 7e signes), celle où le code a été attribué.

    Avant 1986, l'année de naissance des ISRC, c'est l'année d'origine attribuée
    après coup (« USSM16601060 », Kicks, 1966).
    """
    code = clean_isrc(isrc)
    if not code:
        return None
    short = int(code[5:7])
    next_year = datetime.date.today().year % 100 + 1
    return str(2000 + short if short <= next_year else 1900 + short)


def _year_of(date: str | None) -> str | None:
    """L'année d'une date ISO, si elle est plausible (« 0000-00-00 » ne l'est pas)."""
    if not date or not re.match(r"[0-9]{4}", date):
        return None
    year = int(date[:4])
    this_year = datetime.date.today().year
    return str(year) if 1900 <= year <= this_year + 1 else None


@dataclass(frozen=True)
class YearInput:
    """Ce que les sources disent de l'année d'un titre."""

    # L'année du fichier, gardée s'il en a une : « » quand Beets a 0.
    radio: str
    # La date de l'édition trouvée (Deezer, Apple Music…), ISO 8601.
    edition: str | None = None
    edition_source: str | None = None
    album_title: str | None = None
    compilation: bool = False
    # MusicBrainz : la première sortie de l'enregistrement (par son ISRC), puis celle
    # de l'album chez l'artiste.
    recording: str | None = None
    album: str | None = None
    # L'ISRC du morceau trouvé : son année d'attribution.
    isrc: str | None = None


@dataclass(frozen=True)
class YearProposal:
    year: str | None = None
    source: str | None = None
    review: str | None = None


_YEAR_ORDER = {"musicbrainz": 0, "isrc": 1, "edition": 2}


def propose_year(facts: YearInput) -> YearProposal:  # noqa: PLR0911
    """La plus ancienne date connue, et si elle est à revoir.

    La date des plateformes est celle de l'édition trouvée : sur un échantillon de 40
    titres, fausse pour un sur trois (War, « The Cisco Kid » : 2015). Chaque date
    prouve que l'enregistrement existait déjà : la plus ancienne gagne, parmi
    MusicBrainz, un ISRC d'avant 1986 (l'année d'origine) et la date de l'édition. Un
    ISRC plus récent ne date pas le morceau, mais confirme l'édition : sortie l'année
    du code ou la suivante, c'est la sortie d'origine. Restent à revoir : une édition
    que rien ne confirme, une compilation, une réédition.
    """
    if re.fullmatch(r"[0-9]{4}", facts.radio.strip()):
        return YearProposal()
    edition = _year_of(facts.edition)
    code = isrc_year(facts.isrc)
    source = "plateforme" if facts.edition_source is None else facts.edition_source
    dates = [
        ("musicbrainz", _year_of(facts.recording), "MusicBrainz (première sortie)"),
        (
            "musicbrainz",
            _year_of(facts.album),
            "MusicBrainz (première sortie de l'album)",
        ),
        (
            "isrc",
            code if code and int(code) < 1986 else None,
            "ISRC (année d'origine du code)",
        ),
        ("edition", edition, f"{source} (date de l'édition trouvée)"),
    ]
    known = sorted(
        ((year, kind, why) for kind, year, why in dates if year),
        key=lambda date: (date[0], _YEAR_ORDER[date[1]]),
    )
    if not known:
        return YearProposal()
    year, kind, why = known[0]
    reissue = facts.compilation or bool(
        _REISSUE.search(normalize_text(facts.album_title or ""))
    )
    if kind == "musicbrainz":
        if reissue and year == edition:
            return YearProposal(year, why, _COMPILATION_OR_REISSUE)
        return YearProposal(year, why)
    if kind == "isrc":
        return YearProposal(year, why)
    if reissue:
        return YearProposal(year, why, _COMPILATION_OR_REISSUE)
    if code and int(code) <= int(year) <= int(code) + 1:
        return YearProposal(year, f"{why}, confirmée par l'ISRC")
    return YearProposal(year, why, _EDITION_ONLY)


# ===== Le genre musical =====


@dataclass(frozen=True)
class Family:
    """Une famille de genre.

    Son nom court s'écrit dans une requête Beets (`famille:jazz`), sans accent,
    espace ni virgule ; son nom en clair est pour la console.
    """

    name: str
    label: str
    words: re.Pattern[str]


# Les familles, de la plus précise à la plus large. Les genres des plateformes
# (Deezer en français, Apple Music et MusicBrainz en anglais) y entrent par
# mots-clés, normalisés. Aucun code de programmation d'une station : la
# correspondance avec ses catégories se lit dans la console, elle ne s'impose pas.
FAMILIES = (
    Family(
        "hip-hop",
        "Hip-hop",
        js_regex(r"\b(?:rap|hip ?hop|grime|trap|drill|turntablism)\b"),
    ),
    Family(
        "reggae-dub",
        "Reggae, dub",
        js_regex(
            r"\b(?:reggae|dub(?! techno)|dancehall|ragga|ska|rocksteady|lovers rock)\b"
        ),
    ),
    Family("jazz", "Jazz", js_regex(r"\b(?:jazz|bebop|bop|swing|big band)\b")),
    Family(
        "soul-funk",
        "Soul, funk",
        js_regex(r"\b(?:soul|funk|r and b|rnb|rhythm and blues|disco|gospel|boogie)\b"),
    ),
    Family(
        "monde",
        "Musiques du monde",
        js_regex(
            r"\b(?:world|worldwide|africa|african|africaine|afro|afrobeats?|highlife"
            r"|bresil|brazil|brazilian|bresilienne|mpb|latin|latino|latine|salsa"
            r"|cumbia|bossa nova|samba|boogaloo|arab|arabe|arabic|oriental|asia|asian"
            r"|asiatique|indian|indienne|bollywood|maghreb|rai|zouk|kompa|kizomba"
            r"|tropical|balkan|celtic|flamenco|tango|fado|reggaeton|ethio|mandingue"
            r"|sega|maloya|gnawa)\b"
        ),
    ),
    Family(
        "electro",
        "Électro",
        js_regex(
            r"\b(?:electro|electronic|electronique|electronica|techno|house|dance|edm"
            r"|dubstep|drum and bass|jungle|breakbeat|uk garage|2 step|ambient"
            r"|downtempo|trip hop|idm|chill ?out|bass music|synthwave|club)\b"
        ),
    ),
    Family(
        "chanson",
        "Chanson",
        js_regex(r"\b(?:chanson|chansons|variete francaise|french pop)\b"),
    ),
    Family(
        "rock",
        "Rock",
        js_regex(
            r"\b(?:rock|punk|garage|psych|psychedelic|psychedelique|metal|grunge"
            r"|alternative|alternatif|post punk|new wave|shoegaze|stoner|surf)\b"
        ),
    ),
    Family("blues", "Blues", js_regex(r"\bblues\b")),
    Family(
        "folk-country",
        "Folk, country",
        js_regex(r"\b(?:folk|country|americana|bluegrass)\b"),
    ),
    Family(
        "pop",
        "Pop",
        js_regex(r"\b(?:pop|variete|variete internationale|singer|songwriter)\b"),
    ),
    Family(
        "film",
        "Musique de film",
        js_regex(
            r"\b(?:film|films|soundtrack|soundtracks|bande originale|bandes originales"
            r"|jeux video|video game)\b"
        ),
    ),
    Family(
        "classique",
        "Classique",
        js_regex(r"\b(?:classique|classical|opera|baroque)\b"),
    ),
    Family(
        "experimental",
        "Expérimental",
        js_regex(
            r"\b(?:experimental|experimentale|noise|avant garde|musique concrete)\b"
        ),
    ),
)


def genre_family(genres: Iterable[str]) -> Family | None:
    """La famille du premier genre qui en a une : une plateforme donne le genre
    principal d'abord."""
    for genre in genres:
        text = normalize_text(genre)
        for family in FAMILIES:
            if family.words.search(text):
                return family
    return None


# ===== Femme ou minorité de genre =====

# Le genre déclaré : « F » femme, « H » homme, « MG » minorité de genre (non binaire,
# trans, genderqueer…).
MUSICBRAINZ_GENDERS = {"Female": "F", "Male": "H", "Non-binary": "MG", "Other": "MG"}

# Wikidata, propriété P21 : seules les valeurs connues comptent ; une autre reste
# inconnue, jamais « homme ».
WIKIDATA_GENDERS = {
    "Q6581072": "F",  # femme
    "Q1052281": "F",  # femme trans
    "Q15145779": "F",  # femme cisgenre
    "Q6581097": "H",  # homme
    "Q15145778": "H",  # homme cisgenre
    "Q2449503": "MG",  # homme trans
    "Q48270": "MG",  # non binaire
    "Q12964198": "MG",  # genderqueer
    "Q18116794": "MG",  # genre fluide
    "Q505371": "MG",  # agenre
    "Q1097630": "MG",  # intersexe
    "Q27679766": "MG",  # transmasculin
    "Q27679684": "MG",  # transféminin
    "Q859614": "MG",  # bigenre
    "Q301702": "MG",  # bispirituel
    "Q1289754": "MG",  # neutrois
    "Q96000630": "MG",  # genre X
}


@dataclass(frozen=True)
class Period:
    """Une période dans un groupe, en années ; une borne inconnue reste ouverte."""

    begin: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class Member:
    """Un membre de groupe : son genre déclaré s'il l'est, et ses périodes."""

    gender: str | None = None
    periods: tuple[Period, ...] | None = None


@dataclass(frozen=True)
class Person:
    """Une personne : son genre déclaré, par source."""

    musicbrainz: str | None = None
    wikidata: str | None = None


@dataclass(frozen=True)
class Members:
    """Les membres d'un groupe, d'une source ; `year` : l'année du disque, si elle
    est sûre."""

    source: str
    members: tuple[Member, ...]
    year: int | None = None


@dataclass(frozen=True)
class ArtistFacts:
    """Ce que les sources déclarent de l'artiste principal : une personne, ou un
    groupe et ses membres. Rien ne s'en garde : seulement le verdict."""

    person: Person | None = None
    members: Members | None = None


@dataclass(frozen=True)
class FmgVerdict:
    verdict: str  # « oui », « mixte », « non » ou « à vérifier »
    source: str | None = None


class _Dated(Protocol):
    @property
    def periods(self) -> Sequence[Period] | None: ...


def present_in(member: _Dated, year: int) -> bool:
    """Dans le groupe cette année-là ? Un membre sans dates est là tout du long."""
    return not member.periods or any(
        (period.begin is None or period.begin <= year)
        and (period.end is None or year <= period.end)
        for period in member.periods
    )


def _dated(member: Member) -> bool:
    return any(
        period.begin is not None or period.end is not None
        for period in member.periods or ()
    )


def _lineups(members: Sequence[Member]) -> list[list[Member]]:
    """Les formations successives d'un groupe : une par arrivée ou départ daté, plus
    celle d'avant la première date."""
    years: list[int] = []
    for member in members:
        for period in member.periods or ():
            if period.begin is not None and period.begin not in years:
                years.append(period.begin)
            if period.end is not None and period.end + 1 not in years:
                years.append(period.end + 1)
    if years and min(years) - 1 not in years:
        years.append(min(years) - 1)
    lineups = (
        [member for member in members if present_in(member, year)] for year in years
    )
    return [lineup for lineup in lineups if lineup]


def _majority(fmg: int, others: int) -> str:
    total = fmg + others
    return "oui" if fmg * 2 > total else "mixte" if fmg * 2 == total else "non"


def _judge(lineup: Sequence[Member]) -> tuple[str, int]:
    """Une formation : la majorité de ses membres connus, si les inconnus n'y
    changeraient rien. Rend le verdict et le nombre de membres connus."""
    fmg = sum(member.gender in ("F", "MG") for member in lineup)
    men = sum(member.gender == "H" for member in lineup)
    unknown = len(lineup) - fmg - men
    if not fmg and not men:
        return "à vérifier", 0
    best = _majority(fmg + unknown, men)
    worst = _majority(fmg, men + unknown)
    return (best if best == worst else "à vérifier"), fmg + men


def _known_of(known: int, total: int) -> str:
    members = "membres connus" if known > 1 else "membre connu"
    return f"{known} {members} sur {total}"


def fmg_verdict(facts: ArtistFacts) -> FmgVerdict:  # noqa: PLR0911
    """« Oui » : une femme ou une personne d'une minorité de genre, ou un groupe qui en
    compte plus de la moitié de ses membres connus ; « mixte » à égalité.

    Un groupe dont des membres manquent n'a de verdict que si les manquants n'y
    changeraient rien. Il se juge sur sa formation de l'année du disque : les Pixies
    de « Debaser » (1989) ont une bassiste et trois hommes, pas les quatre bassistes
    qui se sont succédé. Sans année sûre, chaque formation doit dire la même chose.
    """
    person = facts.person or Person()
    if person.musicbrainz or person.wikidata:
        if (
            person.musicbrainz
            and person.wikidata
            and person.musicbrainz != person.wikidata
        ):
            return FmgVerdict(
                "à vérifier", "MusicBrainz et Wikidata ne disent pas la même chose"
            )
        gender = person.musicbrainz or person.wikidata
        if person.musicbrainz and person.wikidata:
            source = "MusicBrainz et Wikidata"
        else:
            source = "MusicBrainz" if person.musicbrainz else "Wikidata"
        return FmgVerdict("non" if gender == "H" else "oui", source)
    if facts.members is None:
        return FmgVerdict("à vérifier")
    source, members, year = (
        facts.members.source,
        facts.members.members,
        facts.members.year,
    )

    def single(lineup: Sequence[Member], when: str = "") -> FmgVerdict:
        verdict, known = _judge(lineup)
        if not known:
            return FmgVerdict(verdict)
        return FmgVerdict(verdict, f"{source} : {_known_of(known, len(lineup))}{when}")

    if not any(map(_dated, members)):
        return single(members)
    at_year = []
    if year is not None:
        at_year = [member for member in members if present_in(member, year)]
    if at_year:
        return single(at_year, f" en {year}")
    judged = [_judge(lineup) for lineup in _lineups(members)]
    if not judged:
        return single(members)
    verdicts = {verdict for verdict, _ in judged}
    if len(verdicts) > 1:
        return FmgVerdict(
            "à vérifier", f"{source} : la formation a changé, sans année sûre du disque"
        )
    (only,) = verdicts
    if only != "à vérifier":
        return FmgVerdict(only, f"{source} : le même pour chaque formation")
    if any(known for _, known in judged):
        return FmgVerdict("à vérifier", f"{source} : trop de membres inconnus")
    return FmgVerdict("à vérifier")
