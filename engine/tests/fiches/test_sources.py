"""Ce que les sources disent d'un morceau : le bloc « sources » de
`tests/radio-catalogue.test.ts`, dans Hopper, sur un faux transport httpx.

Toujours par un identifiant, jamais par un nom. Les requêtes sur les personnes ne
partent que verdict allumé.
"""

import base64
import itertools
import json
import logging
from urllib.parse import unquote

import httpx
import pytest

from radiotomate.fiches.http import Http, HttpError
from radiotomate.fiches.proposals import (
    AppleDetails,
    DeezerAlbum,
    DeezerDetails,
    MusicBrainzMember,
    WikidataArtist,
)
from radiotomate.fiches.rules import Period, same_artist_name
from radiotomate.fiches.sources import (
    ACOUSTID,
    BANDCAMP_DETAILS,
    BANDCAMP_SEARCH,
    SETTING_APPLE,
    SETTING_BANDCAMP,
    SETTING_TIDAL,
    SETTING_TIDAL_CLIENT_ID,
    SETTING_TIDAL_CLIENT_SECRET,
    TIDAL_TOKEN,
    AcoustidKeyError,
    Candidate,
    Credit,
    SourceSettings,
    Tidal,
    acoustid_lookup,
    apple_details,
    apple_search,
    bandcamp_candidate,
    bandcamp_ref,
    bandcamp_search,
    bandcamp_url,
    clean_url,
    component,
    credit_from_title,
    deezer_details,
    deezer_releases,
    iso_duration,
    musicbrainz_details,
    musicbrainz_recording,
    prune_deezer_search,
    tidal_candidates,
    to_ean13,
    upc_forms,
    wikidata_artists,
)
from tests.fiches.fakes import VERSION, FakeClock, Services, http

MB = "https://musicbrainz.org/ws/2"


def test_component_encodes_like_javascript():
    assert component("artist:\"Mr. Sweety 'G'\" (x)!*~") == (
        "artist%3A%22Mr.%20Sweety%20'G'%22%20(x)!*~"
    )
    assert component("Kærså/é") == "K%C3%A6rs%C3%A5%2F%C3%A9"


def test_reads_the_deezer_track_by_its_isrc_then_its_album():
    services = Services(
        {
            "https://api.deezer.com/track/isrc:USRHD0703008": {
                "id": 1,
                "title": "The Cisco Kid",
                "isrc": "USRHD0703008",
                "duration": 267,
                "artist": {"id": 10129, "name": "War"},
                "album": {"id": 7, "title": "The World is a Ghetto"},
            },
            "https://api.deezer.com/album/7": {
                "id": 7,
                "title": "The World is a Ghetto",
                "label": "Avenue Records",
                "release_date": "2015-07-31",
                "record_type": "album",
                "genres": {"data": [{"id": 165, "name": "R&B"}]},
                "tracks": {"data": []},
            },
        }
    )
    client = http(services)
    assert deezer_details(client, "tidal", "x", "USRHD0703008") == DeezerDetails(
        track_id="1",
        title="The Cisco Kid",
        duration_s=267,
        isrc="USRHD0703008",
        artist_id="10129",
        artist_name="War",
        album=DeezerAlbum(
            id="7",
            title="The World is a Ghetto",
            label="Avenue Records",
            date="2015-07-31",
            record_type="album",
            genres=("R&B",),
        ),
    )
    assert deezer_details(client, "bandcamp", "x") is None


def test_finds_the_musicbrainz_artist_by_isrc_or_deezer_page_never_by_name():
    deezer_page = component("https://www.deezer.com/artist/10129")
    services = Services(
        {
            f"{MB}/url?resource={deezer_page}&inc=artist-rels&fmt=json": {
                "relations": [
                    {"type": "free streaming", "artist": {"id": "war", "name": "War"}}
                ]
            },
            f"{MB}/artist/war?inc=artist-rels+genres&fmt=json": {
                "id": "war",
                "name": "War",
                "type": "Group",
                "genres": [{"name": "soul", "count": 2}, {"name": "funk", "count": 5}],
                "relations": [
                    _member("p1", "Lonnie Jordan"),
                    _member("p1", "Lonnie Jordan"),
                    _member("p2", "Lee Oskar"),
                    {
                        "type": "member of band",
                        "direction": "forward",
                        "artist": {"id": "other", "name": "Autre groupe"},
                    },
                ],
            },
            f"{MB}/artist/p1?fmt=json": {"type": "Person", "gender": "Male"},
            f"{MB}/artist/p2?fmt=json": {"type": "Person", "gender": "Male"},
            f"{MB}/release-group?artist=war&limit=100&offset=0&fmt=json": {
                "release-group-count": 2,
                "release-groups": [
                    {"title": "The World Is a Ghetto", "first-release-date": "1972-11"},
                    {"title": "Why Can't We Be Friends?", "first-release-date": "1975"},
                ],
            },
        }
    )
    details = musicbrainz_details(
        http(services),
        isrc="USRHD0703008",
        deezer_artist_id="10129",
        album="The World is a Ghetto (Remastered)",
        accept=lambda name: same_artist_name("WAR", name),
        verdict=True,
    )
    assert details.album_date == "1972-11"
    assert details.artist is not None
    assert details.artist.type == "Group"
    assert details.artist.genres == ("funk", "soul")
    assert [(one.id, one.gender) for one in details.artist.members] == [
        ("p1", "Male"),
        ("p2", "Male"),
    ]
    assert services.asked[0] == f"{MB}/isrc/USRHD0703008?inc=artist-credits&fmt=json"
    assert not any("query=" in url for url in services.asked)


