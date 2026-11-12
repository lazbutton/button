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

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from radiotomate.fiches.http import HttpError
from radiotomate.fiches.loose import MbRelease
from radiotomate.fiches.normalize import js_regex, parse_title
from radiotomate.fiches.proposals import (
    DeezerAlbum,
    DeezerDetails,
    MusicBrainzArtist,
    MusicBrainzDetails,
    MusicBrainzMember,
    WikidataArtist,
)
from radiotomate.fiches.rules import Period, present_in, without_edition_mentions

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, MutableMapping

    from radiotomate.fiches.http import Http


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
