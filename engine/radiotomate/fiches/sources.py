"""Ce que les sources disent d'un morceau : Deezer, MusicBrainz, Wikidata, AcoustID.

Le `sources.ts` de Hopper, et ce dont sa recherche se sert dans l'adaptateur Deezer
du site (`lib/adapters/deezer.ts`) et dans `loose.ts` et `third.ts`. Chaque réponse
est réduite aux champs utiles. Un détail se demande toujours par un identifiant,
jamais par un nom : l'ISRC, l'identifiant Deezer de l'artiste ou celui de
MusicBrainz. Deux artistes peuvent porter le même nom ; un genre attribué au mauvais
serait pire qu'aucun.

Les requêtes sur les personnes, les membres d'un groupe et leur genre déclaré, ne
partent que verdict allumé (`verdict`). Éteint, la fiche d'un artiste ne garde même
pas le genre qu'elle déclare.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import parse_qsl, quote, urlsplit

from radiotomate.fiches.covers import apple_cover, bandcamp_cover, deezer_cover
from radiotomate.fiches.http import HttpError
from radiotomate.fiches.loose import MbRelease
from radiotomate.fiches.normalize import (
    js_regex,
    js_trim,
    latin_words,
    normalize_text,
    parse_title,
    search_terms,
    split_artists,
)
from radiotomate.fiches.proposals import (
    AppleDetails,
    DeezerAlbum,
    DeezerDetails,
    MusicBrainzArtist,
    MusicBrainzDetails,
    MusicBrainzMember,
    WikidataArtist,
)
from radiotomate.fiches.rules import (
    Period,
    js_round,
    present_in,
    without_edition_mentions,
)
from radiotomate.fiches.variants import same_artist, token_set_similarity

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence

    from radiotomate.fiches.http import Http

_log = logging.getLogger(__name__)


def component(text: str) -> str:
    """Le `encodeURIComponent` de JavaScript : tout sauf les lettres et chiffres
    ASCII et `-_.!~*'()`."""
    return quote(text, safe="!~*'()")


def _js_string(value: object) -> str:
    """Le `String(value)` de JavaScript, pour un identifiant."""
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _or_none(value: Any) -> Any:
    """Le `value || undefined` de JavaScript."""
    if value is None or value is False or value in (0, ""):
        return None
    return value


# ===== Deezer =====

DEEZER = "https://api.deezer.com"


@dataclass(frozen=True)
class DeezerCandidate:
    """Un morceau de la recherche de Deezer, pour le jugement à la lettre près.

    `artists` : ses contributeurs, sinon son artiste. L'adaptateur de Hopper.
    """

    id: str
    title: str
    artists: tuple[str, ...]
    url: str
    album: str | None = None
    duration_ms: float | None = None
    isrc: str | None = None
    artist_id: str | None = None

    platform: ClassVar[str] = "deezer"


def _playable(track: object) -> bool:
    """Un morceau retiré ou bloqué (`readable: false`) ne s'écouterait pas."""
    return isinstance(track, dict) and track.get("readable") is not False


def _candidate(
    track: dict[str, Any], album: dict[str, Any] | None = None
) -> DeezerCandidate:
    contributors = _list(track.get("contributors"))
    artist = _object(track.get("artist"))
    if contributors:
        artists = tuple(_object(one).get("name") or "" for one in contributors)
    else:
        artists = (artist.get("name") or "",)
    own = track.get("album")
    album_title = (
        own.get("title")
        if isinstance(own, dict) and own.get("title") is not None
        # `track.album?.title ?? album?.title`
        else (album or {}).get("title")
    )
    duration = track.get("duration")
    return DeezerCandidate(
        id=_js_string(track.get("id")),
        title=track.get("title") or "",
        artists=artists,
        url=f"https://www.deezer.com/track/{_js_string(track.get('id'))}",
        album=album_title,
        duration_ms=duration * 1000 if isinstance(duration, (int, float)) else None,
        isrc=track.get("isrc"),
        artist_id=_js_string(artist.get("id")),
    )


def _prune_candidates(body: dict[str, Any]) -> list[DeezerCandidate]:
    return [_candidate(track) for track in _list(body.get("data")) if _playable(track)]


def deezer_search(http: Http, artist: str, title: str) -> list[DeezerCandidate]:
    """Les morceaux d'une recherche, les lisibles seulement.

    `artist` et `title` : l'artiste et les mots du titre déjà normalisés
    (`split_artists`, `search_terms`). La syntaxe avancée d'abord, plus précise,
    puis la recherche libre : au 16/10/2026, le filtre `artist:` de Deezer ne
    rendait plus rien, même seul.
    """
    queries = [f'artist:"{artist}" track:"{title}"', f"{artist} {title}"]
    for query in queries if artist else [title]:
        url = f"{DEEZER}/search?q={component(query)}&limit=10"
        tracks = http.fetch(url, _prune_candidates) or []
        if tracks:
            return tracks
    return []


@dataclass(frozen=True)
class DeezerArtist:
    id: int
    name: str


def _prune_artists(body: dict[str, Any]) -> list[tuple[DeezerArtist, int]]:
    out = []
    for artist in _list(body.get("data")):
        if isinstance(artist, dict):
            fans = artist.get("nb_fan")
            out.append(
                (
                    DeezerArtist(artist.get("id"), artist.get("name") or ""),
                    fans if isinstance(fans, (int, float)) else 0,
                )
            )
    return out


def deezer_artists(http: Http, name: str) -> list[DeezerArtist]:
    """Les artistes d'une recherche de nom, les plus écoutés d'abord : pour
    « Angèle », Deezer classe la chanteuse après cinq homonymes."""
    url = f"{DEEZER}/search/artist?q={component(name)}&limit=25"
    found = http.fetch(url, _prune_artists) or []
    return [artist for artist, _ in sorted(found, key=lambda one: -one[1])]


# Ses sorties les plus écoutées dont l'artiste est l'artiste principal : albums
# d'abord, puis EP et singles. Lues par paquets de cinq, jusqu'à en avoir cinq.
_RELEASE_ORDER = {"album": 0, "ep": 1, "single": 2}
_RELEASES = 5


def to_ean13(upc: str) -> str:
    """Un code-barres sur 13 chiffres : l'UPC-A en a 12, un GTIN-14 un zéro de
    plus."""
    digits = js_regex(r"[^0-9]").sub("", upc)
    return js_regex(r"^0(?=[0-9]{13}\Z)").sub("", digits, count=1).rjust(13, "0")


def upc_forms(upc: str) -> list[str]:
    """L'EAN-13, puis l'UPC-A : Deezer ne connaît souvent que la forme à 12
    chiffres."""
    ean = to_ean13(upc)
    return [ean, ean[1:]] if ean.startswith("0") else [ean]


def _album(body: dict[str, Any]) -> dict[str, Any]:
    return body


def _available(album: object) -> bool:
    return isinstance(album, dict) and album.get("available") is not False


