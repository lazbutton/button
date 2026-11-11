"""Les propositions d'un titre, champ par champ, avec leur niveau et pourquoi.

Le `buildRow` de `report.ts`, dans Hopper : d'un titre, ses champs dans Beets et la
durée de son fichier, et de ce que les sources en ont dit, ce qu'on propose. Un champ
faux est pire qu'un champ vide : rien ne remplace une valeur du fichier, sauf sa
graphie ou une valeur bidon.

- Titre et artiste : la graphie trouvée ; le texte du morceau trouvé quand la
  variante cherchée a nettoyé celui du fichier (« Vaudou Game / Grasse Mat »).
  Pour un titre rapproché par la seconde ou la troisième passe : la faute corrigée à
  la manière du fichier, ses mentions de fin gardées sans ses notes techniques,
  l'artiste et le titre remis à leur place, des accents réparés sans lettre
  improbable, et rien d'après SoundCloud.
- Album : seulement vide ou bidon (« title », « no title »), sinon sa graphie.
- Année : seulement vide, 0 dans `year`, à revoir quand rien ne confirme l'édition.
- Label et ISRC : seulement vides, ou un ISRC mal formé.
- La famille de genre, et le verdict « femme ou minorité de genre », au niveau du
  titre : un artiste mal reconnu donnerait un verdict faux.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from radiotomate.fiches.loose import CLEANED
from radiotomate.fiches.normalize import js_regex, normalize_text, parse_title, squash
from radiotomate.fiches.rules import (
    MUSICBRAINZ_GENDERS,
    WIKIDATA_GENDERS,
    ArtistFacts,
    Member,
    Members,
    Period,
    Person,
    YearInput,
    calmed,
    clean_isrc,
    duration_level,
    exotic_letters,
    fmg_verdict,
    genre_family,
    placeholder_album,
    plain_punctuation,
    present_in,
    propose_year,
    respell_artists,
    respelling,
    retyped,
    same_artist_name,
    split_tail,
    without_edition_mentions,
    without_foreign_mentions,
)
from radiotomate.fiches.third import SWAPPED

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from radiotomate.fiches.rules import Family


# ===== Ce que Beets sait d'un titre =====


@dataclass(frozen=True)
class Track:
    """Les champs d'un titre dans Beets, et la durée de son fichier."""

    title: str = ""
    artist: str = ""
    album: str = ""
    # 0 : pas d'année, comme dans Beets.
    year: int = 0
    label: str = ""
    isrc: str = ""
    # La durée du fichier, en secondes : `length` dans Beets.
    length: float | None = None
    # Les champs flexibles des fiches, s'ils sont déjà posés.
    famille: str = ""
    fmg: str = ""


# ===== Ce que les sources en ont dit =====
# Ces preuves sont réduites aux champs utiles. Le genre d'une personne et les membres
# d'un groupe ne servent qu'au verdict : ils ne se gardent pas avec elles.


@dataclass(frozen=True)
class Match:
    """Le morceau trouvé pour un titre."""

    # Où il a été trouvé (« deezer », « deezer (sorties de l'artiste) »), et la
    # plateforme de son lien.
    source: str
    platform: str
    id: str
    url: str
    title: str
    artists: tuple[str, ...]
    album: str | None = None
    duration_s: float | None = None
    isrc: str | None = None
    artist_id: str | None = None
    # Ce que la variante cherchée a fait du texte du fichier (`RadioVariant.why`) ;
    # pour un titre rapproché, pourquoi la passe l'a pris (`Found.why`).
    why: tuple[str, ...] = ()
    # Les artistes du fichier que le morceau a, tels que la variante les lit.
    credited: str | None = None
    # La date de sortie lue chez une plateforme qui n'a pas d'album à part, ou la
    # première sortie d'un enregistrement rapproché dans MusicBrainz.
    date: str | None = None
    # Un enregistrement rapproché dans MusicBrainz que seules des compilations
    # contiennent : sa date est la leur.
    compilation: bool = False


@dataclass(frozen=True)
class DeezerAlbum:
    id: str
    title: str
    label: str | None = None
    date: str | None = None
    record_type: str | None = None
    genres: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeezerDetails:
    """Le morceau Deezer, par son identifiant ou son ISRC, et son album."""

    track_id: str
    title: str
    duration_s: float | None = None
    isrc: str | None = None
    artist_id: str | None = None
    artist_name: str | None = None
    album: DeezerAlbum | None = None