def _member(member_id, name, begin=None, end=None):
    return {
        "type": "member of band",
        "direction": "backward",
        "begin": begin,
        "end": end,
        "artist": {"id": member_id, "name": name},
    }


def test_keeps_band_members_dates_those_of_the_recording_year_first():
    services = Services(
        {
            f"{MB}/isrc/P?inc=artist-credits&fmt=json": {
                "recordings": [
                    {
                        "first-release-date": "1989-04-17",
                        "artist-credit": [
                            {"artist": {"id": "pixies", "name": "Pixies"}}
                        ],
                    }
                ]
            },
            f"{MB}/artist/pixies?inc=artist-rels+genres&fmt=json": {
                "id": "pixies",
                "name": "Pixies",
                "type": "Group",
                "relations": [
                    _member("paz", "paz", "2014", "2024"),
                    _member("kim", "kim", "1986", "1993"),
                    _member("kim", "kim", "2004-06", "2013-06-14"),
                    _member("frank", "frank", "1986"),
                    _member("joey", "joey"),
                ],
            },
            f"{MB}/artist/kim?fmt=json": {"type": "Person", "gender": "Female"},
            f"{MB}/artist/frank?fmt=json": {"type": "Person", "gender": "Male"},
            f"{MB}/artist/paz?fmt=json": {"type": "Person", "gender": "Female"},
        }
    )
    details = musicbrainz_details(
        http(services),
        isrc="P",
        accept=lambda name: same_artist_name("PIXIES", name),
        verdict=True,
    )
    assert details.artist is not None
    assert details.artist.members == (
        MusicBrainzMember(
            "kim", "kim", "Female", (Period(1986, 1993), Period(2004, 2013))
        ),
        MusicBrainzMember("frank", "frank", "Male", (Period(1986, None),)),
        MusicBrainzMember("joey", "joey", None, (Period(),)),
        MusicBrainzMember("paz", "paz", "Female", (Period(2014, 2024),)),
    )


def test_looks_for_the_album_date_only_without_a_recording_date():
    services = Services(
        {
            f"{MB}/isrc/X?inc=artist-credits&fmt=json": {
                "recordings": [
                    {
                        "first-release-date": "2005-10-24",
                        "artist-credit": [
                            {"artist": {"id": "hp", "name": "Hushpuppies"}}
                        ],
                    },
                    {"first-release-date": "2008", "artist-credit": []},
                ]
            },
            f"{MB}/artist/hp?inc=artist-rels+genres&fmt=json": {
                "id": "hp",
                "name": "Hushpuppies",
                "type": "Group",
                "relations": [],
            },
        }
    )
    details = musicbrainz_details(
        http(services),
        isrc="X",
        album="The Trap",
        accept=lambda name: same_artist_name("HUSH_PUPPIES", name),
        verdict=True,
    )
    assert details.recording_date == "2005-10-24"
    assert details.artist is not None
    assert details.artist.name == "Hushpuppies"
    assert details.album_date is None
    assert not any("/release-group" in url for url in services.asked)


def test_refuses_the_artist_of_a_deezer_page_that_is_not_the_files():
    """Une page Deezer réunit parfois des homonymes : « Driver » pour le duo
    « Driver&Driver »."""
    page = component("https://www.deezer.com/artist/42")
    services = Services(
        {
            f"{MB}/isrc/DEEH61700645?inc=artist-credits&fmt=json": {
                "recordings": [
                    {
                        "first-release-date": "2017",
                        "artist-credit": [
                            {"name": "Driver", "artist": {"id": "d", "name": "Driver"}}
                        ],
                    }
                ]
            },
            f"{MB}/url?resource={page}&inc=artist-rels&fmt=json": {
                "relations": [{"artist": {"id": "d", "name": "Driver"}}]
            },
        }
    )
    details = musicbrainz_details(
        http(services),
        isrc="DEEH61700645",
        deezer_artist_id="42",
        accept=lambda name: same_artist_name("Driver&Driver", name),
        verdict=True,
    )
    assert details.recording_date == "2017"
    assert details.artist is None
    assert details.album_date is None
    assert not any("/artist/d" in url for url in services.asked)