def deezer_releases(http: Http, artist_id: int) -> list[str]:
    """Les codes-barres de ses sorties les plus écoutées dont l'artiste est
    l'artiste principal."""
    url = f"{DEEZER}/artist/{_js_string(artist_id)}/albums?limit=100"
    listed = _list((http.fetch(url, _album) or {}).get("data"))
    ordered = sorted(
        (
            album
            for album in listed
            if isinstance(album, dict)
            and (album.get("record_type") or "") in _RELEASE_ORDER
        ),
        key=lambda album: (
            _RELEASE_ORDER[album["record_type"]],
            -(album.get("fans") or 0),
        ),
    )
    releases: list[str] = []
    start = 0
    while start < min(len(ordered), _RELEASES * 3) and len(releases) < _RELEASES:
        for item in ordered[start : start + _RELEASES]:
            album = http.fetch(f"{DEEZER}/album/{_js_string(item.get('id'))}", _album)
            owner = _object(album.get("artist")) if album else {}
            if (
                _available(album)
                and album.get("upc")
                and owner.get("id") == artist_id
                and len(releases) < _RELEASES
            ):
                releases.append(to_ean13(str(album["upc"])))
        start += _RELEASES
    return releases


def deezer_album_tracks(http: Http, upc: str) -> list[DeezerCandidate]:
    """Les morceaux lisibles de l'album qui porte ce code-barres."""
    for form in upc_forms(upc):
        album = http.fetch(f"{DEEZER}/album/upc:{form}", _album)
        tracks = _list(_object((album or {}).get("tracks")).get("data"))
        if not tracks:
            continue
        return [_candidate(track, album) for track in tracks if _playable(track)]
    return []


@dataclass(frozen=True)
class DeezerHit:
    """Un morceau de la recherche de Deezer, pour la seconde et la troisième
    passe."""

    id: str
    title: str
    artist: str
    url: str
    artist_id: str | None = None
    duration_s: float | None = None
    album: str | None = None


def prune_deezer_search(body: dict[str, Any]) -> list[DeezerHit]:
    """`pruneDeezerSearch` : une recherche, ou les morceaux d'un album."""
    hits = []
    for track in map(_object, _list(body.get("data"))):
        artist = _object(track.get("artist"))
        own = track.get("album")
        hits.append(
            DeezerHit(
                id=_js_string(track.get("id")),
                title=track["title"] if track.get("title") is not None else "",
                artist=artist["name"] if artist.get("name") is not None else "",
                url=track["link"]
                if track.get("link") is not None
                else f"https://www.deezer.com/track/{_js_string(track.get('id'))}",
                artist_id=_js_string(artist["id"]) if artist.get("id") else None,
                duration_s=_or_none(track.get("duration")),
                album=_or_none(own.get("title")) if isinstance(own, dict) else None,
            )
        )
    return hits


@dataclass(frozen=True)
class DeezerAlbumHit:
    id: str
    title: str


def prune_albums(body: dict[str, Any]) -> list[DeezerAlbumHit]:
    """`pruneAlbums` : une recherche d'album."""
    return [
        DeezerAlbumHit(
            _js_string(_object(album).get("id")),
            _object(album).get("title") or "",
        )
        for album in _list(body.get("data"))
    ]


def _prune_track(body: dict[str, Any]) -> dict[str, Any]:
    artist, album = body.get("artist"), body.get("album")
    return {
        "id": body.get("id"),
        "title": body.get("title"),
        "isrc": body.get("isrc"),
        "duration": body.get("duration"),
        "artist": {"id": artist.get("id"), "name": artist.get("name")}
        if isinstance(artist, dict)
        else None,
        "album": {"id": album.get("id"), "title": album.get("title")}
        if isinstance(album, dict)
        else None,
    }


def _prune_album(body: dict[str, Any]) -> dict[str, Any]:
    genres = _list(_object(body.get("genres")).get("data"))
    return {
        "id": body.get("id"),
        "title": body.get("title"),
        "label": body.get("label"),
        "release_date": body.get("release_date"),
        "record_type": body.get("record_type"),
        "genres": [_object(genre).get("name") for genre in genres],
        "cover": deezer_cover(body.get("cover_big")),
    }


def deezer_details(
    http: Http, platform: str, track_id: str, isrc: str | None = None
) -> DeezerDetails | None:
    """Le morceau chez Deezer, par son identifiant s'il y a été trouvé, sinon par son
    ISRC ; puis son album : label, genres, date."""
    if platform == "deezer":
        url = f"{DEEZER}/track/{track_id}"
    elif isrc:
        url = f"{DEEZER}/track/isrc:{component(isrc)}"
    else:
        return None
    track = http.fetch(url, _prune_track)
    if not track or not track["id"]:
        return None
    own = track["album"]
    album = (
        http.fetch(f"{DEEZER}/album/{_js_string(own['id'])}", _prune_album)
        if own and own["id"]
        else None
    )
    if album:
        found_album = DeezerAlbum(
            id=_js_string(album["id"]),
            title=album["title"],
            label=_or_none(album["label"]),
            date=album["release_date"],
            record_type=album["record_type"],
            genres=tuple(album["genres"]),
            cover=album["cover"],
        )
    elif own:
        found_album = DeezerAlbum(id=_js_string(own["id"]), title=own["title"])
    else:
        found_album = None
    artist = track["artist"]
    return DeezerDetails(
        track_id=_js_string(track["id"]),
        title=track["title"],
        duration_s=_or_none(track["duration"]),
        isrc=track["isrc"],
        artist_id=_js_string(artist["id"]) if artist else None,
        artist_name=artist["name"] if artist else None,
        album=found_album,
    )


# ===== MusicBrainz =====

MUSICBRAINZ = "https://musicbrainz.org/ws/2"


@dataclass(frozen=True)
class MbRecording:
    """Un enregistrement de MusicBrainz : sa recherche, ou sa fiche."""

    id: str
    score: float
    title: str
    credit: str
    artist_ids: tuple[str, ...] = ()
    length_ms: float | None = None
    date: str | None = None
    isrcs: tuple[str, ...] = ()
    releases: tuple[MbRelease, ...] = ()

    @property
    def compilation(self) -> bool:
        """Seules des compilations le contiennent : sa date est la leur."""
        return bool(self.releases) and all(
            "Compilation" in release.secondary for release in self.releases
        )


