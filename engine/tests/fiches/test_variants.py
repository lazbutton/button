"""Reconnaître un titre à la lettre près : les cas de Hopper.

Le bloc « à la lettre près » de `tests/radio.test.ts`, et le bloc `compare` de
`tests/score.test.ts`, qui porte le conflit de versions.
"""

import re

import pytest

from radiotomate.fiches.variants import (
    Meta,
    RadioTrack,
    compare,
    radio_variants,
    same_radio_track,
)


def sure(artist: str, title: str, artists: list[str], found: str) -> bool:
    """Une variante du fichier trouve-t-elle ce morceau, à la lettre près ?"""
    candidate = Meta(title=found, artists=tuple(artists))
    return any(
        same_radio_track(variant, candidate)
        for variant in radio_variants(RadioTrack(artist, title))
    )


@pytest.mark.parametrize(
    ("artist", "title", "artists", "found"),
    [
        # Un nom au même squelette, un titre contenu dans un autre.
        ("KOYAKI", "LIFE", ["Kayak"], "Life Is Good"),
        # Une mention d'un seul côté : « Crypto (Mix) » n'est pas « Crypto », ni
        # « Muevete Ya (Bailando) » « Muevete Ya ».
        ("Mike D", "Crypto_Mix", ["Mike D"], "Crypto"),
        ("Whodamanny", "Muevete Ya (Bailando)", ["Whodamanny"], "Muevete Ya"),
        # Une intro, un autre remix, un titre coupé dans le fichier.
        (
            "DeepCuba",
            "Till The End Of Time",
            ["DeepCuba"],
            "Till The End Of Time (Intro)",
        ),
        (
            "Saint Etienne",
            "Only Love Can Break Your Heart (A Mix Of Two Halves)",
            ["Saint Etienne"],
            "Only Love Can Break Your Heart (Masters at Work Mix)",
        ),
        (
            "Louis Jucker",
            "01E - Louis Jucker - A Pharmac",
            ["Louis Jucker"],
            "A Modest Feast",
        ),
        (
            "Vincent Delerm",
            "Vincent Delerm / Je ne veux pa",
            ["Vincent Delerm"],
            "Je ne veux pas mourir ce soir",
        ),
        # Un autre artiste au même titre, un artiste du fichier absent du candidat.
        (
            "The Rhythmagic Orchestra",
            "African Mailman",
            ["Nostalgia 77"],
            "African Mailman",
        ),
        ("Bawrut x Scuola Fatoma", "Hobi ft Hatem Bouchnak", ["Bawrut"], "Hobi"),
        # Une reprise.
        ("Adele", "Hello", ["Adele"], "Hello (Karaoke Version)"),
    ],
)
def test_refuses_the_traps(artist, title, artists, found):
    assert not sure(artist, title, artists, found)


@pytest.mark.parametrize(
    ("artist", "title", "artists", "found"),
    [
        ("Coilguns", "Coilguns - Carbon Magic", ["Coilguns"], "Carbon Magic"),
        ("PAL", "PAL - C_est un désastre - 04 - Pays", ["PAL"], "Pays"),
        ("Cheval Fou", "L_oreille d_un sourd", ["Cheval Fou"], "L'oreille d'un sourd"),
        (
            "Combat dub",
            "Zion Train - Logical Progression",
            ["Zion Train"],
            "Logical progression",
        ),
        (
            "Porter, Nolan",
            "I Like What You Give",
            ["Nolan Porter"],
            "I Like What You Give",
        ),
        ("THE_ANSWER", "THE_BLACK_SEEDS", ["The Black Seeds"], "The Answer"),
        # « 72-Hour Sweat » garde son nombre ; « Ne\x01gationnistes » retrouve son
        # accent.
        ("LPV", "72-Hour Sweat", ["LPV"], "72 Hour Sweat"),
        ("Dogo Suicide", "Ne\x01gationnistes", ["Dogo Suicide"], "Négationnistes"),
    ],
)
def test_reads_what_a_file_name_writes(artist, title, artists, found):
    assert sure(artist, title, artists, found)


@pytest.mark.parametrize(
    ("artist", "title", "artists", "found", "same"),
    [
        (
            "Gayance",
            "Better For My Heart feat. Judith Little D",
            ["Gayance"],
            "Better For My Heart",
            True,
        ),
        (
            "Jacques Greene & umru",
            "What You Say",
            ["Jacques Greene"],
            "What You Say (ft umru)",
            True,
        ),
        (
            "Oli Morris",
            "Henry's Turtle",
            ["Oli Morris"],
            "Henry's Turtle (feat. Stevie Toddler)",
            True,
        ),
        ("Steffi & Rosati", "Bring The Beat", ["Rosati"], "Bring The Beat", False),
    ],
)
def test_a_guest_on_one_side_does_not_count(artist, title, artists, found, same):
    """Un invité cité d'un seul côté ne compte pas ; les artistes principaux, si."""
    assert sure(artist, title, artists, found) is same


