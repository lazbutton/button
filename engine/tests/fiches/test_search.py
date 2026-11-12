"""La recherche d'un titre, sur de faux services.

Les cas de recherche de Hopper : « la cascade » de `tests/radio.test.ts`, et, de
`tests/radio-catalogue.test.ts`, « cherche chez Deezer, puis MusicBrainz, puis
Bandcamp » et « cherche avec le texte relu, l'album de la radio, Tidal, puis
MusicBrainz en recherche floue ». Bandcamp, Tidal et Apple Music viendront avec
FON-30 : leurs cas ne trouvent rien ici. Puis l'empreinte, le verdict, les pannes et
les preuves gardées.
"""

import dataclasses
import logging

import pytest

from radiotomate.fiches.fingerprint import Fpcalc, Print
from radiotomate.fiches.http import Cache, CircuitOpenError, HttpError
from radiotomate.fiches.loose import CLEANED
from radiotomate.fiches.proposals import (
    FINGERPRINT,
    OTHER_PIECE,
    OTHER_VERSION,
    Track,
    build_row,
    proposals,
)
from radiotomate.fiches.search import (
    Searcher,
    by_fingerprint,
    find_harder,
    find_loosely,
    find_radio_track,
)
from radiotomate.fiches.sources import ACOUSTID, component
from radiotomate.fiches.third import SWAPPED
from radiotomate.fiches.variants import RadioTrack
from tests.fiches.fakes import Services, fake_fpcalc, http

MB = "https://musicbrainz.org/ws/2"
DEEZER = "https://api.deezer.com"
SELEEM = RadioTrack("Seleem", "Swarm Behaviour")


def _deezer_track(track_id, title="Swarm Behaviour", artist="Seleem", **extra):
    return {
        "id": track_id,
        "title": title,
        "duration": 240,
        "artist": {"id": 7, "name": artist},
        **extra,
    }


# ===== La cascade, à la lettre près =====


def test_deezer_first():
    services = Services(
        answer=lambda url: {"data": [_deezer_track(42)]}
        if url.startswith(f"{DEEZER}/search?q=")
        else None
    )
    found = find_radio_track(http(services), SELEEM)
    assert found is not None
    assert (found.source, found.platform, found.id) == ("deezer", "deezer", "42")
    assert found.url == "https://www.deezer.com/track/42"
    query = component('artist:"seleem" track:"swarm behaviour"')
    assert services.asked[0] == f"{DEEZER}/search?q={query}&limit=10"


def test_a_deezer_namesake_with_another_title_is_worth_nothing():
    services = Services(
        answer=lambda url: {"data": [_deezer_track(1, title="Swarm")]}
        if url.startswith(f"{DEEZER}/search?q=")
        else None
    )
    assert find_radio_track(http(services), SELEEM) is None


def test_an_unreadable_deezer_track_is_never_taken():
    services = Services(
        answer=lambda url: {"data": [_deezer_track(1, readable=False)]}
        if url.startswith(f"{DEEZER}/search?q=")
        else None
    )
    assert find_radio_track(http(services), SELEEM) is None


def test_a_source_that_does_not_answer_is_an_error_not_an_absence():
    services = Services(answer=lambda url: (503, None))
    with pytest.raises(HttpError, match="503"):
        find_radio_track(http(services), SELEEM)


def test_the_artists_releases_find_what_the_search_misses():
    """Les sorties les plus écoutées de l'artiste, pour un titre que la recherche
    ne trouve pas sous ce nom : l'homonyme le plus écouté d'abord."""
    services = Services(
        {
            f"{DEEZER}/search/artist?q=Seleem&limit=25": {
                "data": [
                    {"id": 8, "name": "Seleem", "nb_fan": 3},
                    {"id": 7, "name": "Seleem", "nb_fan": 300},
                    {"id": 9, "name": "Seleem Trio", "nb_fan": 900},
                ]
            },
            f"{DEEZER}/artist/7/albums?limit=100": {
                "data": [{"id": 70, "record_type": "single", "fans": 1}]
            },
            f"{DEEZER}/album/70": {
                "id": 70,
                "upc": "602527856865",
                "artist": {"id": 7},
            },
            f"{DEEZER}/album/upc:0602527856865": {
                "id": 70,
                "title": "Swarm",
                "tracks": {"data": [_deezer_track(43)]},
            },
        }
    )
    found = find_radio_track(http(services), SELEEM)
    assert found is not None
    assert found.source == "deezer (sorties de l'artiste)"
    assert found.id == "43"
    assert found.album == "Swarm"
    assert f"{DEEZER}/artist/9/albums?limit=100" not in services.asked