def test_without_the_verdict_no_request_about_a_person():
    """Verdict éteint : la fiche de l'artiste pour ses genres musicaux, sans ses
    relations, sans ses membres, et sans le genre qu'elle déclare."""
    services = Services(
        {
            f"{MB}/artist/war?inc=genres&fmt=json": {
                "id": "war",
                "name": "War",
                "type": "Person",
                "gender": "Female",
                "genres": [{"name": "funk", "count": 5}],
                "relations": [_member("p1", "Lonnie Jordan")],
            },
        }
    )
    details = musicbrainz_details(
        http(services), artist_id="war", accept=lambda name: True
    )
    assert details.artist is not None
    assert details.artist.genres == ("funk",)
    assert details.artist.gender is None
    assert details.artist.members == ()
    assert services.asked == [f"{MB}/artist/war?inc=genres&fmt=json"]


def test_reads_wikidata_by_deezer_or_musicbrainz_id():
    def binding(key, item, **extra):
        out = {
            "key": {"value": key},
            "item": {"value": f"http://www.wikidata.org/entity/{item}"},
        }
        for name, value in extra.items():
            text = (
                value if name == "human" else f"http://www.wikidata.org/entity/{value}"
            )
            out[name] = {"value": text}
        return out

    def answer(url):
        query = unquote(url.split("query=")[1])
        if "P2722" in query:
            label = {"label": {"value": "Linda Lewis"}}
            return {
                "results": {
                    "bindings": [
                        binding("70385", "Q1", human="true", gender="Q6581072") | label,
                        binding("70385", "Q1", human="true", gender="Q1052281") | label,
                    ]
                }
            }
        return {
            "results": {
                "bindings": [
                    binding("mb-ec", "Q2", member="Q20", memberGender="Q6581072"),
                    binding("mb-ec", "Q2", member="Q21"),
                ]
            }
        }

    services = Services(answer=answer)
    store: dict = {}
    artists = wikidata_artists(
        http(services), store, ["70385", "70385", "999"], ["mb-ec"]
    )
    assert artists["70385"] == WikidataArtist(
        item="http://www.wikidata.org/entity/Q1",
        names=("Linda Lewis",),
        human=True,
        genders=("Q6581072", "Q1052281"),
        members={},
    )
    assert artists["mb-ec"].members == {
        "http://www.wikidata.org/entity/Q20": ("Q6581072",),
        "http://www.wikidata.org/entity/Q21": (),
    }
    # Une fiche par identifiant, None pour un identifiant que Wikidata ne connaît pas.
    assert sorted(store) == [
        "wikidata:P2722:70385",
        "wikidata:P2722:999",
        "wikidata:P434:mb-ec",
    ]
    assert store["wikidata:P2722:999"] is None
    assert services.headers(0)["Accept"] == "application/sparql-results+json"
    # Gardées : plus aucune question.
    asked = len(services.requests)
    again = wikidata_artists(http(services), store, ["70385"], [])
    assert len(services.requests) == asked
    assert again["70385"].names == ("Linda Lewis",)
    # Sans réponse, rien de gardé.
    empty: dict = {}
    assert wikidata_artists(http(Services()), empty, ["1"], []) == {}
    assert empty == {}


def test_asks_wikidata_eighty_ids_at_a_time():
    services = Services(answer=lambda url: {"results": {"bindings": []}})
    store: dict = {}
    ids = [str(index) for index in range(170)]
    wikidata_artists(http(services), store, ids, [])
    assert len(services.requests) == 3
    assert len(store) == 170


def test_asks_acoustid_with_the_key_in_the_body_never_in_the_address():
    services = Services(
        {
            ACOUSTID: {
                "status": "ok",
                "results": [
                    {
                        "id": "a",
                        "score": 0.97,
                        "recordings": [{"id": "r1"}, {"id": "r2"}],
                    },
                    {"id": "b", "score": 0.4},
                ],
            }
        }
    )
    results = acoustid_lookup(http(services), "clé-test", "AQADtE", 245)
    assert [(one.score, one.recordings) for one in results] == [
        (0.97, ("r1", "r2")),
        (0.4, ()),
    ]
    assert services.requests[0].method == "POST"
    assert services.asked == [ACOUSTID]
    assert services.form() == {
        "client": "clé-test",
        "meta": "recordingids",
        "duration": "245",
        "fingerprint": "AQADtE",
        "format": "json",
    }


