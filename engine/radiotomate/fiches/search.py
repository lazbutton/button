"""La recherche d'un titre, de l'empreinte aux détails, et les preuves à garder.

Le `processItem` de `scripts/radio-catalogue.ts`, dans Hopper, avec `findRadioTrack`
(`radio.ts`), `findLoosely` (`loose.ts`) et `findHarder` (`third.ts`). Un titre passe
par ces étapes, dans l'ordre, et s'arrête à la première qui le trouve :

1. L'empreinte, si elle est prise et que BUTTON a une clé AcoustID. AcoustID rend les
   enregistrements de MusicBrainz qui la portent, cinq au plus, d'un score de 0,5 au
   moins, comme `chroma` ; MusicBrainz donne leur titre, leurs artistes et leur
   durée, qui vérifient toujours le lien d'AcoustID.
2. À la lettre près : les variantes du texte, chez Deezer ; chez Tidal, puis le même
   morceau chez Deezer par son ISRC ; chez Apple Music ; parmi les sorties de
   l'artiste chez Deezer ; chez Bandcamp, sur le compte de l'artiste seulement.
3. La seconde passe : chez Deezer, puis dans MusicBrainz, puis chez Bandcamp, comptes
   de label compris.
4. La troisième passe : le texte relu chez Deezer, les morceaux de l'artiste, l'album
   du fichier, Tidal, MusicBrainz en recherche floue, puis Apple Music.

Tidal, Apple Music et Bandcamp (FON-30) ne sont cherchés qu'allumés, chacun par son
réglage (`SourceSettings`) : une source éteinte n'est jamais appelée. SoundCloud n'est
pas repris.

Un titre trouvé donne ses détails, toujours par un identifiant : le morceau Deezer et
son album, l'enregistrement MusicBrainz par son ISRC et son artiste, Wikidata par
l'identifiant de l'artiste. Les requêtes sur les personnes ne partent que verdict
allumé. Une panne n'est jamais un introuvable : le titre est en erreur, et sera
cherché de nouveau.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from radiotomate.fiches.http import HttpError
from radiotomate.fiches.loose import (
    LOOSE_TOLERANCE_S,
    Found,
    best,
    first_release,
    generic_title,
    loose_judge,
    loose_variants,
    meaningless_title,
    nearly_same,
    quoteless,
    versions,
)
from radiotomate.fiches.normalize import (
    js_regex,
    js_trim,
    parse_title,
    search_terms,
    split_artists,
    squash,
)
from radiotomate.fiches.proposals import (
    FINGERPRINT,
    FROM_FINGERPRINT,
    OTHER_PIECE,
    OTHER_VERSION,
    Details,
    Match,
    SearchResult,
    WikidataArtist,
)
from radiotomate.fiches.rules import (
    clean_isrc,
    duration_level,
    js_falsy,
    same_artist_name,
)
from radiotomate.fiches.sources import (
    DEEZER,
    AcoustidKeyError,
    Candidate,
    DeezerHit,
    MbRecording,
    Platforms,
    SourceSettings,
    Tidal,
    acoustid_lookup,
    apple_details,
    apple_search,
    bandcamp_search,
    component,
    deezer_album_tracks,
    deezer_artists,
    deezer_by_isrc,
    deezer_details,
    deezer_releases,
    deezer_search,
    musicbrainz_details,
    musicbrainz_recording,
    musicbrainz_recordings,
    prune_albums,
    prune_deezer_search,
    wikidata_artists,
)
from radiotomate.fiches.third import (
    PLACEHOLDER,
    Reading,
    ThirdCandidate,
    album_ok,
    any_artist,
    any_title,
    fuzzy,
    readings,
    third_judge,
)
from radiotomate.fiches.variants import (
    Meta,
    RadioTrack,
    RadioVariant,
    is_announcement,
    radio_variants,
    same_radio_track,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence

    from radiotomate.fiches.fingerprint import Print
    from radiotomate.fiches.http import Http
    from radiotomate.fiches.proposals import Track
    from radiotomate.fiches.sources import DeezerCandidate

    # Une étape de la cascade : les candidats d'une variante du texte.
    _Step = Callable[[RadioVariant], Sequence[DeezerCandidate | Candidate]]

_log = logging.getLogger(__name__)

# Aucune des sources de FON-30 : Tidal, Apple Music et Bandcamp éteints.
NONE = Platforms()


def _first(*values: Any) -> Any:
    """La première valeur connue, comme `??` en JavaScript."""
    return next((value for value in values if value is not None), None)


@dataclass(frozen=True)
class _Hit(Found):
    """Un candidat jugé, et ce que la source en a dit."""

    found: Any = None


def _hit(verdict: Found | None, found: object) -> list[_Hit]:
    """Le candidat jugé, s'il convient : une liste vide sinon."""
    if verdict is None:
        return []
    return [_Hit(verdict.why, verdict.gap, verdict.one_sided, found)]