def _shared_album():
    """Deux titres de Seleem sur l'album 70 : « Swarm Behaviour », que la recherche
    trouve, et « Moth », rangé seulement parmi ses sorties."""
    album = {"id": 70, "title": "Swarm"}
    answers = {
        f"{DEEZER}/search/artist?q=Seleem&limit=25": {
            "data": [{"id": 7, "name": "Seleem", "nb_fan": 3}]
        },
        f"{DEEZER}/artist/7/albums?limit=100": {
            "data": [{"id": 70, "record_type": "single", "fans": 1}]
        },
        f"{DEEZER}/album/70": {
            **album,
            "upc": "602527856865",
            "artist": {"id": 7},
            "label": "Label",
            "release_date": "2020-03-06",
            "record_type": "single",
            "genres": {"data": [{"id": 1, "name": "Dance"}]},
        },
        f"{DEEZER}/album/upc:0602527856865": {
            **album,
            "tracks": {"data": [_deezer_track(43, "Moth")]},
        },
        f"{DEEZER}/track/42": _deezer_track(42, album=album),
        f"{DEEZER}/track/43": _deezer_track(43, "Moth", album=album),
    }

    def answer(url):
        if url.startswith(f"{DEEZER}/search?q=") and "swarm" in url:
            return {"data": [_deezer_track(42, album=album)]}
        if url.startswith(f"{DEEZER}/search?q="):
            return {"data": []}
        return None

    return Services(answers, answer)


@pytest.mark.parametrize("first", ["Moth", "Swarm Behaviour"])
def test_the_cache_keeps_each_reading_of_an_album_apart(first):
    """Les sorties de l'artiste et les détails lisent la même page d'album, chacun à
    sa façon : avec le cache, dans un ordre comme dans l'autre, chacun la lit
    bien."""
    searcher = Searcher(http(_shared_album(), cache=Cache()))
    titles = [first, *(one for one in ("Moth", "Swarm Behaviour") if one != first)]
    for title in titles:
        found = searcher.search(Track(title=title, artist="Seleem", length=240))
        assert found.result.status == "trouvé"
        assert found.result.details.deezer.album.genres == ("Dance",)
        assert found.result.details.deezer.album.label == "Label"


def test_the_strict_search_gives_up_after_three_minutes():
    services = Services(answer=lambda url: {"data": []})
    client = http(services)

    def slow(url):
        client.clock.time += 100
        return {"data": []}

    services.answer = slow
    with pytest.raises(HttpError, match="trop longue"):
        find_radio_track(client, RadioTrack("Seleem", "Swarm Behaviour (Remix)"))


# ===== La seconde passe =====


class Answers:
    """Les réponses des cas de Hopper : une pour Deezer, une pour MusicBrainz."""

    def __init__(self) -> None:
        self.deezer: list = []
        self.musicbrainz: list = []

    def __call__(self, url):
        if url.startswith(f"{DEEZER}/"):
            return {"data": self.deezer}
        if url.startswith("https://musicbrainz.org/"):
            return {"recordings": self.musicbrainz}
        return None


def _loose(answers, artist, title, seconds):
    return find_loosely(
        http(Services(answer=answers)),
        Track(title=title, artist=artist, length=seconds),
    )


def test_looks_on_deezer_then_musicbrainz():
    answers = Answers()
    # Le « G » est passé du titre à l'artiste : Hopper le trouve sur un compte de
    # label Bandcamp, que FON-30 ajoutera.
    assert _loose(answers, "MR SWEETY", "G AT THE PLACE TO BE", 305) is None

    answers.musicbrainz = [
        {
            "id": "r1",
            "score": 100,
            "title": "Love Attack",
            "length": 259_000,
            "artist-credit": [
                {"name": "Shotgun", "artist": {"id": "a1", "name": "Shotgun"}}
            ],
            "first-release-date": "1978",
            "releases": [
                {
                    "title": "Good, Bad & Funky",
                    "date": "1978",
                    "release-group": {"primary-type": "Album"},
                }
            ],
        }
    ]
    found = _loose(answers, "Shotgun", "Love Attack", 259)
    assert found is not None
    assert found.platform == "musicbrainz"
    assert found.album == "Good, Bad & Funky"
    assert found.date == "1978"
    assert found.artist_id == "a1"
    assert found.url == "https://musicbrainz.org/recording/r1"
    assert found.compilation is False

    # Seule une compilation contient l'enregistrement : sa date est la sienne.
    answers.musicbrainz = [
        {
            "id": "r2",
            "score": 100,
            "title": "Get Carter",
            "length": 200_626,
            "artist-credit": [
                {"name": "Roy Budd", "artist": {"id": "a2", "name": "Roy Budd"}}
            ],
            "first-release-date": "1995",
            "releases": [
                {
                    "title": "The Sound Spectrum",
                    "date": "1995",
                    "release-group": {
                        "primary-type": "Album",
                        "secondary-types": ["Compilation"],
                    },
                }
            ],
        }
    ]
    found = _loose(answers, "Roy budd", "Get carter", 198)
    assert found is not None
    assert (found.platform, found.date, found.compilation) == (
        "musicbrainz",
        "1995",
        True,
    )

    answers.deezer = [
        {
            "id": 9,
            "title": "Oumako",
            "duration": 596,
            "artist": {"id": 7, "name": "Gnonnas Pedro"},
            "album": {"title": "La belle époque"},
            "link": "https://www.deezer.com/track/9",
        }
    ]
    found = _loose(answers, "Gonnas Pedro", "Oumako", 596)
    assert found is not None
    assert (found.platform, found.id, found.artist_id) == ("deezer", "9", "7")
    assert found.credited == "Gnonnas Pedro"

    # La même version d'abord : le fichier aurait écrit « Live ».
    answers.deezer = [
        {
            "id": 1,
            "title": "Bara to Yaju (Live at The Mayan Theatre, Los Angeles, July,2019)",
            "duration": 264,
            "artist": {"id": 5, "name": "Haruomi Hosono"},
            "link": "https://www.deezer.com/track/1",
        },
        {
            "id": 2,
            "title": "Bara To Yaju",
            "duration": 262,
            "artist": {"id": 5, "name": "Haruomi Hosono"},
            "link": "https://www.deezer.com/track/2",
        },
    ]
    found = _loose(answers, "Haruomi Hosono", "Bara To Yajuu", 264)
    assert found is not None
    assert found.id == "2"
    assert found.why == ("même artiste", "titre à une faute près", "durée à 2 s")

    # Un numéro de piste retiré : noté, pour que le titre trouvé remplace celui du
    # fichier.
    answers.deezer = [
        {
            "id": 3,
            "title": "Perambulator",
            "duration": 200,
            "artist": {"id": 6, "name": "Jimmy Smith"},
            "link": "https://www.deezer.com/track/3",
        }
    ]
    found = _loose(answers, "Jimy Smith", "01 Perambulator", 201)
    assert found is not None
    assert CLEANED in found.why