def test_an_acoustid_key_refused_is_an_error_a_bad_fingerprint_is_nothing():
    """Une clé refusée : une erreur à part, que la recherche saute ; une panne
    d'AcoustID : une erreur ; une empreinte refusée : rien."""
    refused = {"status": "error", "error": {"code": 4, "message": "invalid API key"}}
    with pytest.raises(AcoustidKeyError, match="invalid API key"):
        acoustid_lookup(http(Services({ACOUSTID: (400, refused)})), "x", "AQ", 1)
    busy = {"status": "error", "error": {"code": 13, "message": "service unavailable"}}
    with pytest.raises(HttpError, match="service unavailable") as error:
        acoustid_lookup(http(Services({ACOUSTID: (503, busy)})), "x", "AQ", 1)
    assert not isinstance(error.value, AcoustidKeyError)
    invalid = {
        "status": "error",
        "error": {"code": 3, "message": "invalid fingerprint"},
    }
    assert (
        acoustid_lookup(http(Services({ACOUSTID: (400, invalid)})), "x", "AQ", 1) == []
    )


def test_reads_a_musicbrainz_recording_by_its_id():
    inc = "artist-credits+isrcs+releases+release-groups"
    services = Services(
        {
            f"{MB}/recording/r1?inc={inc}&fmt=json": {
                "id": "r1",
                "title": "Sonny's Crib",
                "length": 325000,
                "first-release-date": "1987",
                "isrcs": ["USX1"],
                "artist-credit": [
                    {"name": "John Zorn", "joinphrase": ", ", "artist": {"id": "z"}},
                    {
                        "name": "George Lewis",
                        "joinphrase": " & ",
                        "artist": {"id": "l"},
                    },
                    {"name": "Bill Frisell", "artist": {"id": "f"}},
                ],
                "releases": [
                    {
                        "title": "News for Lulu",
                        "date": "1988",
                        "release-group": {
                            "primary-type": "Album",
                            "secondary-types": [],
                        },
                    }
                ],
            }
        }
    )
    recording = musicbrainz_recording(http(services), "r1")
    assert recording is not None
    assert recording.credit == "John Zorn, George Lewis & Bill Frisell"
    assert recording.artist_ids == ("z", "l", "f")
    assert recording.length_ms == 325000
    assert recording.isrcs == ("USX1",)
    assert recording.date == "1987"
    assert not recording.compilation
    assert musicbrainz_recording(http(Services()), "absent") is None


def test_prunes_a_deezer_search_like_hopper():
    hits = prune_deezer_search(
        {
            "data": [
                {
                    "id": 9,
                    "title": "Oumako",
                    "duration": 596,
                    "artist": {"id": 7, "name": "Gnonnas Pedro"},
                    "album": {"title": "La belle époque"},
                    "link": "https://www.deezer.com/track/9",
                },
                {"id": 3, "duration": 0, "artist": {"name": "Sans id"}, "album": {}},
            ]
        }
    )
    assert hits[0].id == "9"
    assert hits[0].artist_id == "7"
    assert hits[0].duration_s == 596
    assert hits[0].album == "La belle époque"
    assert hits[1].title == ""
    assert hits[1].artist_id is None
    assert hits[1].duration_s is None
    assert hits[1].album is None
    assert hits[1].url == "https://www.deezer.com/track/3"


def test_barcodes_in_thirteen_digits_and_their_upc_form():
    assert to_ean13("602527856865") == "0602527856865"
    assert to_ean13("00050087478704") == "0050087478704"
    assert upc_forms("602527856865") == ["0602527856865", "602527856865"]
    assert upc_forms("3700187661950") == ["3700187661950"]


def test_reads_an_artists_most_listened_releases_where_they_lead():
    """Albums d'abord, puis EP et singles, les plus écoutés d'abord ; seulement
    ceux dont l'artiste est l'artiste principal, et disponibles."""
    services = Services(
        {
            "https://api.deezer.com/artist/5/albums?limit=100": {
                "data": [
                    {"id": 1, "record_type": "single", "fans": 900},
                    {"id": 2, "record_type": "album", "fans": 10},
                    {"id": 3, "record_type": "compile", "fans": 999},
                    {"id": 4, "record_type": "album", "fans": 50},
                    {"id": 5, "record_type": "ep", "fans": 5},
                ]
            },
            "https://api.deezer.com/album/4": {"upc": "111", "artist": {"id": 5}},
            "https://api.deezer.com/album/2": {"upc": "222", "artist": {"id": 6}},
            "https://api.deezer.com/album/5": {
                "upc": "333",
                "artist": {"id": 5},
                "available": False,
            },
            "https://api.deezer.com/album/1": {"upc": "444", "artist": {"id": 5}},
        }
    )
    assert deezer_releases(http(services), 5) == ["0000000000111", "0000000000444"]
    assert services.asked[1:] == [
        "https://api.deezer.com/album/4",
        "https://api.deezer.com/album/2",
        "https://api.deezer.com/album/5",
        "https://api.deezer.com/album/1",
    ]