@dataclass(frozen=True)
class AppleDetails:
    genre: str | None = None
    date: str | None = None
    album: str | None = None


@dataclass(frozen=True)
class MusicBrainzMember:
    id: str
    name: str
    gender: str | None = None
    periods: tuple[Period, ...] | None = None


@dataclass(frozen=True)
class MusicBrainzArtist:
    id: str
    name: str
    type: str | None = None
    gender: str | None = None
    # Les genres votés, du plus cité au moins cité.
    genres: tuple[str, ...] = ()
    members: tuple[MusicBrainzMember, ...] = ()


@dataclass(frozen=True)
class MusicBrainzDetails:
    """La première sortie de l'enregistrement, par son ISRC, celle de l'album, et
    l'artiste, par le crédit ou par sa page Deezer."""

    recording_date: str | None = None
    album_date: str | None = None
    artist: MusicBrainzArtist | None = None


@dataclass(frozen=True)
class Details:
    deezer: DeezerDetails | None = None
    apple: AppleDetails | None = None
    musicbrainz: MusicBrainzDetails | None = None


@dataclass(frozen=True)
class WikidataArtist:
    """Un artiste de Wikidata, par son identifiant Deezer ou MusicBrainz.

    `names` : ses libellés, pour vérifier que c'est bien l'artiste du fichier.
    `members` : les valeurs de P21 de chaque membre, par membre.
    """

    item: str
    names: tuple[str, ...] = ()
    human: bool = False
    genders: tuple[str, ...] = ()
    members: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    """Où en est la recherche d'un titre : « trouvé », « rapproché », « rien »,
    « écarté » ou « erreur »."""

    status: str
    match: Match | None = None
    details: Details | None = None
    error: str | None = None


# ===== Le verdict, d'après MusicBrainz et Wikidata =====


def _one_gender(values: Iterable[str | None], table: Mapping[str, str]) -> str | None:
    """Plusieurs valeurs déclarées : un genre seulement si elles disent toutes la même
    chose."""
    genders = {table.get(value) if value else None for value in values}
    return genders.pop() if len(genders) == 1 else None


def artist_facts(
    musicbrainz: MusicBrainzArtist | None,
    wikidata: WikidataArtist | None,
    year: int | None = None,
) -> ArtistFacts:
    """Ce que MusicBrainz et Wikidata déclarent de l'artiste principal.

    Une personne et son genre, ou un groupe et ses membres : MusicBrainz d'abord,
    avec leurs dates, Wikidata si MusicBrainz n'en connaît aucun genre. `year` :
    l'année du disque, quand elle est sûre.
    """
    mb_person = musicbrainz is not None and musicbrainz.type == "Person"
    person = Person(
        musicbrainz=(
            MUSICBRAINZ_GENDERS.get(musicbrainz.gender)
            if mb_person and musicbrainz and musicbrainz.gender
            else None
        ),
        wikidata=(
            _one_gender(wikidata.genders, WIKIDATA_GENDERS)
            if wikidata and wikidata.human
            else None
        ),
    )
    if person.musicbrainz or person.wikidata:
        return ArtistFacts(person=person)
    if mb_person or (wikidata and wikidata.human):
        return ArtistFacts()
    mb_members = musicbrainz.members if musicbrainz else ()
    if any(member.gender in MUSICBRAINZ_GENDERS for member in mb_members):
        members = tuple(
            Member(MUSICBRAINZ_GENDERS.get(member.gender or ""), member.periods)
            for member in mb_members
        )
        return ArtistFacts(members=Members("MusicBrainz", members, year))
    wd_members = list(wikidata.members.values()) if wikidata else []
    if any(_one_gender(genders, WIKIDATA_GENDERS) for genders in wd_members):
        known = [
            Member(_one_gender(genders, WIKIDATA_GENDERS)) for genders in wd_members
        ]
        # MusicBrainz en compte plus, sans leur genre : ceux qui manquent à Wikidata
        # sont des inconnus. Au Pairs, deux femmes et deux hommes, n'a que trois
        # membres chez Wikidata.
        expected = sum(
            year is None or present_in(member, year) for member in mb_members
        )
        known += [Member()] * (expected - len(known))
        return ArtistFacts(members=Members("Wikidata", tuple(known)))
    return ArtistFacts()