def test_the_second_pass_needs_the_files_duration_and_a_real_title():
    answers = Answers()
    answers.deezer = [_deezer_track(1, title="Intro")]
    services = Services(answer=answers)
    assert find_loosely(http(services), Track(title="Swarm", artist="Seleem")) is None
    assert (
        find_loosely(http(services), Track(title="Intro", artist="X", length=240))
        is None
    )
    assert services.asked == []


def test_the_second_pass_asks_musicbrainz_strictly_and_keeps_scores_of_80():
    answers = Answers()
    answers.musicbrainz = [
        {
            "id": "low",
            "score": 79,
            "title": "Love Attack",
            "length": 259_000,
            "artist-credit": [{"name": "Shotgun"}],
        }
    ]
    services = Services(answer=answers)
    track = Track(title="Love Attack", artist="Shotgun", length=259)
    assert find_loosely(http(services), track) is None
    query = component('recording:"Love Attack" AND artist:"Shotgun"')
    assert services.asked[-1] == f"{MB}/recording?query={query}&fmt=json&limit=10"


# ===== La troisième passe =====


class HarderAnswers:
    """Les réponses du cas de Hopper : la recherche, les albums, leurs morceaux, et
    les enregistrements de MusicBrainz."""

    def __init__(self) -> None:
        self.search: list = []
        self.albums: list = []
        self.tracks: list = []
        self.recordings: list = []

    def __call__(self, url):
        if "/search/album" in url:
            return {"data": self.albums}
        if "/album/" in url:
            return {"data": self.tracks}
        if "api.deezer.com/search" in url:
            return {"data": self.search}
        return {"recordings": self.recordings}


def _harder(answers, artist, title, seconds, album=""):
    track = Track(title=title, artist=artist, album=album, length=seconds)
    return find_harder(http(Services(answer=answers)), track)


def test_looks_with_the_reread_text_the_files_album_then_a_fuzzy_musicbrainz():
    answers = HarderAnswers()
    answers.search = [
        {
            "id": 1,
            "title": "Move Tan",
            "duration": 176,
            "artist": {"id": 2, "name": "Chouk Bwa"},
            "link": "https://www.deezer.com/track/1",
        }
    ]
    found = _harder(answers, "CHOUK BWA & THE ÅNGSTRÖMERS", "02-MOVE TAN", 176)
    assert found is not None
    assert (found.platform, found.id) == ("deezer", "1")
    assert "numéro de piste collé" in found.why

    answers.search = []
    answers.albums = [
        {"id": 9, "title": "Orkiestra Rozrywkowa PRiTV W Katowicach (Nagrania 1975)"}
    ]
    answers.tracks = [
        {
            "id": 3,
            "title": "Wśród pampasów",
            "duration": 213,
            "artist": {"id": 4, "name": "Jerzy Milian"},
            "link": "https://www.deezer.com/track/3",
        }
    ]
    found = _harder(
        answers,
        "Jerzy Milian",
        "W[rsd Pampassw",
        214,
        album="Orkiestra Rozrywkowa PRiTV",
    )
    assert found is not None
    assert found.id == "3"
    assert found.album == "Orkiestra Rozrywkowa PRiTV W Katowicach (Nagrania 1975)"
    assert found.why == (
        "même artiste",
        "titre aux accents perdus",
        "durée à 1 s",
        "dans l'album de la radio",
    )

    # Hopper trouve « Stars » de Moiré chez Tidal, que FON-30 ajoutera.
    answers.albums = []
    assert _harder(answers, "Moiri", "Stars", 314) is None

    answers.recordings = [
        {
            "id": "r9",
            "score": 90,
            "title": "Sonny's Crib",
            "length": 325_000,
            "artist-credit": [
                {"name": "John Zorn", "joinphrase": ", "},
                {"name": "George Lewis", "joinphrase": " & "},
                {"name": "Bill Frisell"},
            ],
            "releases": [],
        }
    ]
    found = _harder(answers, "Zorn Lewis Frisell", "Sonny's crib", 318)
    assert found is not None
    assert found.platform == "musicbrainz"
    assert found.why == (
        "artistes par leur nom",
        "même titre",
        "durée à 7 s",
        "recherche floue",
    )
    assert _harder(answers, "Zorn Lewis Frisell", "Sonny's crib", 310) is None