# ===== Tidal, Apple Music et Bandcamp (FON-30) =====
#
# Les cas de Hopper sur ses adaptateurs, réduits à ce que la recherche des fiches en
# lit : de `tests/adapters.test.ts`, le bloc « Tidal » et le refus d'iTunes ; de
# `tests/independants.test.ts`, « artiste lu dans le titre » et le bloc
# « Bandcamp ». Ses cas sur ce que la recherche ne lit pas (type de sortie, rang
# d'une piste, pochette, albums et artistes par code-barres, lien collé) ne sont pas
# portés : rien ne s'en sert ici.

TIDAL_API = "https://openapi.tidal.com/v2"


def test_tidal_reads_a_json_api_document_artists_and_album_included():
    [track] = tidal_candidates(
        {
            "data": [
                {
                    "id": "1781887",
                    "type": "tracks",
                    "attributes": {
                        "title": "One More Time",
                        "isrc": "GBDUW0000053",
                        "duration": "PT5M20S",
                        "explicit": False,
                    },
                    "relationships": {
                        "artists": {"data": [{"id": "8847", "type": "artists"}]},
                        "albums": {"data": [{"id": "1781886", "type": "albums"}]},
                    },
                }
            ],
            "included": [
                {"id": "8847", "type": "artists", "attributes": {"name": "Daft Punk"}},
                {
                    "id": "1781886",
                    "type": "albums",
                    "attributes": {
                        "title": "Discovery",
                        "barcodeId": "724384960650",
                        "releaseDate": "2001-03-12",
                    },
                },
            ],
        }
    )
    assert track == Candidate(
        platform="tidal",
        id="1781887",
        url="https://tidal.com/browse/track/1781887",
        title="One More Time",
        artists=("Daft Punk",),
        album="Discovery",
        duration_ms=320_000,
        isrc="GBDUW0000053",
        release_date="2001-03-12",
    )


def test_tidal_album_tracks_in_their_order_unstreamable_ones_left_out():
    """Le rang porté par la liaison, l'album donné en contexte, les morceaux non
    diffusables écartés."""
    tracks = tidal_candidates(
        {
            "data": [
                {"id": "10", "type": "tracks", "meta": {"trackNumber": 1}},
                {"id": "11", "type": "tracks", "meta": {"trackNumber": 2}},
                {"id": "12", "type": "tracks", "meta": {"trackNumber": 3}},
            ],
            "included": [
                {
                    "id": "12",
                    "type": "tracks",
                    "attributes": {"title": "Digital Love", "availability": ["DJ"]},
                },
                {
                    "id": "11",
                    "type": "tracks",
                    "attributes": {
                        "title": "Aerodynamic",
                        "availability": ["STREAM", "DJ"],
                    },
                },
                {
                    "id": "10",
                    "type": "tracks",
                    "attributes": {"title": "One More Time"},
                },
            ],
        },
        {"title": "Discovery", "releaseDate": "2001-03-12", "albumType": "ALBUM"},
    )
    assert [track.id for track in tracks] == ["10", "11"]
    assert (tracks[0].album, tracks[0].release_date) == ("Discovery", "2001-03-12")


def test_tidal_adds_the_version_to_the_title():
    document = {
        "data": [
            {
                "id": "1",
                "type": "tracks",
                "attributes": {
                    "title": "Get Lucky",
                    "version": "Radio Edit",
                    "duration": "PT4M8S",
                },
            }
        ]
    }
    [track] = tidal_candidates(document)
    assert track.title == "Get Lucky (Radio Edit)"
    assert track.duration_ms == 248_000


def test_reads_iso_8601_durations():
    assert iso_duration("PT3M45S") == 225_000
    assert iso_duration("PT1H2M3.5S") == 3_723_500
    assert iso_duration("trois minutes") is None
    assert iso_duration(None) is None


def _tidal_services(token="jeton-1", **answers):
    """Tidal : un jeton, puis les réponses de son API."""
    services = Services(
        {TIDAL_TOKEN: {"access_token": token, "expires_in": 3600}, **answers}
    )
    return services, Tidal(http(services), "id-test", "secret-test")


def _tidal_search(query):
    include = component("tracks,tracks.artists,tracks.albums")
    return (
        f"{TIDAL_API}/searchResults?filter%5Bquery%5D={component(query)}"
        f"&include={include}&countryCode=FR"
    )


def test_tidal_asks_a_token_with_the_stations_key_and_keeps_it():
    url = _tidal_search("seleem swarm behaviour")
    services, tidal = _tidal_services(**{url: {"data": []}})
    assert tidal.search("Seleem", "Swarm Behaviour") == []
    assert tidal.search("Seleem", "Swarm Behaviour") == []
    assert services.asked == [TIDAL_TOKEN, url, url]
    # La clé va dans l'en-tête de la demande de jeton, jamais dans une adresse.
    basic = base64.b64encode(b"id-test:secret-test").decode()
    assert services.headers(0)["Authorization"] == f"Basic {basic}"
    assert services.form(0) == {"grant_type": "client_credentials"}
    assert services.headers(1)["Authorization"] == "Bearer jeton-1"
    assert services.headers(1)["Accept"] == "application/vnd.api+json"
    assert not any("secret" in asked for asked in services.asked)
    assert "secret" not in repr(tidal)