# ===== La rangée d'un titre =====

SOURCES = {
    "deezer": "Deezer",
    "tidal": "Tidal",
    "apple": "Apple Music",
    "bandcamp": "Bandcamp",
    "deezer (sorties de l'artiste)": "Deezer (sorties de l'artiste)",
}
PLATFORMS = {
    "deezer": "Deezer",
    "tidal": "Tidal",
    "apple": "Apple Music",
    "bandcamp": "Bandcamp",
    "soundcloud": "SoundCloud",
    "musicbrainz": "MusicBrainz",
}


@dataclass
class Row:
    """Ce qu'on propose pour un titre, et d'après quoi.

    Ses champs reprennent ceux du titre, changés là où une proposition les change.
    """

    track: Track
    level: str
    reasons: list[str]
    title: str
    artist: str
    album: str
    year: int
    label: str
    isrc: str
    family: Family | None = None
    # Les genres trouvés, et d'où : « Deezer : R&B, Soul & Funk ».
    genres: str = ""
    verdict: str = ""
    verdict_source: str = ""
    found_at: str = ""
    # La plateforme du lien, pour « Écouter sur Deezer ».
    platform: str = ""
    url: str = ""
    found_title: str = ""
    found_album: str = ""
    found_artists: str = ""
    year_source: str = ""
    found_duration: float | None = None
    # Pourquoi l'année est à revoir, si elle l'est.
    year_review: str = ""


def _first(*values: Any) -> Any:
    """La première valeur connue, comme `??` en JavaScript."""
    return next((value for value in values if value is not None), None)


def _row(track: Track, level: str, reasons: list[str]) -> Row:
    return Row(
        track=track,
        level=level,
        reasons=reasons,
        title=track.title,
        artist=track.artist,
        album=track.album,
        year=track.year,
        label=track.label,
        isrc=track.isrc,
    )


# ===== Un titre rapproché =====

# Des notes techniques du fichier, à ne pas reporter : « (16bit44.1kHz) », « [Phat
# Mastered] », « (KOM314) ».
_JUNK = js_regex(
    r"\b(?:[0-9]+\s*bit|[0-9]+(?:[.,][0-9]+)?\s*khz|kbps|mp3|wav|aiff|flac"
    r"|master(?:ed|ing)?|final)\b|^[(\[]\s*[a-z]{2,6}\s?-?[0-9]{2,5}\s*[)\]]\Z",
    re.IGNORECASE,
)


def _words_in(text: str) -> list[str]:
    return [word for word in normalize_text(text).split(" ") if word]


def _covered(tail: str, by: str) -> bool:
    known = _words_in(by)
    return all(word in known for word in _words_in(tail))


def fixed_title(radio: str, found: str, artists: Sequence[str] = ()) -> str:
    """Le titre d'un rapproché corrigé : une faute, une coupe, des mots, un numéro, des
    accents perdus.

    La base trouvée, écrite à la manière du fichier, et les mentions de fin. Celles du
    fichier restent, sans ses notes techniques (« Auditiorium Ft. Slick Rick » →
    « Auditorium Ft. Slick Rick ») ; celles trouvées, si le fichier les écrit ailleurs
    (« Vancouver and Fairfield remix (2004) » → « Vancouver and Fairfield (remix)
    (2004) »). Les mêmes mots, à la ponctuation près, ne changent rien (« Shake Your
    Body (Down to the Ground) »).
    """
    radio_base, radio_tail = split_tail(radio)
    # Un numéro de piste et le nom de l'artiste dans le titre trouvé (« 05 Dj Veekash
    # Patrona De Los Reclusos »), que le fichier n'a pas.
    trimmed = found
    if re.match(r"[0-9]{2}\s", found) and not re.match(r"[0-9]", radio_base):
        trimmed = re.sub(r"^[0-9]{2}\s+", "", found, count=1)
    for name in artists:
        count = len(re.split(r"\s+", name.strip()))
        head = " ".join(re.split(r"\s+", trimmed)[:count])
        if (
            squash(name)
            and squash(head) == squash(name)
            and not squash(radio_base).startswith(squash(name))
        ):
            rest = " ".join(re.split(r"\s+", trimmed)[count:])
            trimmed = re.sub(r"^[-\u2013\u2014:]\s*", "", rest, count=1)
    if squash(radio) == squash(trimmed):
        return radio
    found_base, found_tail = split_tail(trimmed)
    base = retyped(radio_base or radio, found_base or found, sentence=True)
    mine = ""
    if radio_tail and not _JUNK.search(radio_tail) and not _covered(radio_tail, base):
        mine = calmed(radio_tail)
    theirs = ""
    if found_tail and not _covered(found_tail, f"{base} {mine}"):
        theirs = retyped(radio, found_tail, sentence=True, inside=True)
    return " ".join(part for part in (base, theirs, mine) if part)