def _score(value: object) -> float:
    """Le score d'une recherche, de 0 à 100 ; un texte (« 100 ») compte comme en
    JavaScript, rien d'autre."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value))
    except ValueError:
        return 0


def _recording(recording: dict[str, Any]) -> MbRecording:
    artist_credits = list(map(_object, _list(recording.get("artist-credit"))))

    def credited(credit: dict[str, Any]) -> str:
        name = credit.get("name")
        if name is None:
            name = _object(credit.get("artist")).get("name")
        joinphrase = credit.get("joinphrase")
        return (
            f"{'' if name is None else name}{'' if joinphrase is None else joinphrase}"
        )

    releases = []
    for release in map(_object, _list(recording.get("releases"))):
        group = _object(release.get("release-group"))
        secondary = group.get("secondary-types")
        releases.append(
            MbRelease(
                title=release["title"] if release.get("title") is not None else "",
                date=_or_none(release.get("date")),
                type=group.get("primary-type"),
                secondary=tuple(secondary) if isinstance(secondary, list) else (),
            )
        )
    return MbRecording(
        id=recording.get("id") or "",
        score=_score(recording.get("score")),
        title=recording["title"] if recording.get("title") is not None else "",
        credit="".join(credited(credit) for credit in artist_credits),
        artist_ids=tuple(
            artist_id
            for credit in artist_credits
            if (artist_id := _object(credit.get("artist")).get("id"))
        ),
        length_ms=_or_none(recording.get("length")),
        date=_or_none(recording.get("first-release-date")),
        isrcs=tuple(_list(recording.get("isrcs"))),
        releases=tuple(releases),
    )


def prune_recordings(body: dict[str, Any]) -> list[MbRecording]:
    """`pruneRecordings` : une recherche d'enregistrements."""
    return [_recording(_object(one)) for one in _list(body.get("recordings"))]


def musicbrainz_recordings(http: Http, query: str, limit: int) -> list[MbRecording]:
    """Une recherche d'enregistrements, stricte ou floue : `query` dans la syntaxe de
    MusicBrainz."""
    url = f"{MUSICBRAINZ}/recording?query={component(query)}&fmt=json&limit={limit}"
    return http.fetch(url, prune_recordings) or []


def musicbrainz_recording(http: Http, recording_id: str) -> MbRecording | None:
    """Un enregistrement par son identifiant : son titre, ses artistes, sa durée, ses
    ISRC et ses sorties."""
    url = (
        f"{MUSICBRAINZ}/recording/{component(recording_id)}"
        "?inc=artist-credits+isrcs+releases+release-groups&fmt=json"
    )
    return http.fetch(url, _recording)


@dataclass(frozen=True)
class _Credit:
    id: str | None
    name: str | None
    credited: str | None


def _prune_isrc(body: dict[str, Any]) -> list[tuple[str | None, list[_Credit]]]:
    out = []
    for recording in map(_object, _list(body.get("recordings"))):
        found = []
        for credit in map(_object, _list(recording.get("artist-credit"))):
            artist = _object(credit.get("artist"))
            found.append(
                _Credit(artist.get("id"), artist.get("name"), credit.get("name"))
            )
        out.append((_or_none(recording.get("first-release-date")), found))
    return out


def _prune_url(body: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (_object(relation["artist"]).get("id"), _object(relation["artist"]).get("name"))
        for relation in map(_object, _list(body.get("relations")))
        if _truthy_object(relation.get("artist"))
    ]


def _truthy_object(value: object) -> bool:
    return value is not None and value is not False and value not in (0, "")


def _year_in(date: object) -> int | None:
    """« 1986-03-01 » → 1986 ; une date absente reste une borne inconnue."""
    if isinstance(date, str) and js_regex(r"[0-9]{4}").match(date):
        return int(date[:4])
    return None


@dataclass(frozen=True)
class _RawArtist:
    id: str
    name: str
    type: str | None
    gender: str | None
    genres: tuple[tuple[str, float], ...]
    # (identifiant, nom, début, fin) : une relation par période.
    members: tuple[tuple[str, str, int | None, int | None], ...]


def _prune_artist(verdict: bool) -> Callable[[dict[str, Any]], _RawArtist]:
    def prune(body: dict[str, Any]) -> _RawArtist:
        genres = []
        for genre in map(_object, _list(body.get("genres"))):
            count = genre.get("count")
            genres.append((genre.get("name"), count if count is not None else 0))
        members = []
        if verdict:
            for relation in map(_object, _list(body.get("relations"))):
                artist = relation.get("artist")
                if (
                    relation.get("type") == "member of band"
                    and relation.get("direction") == "backward"
                    and _truthy_object(artist)
                ):
                    artist = _object(artist)
                    members.append(
                        (
                            artist.get("id"),
                            artist.get("name"),
                            _year_in(relation.get("begin")),
                            _year_in(relation.get("end")),
                        )
                    )
        return _RawArtist(
            id=body.get("id"),
            name=body.get("name"),
            type=body.get("type"),
            gender=body.get("gender") if verdict else None,
            genres=tuple(genres),
            members=tuple(members),
        )

    return prune


def _prune_person(body: dict[str, Any]) -> str | None:
    """Le genre déclaré d'une personne."""
    return body.get("gender")


def _prune_release_groups(
    body: dict[str, Any],
) -> tuple[float, list[tuple[str, str | None]]]:
    count = body.get("release-group-count")
    groups = [
        (
            _object(group).get("title"),
            _or_none(_object(group).get("first-release-date")),
        )
        for group in _list(body.get("release-groups"))
    ]
    return (count if count is not None else 0), groups


# Au-delà, les membres d'un groupe restent sans genre : une requête par personne, une
# par seconde. Douze ne suffisaient pas aux grands collectifs : Funkadelic compte 29
# membres chez MusicBrainz.
MEMBER_LOOKUPS = 40


def _album_key(title: str) -> str:
    return parse_title(without_edition_mentions(title)).base


def musicbrainz_details(  # noqa: PLR0913
    http: Http,
    *,
    accept: Callable[[str], bool],
    isrc: str | None = None,
    deezer_artist_id: str | None = None,
    artist_id: str | None = None,
    album: str | None = None,
    verdict: bool = False,
) -> MusicBrainzDetails:
    """L'artiste, par l'ISRC du morceau, et la première sortie de cet
    enregistrement ; sinon par la page Deezer de l'artiste, que MusicBrainz relie à
    sa fiche.

    `artist_id` : déjà connu, l'enregistrement rapproché le crédite. `accept` : le
    nom doit être l'un de ceux du fichier (`same_artist_name`), sans quoi rien.
    `album` : sans première sortie de l'enregistrement, chercher celle de l'album
    parmi les sorties de l'artiste, au même titre de base, mentions d'édition
    retirées. `verdict` : ses membres et leur genre déclaré, s'il est allumé.
    """
    recording_date = None
    if isrc:
        url = f"{MUSICBRAINZ}/isrc/{component(isrc)}?inc=artist-credits&fmt=json"
        recordings = http.fetch(url, _prune_isrc) or []
        dates = sorted(date for date, _ in recordings if date)
        recording_date = dates[0] if dates else None
        if artist_id is None:
            artist_id = next(
                (
                    credit.id
                    for _, found in recordings
                    for credit in found
                    if credit.id
                    and (accept(credit.name or "") or accept(credit.credited or ""))
                ),
                None,
            )
    if not artist_id and deezer_artist_id:
        page = component(f"https://www.deezer.com/artist/{deezer_artist_id}")
        url = f"{MUSICBRAINZ}/url?resource={page}&inc=artist-rels&fmt=json"
        artists = http.fetch(url, _prune_url) or []
        artist_id = next((one for one, name in artists if accept(name)), None)
    if not artist_id:
        return MusicBrainzDetails(recording_date=recording_date)

    inc = "artist-rels+genres" if verdict else "genres"
    url = f"{MUSICBRAINZ}/artist/{artist_id}?inc={inc}&fmt=json"
    raw = http.fetch(url, _prune_artist(verdict))
    if not raw:
        return MusicBrainzDetails(recording_date=recording_date)
    members: list[MusicBrainzMember] = []
    if verdict and raw.type != "Person":
        members = _members(http, raw, _year_in(recording_date))
    artist = MusicBrainzArtist(
        id=raw.id,
        name=raw.name,
        type=raw.type,
        gender=raw.gender,
        genres=tuple(
            name for name, _ in sorted(raw.genres, key=lambda genre: -genre[1])
        ),
        members=tuple(members),
    )

    album_date = None
    key = _album_key(album) if album and not recording_date else ""
    offset = 0
    while key and not album_date and offset < 300:
        url = (
            f"{MUSICBRAINZ}/release-group?artist={artist_id}"
            f"&limit=100&offset={offset}&fmt=json"
        )
        page = http.fetch(url, _prune_release_groups)
        if not page:
            break
        count, groups = page
        dates = sorted(
            date for title, date in groups if date and _album_key(title) == key
        )
        album_date = dates[0] if dates else None
        if offset + 100 >= count:
            break
        offset += 100
    return MusicBrainzDetails(recording_date, album_date, artist)