def test_the_fuzzy_query_allows_a_typo_per_word():
    """Dès quatre lettres, sur le texte normalisé : « Sonny's » devient « sonnys »."""
    answers = HarderAnswers()
    services = Services(answer=answers)
    find_harder(
        http(services),
        Track(title="Sonny's crib", artist="Zorn Lewis Frisell", length=318),
    )
    query = component("recording:(sonnys~ crib~) AND artist:(zorn~ lewis~ frisell~)")
    assert f"{MB}/recording?query={query}&fmt=json&limit=25" in services.asked


# ===== L'empreinte =====

PRINT = Print("AQADtEmUaFKSJEmS", 240.4)


def _recording(recording_id, title, artist, length_ms, **extra):
    return {
        "id": recording_id,
        "title": title,
        "length": length_ms,
        "artist-credit": [
            {"name": artist, "artist": {"id": f"{artist}-id", "name": artist}}
        ],
        **extra,
    }


def _recording_url(recording_id):
    inc = "artist-credits+isrcs+releases+release-groups"
    return f"{MB}/recording/{recording_id}?inc={inc}&fmt=json"


def _fingerprinted(recordings, score=0.97, deezer=None, results=None):
    """AcoustID, les enregistrements de MusicBrainz, et une recherche Deezer."""
    best = {
        "id": "x",
        "score": score,
        "recordings": [{"id": one["id"]} for one in recordings],
    }
    answers = {
        ACOUSTID: {"status": "ok", "results": results or [best]},
        **{_recording_url(one["id"]): one for one in recordings},
    }

    def answer(url):
        if url.startswith(f"{DEEZER}/search?q=") and deezer:
            return {"data": deezer}
        return None

    return Services(answers, answer)


def _search(services, track, **options):
    return Searcher(http(services), acoustid_key="clé-test", **options).search(
        track, PRINT
    )


def test_a_recording_with_the_same_text_within_10_s_is_sure():
    services = _fingerprinted([_recording("r1", "Swarm Behaviour", "Seleem", 245_000)])
    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    found = _search(services, track)
    assert found.result.status == "trouvé"
    assert found.result.match.source == FINGERPRINT
    assert found.result.match.id == "r1"
    row = build_row(track, found.result, found.wikidata)
    assert row.level == "sûr"
    assert row.found_at == "MusicBrainz, par l'empreinte"
    # Trouvé par l'empreinte : pas de recherche de texte.
    assert not any("/search" in url or "query=" in url for url in services.asked)
    form = services.form(0)
    assert (form["fingerprint"], form["duration"]) == ("AQADtEmUaFKSJEmS", "240")


def test_from_a_fake_fpcalc_to_the_level(tmp_path):
    """La chaîne entière : un faux `fpcalc`, son empreinte et sa durée envoyées à
    AcoustID, puis le niveau du titre."""
    audio = tmp_path / "titre.flac"
    audio.write_bytes(b"")
    taken = Fpcalc(fake_fpcalc(tmp_path, "AQADfauxFPCALC", 241.9))(audio)
    track = Track(title="Swarm Behaviour", artist="Seleem", length=241)
    searcher = Searcher(
        http(
            services := _fingerprinted(
                [_recording("r1", "Swarm Behaviour", "Seleem", 245_000)]
            )
        ),
        acoustid_key="clé-test",
    )
    found = searcher.search(track, taken)
    assert services.form(0)["fingerprint"] == "AQADfauxFPCALC"
    assert services.form(0)["duration"] == "241"
    assert build_row(track, found.result, {}).level == "sûr"
    other = _fingerprinted(
        [_recording("r2", "Something Else", "Somebody Else", 241_000)],
        deezer=[_deezer_track(42)],
    )
    found = Searcher(http(other), acoustid_key="clé-test").search(track, taken)
    assert build_row(track, found.result, {}).level == "à revoir"