def test_tidal_asks_a_new_token_once_when_refused():
    url = _tidal_search("seleem swarm behaviour")
    services, tidal = _tidal_services(**{url: (401, {})})
    assert tidal.search("Seleem", "Swarm Behaviour") == []
    assert services.asked == [TIDAL_TOKEN, url, TIDAL_TOKEN, url]


def test_a_token_expires_a_minute_early():
    url = _tidal_search("seleem swarm behaviour")
    services, tidal = _tidal_services(**{url: {"data": []}})
    tidal.search("Seleem", "Swarm Behaviour")
    services.clock.time += 3600 - 61
    tidal.search("Seleem", "Swarm Behaviour")
    assert services.asked.count(TIDAL_TOKEN) == 1
    services.clock.time += 2
    tidal.search("Seleem", "Swarm Behaviour")
    assert services.asked.count(TIDAL_TOKEN) == 2


def test_a_refused_tidal_key_skips_tidal_and_is_said_once(caplog):
    services = Services({TIDAL_TOKEN: (401, {"error": "invalid_client"})})
    tidal = Tidal(http(services), "id-test", "secret-test")
    with caplog.at_level(logging.WARNING):
        assert tidal.search("Seleem", "Swarm Behaviour") == []
        assert tidal.search("Seleem", "Moth") == []
    assert tidal.refused
    assert services.asked == [TIDAL_TOKEN]
    assert [record.message for record in caplog.records] == [
        "fiches : Tidal refuse la clé d'application, Tidal est sauté"
    ]


@pytest.mark.parametrize("status", [429, 503])
def test_tidal_overloaded_or_down_is_a_failure_not_an_absence(status):
    url = _tidal_search("seleem swarm behaviour")
    _, tidal = _tidal_services(**{url: (status, {})})
    with pytest.raises(HttpError, match=f"Tidal : réponse {status}"):
        tidal.search("Seleem", "Swarm Behaviour")


def test_a_token_service_down_is_a_failure_not_a_refused_key():
    services = Services({TIDAL_TOKEN: (503, {})})
    tidal = Tidal(http(services), "id-test", "secret-test")
    with pytest.raises(HttpError, match="jeton refusé"):
        tidal.search("Seleem", "Swarm Behaviour")
    assert not tidal.refused


ITUNES_SEARCH = (
    "https://itunes.apple.com/search?term=daft%20punk%20get%20lucky"
    "&entity=song&limit=10&country=FR"
)


def test_apple_music_reads_the_songs_of_an_itunes_search():
    services = Services(
        {
            ITUNES_SEARCH: {
                "results": [
                    {
                        "wrapperType": "track",
                        "kind": "music-video",
                        "trackId": 1,
                        "trackName": "Get Lucky",
                    },
                    {
                        "wrapperType": "track",
                        "kind": "song",
                        "trackId": 617154366,
                        "artistName": "Daft Punk",
                        "trackName": "Get Lucky (feat. Pharrell Williams)",
                        "collectionName": "Random Access Memories",
                        "trackTimeMillis": 369_629,
                        "releaseDate": "2013-04-19T07:00:00Z",
                        "trackViewUrl": "https://music.apple.com/fr/album/get-lucky/"
                        "617154241?i=617154366&uo=4",
                    },
                ]
            }
        }
    )
    assert apple_search(http(services), "Daft Punk", "Get Lucky") == [
        Candidate(
            platform="apple",
            id="617154366",
            url="https://music.apple.com/fr/album/get-lucky/617154241?i=617154366",
            title="Get Lucky (feat. Pharrell Williams)",
            artists=("Daft Punk",),
            album="Random Access Memories",
            duration_ms=369_629,
            release_date="2013-04-19",
        )
    ]


def test_an_itunes_refusal_over_its_quota_is_a_failure_not_an_absence():
    services = Services({ITUNES_SEARCH: (403, {})})
    with pytest.raises(HttpError, match="403"):
        apple_search(http(services), "Daft Punk", "Get Lucky")


def test_apple_music_asks_twenty_searches_a_minute_at_most():
    """Cinq d'affilée, puis une toutes les 3,2 s."""
    services = Services(answer=lambda url: {"results": []})
    client = http(services)
    for _ in range(10):
        apple_search(client, "Daft Punk", "Get Lucky")
    gaps = [b - a for a, b in itertools.pairwise(services.times)]
    assert gaps[:4] == [0, 0, 0, 0]
    assert all(gap == pytest.approx(3.2) for gap in gaps[4:])