def _members(http: Http, raw: _RawArtist, year: int | None) -> list[MusicBrainzMember]:
    """Les membres d'un groupe, dédoublonnés, avec leurs périodes dans le groupe et
    leur genre déclaré, demandé pour quarante au plus : ceux de l'année de
    l'enregistrement d'abord, ce sont eux qui comptent."""
    # Une relation par période : Kim Deal, chez les Pixies de 1986 à 1993 puis de
    # 2004 à 2013.
    unique: dict[str, MusicBrainzMember] = {}
    for member_id, name, begin, end in raw.members:
        known = unique.get(member_id)
        periods = (
            (*(known.periods or ()), Period(begin, end))
            if known
            else (Period(begin, end),)
        )
        unique[member_id] = MusicBrainzMember(id=member_id, name=name, periods=periods)
    ordered = list(unique.values())
    if year is not None:
        ordered.sort(key=lambda member: not present_in(member, year))
    members = []
    for index, member in enumerate(ordered):
        gender = None
        if index < MEMBER_LOOKUPS:
            gender = http.fetch(
                f"{MUSICBRAINZ}/artist/{member.id}?fmt=json", _prune_person
            )
        members.append(
            MusicBrainzMember(member.id, member.name, gender, member.periods)
        )
    return members


# ===== Wikidata =====

WIKIDATA = "https://query.wikidata.org/sparql"


def wikidata_key(prop: str, artist_id: str) -> str:
    return f"wikidata:{prop}:{artist_id}"


def _qid(uri: str) -> str:
    return uri[uri.rfind("/") + 1 :]


@dataclass(frozen=True)
class _Binding:
    key: str | None
    item: str | None
    label: str | None
    human: bool
    gender: str | None
    member: str | None
    member_gender: str | None


def _prune_sparql(body: dict[str, Any]) -> list[_Binding]:
    def value(binding: dict[str, Any], name: str) -> Any:
        return _object(binding.get(name)).get("value")

    return [
        _Binding(
            key=value(binding, "key"),
            item=value(binding, "item"),
            label=value(binding, "label"),
            human=value(binding, "human") == "true",
            gender=value(binding, "gender"),
            member=value(binding, "member"),
            member_gender=value(binding, "memberGender"),
        )
        for binding in map(_object, _list(_object(body.get("results")).get("bindings")))
    ]


_SPARQL = """SELECT ?key ?item ?label ?human ?gender ?member ?memberGender WHERE {{
  VALUES ?key {{ {values} }} ?item wdt:{prop} ?key .
  OPTIONAL {{ ?item rdfs:label ?label . FILTER(LANG(?label) IN ("en", "fr", "mul")) }}
  OPTIONAL {{ ?item wdt:P31 wd:Q5 . BIND(true AS ?human) }}
  OPTIONAL {{ ?item wdt:P21 ?gender }}
  OPTIONAL {{ {{ ?item wdt:P527 ?member }} UNION {{ ?member wdt:P463 ?item }} ?member wdt:P31 wd:Q5 . OPTIONAL {{ ?member wdt:P21 ?memberGender }} }}
}}"""  # noqa: E501 (la requête de Hopper, telle quelle)


@dataclass
class _Entry:
    item: str
    names: list[str]
    human: bool
    genders: list[str]
    members: dict[str, list[str]]


def _entries(bindings: Iterable[_Binding]) -> dict[str, _Entry]:
    """Les fiches d'un paquet de réponses, une par identifiant."""
    found: dict[str, _Entry] = {}
    for binding in bindings:
        if not binding.key or not binding.item:
            continue
        entry = found.get(binding.key) or _Entry(binding.item, [], False, [], {})
        # Deux fiches pour un même identifiant : la première seulement.
        if binding.item != entry.item:
            continue
        if binding.label and binding.label not in entry.names:
            entry.names.append(binding.label)
        entry.human = entry.human or binding.human
        if binding.gender and _qid(binding.gender) not in entry.genders:
            entry.genders.append(_qid(binding.gender))
        if binding.member:
            genders = entry.members.setdefault(binding.member, [])
            gender = binding.member_gender
            if gender and _qid(gender) not in genders:
                genders.append(_qid(gender))
        found[binding.key] = entry
    return found


def _wikidata_artist(entry: _Entry) -> WikidataArtist:
    return WikidataArtist(
        item=entry.item,
        names=tuple(entry.names),
        human=entry.human,
        genders=tuple(entry.genders),
        members={member: tuple(genders) for member, genders in entry.members.items()},
    )


def wikidata_artists(
    http: Http,
    store: MutableMapping[str, WikidataArtist | None],
    deezer_ids: Iterable[str],
    musicbrainz_ids: Iterable[str],
) -> dict[str, WikidataArtist]:
    """Les artistes par leur identifiant Deezer (P2722) ou MusicBrainz (P434) :
    personne ou non, genre déclaré (P21), membres humains d'un groupe (P527 du
    groupe, ou P463 du membre) et leur genre déclaré.

    Chaque fiche se garde à part dans `store`, `None` pour un identifiant que
    Wikidata ne connaît pas : seuls les identifiants nouveaux sont demandés, par
    paquets de 80. Une question sans réponse ne garde rien. `store` vit en mémoire :
    il porte des genres de personnes.
    """
    out: dict[str, WikidataArtist] = {}
    headers = {"Accept": "application/sparql-results+json"}
    for prop, ids in (("P2722", deezer_ids), ("P434", musicbrainz_ids)):
        unique = sorted({one for one in ids if one})
        missing = [one for one in unique if wikidata_key(prop, one) not in store]
        for start in range(0, len(missing), 80):
            keys = missing[start : start + 80]
            values = " ".join(json.dumps(key, ensure_ascii=False) for key in keys)
            query = _SPARQL.format(values=values, prop=prop)
            url = f"{WIKIDATA}?format=json&query={component(query)}"
            bindings = http.fetch(url, _prune_sparql, headers)
            if bindings is None:
                continue
            found = _entries(bindings)
            for key in keys:
                entry = found.get(key)
                store[wikidata_key(prop, key)] = (
                    _wikidata_artist(entry) if entry else None
                )
        for one in unique:
            stored = store.get(wikidata_key(prop, one))
            if stored:
                out[one] = stored
    return out