def _milliseconds(seconds: float | None) -> float | None:
    return seconds * 1000 if seconds else None


# ===== À la lettre près =====

# Une recherche à la lettre près qui dure plus longtemps est en panne.
STRICT_TIMEOUT_S = 180.0


def _strict_match(
    source: str, found: DeezerCandidate | Candidate, variant: RadioVariant
) -> Match:
    return Match(
        source=source,
        platform=found.platform,
        id=found.id,
        url=found.url,
        title=found.title,
        artists=found.artists,
        album=found.album,
        duration_s=found.duration_ms / 1000 if found.duration_ms else None,
        isrc=found.isrc,
        artist_id=found.artist_id,
        why=variant.why,
        credited=variant.credited,
    )


def _meta(found: DeezerCandidate | Candidate) -> Meta:
    return Meta(found.title, found.artists, found.duration_ms, found.album)


def find_radio_track(
    http: Http,
    track: RadioTrack,
    *,
    platforms: Platforms = NONE,
    timeout: float = STRICT_TIMEOUT_S,
) -> Match | None:
    """Le morceau du fichier, à la lettre près, ou None.

    En cascade, chacune pour ce que les précédentes ont manqué : chez Deezer, chaque
    variante du texte ; chez Tidal, trois, puis le même morceau chez Deezer par son
    ISRC ; chez Apple Music, deux, sous son quota de 20 requêtes par minute ; parmi
    les sorties les plus écoutées de l'artiste chez Deezer, pour un titre que sa
    recherche ne trouve pas sous ce nom, deux ; chez Bandcamp, deux, sur le compte de
    l'artiste seulement. Tidal, Apple Music et Bandcamp seulement allumés
    (`platforms`). Lève l'erreur d'une source qui n'a pas répondu si rien ne l'a
    trouvé ailleurs : l'absence n'est alors pas sûre.
    """
    deadline = http.clock.now() + timeout
    variants = radio_variants(track)
    seen: set[str] = set()

    def deezer(variant: RadioVariant) -> list[DeezerCandidate]:
        artist = next(iter(split_artists([variant.artist])), "")
        return deezer_search(http, artist, search_terms(variant.title))

    def releases(variant: RadioVariant) -> list[DeezerCandidate]:
        name = squash(variant.artist)
        if name in seen:
            return []
        seen.add(name)
        namesakes = [
            artist
            for artist in deezer_artists(http, variant.artist)
            if squash(artist.name) == name
        ][:2]
        return [
            found
            for artist in namesakes
            for upc in deezer_releases(http, artist.id)
            for found in deezer_album_tracks(http, upc)
        ]

    def tidal(variant: RadioVariant) -> list[DeezerCandidate | Candidate]:
        """Le morceau Tidal, puis le même chez Deezer par son ISRC, jugé à son tour.
        Deezer en panne n'y change rien : le morceau de Tidal reste."""
        assert platforms.tidal is not None
        found = [
            one
            for one in platforms.tidal.search(variant.artist, variant.title)
            if same_radio_track(variant, _meta(one))
        ]
        isrc = next((one.isrc for one in found if one.isrc), None)
        again: list[DeezerCandidate] = []
        if isrc:
            try:
                again = deezer_by_isrc(http, isrc)
            except HttpError:
                again = []
        same = [one for one in again if same_radio_track(variant, _meta(one))]
        return [*same, *found]

    def apple(variant: RadioVariant) -> list[Candidate]:
        return apple_search(http, variant.artist, variant.title)

    def bandcamp(variant: RadioVariant) -> list[Candidate]:
        """Le compte de l'artiste seulement : sans album à comparer, un compte de
        label ne prouve rien."""
        found = bandcamp_search(http, variant.artist, variant.title)
        return [one for one in found if not one.by_label]

    steps: list[tuple[str, int, _Step]] = [("deezer", len(variants), deezer)]
    if platforms.tidal:
        steps.append(("tidal", 3, tidal))
    if platforms.apple:
        steps.append(("apple", 2, apple))
    steps.append(("deezer (sorties de l'artiste)", 2, releases))
    if platforms.bandcamp:
        steps.append(("bandcamp", 2, bandcamp))
    failure: HttpError | None = None
    for source, count, find in steps:
        for variant in variants[:count]:
            if http.clock.now() > deadline:
                raise HttpError("Recherche à la lettre près trop longue")
            try:
                candidates = find(variant)
            except HttpError as error:
                failure = error
                continue
            for found in candidates:
                if same_radio_track(variant, _meta(found)):
                    return _strict_match(source, found, variant)
    if failure:
        raise failure
    return None


# ===== La seconde passe =====


def _deezer_query(query: str, limit: int) -> str:
    return f"{DEEZER}/search?q={component(query)}&limit={limit}"


