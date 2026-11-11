"""Le texte normalisé : les cas de `tests/normalize.test.ts`, dans Hopper."""

import re

import pytest

from radiotomate.fiches.normalize import (
    js_regex,
    js_trim,
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


@pytest.mark.parametrize(
    ("pattern", "flags", "text", "found"),
    [
        # Les espaces de JavaScript : ni 0x1F ni 0x85, que Python compte, mais U+FEFF.
        (r"\s", 0, "Da\x1flar", False),
        (r"\s", 0, "a\x85b", False),
        (r"\s", 0, "\ufeffSong", True),
        (r"\s", 0, "a\u00a0b", True),
        (r"^\S+\Z", 0, "Da\x1flar", True),
        # `\b` et `\B` ne connaissent que les lettres ASCII.
        (r"\bet\b", 0, "Søet", True),
        (r"a\B", 0, "aé", False),
        # Le `.` ne prend aucun saut de ligne.
        (r"^a.b\Z", 0, "a\rb", False),
        (r"^a.b\Z", 0, "a\u2028b", False),
        (r"^a.b\Z", 0, "a b", True),
        # Sans le drapeau `u`, seules les lettres ASCII changent de casse : ni le « İ »
        # ni le « i » sans point turcs, ni le signe kelvin.
        (r"^featuring\Z", re.IGNORECASE, "FEATURING", True),
        (r"^featuring\Z", re.IGNORECASE, "FEATURİNG", False),
        (r"^remix\Z", re.IGNORECASE, "REM\u0131X", False),
        (r"^k\Z", re.IGNORECASE, "\u212a", False),
        # Une regex aux classes d'Unicode, écrite pour le drapeau `u` : la casse
        # d'Unicode, où le « s » long est un « s ».
        (r"^(?=[^\W\d_])s\Z", re.IGNORECASE, "\u017f", True),
    ],
)
def test_js_regex_reads_like_javascript(pattern, flags, text, found):
    """Les réponses de JavaScript, relevées par Node 24."""
    assert bool(js_regex(pattern, flags).search(text)) is found


@pytest.mark.parametrize(
    ("pattern", "error"),
    [
        (r"[\S]", "classe d'espaces"),
        (r"[\x00-\s]", "classe d'espaces"),
        (r"[\s-x]", "classe d'espaces"),
        (r"(?i)abc", "drapeau"),
    ],
)
def test_js_regex_refuses_what_it_cannot_translate(pattern, error):
    """Ce qui n'a pas de traduction est refusé, plutôt que lu de travers."""
    with pytest.raises(ValueError, match=error):
        js_regex(pattern)


@pytest.mark.parametrize(
    ("text", "trimmed"),
    [
        ("\ufeff Dağlar \u00a0", "Dağlar"),
        # 0x1F, « ğ » abîmé à l'import, et 0x85 ne sont pas des espaces.
        ("\x1fDağlar\x85", "\x1fDağlar\x85"),
    ],
)
def test_js_trim(text, trimmed):
    assert js_trim(text) == trimmed