# ===== AcoustID =====

ACOUSTID = "https://api.acoustid.org/v2/lookup"
# La clé d'application de BUTTON chez AcoustID, comme celle que Beets écrit dans son
# plugin chroma : elle dit quelle application demande, et n'ouvre aucun compte. Une
# station peut poser la sienne (`fiches.acoustid_key`). Un usage hors de BUTTON
# demande sa propre clé : https://acoustid.org/new-application
BUTTON_ACOUSTID_KEY = "Hg5cySRJWo"
# Une empreinte ou une durée que le service refuse pour ce fichier : rien à en
# tirer, pas une panne.
_ACOUSTID_NOTHING = frozenset({3, 8})
# Une clé d'application refusée.
_ACOUSTID_KEY = 4


class AcoustidKeyError(HttpError):
    """AcoustID refuse la clé d'application : la passe de l'empreinte attend une
    autre clé, rien ne sert de réessayer."""


@dataclass(frozen=True)
class AcoustidResult:
    """Un résultat d'AcoustID : son score, de 0 à 1, et les enregistrements de
    MusicBrainz qui portent cette empreinte."""

    score: float
    recordings: tuple[str, ...]


def acoustid_lookup(
    http: Http, key: str, fingerprint: str, duration: int
) -> list[AcoustidResult]:
    """Les enregistrements d'une empreinte et de sa durée, en secondes.

    La clé d'application va dans le corps de la requête, jamais dans l'adresse.
    """
    data = {
        "client": key,
        "meta": "recordingids",
        "duration": str(duration),
        "fingerprint": fingerprint,
        "format": "json",
    }
    status, body = http.send("POST", ACOUSTID, data=data)
    body = _object(body)
    if status == 200 and body.get("status") == "ok":
        return [
            AcoustidResult(
                score=float(result.get("score") or 0),
                recordings=tuple(
                    one["id"]
                    for one in map(_object, _list(result.get("recordings")))
                    if isinstance(one.get("id"), str)
                ),
            )
            for result in map(_object, _list(body.get("results")))
        ]
    error = _object(body.get("error"))
    if error.get("code") in _ACOUSTID_NOTHING:
        return []
    message = error.get("message") or f"réponse {status}"
    if error.get("code") == _ACOUSTID_KEY:
        raise AcoustidKeyError(f"api.acoustid.org : {message}", status)
    raise HttpError(f"api.acoustid.org : {message}", status)


# ===== Tidal, Apple Music et Bandcamp (FON-30) =====
#
# Les adaptateurs du site de Hopper (`lib/adapters/tidal.ts`, `apple.ts`,
# `bandcamp.ts`), pour ce dont sa recherche se sert : la recherche d'un morceau, et
# chez Apple Music le genre et la date d'un morceau trouvé. Chacune derrière son
# réglage, éteint par défaut (`SourceSettings`) : une source éteinte n'est jamais
# appelée.

# Les réglages, dans la table `settings`. Une clé absente laisse la source éteinte.
SETTING_TIDAL = "features.fiches_tidal"
SETTING_APPLE = "features.fiches_apple_music"
SETTING_BANDCAMP = "features.fiches_bandcamp"
# La clé d'application Tidal de la station : un secret, que nulle route ne rend.
SETTING_TIDAL_CLIENT_ID = "fiches.tidal_client_id"
SETTING_TIDAL_CLIENT_SECRET = "fiches.tidal_client_secret"

_SETTING_OFF = frozenset({"0", "false", "off", "non", ""})


def _switched_on(value: object) -> bool:
    return value is not None and str(value).strip().lower() not in _SETTING_OFF


@dataclass(frozen=True)
class SourceSettings:
    """Les sources allumées, et la clé d'application Tidal de la station.

    La clé ne paraît jamais dans un journal : `repr` la tait.
    """

    tidal: bool = False
    apple: bool = False
    bandcamp: bool = False
    tidal_client_id: str = field(default="", repr=False)
    tidal_client_secret: str = field(default="", repr=False)

    @property
    def tidal_key(self) -> bool:
        """La station a-t-elle une clé d'application Tidal entière ?"""
        return bool(self.tidal_client_id.strip() and self.tidal_client_secret.strip())

    @classmethod
    def from_settings(cls, values: Mapping[str, object]) -> SourceSettings:
        """Les réglages lus dans la table `settings`, clé par clé."""
        return cls(
            tidal=_switched_on(values.get(SETTING_TIDAL)),
            apple=_switched_on(values.get(SETTING_APPLE)),
            bandcamp=_switched_on(values.get(SETTING_BANDCAMP)),
            tidal_client_id=str(values.get(SETTING_TIDAL_CLIENT_ID) or ""),
            tidal_client_secret=str(values.get(SETTING_TIDAL_CLIENT_SECRET) or ""),
        )


@dataclass(frozen=True)
class Candidate:
    """Un morceau de Tidal, d'Apple Music ou de Bandcamp, pour les trois passes.

    `by_label` : chez Bandcamp, l'artiste n'est lu que dans le titre, sur le compte
    d'un autre, un label ou un réenvoi.
    """

    platform: str
    id: str
    url: str
    title: str
    artists: tuple[str, ...]
    album: str | None = None
    duration_ms: float | None = None
    isrc: str | None = None
    release_date: str | None = None
    artist_id: str | None = None
    by_label: bool = False
    kind: str = "track"
    # Le lien de sa pochette (FON-83), chez Bandcamp.
    cover: str | None = None


def _coalesce(value: Any, default: Any) -> Any:
    """Le `??` de JavaScript."""
    return default if value is None else value


def _template(value: object) -> str:
    """Une valeur dans un gabarit de JavaScript, `${value}`."""
    return _js_string(value) if not isinstance(value, str) else value


def _optional_text(value: object) -> str | None:
    """`value ? String(value) : undefined`."""
    return _template(value) if _truthy_object(value) else None


_ISO_DURATION = js_regex(
    r"^P(?:([0-9]+)D)?T?(?:([0-9]+)H)?(?:([0-9]+)M)?(?:([0-9]+(?:\.[0-9]+)?)S)?\Z"
)


def iso_duration(value: object) -> int | None:
    """Une durée ISO 8601 (« PT3M45S ») en millisecondes : Tidal l'écrit ainsi."""
    found = _ISO_DURATION.match(value) if isinstance(value, str) else None
    if not found:
        return None
    days, hours, minutes, seconds = (float(part or 0) for part in found.groups())
    return js_round(((days * 24 + hours) * 3600 + minutes * 60 + seconds) * 1000)


# ===== Tidal =====