def _from_deezer(hit: DeezerHit, why: Sequence[str]) -> Match:
    return Match(
        source="rapprochement",
        platform="deezer",
        id=hit.id,
        url=hit.url,
        title=hit.title,
        artists=(hit.artist,),
        album=hit.album,
        duration_s=hit.duration_s,
        artist_id=hit.artist_id,
        why=tuple(why),
        credited=hit.artist,
    )


def _from_musicbrainz(
    recording: MbRecording, why: Sequence[str], source: str = "rapprochement"
) -> Match:
    return Match(
        source=source,
        platform="musicbrainz",
        id=recording.id,
        url=f"https://musicbrainz.org/recording/{recording.id}",
        title=recording.title,
        artists=(recording.credit,),
        album=first_release(recording.releases),
        duration_s=recording.length_ms / 1000 if recording.length_ms else None,
        isrc=next(iter(recording.isrcs), None),
        artist_id=next(iter(recording.artist_ids), None),
        why=tuple(why),
        credited=recording.credit,
        date=recording.date,
        compilation=recording.compilation,
    )


def _deezer_candidate(hit: DeezerHit, *, from_album: bool = False) -> ThirdCandidate:
    return ThirdCandidate(
        hit.title,
        (hit.artist,),
        _milliseconds(hit.duration_s),
        from_album=from_album,
    )


def _recording_candidate(recording: MbRecording) -> ThirdCandidate:
    return ThirdCandidate(recording.title, (recording.credit,), recording.length_ms)


def _loose_queries(variant: RadioTrack, *, first: bool) -> list[str]:
    """Deux requêtes pour la première variante, plus le titre seul pour un artiste
    mal écrit ; une pour la seconde."""
    artist, title = quoteless(variant.artist), quoteless(variant.title)
    queries = [f'artist:"{artist}" track:"{title}"']
    if first:
        queries.append(f"{artist} {title}")
        if len(squash(title)) >= 8:
            queries.append(title)
    return queries


def _loosely_on_deezer(
    http: Http, item: Track, variants: Sequence[RadioTrack]
) -> _Hit | None:
    judged: list[_Hit] = []
    for index, variant in enumerate(variants[:2]):
        for query in _loose_queries(variant, first=index == 0):
            for hit in http.fetch(_deezer_query(query, 25), prune_deezer_search) or []:
                verdict = loose_judge(
                    item, variant, _deezer_candidate(hit), item.length
                )
                judged += _hit(verdict, hit)
        if judged:
            break
    return best(judged)


def _loosely_on_musicbrainz(http: Http, item: Track, first: RadioTrack) -> _Hit | None:
    """L'enregistrement seul, qui donne l'année, le disque et l'artiste."""
    title, artist = quoteless(first.title), quoteless(first.artist)
    query = f'recording:"{title}" AND artist:"{artist}"'
    judged: list[_Hit] = []
    for recording in musicbrainz_recordings(http, query, 10):
        if recording.score >= 80:
            candidate = _recording_candidate(recording)
            judged += _hit(loose_judge(item, first, candidate, item.length), recording)
    return best(judged)


def _from_platform(platform: str, found: Candidate, why: Sequence[str]) -> Match:
    """Un morceau rapproché chez Tidal, Apple Music ou Bandcamp."""
    return Match(
        source="rapprochement",
        platform=platform,
        id=found.id,
        url=found.url,
        title=found.title,
        artists=found.artists,
        album=found.album,
        duration_s=found.duration_ms / 1000 if found.duration_ms else None,
        isrc=found.isrc,
        why=tuple(why),
        credited=", ".join(found.artists),
        date=found.release_date,
    )


def _platform_candidate(found: Candidate) -> ThirdCandidate:
    return ThirdCandidate(found.title, found.artists, found.duration_ms)


def _loosely_on_bandcamp(http: Http, item: Track, first: RadioTrack) -> Match | None:
    """Bandcamp, comptes de label compris : la durée tient lieu de preuve."""
    judged: list[_Hit] = []
    for found in bandcamp_search(http, first.artist, first.title):
        candidate = _platform_candidate(found)
        judged += _hit(loose_judge(item, first, candidate, item.length), found)
    hit = best(judged)
    return _from_platform("bandcamp", hit.found, hit.why) if hit else None


def find_loosely(http: Http, item: Track, platforms: Platforms = NONE) -> Match | None:
    """Le morceau, rapproché : chez Deezer, deux requêtes de la recherche, plus le
    titre seul pour un artiste mal écrit ; puis dans MusicBrainz, l'enregistrement,
    avec sa durée, sans lien d'écoute ; puis chez Bandcamp, allumé, comptes de label
    compris. La même version d'abord, au plus petit écart de durée ; None sinon."""
    if js_falsy(item.length):
        return None
    variants = loose_variants(item)
    if not variants or generic_title(variants[0].title):
        return None
    on_deezer = _loosely_on_deezer(http, item, variants)
    if on_deezer:
        return _from_deezer(on_deezer.found, on_deezer.why)
    on_musicbrainz = _loosely_on_musicbrainz(http, item, variants[0])
    if on_musicbrainz:
        return _from_musicbrainz(on_musicbrainz.found, on_musicbrainz.why)
    if platforms.bandcamp:
        return _loosely_on_bandcamp(http, item, variants[0])
    return None