def test_another_piece_puts_the_title_to_review():
    """L'empreinte désigne un tout autre morceau : le texte le trouve chez Deezer à
    la lettre près, mais il n'est que « à revoir »."""
    services = _fingerprinted(
        [_recording("r2", "Something Else", "Somebody Else", 240_000)],
        deezer=[_deezer_track(42)],
    )
    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    found = _search(services, track)
    assert found.result.status == "trouvé"
    assert found.result.match.source == "deezer"
    assert found.result.doubt == OTHER_PIECE
    row = build_row(track, found.result, found.wikidata)
    assert row.level == "à revoir"
    assert OTHER_PIECE in row.reasons
    assert {one.level for one in proposals(row)} <= {"à revoir"}
    # Introuvable par le texte : il le dit aussi.
    services = _fingerprinted(
        [_recording("r2", "Something Else", "Somebody Else", 240_000)]
    )
    found = _search(services, track)
    assert found.result.status == "rien"
    assert build_row(track, found.result, {}).reasons == [OTHER_PIECE]


def test_a_title_approached_by_its_text_keeps_its_level_and_the_doubt():
    hit = {
        "id": 9,
        "title": "Oumako",
        "duration": 596,
        "artist": {"id": 7, "name": "Gnonnas Pedro"},
        "link": "https://www.deezer.com/track/9",
    }
    services = _fingerprinted(
        [_recording("r2", "Something Else", "Somebody Else", 596_000)], deezer=[hit]
    )
    track = Track(title="Oumako", artist="Gonnas Pedro", length=596)
    found = _search(services, track)
    assert (found.result.status, found.result.doubt) == ("rapproché", OTHER_PIECE)
    row = build_row(track, found.result, {})
    assert row.level == "rapproché"
    assert row.reasons[-1] == OTHER_PIECE


def test_another_version_at_the_files_length_puts_the_title_to_review():
    """L'empreinte désigne un remix, à 6 s du fichier ; le texte trouve l'original
    chez Deezer : jamais un autre remix, le titre est à revoir."""
    services = _fingerprinted(
        [_recording("r1", "Swarm Behaviour (KMTR Remix)", "Seleem", 247_000)],
        deezer=[_deezer_track(42)],
    )
    track = Track(title="Swarm Behaviour", artist="Seleem", length=241)
    found = _search(services, track)
    assert found.result.match.source == "deezer"
    assert found.result.doubt == OTHER_VERSION
    row = build_row(track, found.result, {})
    assert row.level == "à revoir"
    assert OTHER_VERSION in row.reasons


def test_the_same_piece_at_another_length_is_not_another_piece():
    """Le même morceau, mais 30 s de plus : une autre édition, que la durée du
    fichier dément. Le texte la cherche, sans rien en déduire."""
    services = _fingerprinted(
        [_recording("r1", "Swarm Behaviour (Extended Mix)", "Seleem", 270_000)],
        deezer=[_deezer_track(42)],
    )
    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    found = _search(services, track)
    assert found.result.match.source == "deezer"
    assert found.result.doubt == ""
    assert build_row(track, found.result, {}).level == "sûr"


def test_a_close_text_confirmed_by_the_fingerprint_is_to_review():
    services = _fingerprinted([_recording("r1", "Swarm Behaviour", "Seleem", 242_000)])
    track = Track(title="Swarm Behavior", artist="Seleem", length=240)
    found = _search(services, track)
    assert found.result.status == "rapproché"
    assert found.result.match.source == FINGERPRINT
    row = build_row(track, found.result, {})
    assert row.level == "à revoir"
    assert row.reasons[0].startswith("rapproché, confirmé par l'empreinte : ")
    assert row.title == "Swarm Behaviour"


def test_a_short_title_has_a_meaning_found_at_the_letter():
    """« Go » est trop court pour la seconde passe, pas vide de sens : l'empreinte le
    trouve à la lettre près, et ne le remplace jamais."""
    track = Track(title="Go", artist="Moby", length=240)
    found = _search(_fingerprinted([_recording("r1", "Go", "Moby", 243_000)]), track)
    assert found.result.status == "trouvé"
    assert build_row(track, found.result, {}).level == "sûr"
    naima = _recording("r2", "Naima", "John Coltrane", 242_000)
    found = _search(_fingerprinted([naima], score=0.95), track)
    assert (found.result.status, found.result.doubt) == ("rien", OTHER_PIECE)


def test_a_file_without_text_takes_the_fingerprints_from_09():
    recording = _recording("r1", "Swarm Behaviour", "Seleem", 245_000)
    track = Track(title="Piste 04", artist="", length=240)
    found = _search(_fingerprinted([recording], score=0.93), track)
    assert found.result.status == "trouvé"
    row = build_row(track, found.result, {})
    assert row.level == "à revoir"
    assert (row.title, row.artist) == ("Swarm Behaviour", "Seleem")
    # Sous 0,9, ou au-delà de 7 s : rien, et un fichier sans artiste est écarté.
    found = _search(_fingerprinted([recording], score=0.8), track)
    assert found.result.status == "écarté"
    late = _recording("r1", "Swarm Behaviour", "Seleem", 250_000)
    found = _search(_fingerprinted([late], score=0.95), track)
    assert found.result.status == "écarté"


