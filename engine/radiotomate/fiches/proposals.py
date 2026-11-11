"""Les propositions d'un titre, champ par champ, avec leur niveau et pourquoi.

Le `buildRow` de `report.ts`, dans Hopper, pour un titre trouvé à la lettre près :
d'un titre, ses champs dans Beets et la durée de son fichier, et de ce que les
sources en ont dit, ce qu'on propose. Un champ faux est pire qu'un champ vide : rien
ne remplace une valeur du fichier, sauf sa graphie ou une valeur bidon.

- Titre et artiste : la graphie trouvée ; le texte du morceau trouvé quand la
  variante cherchée a nettoyé celui du fichier (« Vaudou Game / Grasse Mat »).
- Album : seulement vide ou bidon (« title », « no title »), sinon sa graphie.
- Année : seulement vide, 0 dans `year`, à revoir quand rien ne confirme l'édition.
- Label et ISRC : seulement vides, ou un ISRC mal formé.
- La famille de genre, et le verdict « femme ou minorité de genre », au niveau du
  titre : un artiste mal reconnu donnerait un verdict faux.

Le titre rapproché par la seconde ou la troisième passe viendra avec FON-23.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from radiotomate.fiches.rules import (
    MUSICBRAINZ_GENDERS,
    WIKIDATA_GENDERS,
    ArtistFacts,
    Member,
    Members,
    Period,
    Person,
    YearInput,
    clean_isrc,
    duration_level,
    fmg_verdict,
    genre_family,
    placeholder_album,
    plain_punctuation,
    present_in,
    propose_year,
    respell_artists,
    respelling,
    same_artist_name,
    without_edition_mentions,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

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
    # Ce que la variante cherchée a fait du texte du fichier (`RadioVariant.why`).
    why: tuple[str, ...] = ()
    # Les artistes du fichier que le morceau a, tels que la variante les lit.
    credited: str | None = None
    # La date de sortie lue chez une plateforme qui n'a pas d'album à part.
    date: str | None = None


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
    if result.status == "rapproché":
        msg = "un titre rapproché viendra avec la seconde passe (FON-23)"
        raise NotImplementedError(msg)

    match = result.match
    details = result.details or Details()
    deezer, apple, musicbrainz = details.deezer, details.apple, details.musicbrainz
    deezer_album = deezer.album if deezer else None
    found_seconds = _first(deezer.duration_s if deezer else None, match.duration_s)
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

    # La variante cherchée a nettoyé le texte du fichier (« Vaudou Game / Grasse
    # Mat », « 02 - LAST DRINK », l'artiste et le titre inversés) : le morceau trouvé
    # a le titre à la lettre près, le sien est le bon.
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
    year = propose_year(
        YearInput(
            radio=str(track.year) if track.year else "",
            edition=_first(
                deezer_album.date if deezer_album else None,
                apple.date if apple else None,
                match.date if match.platform in ("bandcamp", "tidal") else None,
            ),
            edition_source=edition_source,
            album_title=album_title,
            compilation=bool(deezer_album and deezer_album.record_type == "compile"),
            recording=musicbrainz.recording_date if musicbrainz else None,
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