# ===== La troisième passe =====

_SPACES = js_regex(r"\s+")
# Un morceau de l'album du fichier, retrouvé chez Deezer.
IN_RADIO_ALBUM = "dans l'album de la radio"


class _Harder:
    """La troisième passe d'un titre : ses lectures, et ses quatre recherches."""

    def __init__(
        self,
        http: Http,
        item: Track,
        every: list[Reading],
        platforms: Platforms = NONE,
    ) -> None:
        self.http = http
        self.platforms = platforms
        self.item = item
        self.every = every
        self.fixed = [reading for reading in every if reading.fix]
        self.album = js_trim(item.album)
        # L'album du fichier peut se passer de l'artiste s'il en est un vrai.
        self.album_ok = album_ok(self.album, item.artist)

    def judge(
        self,
        candidates: Iterable[tuple[ThirdCandidate, object]],
        among: Sequence[Reading] | None = None,
    ) -> _Hit | None:
        """Le meilleur candidat, toutes lectures confondues : la même version
        d'abord, puis le plus petit écart de durée."""
        candidates = list(candidates)
        judged: list[_Hit] = []
        for reading in self.every if among is None else among:
            for candidate, found in candidates:
                verdict = third_judge(
                    self.item, reading, candidate, self.item.length, self.album_ok
                )
                judged += _hit(verdict, found)
        return best(judged)

    def on_deezer(
        self,
        hits: Iterable[DeezerHit],
        among: Sequence[Reading] | None = None,
        *,
        from_album: bool = False,
    ) -> _Hit | None:
        candidates = (
            (_deezer_candidate(hit, from_album=from_album), hit) for hit in hits
        )
        return self.judge(candidates, among)

    def search(self, query: str, limit: int) -> list[DeezerHit]:
        return self.http.fetch(_deezer_query(query, limit), prune_deezer_search) or []

    def reread(self) -> Match | None:
        """1. Deezer, avec le texte relu."""
        for reading in self.fixed:
            artist, title = quoteless(reading.artist), quoteless(reading.title)
            for query in (f'artist:"{artist}" track:"{title}"', f"{artist} {title}"):
                found = self.on_deezer(self.search(query, 25), [reading])
                if found:
                    return _from_deezer(found.found, found.why)
        return None

    def artist_tracks(self) -> Match | None:
        """2. Deezer, tous les morceaux de l'artiste ; un artiste coupé à 30 signes,
        sans son dernier mot."""
        for artist in list(dict.fromkeys(reading.artist for reading in self.every))[:2]:
            name = artist
            if len(js_trim(artist)) >= 28:
                name = " ".join(_SPACES.split(js_trim(artist))[:-1])
            found = self.on_deezer(self.search(f'artist:"{quoteless(name)}"', 100))
            if found:
                why = (*found.why, "parmi les morceaux de l'artiste")
                return _from_deezer(found.found, why)
        return None

    def album_tracks(self) -> Match | None:
        """3. Deezer, l'album du fichier, une compilation souvent : ses morceaux. Le
        même album, ou son début : un catalogue coupe les noms longs."""
        album = self.album
        if len(_SPACES.sub("", album)) < 6 or PLACEHOLDER.fullmatch(album):
            return None
        url = f"{DEEZER}/search/album?q={component(quoteless(album))}&limit=10"
        near = [
            one
            for one in self.http.fetch(url, prune_albums) or []
            if nearly_same(one.title, album)
            or (
                len(squash(album)) >= 12 and squash(one.title).startswith(squash(album))
            )
        ]
        for one in near[:3]:
            url = f"{DEEZER}/album/{one.id}/tracks?limit=200"
            tracks = self.http.fetch(url, prune_deezer_search) or []
            hits = [replace(hit, album=one.title) for hit in tracks]
            found = self.on_deezer(hits, from_album=True)
            if found:
                why = (
                    found.why
                    if IN_RADIO_ALBUM in found.why
                    else (*found.why, IN_RADIO_ALBUM)
                )
                return _from_deezer(found.found, why)
        return None

    def _on_platform(
        self,
        platform: str,
        search: Callable[[Http, str, str], list[Candidate]],
        among: Sequence[Reading],
    ) -> Match | None:
        """La recherche d'une plateforme, lecture par lecture, avec les règles de la
        troisième passe."""
        for reading in among:
            found = search(self.http, reading.artist, reading.title)
            candidates = ((_platform_candidate(one), one) for one in found)
            hit = self.judge(candidates, [reading])
            if hit:
                return _from_platform(platform, hit.found, hit.why)
        return None

    def tidal(self) -> Match | None:
        """4. Tidal, allumé : les deux premières lectures, et le premier texte
        relu."""
        tidal = self.platforms.tidal
        if tidal is None:
            return None
        among: list[Reading] = []
        for reading in [*self.every[:2], *self.fixed[:1]]:
            if not any(reading is other for other in among):
                among.append(reading)
        return self._on_platform(
            "tidal", lambda _, artist, title: tidal.search(artist, title), among
        )

    def apple(self) -> Match | None:
        """6. Apple Music, allumé, le plus lent : 20 recherches par minute. La
        première lecture seulement."""
        if not self.platforms.apple:
            return None
        return self._on_platform("apple", apple_search, self.every[:1])

    def fuzzy(self) -> Match | None:
        """5. MusicBrainz, en recherche floue : une faute permise par mot, le titre
        sans invité ni mention."""
        tried: list[Reading] = []
        for reading in [self.every[0], *self.fixed[:1]]:
            if any(reading is other for other in tried):
                continue
            tried.append(reading)
            title = fuzzy(parse_title(reading.title).base or reading.title)
            artist = fuzzy(reading.artist)
            if not title or not artist:
                continue
            query = f"recording:({title}) AND artist:({artist})"
            recordings = musicbrainz_recordings(self.http, query, 25)
            candidates = ((_recording_candidate(one), one) for one in recordings)
            found = self.judge(candidates, [reading])
            if found:
                return _from_musicbrainz(found.found, (*found.why, "recherche floue"))
        return None