def test_a_lone_fingerprint_keeps_what_the_file_knows():
    """Un titre vide de sens : l'empreinte donne le titre, si l'artiste du fichier
    s'y retrouve ; un crédit plus long ne remplace pas le sien."""
    credit = _recording("r1", "Swarm Behaviour", "Seleem & Friend", 243_000)
    track = Track(title="Piste 04", artist="Seleem", length=240)
    found = _search(_fingerprinted([credit], score=0.95), track)
    assert found.result.status == "trouvé"
    row = build_row(track, found.result, {})
    assert row.level == "à revoir"
    assert (row.title, row.artist) == ("Swarm Behaviour", "Seleem")


def test_a_lone_fingerprint_never_replaces_what_the_file_knows():
    """Un lien d'AcoustID peut être faux : l'artiste ou le titre du fichier le
    vérifient. Contredits, c'est un autre morceau, et rien ne se propose."""
    naima = _recording("r1", "Naima", "John Coltrane", 242_000)
    track = Track(title="Piste 04", artist="Miles Davis", length=240)
    found = _search(_fingerprinted([naima], score=0.95), track)
    assert (found.result.status, found.result.doubt) == ("rien", OTHER_PIECE)
    row = build_row(track, found.result, {})
    assert (row.level, row.artist, row.title) == (
        "introuvable",
        "Miles Davis",
        "Piste 04",
    )
    # Un titre sans artiste : le titre vérifie, même écrit « Artiste - Titre ».
    found = _search(
        _fingerprinted([naima], score=0.95), Track(title="So What", length=240)
    )
    assert found.result.status == "écarté"
    kind = Track(title="Miles Davis - Naima", length=240)
    found = _search(_fingerprinted([naima], score=0.95), kind)
    assert found.result.status == "trouvé"


def test_the_thresholds_of_the_fingerprint():
    """0,5 pour un enregistrement, 0,9 pour l'empreinte seule ; 10 s arrondies à la
    lettre près, 7 s pour l'empreinte seule ; le meilleur résultat, pas le premier."""
    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)

    def match(recording, score, item=track, results=None):
        services = _fingerprinted([recording], score=score, results=results)
        return by_fingerprint(http(services), item, PRINT, "clé-test").match

    same = _recording("r1", "Swarm Behaviour", "Seleem", 245_000)
    assert match(same, 0.5) is not None
    assert match(same, 0.49) is None
    assert match(_recording("r1", "Swarm Behaviour", "Seleem", 250_400), 0.97)
    assert match(_recording("r1", "Swarm Behaviour", "Seleem", 250_600), 0.97) is None
    alone = Track(title="Piste 04", length=240)
    assert match(same, 0.9, alone) is not None
    assert match(same, 0.89, alone) is None
    assert match(_recording("r1", "X", "Y", 247_000), 0.95, alone) is not None
    assert match(_recording("r1", "X", "Y", 247_500), 0.95, alone) is None
    results = [
        {"id": "a", "score": 0.6, "recordings": [{"id": "r9"}]},
        {"id": "b", "score": 0.95, "recordings": [{"id": "r1"}]},
    ]
    services = _fingerprinted([same], results=results)
    found = by_fingerprint(http(services), track, PRINT, "clé-test")
    assert found.match.id == "r1"
    assert not any("/recording/r9" in url for url in services.asked)


def test_takes_five_recordings_of_the_best_result_from_05():
    recordings = [_recording(f"r{index}", "Other", "Other", 1000) for index in range(7)]
    services = _fingerprinted(recordings)
    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    found = by_fingerprint(http(services), track, PRINT, "clé-test")
    assert found.doubt == OTHER_PIECE
    assert sum("/recording/" in url for url in services.asked) == 5
    services = _fingerprinted(recordings[:1], score=0.4)
    assert by_fingerprint(http(services), track, PRINT, "clé-test").match is None
    assert not any("/recording/" in url for url in services.asked)


def test_a_failure_of_the_fingerprint_puts_the_title_in_error_even_found():
    """L'empreinte n'a pas pu vérifier le morceau que le texte trouve : le titre est
    en erreur, avec ce morceau, et sera cherché de nouveau."""

    def deezer(url):
        if url.startswith(f"{DEEZER}/search?q="):
            return {"data": [_deezer_track(42)]}
        return None

    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    found = _search(Services({ACOUSTID: (503, None)}, deezer), track)
    assert found.result.status == "erreur"
    assert found.result.match.id == "42"
    assert "503" in found.result.error
    assert isinstance(found.failure, HttpError)
    assert build_row(track, found.result, {}).level == "erreur"
    # MusicBrainz muet pendant la passe de l'empreinte : pareil.
    answers = {
        ACOUSTID: {
            "status": "ok",
            "results": [{"score": 0.9, "recordings": [{"id": "r1"}]}],
        },
        _recording_url("r1"): (503, None),
    }
    assert _search(Services(answers, deezer), track).result.status == "erreur"
    # Rien trouvé : une erreur aussi, jamais un introuvable.
    found = _search(Services({ACOUSTID: (503, None)}), track)
    assert (found.result.status, found.result.match) == ("erreur", None)