def _swapped_fields(track: Track, match: Match) -> bool:
    """L'artiste et le titre inversés dans le fichier : le titre trouvé est dans son
    artiste, pas dans son titre."""
    title = parse_title(match.title).base.replace(" ", "")
    return (
        len(title) >= 4
        and title in squash(track.artist)
        and title not in squash(track.title)
    )


# Ce qui corrige le titre d'un rapproché : une faute, une coupe, des mots, un numéro
# de piste, des accents perdus à l'import.
_TITLE_FIXES = frozenset(
    {
        "titre à une faute près",
        "titre coupé",
        "mots en plus ou en moins",
        CLEANED,
        "titre aux accents perdus",
        "numéro de piste collé",
        "chiffre en trop",
    }
)
# Ce que le fichier écrit lui-même, et que la passe a mis de côté pour chercher.
_RADIO_NOTES = frozenset(
    {
        "annotation entre crochets retirée",
        "version hors parenthèses",
        "parenthèse coupée retirée",
    }
)
_ARTIST_FIXES = frozenset({"artiste à une faute près", "artiste aux accents perdus"})


def _close_title_and_artist(track: Track, match: Match) -> tuple[str, str]:
    """Le titre et l'artiste proposés pour un titre rapproché.

    Une faute de frappe du fichier se corrige, à sa manière d'écrire et sans les
    mentions qu'il n'a pas ; un crédit plus long ne remplace pas le sien ; SoundCloud,
    où chaque compte écrit ce qu'il veut, ne propose rien.
    """
    trusted = match.platform != "soundcloud"
    # Une faute, une coupe, des mots, un numéro de piste, des accents perdus à
    # l'import ; pas une annotation du fichier (« ['Lyrics to Go'] »), ni une version
    # qu'il écrit hors parenthèses.
    reasons = [part for why in match.why for part in why.split(", ")]
    radio_notes = any(why in _RADIO_NOTES for why in reasons)
    fix_title = (
        trusted and not radio_notes and any(why in _TITLE_FIXES for why in reasons)
    )
    fix_artist = trusted and any(why in _ARTIST_FIXES for why in reasons)
    # L'artiste et le titre inversés dans le fichier (« TI_FI_LA_OU_TE_MADAM »,
    # de « ANZALA_DOLOR_VELO ») : chacun reprend sa place.
    swapped = trusted and (SWAPPED in reasons or _swapped_fields(track, match))
    radio_title = track.artist if swapped else track.title
    radio_artist = track.title if swapped else track.artist
    title = without_foreign_mentions(match.title, radio_title)
    fixed = fixed_title(radio_title, title, [*match.artists, radio_artist])
    fixed_artist = retyped(radio_artist, ", ".join(match.artists))
    # Des accents perdus réparés, mais pas avec des lettres improbables (« Nehḗz »
    # dans MusicBrainz pour « Nehéz »).
    lost_accents = any(why.endswith("aux accents perdus") for why in reasons)

    def odd(proposal: str, radio: str) -> bool:
        return lost_accents and exotic_letters(proposal) and not exotic_letters(radio)

    respelled = respelling(radio_title, title, sentence=True) if trusted else None
    if respelled:
        new_title = respelled
    elif (fix_title or swapped) and not odd(fixed, radio_title):
        new_title = fixed
    else:
        new_title = radio_title
    if swapped:
        return new_title, fixed_artist
    respelled = respell_artists(track.artist, match.artists) if trusted else None
    if respelled:
        return new_title, respelled
    if fix_artist and not odd(fixed_artist, track.artist):
        return new_title, fixed_artist
    return new_title, track.artist