def find_harder(http: Http, item: Track, platforms: Platforms = NONE) -> Match | None:
    """Le morceau, cherché autrement : chez Deezer avec le texte relu, puis tous les
    morceaux de l'artiste chez Deezer, où le titre n'est plus cherché mais comparé,
    puis l'album du fichier chez Deezer, Tidal, MusicBrainz en recherche floue, et
    Apple Music ; Tidal et Apple Music seulement allumés. La même version d'abord,
    au plus petit écart ; None sinon."""
    if js_falsy(item.length):
        return None
    every = readings(RadioTrack(item.artist, item.title), item.album)
    if not every:
        return None
    harder = _Harder(http, item, every, platforms)
    for step in (
        harder.reread,
        harder.artist_tracks,
        harder.album_tracks,
        harder.tidal,
        harder.fuzzy,
        harder.apple,
    ):
        match = step()
        if match:
            return match
    return None


# ===== L'empreinte =====

# Cinq enregistrements au plus, du meilleur résultat d'AcoustID, d'un score de 0,5 au
# moins : comme `chroma`.
ACOUSTID_SCORE = 0.5
ACOUSTID_RECORDINGS = 5
# Un fichier sans artiste, ou au titre vide de sens, ne prend le texte de l'empreinte
# qu'à 0,9, et à 7 s près.
ACOUSTID_ALONE = 0.9
ALONE_TOLERANCE_S = 7


@dataclass(frozen=True)
class ByFingerprint:
    """Ce que l'empreinte dit d'un titre : le morceau qu'elle trouve, et son état
    (« trouvé » ou « rapproché ») ; ou ce qu'elle dit contre le texte du fichier
    (`doubt`), un tout autre morceau, ou une autre version."""

    status: str = ""
    match: Match | None = None
    doubt: str = ""


def _gap(recording: MbRecording, seconds: float | None) -> float | None:
    if js_falsy(recording.length_ms) or js_falsy(seconds):
        return None
    return abs(recording.length_ms / 1000 - seconds)  # type: ignore[operator]


# « Miles Davis - So What », « 01 - So What » : un titre de fichier sans artiste.
_DASH = js_regex(r"\s+[-\u2013]\s+")


def _alone(
    item: Track, recordings: Sequence[MbRecording], score: float
) -> ByFingerprint:
    """Un fichier sans artiste, ou au titre vide de sens : le titre et l'artiste de
    l'empreinte, d'un score de 0,9 au moins, à 7 s près.

    Ce que le fichier sait de lui doit s'y retrouver : son artiste, s'il en a un ;
    son titre, s'il a un sens. Un lien d'AcoustID peut être faux. Sinon, c'est un
    autre morceau.
    """
    has_artist = bool(js_trim(item.artist))
    titles = [] if meaningless_title(item.title) else [item.title]
    titles += _DASH.split(item.title)[-1:] if titles else []

    def agrees(recording: MbRecording) -> bool:
        credit, title = (recording.credit,), recording.title
        return (not has_artist or bool(any_artist(item.artist, credit, title))) and (
            not titles or any(any_title(one, title) for one in titles)
        )

    if score >= ACOUSTID_ALONE:
        for recording in recordings:
            gap = _gap(recording, item.length)
            if agrees(recording) and gap is not None and gap <= ALONE_TOLERANCE_S:
                match = _from_musicbrainz(recording, (FROM_FINGERPRINT,), FINGERPRINT)
                return ByFingerprint("trouvé", match)
    if (has_artist or titles) and not any(map(agrees, recordings)):
        return ByFingerprint(doubt=OTHER_PIECE)
    return ByFingerprint()


