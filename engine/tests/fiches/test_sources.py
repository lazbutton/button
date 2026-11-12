"""Ce que les sources disent d'un morceau : le bloc « sources » de
`tests/radio-catalogue.test.ts`, dans Hopper, sur un faux transport httpx.

Toujours par un identifiant, jamais par un nom. Les requêtes sur les personnes ne
partent que verdict allumé.
"""

from urllib.parse import unquote

import pytest

from radiotomate.fiches.http import HttpError
from radiotomate.fiches.proposals import (
    DeezerAlbum,
    DeezerDetails,
    MusicBrainzMember,
    WikidataArtist,
)
from radiotomate.fiches.rules import Period, same_artist_name
from radiotomate.fiches.sources import (
    ACOUSTID,
    AcoustidKeyError,
    acoustid_lookup,
    component,
    deezer_details,
    deezer_releases,
    musicbrainz_details,
    musicbrainz_recording,
    prune_deezer_search,
    to_ean13,
    upc_forms,
    wikidata_artists,
)
from tests.fiches.fakes import Services, http

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