def build_row(  # noqa: PLR0912, PLR0915
    track: Track,
    result: SearchResult | None,
    wikidata: Mapping[str, WikidataArtist],
) -> Row:
    """Ce qu'on propose pour un titre, d'après sa recherche."""
    if result is None:
        return _row(track, "pas encore cherché", [])
    if result.status == "écarté":
        return _row(track, "écarté", ["sans artiste ou annonce"])
    if result.status == "rien":
        return _row(track, "introuvable", [])
    if result.status == "erreur" or result.match is None:
        return _row(track, "erreur", [result.error or "erreur"])

    match = result.match
    close = result.status == "rapproché"
    details = result.details or Details()
    deezer, apple, musicbrainz = details.deezer, details.apple, details.musicbrainz
    deezer_album = deezer.album if deezer else None
    deezer_seconds = deezer.duration_s if deezer else None
    if close:
        # La durée du morceau rapproché, qui l'a confirmé : Deezer, rejoint par l'ISRC,
        # a parfois une autre édition.
        found_seconds = _first(match.duration_s, deezer_seconds)
        row = _row(track, "rapproché", [f"rapproché : {', '.join(match.why)}"])
        row.found_at = PLATFORMS.get(match.platform, match.platform)
    else:
        found_seconds = _first(deezer_seconds, match.duration_s)
        checked = duration_level(track.length, found_seconds)
        row = _row(track, checked.level, [checked.why] if checked.why else [])
        row.found_at = SOURCES.get(match.source, match.source)
    if match.source == "tidal" and match.platform == "deezer":
        row.found_at = "Tidal, puis Deezer par l'ISRC"
    row.platform = PLATFORMS.get(match.platform, match.platform)
    row.url = match.url
    row.found_title = match.title
    album_title = _first(
        deezer_album.title if deezer_album else None,
        apple.album if apple else None,
        match.album,
    )
    row.found_album = album_title or ""
    row.found_artists = ", ".join(match.artists)
    row.found_duration = found_seconds or None

    if close:
        row.title, row.artist = _close_title_and_artist(track, match)
    else:
        # La variante cherchée a nettoyé le texte du fichier (« Vaudou Game / Grasse
        # Mat », « 02 - LAST DRINK », l'artiste et le titre inversés) : le morceau
        # trouvé a le titre à la lettre près, le sien est le bon.
        cleaned_title = any(
            why not in ("soulignés", "premier artiste cherché") for why in match.why
        )
        artist_in_title = any(
            why in ("artiste lu dans le titre", "artiste et titre inversés")
            for why in match.why
        )
        title = without_edition_mentions(match.title)
        row.title = _first(
            respelling(track.title, title, sentence=True),
            plain_punctuation(title) if cleaned_title else track.title,
        )
        row.artist = _first(
            respell_artists(track.artist, match.artists),
            plain_punctuation(", ".join(match.artists))
            if artist_in_title
            else track.artist,
        )
    if album_title:
        if placeholder_album(track.album):
            row.album = plain_punctuation(without_edition_mentions(album_title))
        else:
            row.album = _first(
                respelling(track.album, album_title, sentence=True), track.album
            )

    if deezer_album and deezer_album.date:
        edition_source = "Deezer"
    elif apple and apple.date:
        edition_source = "Apple Music"
    else:
        edition_source = PLATFORMS.get(match.platform)
    # Un enregistrement rapproché dans MusicBrainz que seules des compilations
    # contiennent : sa date est celle d'une compilation (« Get Carter » de Roy Budd,
    # 1971, daté 1995 par « The Sound Spectrum »), à relire.
    compiled = close and match.platform == "musicbrainz" and match.compilation
    year = propose_year(
        YearInput(
            radio=str(track.year) if track.year else "",
            edition=_first(
                deezer_album.date if deezer_album else None,
                apple.date if apple else None,
                match.date
                if match.platform in ("bandcamp", "tidal") or compiled
                else None,
            ),
            edition_source=edition_source,
            album_title=album_title,
            compilation=bool(deezer_album and deezer_album.record_type == "compile")
            or compiled,
            recording=None
            if compiled
            else (musicbrainz.recording_date if musicbrainz else None),
            album=musicbrainz.album_date if musicbrainz else None,
            isrc=_first(match.isrc, deezer.isrc if deezer else None),
        )
    )
    if year.year:
        row.year = int(year.year)
        row.year_source = year.source or ""
        if year.review:
            row.reasons.append(year.review)
            row.year_review = year.review
    if not track.label.strip() and deezer_album and deezer_album.label:
        row.label = deezer_album.label
    isrc = clean_isrc(_first(match.isrc, deezer.isrc if deezer else None))
    if not clean_isrc(track.isrc) and isrc:
        row.isrc = isrc

    genres: tuple[str, ...] = ()
    genre_source = ""
    if deezer_album and deezer_album.genres:
        genres, genre_source = deezer_album.genres, "Deezer"
    elif apple and apple.genre:
        genres, genre_source = (apple.genre,), "Apple Music"
    elif musicbrainz and musicbrainz.artist and musicbrainz.artist.genres:
        genres, genre_source = musicbrainz.artist.genres[:4], "MusicBrainz"
    if genres:
        row.genres = f"{genre_source} : {', '.join(genres)}"
        row.family = genre_family(genres)

    # MusicBrainz a déjà vérifié le nom de son artiste. Wikidata par sa fiche
    # MusicBrainz, sinon par la page Deezer, si l'un de ses libellés est l'artiste du
    # fichier.
    mb_artist = musicbrainz.artist if musicbrainz else None
    deezer_artist = _first(
        deezer.artist_id if deezer else None,
        match.artist_id if match.platform == "deezer" else None,
    )
    by_deezer = wikidata.get(deezer_artist) if deezer_artist else None
    credited = _first(match.credited, track.artist)
    if mb_artist and wikidata.get(mb_artist.id):
        wd = wikidata[mb_artist.id]
    elif by_deezer and any(
        same_artist_name(credited, name) for name in by_deezer.names
    ):
        wd = by_deezer
    else:
        wd = None
    # Un groupe se juge sur sa formation de l'année du disque, si cette année est sûre.
    recorded = row.year if not row.year_review and 1000 <= row.year <= 9999 else None
    verdict = fmg_verdict(artist_facts(mb_artist, wd, recorded))
    row.verdict = verdict.verdict
    row.verdict_source = verdict.source or ""
    return row