def _letter(item: Track, recordings: Sequence[MbRecording]) -> ByFingerprint | None:
    """Un enregistrement au même texte, à la lettre près, et à 10 s près."""
    variants = radio_variants(RadioTrack(item.artist, item.title))
    for recording in recordings:
        meta = Meta(recording.title, (recording.credit,), recording.length_ms)
        variant = next((one for one in variants if same_radio_track(one, meta)), None)
        seconds = recording.length_ms / 1000 if recording.length_ms else None
        if variant and duration_level(item.length, seconds).level == "sûr":
            match = _from_musicbrainz(recording, variant.why, FINGERPRINT)
            return ByFingerprint("trouvé", replace(match, credited=variant.credited))
    return None


def _close(
    item: Track, texts: Sequence[RadioTrack], recordings: Sequence[MbRecording]
) -> ByFingerprint | None:
    """Un enregistrement au texte proche, selon la seconde passe, à 7 s près."""
    judged: list[_Hit] = []
    for variant in texts:
        for recording in recordings:
            candidate = _recording_candidate(recording)
            judged += _hit(
                loose_judge(item, variant, candidate, item.length), recording
            )
    found = best(judged)
    if not found:
        return None
    return ByFingerprint(
        "rapproché", _from_musicbrainz(found.found, found.why, FINGERPRINT)
    )


def _same_piece(texts: Iterable[RadioTrack], recording: MbRecording) -> bool:
    """L'enregistrement est-il le morceau du fichier, d'après son texte seul, quelles
    que soient sa durée et sa version ?"""
    return any(
        any_artist(text.artist, (recording.credit,), recording.title)
        and any_title(text.title, recording.title)
        for text in texts
    )


def _doubt(
    item: Track, texts: Sequence[RadioTrack], recordings: Sequence[MbRecording]
) -> str:
    """Ce que l'empreinte dit contre le texte du fichier, qu'elle n'a pas trouvé.

    Aucun de ses enregistrements n'a l'artiste et le titre du fichier : un tout autre
    morceau. Ceux qui les ont, à la durée du fichier, sont tous d'une autre version :
    une autre version, jamais un autre remix. Le même morceau à une autre durée est
    une autre édition, que le texte cherchera : rien à en dire.
    """
    every = [*texts, *readings(RadioTrack(item.artist, item.title), item.album)]
    same = [recording for recording in recordings if _same_piece(every, recording)]
    if not same:
        return OTHER_PIECE
    near = [
        recording
        for recording in same
        if (gap := _gap(recording, item.length)) is not None
        and gap <= LOOSE_TOLERANCE_S
    ]
    other = [
        recording
        for recording in near
        if not any(versions(text.title, recording.title) == "mêmes" for text in texts)
    ]
    return OTHER_VERSION if near and other == near else ""


def by_fingerprint(http: Http, item: Track, print_: Print, key: str) -> ByFingerprint:
    """Le morceau d'une empreinte, vérifié par le texte et la durée du fichier.

    - Un enregistrement au même titre et aux mêmes artistes, à la lettre près, et de
      la même durée à 10 s près : trouvé, `sûr`.
    - Au texte proche, selon les règles de la seconde passe, à 7 s près : rapproché,
      `à revoir`, l'empreinte confirmant le son.
    - Un fichier sans artiste, ou au titre vide de sens, prend le titre et l'artiste
      de l'empreinte, d'un score de 0,9 au moins, à 7 s près : `à revoir`.
    - Une empreinte qui désigne un tout autre morceau, ou le même dans une autre
      version, ne trouve rien : le titre passe aux étapes suivantes, mais ne sera
      jamais plus que `à revoir`.
    """
    results = acoustid_lookup(http, key, print_.fingerprint, int(print_.duration))
    top = max(results, key=lambda result: result.score, default=None)
    if js_falsy(item.length) or top is None or top.score < ACOUSTID_SCORE:
        return ByFingerprint()
    recordings = [
        recording
        for recording_id in list(dict.fromkeys(top.recordings))[:ACOUSTID_RECORDINGS]
        if (recording := musicbrainz_recording(http, recording_id))
    ]
    if not recordings:
        return ByFingerprint()
    if js_trim(item.artist) and js_trim(item.title):
        found = _letter(item, recordings)
        if found:
            return found
    if not js_trim(item.artist) or meaningless_title(item.title):
        return _alone(item, recordings, top.score)
    texts = loose_variants(item)
    found = _close(item, texts, recordings)
    return found or ByFingerprint(doubt=_doubt(item, texts, recordings))


# ===== Les détails =====


def _accept(match: Match, item: Track) -> Callable[[str], bool]:
    """Le nom d'un artiste rejoint par identifiant doit être l'un de ceux du fichier,
    tels que la variante retenue les lit."""
    radio = _first(match.credited, item.artist)
    return lambda name: same_artist_name(radio, name)