def test_acoustid_down_opens_its_breaker_and_says_so():
    services = Services({ACOUSTID: (503, None)})
    searcher = Searcher(http(services), acoustid_key="clé-test")
    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    for _ in range(5):
        searcher.search(track, PRINT)
    asked = services.asked.count(ACOUSTID)
    found = searcher.search(track, PRINT)
    assert isinstance(found.failure, CircuitOpenError)
    assert services.asked.count(ACOUSTID) == asked


def test_a_refused_acoustid_key_is_skipped_and_said_once(caplog):
    refused = {"status": "error", "error": {"code": 4, "message": "invalid API key"}}
    services = Services(
        {ACOUSTID: (400, refused)},
        lambda url: {"data": [_deezer_track(42)]}
        if url.startswith(f"{DEEZER}/search?q=")
        else None,
    )
    searcher = Searcher(http(services), acoustid_key="clé-refusée")
    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    with caplog.at_level(logging.WARNING, logger="radiotomate.fiches.search"):
        assert searcher.search(track, PRINT).result.status == "trouvé"
        assert searcher.search(track, PRINT).result.status == "trouvé"
    assert services.asked.count(ACOUSTID) == 1
    assert [record.message for record in caplog.records] == [
        "fiches : AcoustID refuse la clé, l'empreinte est sautée"
    ]


def test_without_an_acoustid_key_the_fingerprint_is_skipped_and_said_once(caplog):
    services = Services()
    searcher = Searcher(http(services))
    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    with caplog.at_level(logging.WARNING, logger="radiotomate.fiches.search"):
        searcher.search(track, PRINT)
        searcher.search(track, PRINT)
    assert ACOUSTID not in services.asked
    assert [record.message for record in caplog.records].count(
        "fiches : pas de clé AcoustID, l'empreinte est sautée"
    ) == 1


# ===== Ce qui est écarté, ce qui est en panne =====


def test_a_title_without_duration_an_announcement_or_without_artist_is_set_aside():
    services = Services()
    searcher = Searcher(http(services))
    for track, why in (
        (Track(title="Swarm Behaviour", artist="Seleem"), "sans durée"),
        (Track(title="Jingle station", artist="Radio", length=12), None),
        (Track(title="Pub 3", artist="Agence", length=30), None),
        (Track(title="Swarm Behaviour", artist="  ", length=240), None),
    ):
        result = searcher.search(track).result
        assert result.status == "écarté"
        reasons = build_row(track, result, {}).reasons
        assert reasons == [why or "sans artiste ou annonce"]
    assert services.asked == []


def test_a_failure_in_the_second_pass_is_an_error_never_a_not_found():
    def answer(url):
        if url.startswith("https://musicbrainz.org/"):
            return (503, None)
        return {"data": []}

    track = Track(title="Love Attack", artist="Shotgun", length=259)
    found = Searcher(http(Services(answer=answer))).search(track)
    assert found.result.status == "erreur"
    assert build_row(track, found.result, {}).level == "erreur"


def test_a_failure_in_the_details_keeps_the_match():
    def answer(url):
        if url.startswith(f"{DEEZER}/search?q="):
            return {"data": [_deezer_track(42)]}
        if url.startswith("https://musicbrainz.org/"):
            return (503, None)
        return None

    track = Track(title="Swarm Behaviour", artist="Seleem", length=240)
    found = Searcher(http(Services(answer=answer))).search(track)
    assert found.result.status == "erreur"
    assert found.result.match.id == "42"


# ===== Le verdict, et les preuves gardées =====


def _war(answer_persons=True):
    """Un titre de War, trouvé chez Deezer, son artiste dans MusicBrainz par l'ISRC,
    deux membres, et Wikidata."""
    answers = {
        f"{DEEZER}/track/42": _deezer_track(
            42,
            "The Cisco Kid",
            "War",
            isrc="USRHD0703008",
            album={"id": 7, "title": "The World is a Ghetto"},
        )
        | {"artist": {"id": 10129, "name": "War"}},
        f"{DEEZER}/album/7": {
            "id": 7,
            "title": "The World is a Ghetto",
            "release_date": "1972-11-17",
            "record_type": "album",
            "genres": {"data": [{"name": "R&B"}]},
        },
        f"{MB}/isrc/USRHD0703008?inc=artist-credits&fmt=json": {
            "recordings": [
                {
                    "first-release-date": "1972",
                    "artist-credit": [
                        {"name": "War", "artist": {"id": "war", "name": "War"}}
                    ],
                }
            ]
        },
        f"{MB}/artist/war?inc=genres&fmt=json": {
            "id": "war",
            "name": "War",
            "type": "Group",
            "genres": [{"name": "funk", "count": 1}],
        },
        f"{MB}/artist/war?inc=artist-rels+genres&fmt=json": {
            "id": "war",
            "name": "War",
            "type": "Group",
            "genres": [{"name": "funk", "count": 1}],
            "relations": [_band("p1", "1969"), _band("p2", "1969")],
        },
    }
    if answer_persons:
        answers[f"{MB}/artist/p1?fmt=json"] = {"type": "Person", "gender": "Female"}
        answers[f"{MB}/artist/p2?fmt=json"] = {"type": "Person", "gender": "Female"}

    def answer(url):
        if url.startswith(f"{DEEZER}/search?q="):
            return {
                "data": [_deezer_track(42, "The Cisco Kid", "War") | {"duration": 267}]
            }
        if url.startswith("https://query.wikidata.org/"):
            return {
                "results": {
                    "bindings": [
                        {
                            "key": {"value": "war"},
                            "item": {"value": "http://www.wikidata.org/entity/Q1"},
                            "label": {"value": "War"},
                            "member": {"value": "http://www.wikidata.org/entity/Q2"},
                            "memberGender": {
                                "value": "http://www.wikidata.org/entity/Q6581072"
                            },
                        }
                    ]
                }
            }
        return None

    return Services(answers, answer)