@pytest.mark.parametrize(
    ("artist", "title"),
    [
        ("Envie d'être annoncé ? Contacte-nous !", "Pub 1"),
        ("Radio Campus France", "Jingle Mercato"),
    ],
)
def test_an_ad_or_a_jingle_is_not_searched(artist, title):
    assert radio_variants(RadioTrack(artist, title)) == []


@pytest.mark.parametrize(
    ("title", "first"),
    [
        # 0x1C et 0x1D, des espaces pour Python, sont pour JavaScript des guillemets
        # perdus en route.
        ("\x1cSong\x1d", "\u201cSong\u201d"),
        # Hopper met une version entre parenthèses avec le drapeau `u` : le « s » long
        # y est un « s », mais le « i » turc, avec ou sans point, n'y est pas un « i ».
        ("Song VER\u017fION", "Song (VER\u017fION)"),
        ("Song Rem\u0131x", "Song Rem\u0131x"),
        ("Song ED\u0130T", "Song ED\u0130T"),
    ],
)
def test_the_first_variant_reads_like_javascript(title, first):
    """Les réponses de Hopper, relevées par Node."""
    assert radio_variants(RadioTrack("Artiste", title))[0].title == first


def meta(**fields) -> Meta:
    defaults = {
        "title": "Get Lucky",
        "artists": ("Daft Punk",),
        "duration_ms": 248_000,
        "album": "Random Access Memories",
    }
    return Meta(**(defaults | fields))


HOUSTON = meta(
    title="Hotel California ('Live' at The Summit, Houston, 1976)",
    artists=("Eagles",),
    album="The Eagles Greatest Hits (Live)",
    duration_ms=422_000,
)


@pytest.mark.parametrize(
    ("source", "candidate", "conflict"),
    [
        # Une version différente, même à score parfait.
        (meta(), meta(title="Get Lucky (Radio Edit)"), r"radio edit"),
        # Deux remixes de remixeurs différents.
        (
            meta(title="Midnight City (Eric Prydz Remix)"),
            meta(title="Midnight City (Trentemøller Remix)"),
            r"^remixeurs différents$",
        ),
        # Une mention inconnue d'un seul côté.
        (meta(), meta(title="Get Lucky (Drumless Edition)"), r"drumless edition"),
        # Deux concerts.
        (
            HOUSTON,
            meta(
                title="Hotel California (Live)",
                artists=("Eagles",),
                album="Hell Freezes Over",
                duration_ms=425_000,
            ),
            r"^autre album live$",
        ),
        (
            HOUSTON,
            meta(
                title="Hotel California (Live on MTV, 1994)",
                artists=("Eagles",),
                album="The Eagles Greatest Hits (Live)",
                duration_ms=425_000,
            ),
            r"^concert différent$",
        ),
    ],
)
def test_compare_finds_the_conflict(source, candidate, conflict):
    found = compare(source, candidate).conflict
    assert found is not None
    assert re.search(conflict, found)


@pytest.mark.parametrize(
    ("source", "candidate", "accepted"),
    [
        # Le même morceau sur une autre plateforme.
        (
            meta(artists=("Daft Punk", "Pharrell Williams", "Nile Rodgers")),
            meta(
                title="Get Lucky (feat. Pharrell Williams & Nile Rodgers)",
                duration_ms=248_500,
            ),
            True,
        ),
        # Une version différente, même à score parfait.
        (meta(title="Hotel California"), meta(title="Hotel California (Live)"), False),
        (meta(title="Cola (Extended Mix)"), meta(title="Cola (Original Mix)"), False),
        # « Original Mix » est la version de base.
        (meta(title="Cola"), meta(title="Cola (Original Mix)"), True),
        # Un homonyme d'un autre artiste.
        (
            meta(title="Hello", artists=("Adele",), duration_ms=295_000, album="25"),
            meta(
                title="Hello",
                artists=("Lionel Richie",),
                duration_ms=251_000,
                album="Can't Slow Down",
            ),
            False,
        ),
        # Un invité ajouté après coup (« with Justin Bieber »).
        (
            meta(title="bad guy", artists=("Billie Eilish",)),
            meta(
                title="bad guy (with Justin Bieber)",
                artists=("Billie Eilish", "Justin Bieber"),
            ),
            False,
        ),
    ],
)
def test_compare_accepts(source, candidate, accepted):
    assert compare(source, candidate).accepted is accepted


def test_compare_same_track_scores_high():
    result = compare(
        meta(artists=("Daft Punk", "Pharrell Williams", "Nile Rodgers")),
        meta(
            title="Get Lucky (feat. Pharrell Williams & Nile Rodgers)",
            duration_ms=248_500,
        ),
    )
    assert result.score > 0.95


def test_compare_tolerates_a_remaster_on_one_side():
    """Un remaster d'un seul côté passe, avec une pénalité."""
    result = compare(
        meta(title="Bohemian Rhapsody", album="A Night at the Opera"),
        meta(title="Bohemian Rhapsody - Remastered 2011", album="A Night at the Opera"),
    )
    assert result.conflict is None
    assert result.score == pytest.approx(0.9, abs=0.005)


def test_compare_penalizes_explicit_against_clean():
    assert compare(meta(explicit=True), meta(explicit=False)).score == pytest.approx(
        0.95, abs=0.005
    )