TIDAL = "https://openapi.tidal.com/v2"
TIDAL_TOKEN = "https://auth.tidal.com/v1/oauth2/token"
_TIDAL_COUNTRY = "FR"


def _tidal_resources(document: object) -> list[dict[str, Any]]:
    data = _object(document).get("data")
    if isinstance(data, list):
        return list(map(_object, data))
    return [_object(data)] if _truthy_object(data) else []


def _tidal_key(resource: dict[str, Any]) -> str:
    return f"{_template(resource.get('type'))}/{_template(resource.get('id'))}"


def _streamable(attributes: dict[str, Any]) -> bool:
    """Un morceau non diffusable (`availability` sans STREAM) ne s'écouterait pas."""
    availability = attributes.get("availability")
    return not isinstance(availability, list) or "STREAM" in availability


def tidal_candidates(
    document: object, album: dict[str, Any] | None = None
) -> list[Candidate]:
    """`tidalCandidates` : les morceaux d'un document JSON:API, artistes et album lus
    dans `included`, dans l'ordre de pertinence de la recherche.

    `album` : les attributs de l'album, pour les pistes d'un album.
    """
    resources = _tidal_resources(document)
    included_list = list(map(_object, _list(_object(document).get("included"))))
    included = {_tidal_key(resource): resource for resource in included_list}
    linkages = [
        *(resource for resource in resources if resource.get("type") == "tracks"),
        *(
            _object(link)
            for resource in resources
            for link in _list(
                _object(_object(resource.get("relationships")).get("tracks")).get(
                    "data"
                )
            )
        ),
    ]
    position = {link.get("id"): index for index, link in enumerate(linkages)}
    seen: set[Any] = set()
    tracks = []
    for resource in [*resources, *included_list]:
        attributes = resource.get("attributes")
        if resource.get("type") != "tracks" or not _truthy_object(attributes):
            continue
        if resource.get("id") in seen:
            continue
        seen.add(resource.get("id"))
        if _streamable(_object(attributes)):
            tracks.append(resource)
    tracks.sort(key=lambda resource: position.get(resource.get("id"), math.inf))
    return [_tidal_candidate(resource, included, album) for resource in tracks]


def _tidal_candidate(
    resource: dict[str, Any],
    included: dict[str, dict[str, Any]],
    context: dict[str, Any] | None,
) -> Candidate:
    attributes = _object(resource.get("attributes"))

    def related(name: str) -> list[dict[str, Any]]:
        links = _object(_object(resource.get("relationships")).get(name)).get("data")
        found = (included.get(_tidal_key(_object(link))) for link in _list(links))
        return [one for one in found if one]

    albums = related("albums")
    album = albums[0].get("attributes") if albums else None
    album = _object(_coalesce(album, context))
    title = _template(_coalesce(attributes.get("title"), ""))
    version = attributes.get("version")
    track_id = _template(resource.get("id"))
    return Candidate(
        platform="tidal",
        id=track_id,
        url=f"https://tidal.com/browse/track/{track_id}",
        title=f"{title} ({_template(version)})" if _truthy_object(version) else title,
        artists=tuple(
            _template(_coalesce(_object(artist.get("attributes")).get("name"), ""))
            for artist in related("artists")
        ),
        album=_optional_text(album.get("title")),
        duration_ms=iso_duration(attributes.get("duration")),
        isrc=_optional_text(attributes.get("isrc")),
        release_date=_optional_text(album.get("releaseDate")),
    )


class TidalKeyError(HttpError):
    """Tidal refuse la clé d'application de la station : la source est sautée, rien
    ne sert de réessayer."""


class Tidal:
    """Tidal, par son API officielle (openapi.tidal.com/v2, au format JSON:API), avec
    la clé d'application de la station.

    Le jeton se garde en mémoire jusqu'à une minute avant qu'il expire. Une clé
    refusée saute Tidal pour toute la tâche, et le journal le dit une fois. La clé
    ne paraît jamais dans un journal ni dans une adresse.
    """

    def __init__(self, http: Http, client_id: str, client_secret: str) -> None:
        self._http = http
        basic = f"{client_id.strip()}:{client_secret.strip()}".encode()
        self._basic = base64.b64encode(basic).decode()
        self._token: tuple[str, float] | None = None
        self.refused = False

    def __repr__(self) -> str:
        return "Tidal()"

    def _bearer(self, *, force: bool = False) -> str:
        clock = self._http.clock
        if not force and self._token and clock.now() < self._token[1]:
            return self._token[0]
        headers = {"Authorization": f"Basic {self._basic}"}
        data = {"grant_type": "client_credentials"}
        status, body = self._http.send("POST", TIDAL_TOKEN, headers=headers, data=data)
        body = _object(body)
        token = body.get("access_token")
        if status != 200 or not isinstance(token, str) or not token:
            error = body.get("error")
            said = f", {error}" if _truthy_object(error) else ""
            message = f"Tidal : jeton refusé ({status}{said})"
            if status in (400, 401):
                raise TidalKeyError(message, status)
            raise HttpError(message, status)
        expires = _coalesce(body.get("expires_in"), 3600)
        if not isinstance(expires, (int, float)):
            expires = 3600
        self._token = (token, clock.now() + expires - 60)
        return token

    def _get(self, path: str) -> object:
        """Un document de Tidal ; None pour une absence. Un jeton refusé se redemande
        une fois."""
        url = f"{TIDAL}{path}{'&' if '?' in path else '?'}countryCode={_TIDAL_COUNTRY}"
        for attempt in (0, 1):
            headers = {
                "Authorization": f"Bearer {self._bearer(force=attempt > 0)}",
                "Accept": "application/vnd.api+json",
            }
            status, body = self._http.send("GET", url, headers=headers)
            if status == 401 and attempt == 0:
                continue
            if status == 429 or status >= 500:
                raise HttpError(f"Tidal : réponse {status}", status)
            return body if status == 200 else None
        return None

    def search(self, artist: str, title: str) -> list[Candidate]:
        """Les morceaux d'une recherche : le premier artiste, et les mots du titre."""
        if self.refused:
            return []
        first = next(iter(split_artists([artist])), "")
        query = js_trim(f"{first} {search_terms(title)}")
        include = component("tracks,tracks.artists,tracks.albums")
        path = f"/searchResults?filter%5Bquery%5D={component(query)}&include={include}"
        try:
            return tidal_candidates(self._get(path))
        except TidalKeyError:
            self.refused = True
            _log.warning("fiches : Tidal refuse la clé d'application, Tidal est sauté")
            return []


# ===== Apple Music =====

ITUNES = "https://itunes.apple.com"
_ITUNES_COUNTRY = "FR"


def _form_component(text: str) -> str:
    """Le codage `application/x-www-form-urlencoded` de `URLSearchParams`."""
    out = []
    for char in text:
        if char.isascii() and (char.isalnum() or char in "*-._"):
            out.append(char)
        elif char == " ":
            out.append("+")
        else:
            out.append("".join(f"%{byte:02X}" for byte in char.encode()))
    return "".join(out)