def test_the_apple_music_link_loses_its_tracking_only():
    assert clean_url(None, "https://music.apple.com/fr/song/1") == (
        "https://music.apple.com/fr/song/1"
    )
    assert clean_url("https://music.apple.com/fr/song/x/1?uo=4", "") == (
        "https://music.apple.com/fr/song/x/1"
    )
    assert clean_url("https://music.apple.com/fr/album/x/2?i=1&uo=4&ls=1", "") == (
        "https://music.apple.com/fr/album/x/2?i=1&ls=1"
    )


def test_reads_the_genre_date_and_album_of_an_apple_music_song():
    services = Services(
        {
            "https://itunes.apple.com/lookup?id=617154366&country=FR": {
                "results": [
                    {
                        "primaryGenreName": "Dance",
                        "releaseDate": "2013-04-19T07:00:00Z",
                        "collectionName": "Random Access Memories",
                    }
                ]
            }
        }
    )
    assert apple_details(http(services), "617154366") == AppleDetails(
        genre="Dance",
        date="2013-04-19T07:00:00Z",
        album="Random Access Memories",
    )
    assert apple_details(http(services), "1") is None


def test_credit_from_title_removes_a_label_accounts_prefix_side_and_underscores():
    assert credit_from_title(
        "Keope - Osem (Acid Coco Remix)", "Bigamo", ["Keope"]
    ) == Credit("Osem (Acid Coco Remix)", "Keope", False)
    assert credit_from_title(
        "B1_Pieuvre_Home Office", "Kitchen Leg records", ["Pieuvre"]
    ) == Credit("Home Office", "Pieuvre", False)
    assert credit_from_title(
        "Coilguns - Carbon Magic", "Coilguns", ["Coilguns"]
    ) == Credit("Carbon Magic", "Coilguns", True)
    # « The » en tête ou non, espaces d'un nom d'utilisateur.
    found = credit_from_title(
        "Rhythmagic Orchestra - African Mailman",
        "Paul Murphy",
        ["The Rhythmagic Orchestra"],
    )
    assert found.artist == "Rhythmagic Orchestra"
    assert credit_from_title("Drifting", "okkyunglee", ["Okkyung Lee"]) == Credit(
        "Drifting", "okkyunglee", True
    )


def test_credit_from_title_keeps_the_title_when_the_prefix_is_not_wanted():
    assert credit_from_title("Crypto_Mix", "Mike D", ["Mike D"]).title == "Crypto_Mix"
    found = credit_from_title(
        "Squeal Of Swine - Live", "Radwan Ghazi Moumneh", ["Radwan Ghazi Moumneh"]
    )
    assert (found.title, found.by_account) == ("Squeal Of Swine - Live", True)


KEOPE = {
    "id": 4192299102,
    "type": "t",
    "title": "Keope - Osem (Acid Coco Remix)",
    "tralbum_artist": "Bigamo",
    "band": {"band_id": 3851401248, "name": "Bigamo"},
    "album_title": "FLIKKA FLOKKA REMIXED PT.2",
    "release_date": 1724284800,
    "bandcamp_url": "https://bigamo.bandcamp.com/track/keope-osem-acid-coco-remix",
    "art_id": 2340984311,
    "tracks": [
        {
            "track_id": 4192299102,
            "title": "Keope - Osem (Acid Coco Remix)",
            "duration": 196.87,
            "track_num": 2,
        }
    ],
}


def test_bandcamp_reads_a_label_page_the_artist_of_the_title_length_and_album():
    assert bandcamp_candidate(KEOPE, {}, ["Keope"]) == Candidate(
        platform="bandcamp",
        id="bigamo/track/keope-osem-acid-coco-remix",
        url="https://bigamo.bandcamp.com/track/keope-osem-acid-coco-remix",
        title="Osem (Acid Coco Remix)",
        artists=("Keope",),
        album="FLIKKA FLOKKA REMIXED PT.2",
        duration_ms=196_870,
        release_date="2024-08-22",
        by_label=True,
    )


def test_bandcamp_the_publishing_account_counts_not_the_artist_it_declares():
    bootleg = {
        **KEOPE,
        "title": "One More Time",
        "tralbum_artist": "Daft Punk",
        "band": {"band_id": 1, "name": "jakebob"},
        "album_title": None,
        "bandcamp_url": "https://jakebob.bandcamp.com/track/one-more-time",
    }
    found = bandcamp_candidate(bootleg, {}, ["Daft Punk"])
    assert (found.artists, found.by_label) == (("Daft Punk",), True)
    # Le compte de CamelPhat publie « CamelPhat & Elderbrook » : un des artistes
    # crédités, pas un label.
    camelphat = {
        **KEOPE,
        "title": "Cola (Franky Rizardo Remix)",
        "tralbum_artist": "CamelPhat & Elderbrook",
        "band": {"band_id": 2, "name": "CamelPhat"},
        "bandcamp_url": "https://camelphat.bandcamp.com/track/cola-franky-rizardo-remix",
    }
    wanted = ["CAMELPHAT", "Elderbrook", "Franky Rizardo"]
    assert not bandcamp_candidate(camelphat, {}, wanted).by_label