def details_for(http: Http, match: Match, item: Track, *, verdict: bool) -> Details:
    """Les détails d'un titre trouvé : le morceau Deezer, par son identifiant ou son
    ISRC, et son album ; trouvé chez Apple Music, son genre et sa date ;
    l'enregistrement MusicBrainz par son ISRC, et l'artiste, par le crédit ou par sa
    page Deezer. Sans année dans le fichier, l'album aussi, pour sa première
    sortie."""
    deezer = deezer_details(http, match.platform, match.id, clean_isrc(match.isrc))
    apple = apple_details(http, match.id) if match.platform == "apple" else None
    fingerprinted = match.source == FINGERPRINT
    # Sans année dans le fichier, l'album pour sa première sortie ; un enregistrement
    # trouvé par l'empreinte a déjà la sienne.
    year_missing = not 1000 <= item.year <= 9999
    album = None
    if year_missing and not (fingerprinted and match.date):
        album = _first(
            deezer.album.title if deezer and deezer.album else None,
            apple.album if apple else None,
            match.album,
        )
    musicbrainz = musicbrainz_details(
        http,
        isrc=clean_isrc(_first(match.isrc, deezer.isrc if deezer else None)),
        deezer_artist_id=_first(
            deezer.artist_id if deezer else None,
            match.artist_id if match.platform == "deezer" else None,
        ),
        # L'enregistrement trouvé par l'empreinte crédite déjà l'artiste.
        artist_id=match.artist_id if fingerprinted else None,
        album=album,
        accept=_accept(match, item),
        verdict=verdict,
    )
    if fingerprinted:
        recorded = _first(match.date, musicbrainz.recording_date)
        musicbrainz = replace(musicbrainz, recording_date=recorded)
    return Details(deezer=deezer, apple=apple, musicbrainz=musicbrainz)


def loose_details(http: Http, match: Match, item: Track, *, verdict: bool) -> Details:
    """Les détails d'un titre rapproché : ceux de Deezer, comme à la lettre près (de
    Tidal, le même morceau chez Deezer par son ISRC ; d'Apple Music, aussi son
    genre) ; d'un enregistrement MusicBrainz, son artiste et sa première sortie ; de
    Bandcamp, rien de plus : MusicBrainz a déjà été cherché."""
    if match.platform in ("deezer", "tidal", "apple") or match.source == FINGERPRINT:
        return details_for(http, match, item, verdict=verdict)
    if match.platform != "musicbrainz" or not match.artist_id:
        return Details()
    musicbrainz = musicbrainz_details(
        http, artist_id=match.artist_id, accept=lambda _: True, verdict=verdict
    )
    recorded = _first(match.date, musicbrainz.recording_date)
    return Details(musicbrainz=replace(musicbrainz, recording_date=recorded))


# ===== La recherche d'un titre =====


@dataclass(frozen=True)
class Search:
    """Ce que la recherche d'un titre a trouvé.

    `result` et `wikidata` servent à `build_row` tout de suite, verdict compris :
    verdict allumé, ils portent le genre déclaré de personnes. Ce qui se garde, ce
    sont les preuves (`evidence`), qui n'en portent aucun.
    """

    result: SearchResult
    wikidata: Mapping[str, WikidataArtist] = field(default_factory=dict)
    # La panne qui a mis le titre en erreur, pour la tâche : un disjoncteur ouvert
    # (`CircuitOpenError`) attend une minute. Elle ne se garde pas.
    failure: HttpError | None = field(default=None, compare=False)

    def evidence(self) -> Search:
        """Les preuves à garder : ce que les sources ont dit, sans le genre d'une
        personne ni les membres d'un groupe. Elles refont les propositions sans
        réseau, sauf le verdict."""
        details = self.result.details
        if details and details.musicbrainz and details.musicbrainz.artist:
            artist = replace(details.musicbrainz.artist, gender=None, members=())
            musicbrainz = replace(details.musicbrainz, artist=artist)
            details = replace(details, musicbrainz=musicbrainz)
        wikidata = {
            key: WikidataArtist(item=one.item, names=one.names, human=one.human)
            for key, one in self.wikidata.items()
        }
        return Search(replace(self.result, details=details), wikidata)