def clean_url(url: str | None, fallback: str) -> str:
    """L'adresse Apple Music sans le paramètre de suivi « uo ».

    Comme `URLSearchParams.delete`, le reste de la requête se récrit, et une requête
    vide disparaît.
    """
    if not url:
        return fallback
    head, hash_, fragment = url.partition("#")
    base, _, query = head.partition("?")
    kept = [
        (name, value)
        for name, value in parse_qsl(query, keep_blank_values=True)
        if name != "uo"
    ]
    query = "&".join(f"{_form_component(n)}={_form_component(v)}" for n, v in kept)
    return f"{base}{'?' if query else ''}{query}{hash_}{fragment}"


def _itunes_song(result: dict[str, Any]) -> bool:
    return result.get("wrapperType") == "track" and result.get("kind") == "song"


def apple_candidate(track: dict[str, Any]) -> Candidate:
    """Un morceau de l'API d'iTunes, comme l'adaptateur Apple Music de Hopper."""
    track_id = track.get("trackId")
    date = track.get("releaseDate")
    fallback = f"https://music.apple.com/fr/song/{_template(_coalesce(track_id, 0))}"
    return Candidate(
        platform="apple",
        id=_js_string(track_id),
        url=clean_url(track.get("trackViewUrl"), fallback),
        title=_coalesce(track.get("trackName"), ""),
        artists=(_coalesce(track.get("artistName"), ""),),
        album=track.get("collectionName"),
        duration_ms=track.get("trackTimeMillis"),
        release_date=date[:10] if isinstance(date, str) else None,
        cover=apple_cover(track.get("artworkUrl100")),
    )


def _itunes_results(body: dict[str, Any]) -> list[dict[str, Any]]:
    return list(map(_object, _list(body.get("results"))))


def apple_search(http: Http, artist: str, title: str) -> list[Candidate]:
    """Les morceaux d'une recherche d'iTunes, catalogue français : le premier artiste,
    et les mots du titre. iTunes refuse (403) au-delà de son quota : une panne,
    jamais une absence."""
    first = next(iter(split_artists([artist])), "")
    term = js_trim(f"{first} {search_terms(title)}")
    url = (
        f"{ITUNES}/search?term={component(term)}&entity=song&limit=10"
        f"&country={_ITUNES_COUNTRY}"
    )
    results = http.fetch(url, _itunes_results) or []
    return [apple_candidate(result) for result in results if _itunes_song(result)]


def _prune_itunes(body: dict[str, Any]) -> AppleDetails | None:
    result = next(iter(_itunes_results(body)), None)
    if result is None:
        return None
    return AppleDetails(
        genre=result.get("primaryGenreName"),
        date=result.get("releaseDate"),
        album=result.get("collectionName"),
        cover=apple_cover(result.get("artworkUrl100")),
    )


def apple_details(http: Http, track_id: str) -> AppleDetails | None:
    """`appleDetails` : le genre principal d'un morceau Apple Music, sa date et son
    album."""
    url = f"{ITUNES}/lookup?id={component(track_id)}&country={_ITUNES_COUNTRY}"
    return http.fetch(url, _prune_itunes)


# ===== Bandcamp =====

BANDCAMP_SEARCH = "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic"
BANDCAMP_DETAILS = "https://bandcamp.com/api/mobile/25/tralbum_details"
# Fiches lues par recherche : la recherche rend une dizaine de résultats, la plupart
# d'autres titres.
BANDCAMP_DETAILED = 3
# Un titre assez proche pour mériter la lecture de sa fiche.
BANDCAMP_PLAUSIBLE = 0.8


def _unqualified(name: str) -> str:
    """« Nirvana (UK) » : la précision entre parenthèses ne fait pas un autre nom."""
    return js_regex(r"\s*[(\[][^)\]]*[)\]]\s*\Z").sub("", name, count=1) or name


def same_platform_artist(a: str, b: str) -> bool:
    """Le `sameArtistName` de `score.ts`, à ne pas confondre avec celui de
    `rules.ts` (`same_artist_name`) : deux plateformes nomment-elles le même
    artiste ? Écrit dans deux alphabets, il se compare en latin."""
    if same_artist(normalize_text(_unqualified(a)), normalize_text(_unqualified(b))):
        return True
    left = " ".join(latin_words(_unqualified(a)))
    right = " ".join(latin_words(_unqualified(b)))
    return bool(left) and same_artist(left, right)


def _squashed(name: str) -> str:
    return js_regex(r"\s+").sub(
        "", normalize_text(js_regex(r"^the\s+", re.IGNORECASE).sub("", name, count=1))
    )


def same_credit(a: str, b: str) -> bool:
    """`sameCredit` : deux noms d'artiste pour un même compte, « The » en tête ou pas,
    ou sans espaces (« okkyunglee », nom d'utilisateur d'Okkyung Lee)."""
    return (
        bool(js_trim(a))
        and bool(js_trim(b))
        and (same_platform_artist(a, b) or _squashed(a) == _squashed(b))
    )


@dataclass(frozen=True)
class Credit:
    """Ce qu'un titre de Bandcamp dit de son artiste : le titre sans lui, l'artiste
    crédité, et si c'est le compte qui publie."""

    title: str
    artist: str
    by_account: bool


_SIDE = js_regex(r"^(?:[A-D][0-9]{1,2}|[0-9]{1,2})(?:_|\.\s+|\s+[-\u2013]\s+)(?=\S)")
_UNDERSCORED = js_regex(r"^([^_]+)_(.+)\Z")
_PREFIXED = js_regex(r"^(.+?)\s+[-\u2013\u2014]\s+(.+)\Z")


def credit_from_title(title: str, account: str, wanted: Sequence[str] = ()) -> Credit:
    """`creditFromTitle` : un label, ou un compte qui réenvoie, écrit l'artiste dans
    le titre (« Keope - Osem (Acid Coco Remix) » chez Bigamo). Le titre sans ce
    préfixe ni son rang de face, l'artiste crédité, et si c'est le compte.

    `wanted` : les artistes cherchés, seuls reconnus en préfixe.
    """
    text = _SIDE.sub("", js_trim(title), count=1)

    def known(name: str) -> bool:
        return same_credit(name, account) or any(
            same_credit(name, artist) for artist in wanted
        )

    underscored = _UNDERSCORED.match(text)
    parts = _PREFIXED.match(text) or (
        underscored if underscored and known(underscored[1]) else None
    )
    if parts:
        prefix, rest = parts[1], parts[2]
        clean = js_trim(rest.replace("_", " "))
        if same_credit(prefix, account):
            return Credit(clean, account, True)
        if any(same_credit(prefix, artist) for artist in wanted) or not wanted:
            return Credit(clean, js_trim(prefix), False)
    return Credit(text, account, True)


_ALBUM_ARTIST = js_regex(r"^(.+?)\s*[-\u2013]\s*(.+)\Z")


def _album_title(album: str | None, artist: str) -> str | None:
    """« Pieuvre-Away From Human Behaviour » : l'album d'un label, l'artiste en
    tête."""
    if not album:
        return None
    parts = _ALBUM_ARTIST.match(album)
    if (
        parts
        and token_set_similarity(parse_title(parts[1]).base, parse_title(artist).base)
        == 1
    ):
        return parts[2]
    return album