def test_bandcamp_page_addresses():
    url = "https://pieuvres.bandcamp.com/track/home-office-2"
    assert bandcamp_ref(url, "track") == "pieuvres/track/home-office-2"
    assert bandcamp_ref(url, "album") is None
    assert bandcamp_ref("https://music.label.fr/track/x?y=1", "track") == (
        "music.label.fr/track/x"
    )
    assert bandcamp_ref("/track/x", "track") is None
    assert bandcamp_url("pieuvres/track/home-office-2") == url
    assert bandcamp_url("music.label.fr/track/x") == "https://music.label.fr/track/x"


BANDCAMP_DETAILS_URL = (
    f"{BANDCAMP_DETAILS}?band_id=3851401248&tralbum_type=t&tralbum_id=4192299102"
)


def test_bandcamp_searches_then_reads_the_three_most_plausible_pages():
    hit = {
        "type": "t",
        "id": 4192299102,
        "band_id": 3851401248,
        "name": "Keope - Osem (Acid Coco Remix)",
        "band_name": "Bigamo",
    }
    others = [
        {**hit, "id": number, "name": f"Keope - Osem {number}"} for number in (1, 2, 3)
    ]
    services = Services(
        {
            BANDCAMP_SEARCH: {
                "auto": {
                    "results": [
                        {"type": "a", "id": 9, "band_id": 9, "name": "Osem"},
                        {**hit, "name": "Keope - Autre Chose"},
                        hit,
                        *others,
                    ]
                }
            },
            BANDCAMP_DETAILS_URL: KEOPE,
        }
    )
    [found] = bandcamp_search(http(services), "Keope", "Osem (Acid Coco Remix)")
    assert found.title == "Osem (Acid Coco Remix)"
    assert json.loads(services.requests[0].content) == {
        "search_text": "keope osem acid coco remix",
        "search_filter": "t",
        "full_page": False,
        "fan_id": None,
    }
    # Trois fiches lues au plus ; une fiche retirée depuis la recherche ne compte
    # pas.
    assert services.asked[1:] == [
        BANDCAMP_DETAILS_URL,
        f"{BANDCAMP_DETAILS}?band_id=3851401248&tralbum_type=t&tralbum_id=1",
        f"{BANDCAMP_DETAILS}?band_id=3851401248&tralbum_type=t&tralbum_id=2",
    ]


@pytest.mark.parametrize(
    "answer",
    [
        (403, "<html><title>Just a moment...</title></html>"),
        (200, "<!DOCTYPE html><html>"),
        (200, {"error": True}),
    ],
)
def test_an_unreadable_bandcamp_answer_is_a_failure_never_nothing(answer, caplog):
    status, body = answer
    content = body if isinstance(body, str) else json.dumps(body)

    def respond(request):
        return httpx.Response(status, content=content.encode())

    client = Http(VERSION, transport=httpx.MockTransport(respond), clock=FakeClock())
    with (
        caplog.at_level(logging.WARNING),
        pytest.raises(HttpError, match=f"^Bandcamp : réponse {status}$"),
    ):
        bandcamp_search(client, "Okkyung Lee", "Drifting")
    if status == 403:
        assert (
            "Bandcamp, recherche : réponse 403 « <html><title>Just a moment..."
            "</title></html> »" in caplog.text
        )


def test_a_page_withdrawn_since_the_search_is_nothing():
    services = Services(
        {
            BANDCAMP_SEARCH: {
                "auto": {
                    "results": [
                        {"type": "t", "id": 1, "band_id": 2, "name": "Drifting"}
                    ]
                }
            },
            f"{BANDCAMP_DETAILS}?band_id=2&tralbum_type=t&tralbum_id=1": {
                "error": True
            },
        }
    )
    assert bandcamp_search(http(services), "Okkyung Lee", "Drifting") == []


def test_the_sources_settings_are_off_unless_set():
    assert SourceSettings.from_settings({}) == SourceSettings()
    settings = SourceSettings.from_settings(
        {
            SETTING_TIDAL: "1",
            SETTING_APPLE: "true",
            SETTING_BANDCAMP: "0",
            SETTING_TIDAL_CLIENT_ID: "id-test",
            SETTING_TIDAL_CLIENT_SECRET: "secret-test",
        }
    )
    assert (settings.tidal, settings.apple, settings.bandcamp) == (True, True, False)
    assert settings.tidal_key
    # La clé ne paraît jamais dans un journal.
    assert "id-test" not in repr(settings)
    assert "secret-test" not in repr(settings)
    assert not SourceSettings(tidal=True, tidal_client_id="id-test").tidal_key
    assert [SETTING_TIDAL, SETTING_APPLE, SETTING_BANDCAMP] == [
        "features.fiches_tidal",
        "features.fiches_apple_music",
        "features.fiches_bandcamp",
    ]