class Searcher:
    """La recherche des fiches : son client, la clé AcoustID, le verdict, et les
    sources de FON-30 allumées.

    Une seule pour toute la tâche de fond : ses seaux et ses disjoncteurs sont
    partagés, et elle ne dit qu'une fois au journal que l'empreinte ou Tidal est
    sauté. `wikidata` : les fiches Wikidata déjà lues, en mémoire seulement.
    `sources` : Tidal, Apple Music et Bandcamp, tous éteints par défaut ; Tidal
    allumé sans clé d'application est sauté.
    """

    def __init__(
        self,
        http: Http,
        *,
        acoustid_key: str | None = None,
        verdict: bool = False,
        wikidata: MutableMapping[str, WikidataArtist | None] | None = None,
        sources: SourceSettings | None = None,
    ) -> None:
        self.http = http
        self.acoustid_key = acoustid_key
        self.verdict = verdict
        self.wikidata: MutableMapping[str, WikidataArtist | None] = (
            {} if wikidata is None else wikidata
        )
        self._said: set[str] = set()
        sources = sources or SourceSettings()
        tidal = None
        if sources.tidal and sources.tidal_key:
            tidal = Tidal(http, sources.tidal_client_id, sources.tidal_client_secret)
        elif sources.tidal:
            self._once("tidal", "fiches : Tidal allumé sans clé d'application, sauté")
        self.platforms = Platforms(tidal, sources.apple, sources.bandcamp)
        # Les clés qu'AcoustID a refusées : la passe les saute sans redemander.
        self._refused: set[str] = set()

    def search(self, item: Track, fingerprint: Print | None = None) -> Search:
        """Un titre, de l'empreinte aux détails.

        `fingerprint` : son empreinte, si `fpcalc` a pu la prendre. Un titre sans
        durée est écarté, comme une annonce ou un jingle ; un titre sans artiste
        aussi, si l'empreinte ne le trouve pas. Une panne, même de la seule
        empreinte, met le titre en erreur : l'absence n'est pas sûre, ni le morceau
        que l'empreinte n'a pas pu vérifier.
        """
        artist, title = js_trim(item.artist), js_trim(item.title)
        reason = "sans durée" if js_falsy(item.length) else ""
        if reason or is_announcement(RadioTrack(artist, title)):
            return Search(SearchResult("écarté", reason=reason))
        by_print, failure = self._fingerprint(item, fingerprint)
        if by_print.match:
            return self._found(item, by_print.status, by_print.match)
        found = None
        if artist and title:
            try:
                found = self._text(item, RadioTrack(artist, title))
            except HttpError as error:
                failure = error
        elif not failure:
            return Search(SearchResult("écarté"))
        if failure:
            match = found[1] if found else None
            result = SearchResult("erreur", match, error=str(failure))
            return Search(replace(result, doubt=by_print.doubt), failure=failure)
        if found:
            return self._found(item, *found, doubt=by_print.doubt)
        return Search(SearchResult("rien", doubt=by_print.doubt))

    def _fingerprint(
        self, item: Track, fingerprint: Print | None
    ) -> tuple[ByFingerprint, HttpError | None]:
        """L'empreinte, s'il y en a une et une clé pour AcoustID. Sans clé, ou avec
        une clé refusée, la passe est sautée, et le journal le dit une fois."""
        key = self.acoustid_key
        if fingerprint is None:
            return ByFingerprint(), None
        if not key:
            self._once("clé", "fiches : pas de clé AcoustID, l'empreinte est sautée")
            return ByFingerprint(), None
        if key in self._refused:
            return ByFingerprint(), None
        try:
            found = by_fingerprint(self.http, item, fingerprint, key)
        except AcoustidKeyError:
            self._refused.add(key)
            _log.warning("fiches : AcoustID refuse la clé, l'empreinte est sautée")
            return ByFingerprint(), None
        except HttpError as error:
            return ByFingerprint(), error
        return found, None

    def _text(self, item: Track, track: RadioTrack) -> tuple[str, Match] | None:
        """À la lettre près, puis la seconde et la troisième passe."""
        platforms = self.platforms
        match = find_radio_track(self.http, track, platforms=platforms)
        if match:
            return "trouvé", match
        match = find_loosely(self.http, item, platforms) or find_harder(
            self.http, item, platforms
        )
        return ("rapproché", match) if match else None

    def _found(
        self, item: Track, status: str, match: Match, *, doubt: str = ""
    ) -> Search:
        """Le morceau trouvé et ses détails ; une panne pendant les détails garde le
        morceau, et met le titre en erreur."""
        try:
            if status == "trouvé":
                details = details_for(self.http, match, item, verdict=self.verdict)
            else:
                details = loose_details(self.http, match, item, verdict=self.verdict)
            wikidata = self._wikidata(match, details) if self.verdict else {}
        except HttpError as error:
            result = SearchResult("erreur", match, error=str(error), doubt=doubt)
            return Search(result, failure=error)
        return Search(SearchResult(status, match, details, doubt=doubt), wikidata)

    def _wikidata(self, match: Match, details: Details) -> dict[str, WikidataArtist]:
        """L'artiste dans Wikidata, par son identifiant Deezer ou MusicBrainz."""
        deezer = _first(
            details.deezer.artist_id if details.deezer else None,
            match.artist_id if match.platform == "deezer" else None,
        )
        musicbrainz = details.musicbrainz
        artist = musicbrainz.artist.id if musicbrainz and musicbrainz.artist else None
        return wikidata_artists(
            self.http,
            self.wikidata,
            [deezer] if deezer else [],
            [artist] if artist else [],
        )

    def _once(self, what: str, message: str) -> None:
        if what not in self._said:
            self._said.add(what)
            _log.warning(message)