def bandcamp_ref(url: str, kind: str) -> str | None:
    """L'adresse d'une page → son identifiant (« pieuvres/track/home-office-2 ») ; un
    domaine propre garde son nom complet."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
    except ValueError:
        return None
    if not parsed.scheme or not host:
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0] != kind:
        return None
    host = host.lower()
    site = host.removesuffix(".bandcamp.com")
    return f"{site}/{segments[0]}/{segments[1]}"


def bandcamp_url(ref: str) -> str:
    site, *path = ref.split("/")
    domain = site if "." in site else f"{site}.bandcamp.com"
    return f"https://{domain}/{'/'.join(path)}"


def _iso_day(seconds: object) -> str | None:
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    if not seconds:
        return None
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%d")


def bandcamp_candidate(
    details: dict[str, Any],
    hit: dict[str, Any] | None = None,
    wanted: Sequence[str] = (),
) -> Candidate | None:
    """`bandcampCandidate` : la fiche d'un morceau ou d'un album, l'artiste lu dans le
    titre s'il y est.

    Le compte qui publie fait foi : l'artiste qu'une sortie déclare, même « Daft
    Punk » sur un réenvoi, ne suffit pas (`by_label`).
    """
    hit = hit or {}
    kind = "album" if details.get("type") == "a" else "track"
    url = _coalesce(details.get("bandcamp_url"), hit.get("item_url_path"))
    ref = bandcamp_ref(url, kind) if isinstance(url, str) and url else None
    if not ref:
        return None
    band = details.get("band")
    account = _coalesce(
        _object(band).get("name") if isinstance(band, dict) else None,
        _coalesce(details.get("tralbum_artist"), ""),
    )
    declared = next(
        (
            name
            for name in (details.get("tralbum_artist"), hit.get("band_name"))
            if isinstance(name, str) and name and not same_credit(name, account)
        ),
        None,
    )
    title = _coalesce(details.get("title"), "")
    credit = credit_from_title(title, account, wanted)
    named = (
        credit_from_title(title, declared, wanted)
        if credit.by_account and declared and wanted
        else credit
    )
    by_label = not any(
        same_credit(name, account) for name in split_artists(named.artist)
    )
    track = None
    if kind == "track":
        tracks = list(map(_object, _list(details.get("tracks"))))
        track = next(
            (one for one in tracks if one.get("track_id") == details.get("id")),
            tracks[0] if tracks else None,
        )
    duration = track.get("duration") if track else None
    return Candidate(
        platform="bandcamp",
        id=ref,
        url=bandcamp_url(ref),
        title=named.title,
        artists=(named.artist,),
        album=_album_title(details.get("album_title"), named.artist)
        if kind == "track"
        else None,
        duration_ms=js_round(duration * 1000)
        if isinstance(duration, (int, float)) and duration
        else None,
        release_date=_iso_day(details.get("release_date")),
        by_label=by_label,
        kind=kind,
        cover=bandcamp_cover(details.get("art_id")),
    )


_SPACES = js_regex(r"\s+")


def _unreadable(what: str, status: int, body: object) -> HttpError:
    """Une réponse que Bandcamp ne devrait pas rendre : refus, page de vérification,
    format changé. Une panne, jamais une absence ; le journal le dit, sans quoi
    rien ne dirait que Bandcamp ne répond plus."""
    if isinstance(body, str):
        head = f" « {js_trim(_SPACES.sub(' ', body))[:160]} »"
    elif body is None:
        head = " (vide)"
    else:
        head = f" ({', '.join(list(_object(body))[:6])})"
    _log.warning("fiches : Bandcamp, %s : réponse %s%s", what, status, head)
    return HttpError(f"Bandcamp : réponse {status}", status)


def _bandcamp_hits(http: Http, text: str, kind: str) -> list[dict[str, Any]]:
    """La recherche du site, celle qu'interroge sa barre de recherche."""
    body = {
        "search_text": text,
        "search_filter": kind,
        "full_page": False,
        "fan_id": None,
    }
    status, answer = http.send("POST", BANDCAMP_SEARCH, json_body=body)
    auto = _object(answer).get("auto") if status == 200 else None
    results = _object(auto).get("results")
    if not isinstance(results, list):
        raise _unreadable("recherche", status, answer)
    return [hit for hit in map(_object, results) if hit.get("type") == kind]


def _bandcamp_details(http: Http, hit: dict[str, Any]) -> dict[str, Any] | None:
    """La fiche d'un résultat ; None pour une fiche retirée depuis la recherche."""
    url = (
        f"{BANDCAMP_DETAILS}?band_id={_template(hit.get('band_id'))}"
        f"&tralbum_type={_template(hit.get('type'))}"
        f"&tralbum_id={_template(hit.get('id'))}"
    )
    status, body = http.send("GET", url)
    if status == 404 or (
        status == 200 and isinstance(body, dict) and _truthy_object(body.get("error"))
    ):
        return None
    if status != 200 or not isinstance(body, dict):
        raise _unreadable("fiche", status, body)
    return body


def bandcamp_search(http: Http, artist: str, title: str) -> list[Candidate]:
    """Les morceaux d'une recherche de Bandcamp, sans clé : il n'a pas d'API publique.

    La recherche du site, puis la fiche des trois résultats les plus plausibles, pour
    leur durée, leur artiste et leur album. Les comptes de label en sont, marqués
    (`by_label`) : à la lettre près, on ne les prend pas.
    """
    wanted = (artist,)
    first = next(iter(split_artists([artist])), "")
    hits = _bandcamp_hits(http, js_trim(f"{first} {search_terms(title)}"), "t")
    base = parse_title(title).base
    plausible = [
        hit
        for hit in hits
        if token_set_similarity(
            parse_title(
                credit_from_title(
                    _coalesce(hit.get("name"), ""),
                    _coalesce(hit.get("band_name"), ""),
                    wanted,
                ).title
            ).base,
            base,
        )
        >= BANDCAMP_PLAUSIBLE
    ][:BANDCAMP_DETAILED]
    found = []
    for hit in plausible:
        details = _bandcamp_details(http, hit)
        candidate = details and bandcamp_candidate(details, hit, wanted)
        if candidate and not (candidate.kind == "album" and candidate.by_label):
            found.append(candidate)
    return found


@dataclass(frozen=True)
class Platforms:
    """Les sources de FON-30 allumées pour une recherche : Tidal, avec la clé de la
    station, Apple Music et Bandcamp."""

    tidal: Tidal | None = None
    apple: bool = False
    bandcamp: bool = False


def deezer_by_isrc(http: Http, isrc: str) -> list[DeezerCandidate]:
    """Le morceau Deezer qui porte cet ISRC, s'il est lisible : le même que celui de
    Tidal."""
    url = f"{DEEZER}/track/isrc:{component(isrc)}"
    track = http.fetch(url, _album)
    return [_candidate(track)] if _playable(track) else []
