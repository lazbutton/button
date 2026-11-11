"""Le texte normalisé : les cas de `tests/normalize.test.ts`, dans Hopper."""

import pytest

from radiotomate.fiches.normalize import (
    latin_words,
    normalize_text,
    parse_title,
    search_terms,
    split_artists,
)


@pytest.mark.parametrize(
    ("title", "terms"),
    [
        ("Get Lucky (Radio Edit - feat. Pharrell Williams)", "get lucky radio edit"),
        ("Midnight City (Eric Prydz Remix)", "midnight city eric prydz remix"),
        ("Bohemian Rhapsody - Remastered 2011", "bohemian rhapsody"),
    ],
)
def test_search_terms_keep_the_version(title, terms):
    """La version reste dans les mots de la recherche, pour trouver la bonne."""
    assert search_terms(title) == terms


@pytest.mark.parametrize(
    ("text", "normalized"),
    [
        ("Désenchantée", "desenchantee"),
        ("Don't Stop Me Now", "dont stop me now"),
        ("Harder, Better, Faster, Stronger", "harder better faster stronger"),
        ("HUMBLE.", "humble"),
        ("Rock & Roll", "rock and roll"),
        ("Группа крови", "группа крови"),
        ("  L\u2019amour   toujours ", "lamour toujours"),
    ],
)
def test_normalize_text(text, normalized):
    assert normalize_text(text) == normalized


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("Группа крови", ["gruppa", "krovi"]),
        ("Από λιμάνι σε λιμάνι", ["apo", "limani", "se", "limani"]),
        ("Lotte Kærså", ["lotte", "kaersa"]),
        ("Łobaszewska", ["lobaszewska"]),
        # Les voyelles coréennes valent toutes « a ».
        ("서울", ["saal"]),
        ("Don't Stop", ["dont", "stop"]),
    ],
)
def test_latin_words(text, words):
    """Le texte en latin, mot par mot : d'après les exemples de `normalize.ts`, que
    ses tests ne lisent pas directement."""
    assert latin_words(text) == words


@pytest.mark.parametrize(
    ("names", "artists"),
    [
        ("Major Lazer & DJ Snake", ["major lazer", "dj snake"]),
        (["Daft Punk", "Pharrell Williams"], ["daft punk", "pharrell williams"]),
        ("Kassius Nord x Mira K", ["kassius nord", "mira k"]),
        # Un nom qui finit par x n'est pas coupé.
        ("Malcolm X", ["malcolm x"]),
    ],
)
def test_split_artists(names, artists):
    assert split_artists(names) == artists


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("Christine and the Queens", "Christine & The Queens"),
        ("Bigflo et Oli", "Bigflo & Oli"),
    ],
)
def test_split_artists_reads_both_sides_alike(one, other):
    """Toutes les conjonctions séparent, des deux côtés pareil."""
    assert split_artists(one) == split_artists(other)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("One More Time", {"base": "one more time", "tags": []}),
        (
            "Get Lucky (Radio Edit) [feat. Pharrell Williams & Nile Rodgers]",
            {
                "base": "get lucky",
                "tags": ["radio edit"],
                "featuring": ["pharrell williams", "nile rodgers"],
            },
        ),
        (
            "Get Lucky (Radio Edit - feat. Pharrell Williams and Nile Rodgers)",
            {
                "base": "get lucky",
                "tags": ["radio edit"],
                "featuring": ["pharrell williams", "nile rodgers"],
            },
        ),
        (
            "Bohemian Rhapsody - Remastered 2011",
            {"base": "bohemian rhapsody", "tags": ["remaster"]},
        ),
        (
            "La vie en rose (Remasterisé en 2015)",
            {"base": "la vie en rose", "tags": ["remaster"]},
        ),
        (
            "Hotel California (Live on MTV, 1994)",
            {"base": "hotel california", "tags": ["live"]},
        ),
        (
            "Midnight City (Eric Prydz Remix)",
            {"base": "midnight city", "tags": ["remix"], "remixers": ["eric prydz"]},
        ),
        ("Cola (Original Mix)", {"base": "cola", "tags": []}),
        ("Cola (Extended Mix)", {"base": "cola", "tags": ["extended"]}),
        (
            "Blue (Da Ba Dee) - Gabry Ponte Ice Pop Mix",
            {
                "base": "blue",
                "tags": ["remix"],
                "remixers": ["gabry ponte ice pop"],
                "extras": ["da ba dee"],
            },
        ),
        (
            "Chandelier (Piano Version)",
            {"base": "chandelier", "tags": ["version:piano"]},
        ),
        ("Christine (English Version)", {"base": "christine", "tags": ["langue:en"]}),
        ("Without Me (Clean)", {"base": "without me", "tags": []}),
        ("Lean On feat. MØ", {"base": "lean on", "tags": [], "featuring": ["mø"]}),
        (
            "bad guy (with Justin Bieber)",
            {"base": "bad guy", "tags": [], "featuring": ["justin bieber"]},
        ),
        ("Alors on danse - Remix", {"base": "alors on danse", "tags": ["remix"]}),
        (
            'Stayin\' Alive (From "Saturday Night Fever")',
            {"base": "stayin alive", "tags": []},
        ),
        ("Gymnopédie No. 1", {"base": "gymnopedie no 1", "tags": []}),
        ("Live and Let Die", {"base": "live and let die", "tags": []}),
        (
            "Clair de lune (Suite bergamasque)",
            {"base": "clair de lune", "tags": [], "extras": ["suite bergamasque"]},
        ),
        (
            "Get Lucky (Drumless Edition) (feat. Pharrell Williams and Nile Rodgers)",
            {"base": "get lucky", "tags": [], "extras": ["drumless edition"]},
        ),
        (
            "Hotel California ('Live' at The Summit, Houston, 1976)",
            {"base": "hotel california", "tags": ["live"], "years": ["1976"]},
        ),
    ],
)
def test_parse_title(title, expected):
    parsed = parse_title(title)
    assert parsed.base == expected["base"]
    assert sorted(parsed.tags) == sorted(expected["tags"])
    for key in ("featuring", "remixers", "extras", "years"):
        if key in expected:
            assert list(getattr(parsed, key)) == expected[key]
