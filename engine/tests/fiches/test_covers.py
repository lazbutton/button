"""Les pochettes (FON-83) : leur lien, gardé dans les preuves, et seulement s'il
mène à un hôte d'images des sources que la politique de contenu de la console
admet."""

import re
from pathlib import Path

import pytest

from radiotomate.fiches.covers import (
    COVER_DOMAINS,
    apple_cover,
    bandcamp_cover,
    cover_link,
    cover_of,
)
from radiotomate.fiches.evidence import from_json, to_json
from radiotomate.fiches.proposals import (
    AppleDetails,
    DeezerAlbum,
    DeezerDetails,
    Details,
    Match,
    SearchResult,
)
from radiotomate.fiches.sources import apple_details, deezer_details
from tests.fiches.fakes import Services, http

DEEZER = "https://cdn-images.dzcdn.net/images/cover/abc/500x500-000000-80-0-0.jpg"
APPLE = "https://is1-ssl.mzstatic.com/image/thumb/Music/x/600x600bb.jpg"
BANDCAMP = "https://f4.bcbits.com/img/a2340984311_5.jpg"
TEMPLATE = (
    Path(__file__).resolve().parents[3]
    / "console/docker/security-headers.conf.template"
)


@pytest.mark.parametrize("url", [DEEZER, APPLE, BANDCAMP, f"  {DEEZER} "])
def test_a_cover_of_the_sources_is_kept(url):
    assert cover_link(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        42,
        "http://cdn-images.dzcdn.net/x.jpg",
        "https://dzcdn.net.example/x.jpg",
        "https://evildzcdn.net/x.jpg",
        "https://user:mot@cdn-images.dzcdn.net/x.jpg",
        "https://cdn-images.dzcdn.net:8443/x.jpg",
        "https://cdn-images.dzcdn.net/x y.jpg",
        "javascript:alert(1)",
        "https://cdn-images.dzcdn.net/" + "x" * 500,
    ],
)
def test_any_other_link_is_not(url):
    assert cover_link(url) is None


def test_each_source_gives_its_cover():
    assert apple_cover(APPLE.replace("600x600bb", "100x100bb")) == APPLE
    assert apple_cover(None) is None
    assert bandcamp_cover(2340984311) == BANDCAMP
    assert bandcamp_cover(12) == "https://f4.bcbits.com/img/a0000000012_5.jpg"
    assert bandcamp_cover(0) is None
    assert bandcamp_cover(True) is None


def _match(cover=None):
    return Match(
        source="deezer",
        platform="deezer",
        id="1",
        url="https://www.deezer.com/track/1",
        title="x",
        artists=("y",),
        cover=cover,
    )


def test_the_cover_of_a_title_found_deezer_first():
    album = DeezerAlbum(id="7", title="x", cover=DEEZER)
    deezer = DeezerDetails(track_id="1", title="x", album=album)
    apple = AppleDetails(cover=APPLE)
    found = SearchResult("trouvé", _match(BANDCAMP), Details(deezer, apple))
    assert cover_of(found) == DEEZER
    found = SearchResult("trouvé", _match(BANDCAMP), Details(apple=apple))
    assert cover_of(found) == APPLE
    assert cover_of(SearchResult("trouvé", _match(BANDCAMP))) == BANDCAMP
    assert cover_of(SearchResult("rien")) is None
    assert cover_of(None) is None
    # Un lien d'ailleurs, gardé par une ancienne règle, ne se rend pas.
    assert cover_of(SearchResult("trouvé", _match("https://x.example/a.jpg"))) is None


def test_the_cover_goes_through_the_kept_evidence():
    album = DeezerAlbum(id="7", title="x", cover=DEEZER)
    found = SearchResult(
        "trouvé", _match(), Details(DeezerDetails("1", "x", album=album))
    )
    result, _ = from_json(to_json(found, {}))
    assert cover_of(result) == DEEZER
    # Des preuves gardées avant FON-83 se relisent, sans pochette.
    older = to_json(found, {})
    del older["result"]["details"]["deezer"]["album"]["cover"]
    result, _ = from_json(older)
    assert cover_of(result) is None


def test_deezer_and_apple_music_details_keep_the_link():
    services = Services(
        {
            "https://api.deezer.com/track/1": {
                "id": 1,
                "title": "x",
                "album": {"id": 7, "title": "Album"},
            },
            "https://api.deezer.com/album/7": {
                "id": 7,
                "title": "Album",
                "cover_big": DEEZER,
                "cover_xl": DEEZER.replace("500x500", "1000x1000"),
            },
            "https://itunes.apple.com/lookup?id=5&country=FR": {
                "results": [{"artworkUrl100": APPLE.replace("600x600bb", "100x100bb")}]
            },
        }
    )
    client = http(services)
    assert deezer_details(client, "deezer", "1").album.cover == DEEZER
    assert apple_details(client, "5").cover == APPLE


def test_the_content_policy_admits_each_host_of_covers():
    """La console ne charge une pochette que si sa politique de contenu admet son
    hôte : chaque domaine que le moteur rend y est, en HTTPS."""
    header = next(
        line
        for line in TEMPLATE.read_text(encoding="utf-8").splitlines()
        if line.startswith("add_header Content-Security-Policy")
    )
    policy = re.search(r"img-src ([^;\"]+)", header)
    assert policy is not None
    admitted = policy.group(1).split()
    assert "'self'" in admitted
    assert sorted(admitted[1:]) == sorted(
        f"https://*.{domain}" for domain in COVER_DOMAINS
    )