def _band(member_id, begin):
    return {
        "type": "member of band",
        "direction": "backward",
        "begin": begin,
        "artist": {"id": member_id, "name": member_id},
    }


WAR = Track(title="The Cisco Kid", artist="War", length=267)


def test_with_the_verdict_off_no_request_about_a_person():
    services = _war()
    found = Searcher(http(services)).search(WAR)
    assert found.result.status == "trouvé"
    assert found.result.details.musicbrainz.artist.genres == ("funk",)
    assert not any("artist-rels+genres" in url for url in services.asked)
    assert not any(
        url.endswith("?fmt=json") and "/artist/" in url for url in services.asked
    )
    assert not any("wikidata" in url for url in services.asked)
    row = build_row(WAR, found.result, found.wikidata)
    assert row.verdict == "à vérifier"
    assert not [one for one in proposals(row) if one.key == "fmg"]


def test_with_the_verdict_on_members_and_wikidata_give_the_verdict():
    services = _war()
    found = Searcher(http(services), verdict=True).search(WAR)
    assert f"{MB}/artist/p1?fmt=json" in services.asked
    assert any("query.wikidata.org" in url for url in services.asked)
    row = build_row(WAR, found.result, found.wikidata)
    assert row.verdict == "oui"
    assert row.verdict_source == "MusicBrainz : 2 membres connus sur 2 en 1972"


def test_with_the_verdict_on_a_title_found_by_its_fingerprint_keeps_no_gender():
    services = _war()
    recording = {
        "id": "r-war",
        "title": "The Cisco Kid",
        "length": 267_000,
        "isrcs": ["USRHD0703008"],
        "first-release-date": "1972-11",
        "artist-credit": [{"name": "War", "artist": {"id": "war", "name": "War"}}],
    }
    services.answers[ACOUSTID] = {
        "status": "ok",
        "results": [{"score": 0.98, "recordings": [{"id": "r-war"}]}],
    }
    services.answers[_recording_url("r-war")] = recording
    searcher = Searcher(http(services), acoustid_key="clé-test", verdict=True)
    found = searcher.search(WAR, PRINT)
    assert (found.result.status, found.result.match.source) == ("trouvé", FINGERPRINT)
    assert f"{MB}/artist/p1?fmt=json" in services.asked
    row = build_row(WAR, found.result, found.wikidata)
    assert row.verdict == "oui"
    assert _genders(found)
    assert _genders(found.evidence()) == []


def _genders(value, path="preuves"):
    """Les genres de personne d'une valeur, à toute profondeur."""
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        out = []
        for key, item in value.items():
            if key in ("gender", "genders", "members") and item:
                out.append(f"{path}.{key}")
            out += _genders(item, f"{path}.{key}")
        return out
    if isinstance(value, (list, tuple)):
        return [
            found
            for index, item in enumerate(value)
            for found in _genders(item, f"{path}[{index}]")
        ]
    return []


def test_the_kept_evidence_holds_no_gender_of_a_person():
    found = Searcher(http(_war()), verdict=True).search(WAR)
    assert _genders(found)  # ce qui sert au verdict tout de suite en porte
    kept = found.evidence()
    assert _genders(kept) == []
    assert kept.result.details.musicbrainz.artist.genres == ("funk",)
    assert kept.wikidata["war"].names == ("War",)
    # Les preuves refont les propositions sans réseau, sauf le verdict.
    again = build_row(WAR, kept.result, kept.wikidata)
    row = build_row(WAR, found.result, found.wikidata)
    assert (again.title, again.year, again.album, again.family) == (
        row.title,
        row.year,
        row.album,
        row.family,
    )
    assert again.verdict == "à vérifier"


def test_the_loose_and_third_judges_agree_on_the_swapped_reason():
    from radiotomate.fiches.loose import _SWAPPED

    assert _SWAPPED == SWAPPED