# ===== Les propositions =====

# Les champs qu'une rangée propose de changer, dans l'ordre du fichier.
FIELDS = ("title", "artist", "album", "year", "label", "isrc")


def changes(row: Row) -> list[str]:
    """Les champs que la rangée change."""
    return [key for key in FIELDS if getattr(row, key) != getattr(row.track, key)]


@dataclass(frozen=True)
class Proposal:
    """Un champ proposé : la valeur d'avant, la valeur proposée, son niveau,
    pourquoi, et d'où elle vient."""

    key: str
    before: str | int
    value: str | int
    level: str
    why: str = ""
    source: str = ""


def proposals(row: Row) -> list[Proposal]:
    """Les propositions d'un titre, champ par champ.

    Chacune prend le niveau du titre, sauf une année douteuse : à revoir. La famille
    et le verdict aussi : un artiste mal reconnu donnerait un verdict faux. « À
    vérifier » ne se propose pas.
    """
    out = [
        Proposal(
            key,
            getattr(row.track, key),
            getattr(row, key),
            "à revoir" if key == "year" and row.year_review else row.level,
            row.year_review if key == "year" else "",
            row.year_source if key == "year" else row.found_at,
        )
        for key in changes(row)
    ]
    if row.family and row.family.name != row.track.famille:
        out.append(
            Proposal(
                "famille",
                row.track.famille,
                row.family.name,
                row.level,
                source=row.genres,
            )
        )
    if row.verdict in ("oui", "mixte", "non") and row.verdict != row.track.fmg:
        out.append(
            Proposal(
                "fmg", row.track.fmg, row.verdict, row.level, source=row.verdict_source
            )
        )
    return out
