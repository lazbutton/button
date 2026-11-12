"""La seconde passe : le bloc « rapprochement (seconde passe) » de
`tests/radio-catalogue.test.ts`, dans Hopper.

Ses cas viennent de 80 introuvables tirés au hasard et vérifiés à la main. La
recherche chez Deezer, MusicBrainz et Bandcamp, son dernier cas, est dans
`test_search.py`, sans Bandcamp, qui viendra avec FON-30.
"""

import pytest

from radiotomate.fiches.loose import (
    ONE_SIDED,
    Found,
    LooseCandidate,
    MbRelease,
    best,
    close_artist,
    close_title,
    edit_distance,
    first_release,
    generic_title,
    loose_match,
    loose_variants,
    nearly_same,
    same_version,
)
from radiotomate.fiches.variants import RadioTrack


def test_edit_distance():
    assert edit_distance("gonnaspedro", "gnonnaspedro") == 1


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Gonnas Pedro", "Gnonnas Pedro", True),
        ("the spec lady", "The Space Lady", True),
        ("Southsayers", "Soothsayers", True),
        # Un nom court ne tolère aucune faute.
        ("Low", "Lou", False),
        ("Kizumbau", "Kizumbo", False),
    ],
)
def test_one_or_two_typos_depending_on_the_length(a, b, same):
    """Une ou deux fautes de frappe, selon la longueur."""
    assert nearly_same(a, b) is same


@pytest.mark.parametrize(
    ("radio", "found", "why"),
    [
        ("Gonnas Pedro", ["Gnonnas Pedro"], "artiste à une faute près"),
        (
            "Joe Cuba Sextet",
            ["Joe Cuba Sextette"],
            "artiste à « The » ou à l'ensemble près",
        ),
        (
            "The tommy olivencia orchestra",
            ["Tommy Olivencia"],
            "artiste à « The » ou à l'ensemble près",
        ),
        ("the spec lady", ["The Space Lady"], "artiste à une faute près"),
        ("C L A U D E", ["Claude"], "même artiste"),
        # La faute se corrige, pas l'orchestre en plus : « Henry Mancini & His
        # Orchestra » ne remplace pas « Henri Mancini ».
        (
            "Henri Mancini",
            ["Henry Mancini & His Orchestra"],
            "artiste à une faute et à « The » ou à l'ensemble près",
        ),
        ("Willie Bobo", ["Willie Bobo & The Bo-Gents"], "artiste crédité autrement"),
        ("JFX MEETS BLEUBIRD", ["Bleubird"], "artiste crédité autrement"),
        ("DJ Pupo", ["Afro DJ Pupo"], "artiste crédité autrement"),
        ("Low", ["Low Leaf"], None),
        ("Luis Visconde E Alvarito", ["Kilereme"], None),
    ],
)
def test_close_artist(radio, found, why):
    """Un artiste écrit autrement, jamais un nom court contenu dans un autre."""
    assert close_artist(radio, found) == why


@pytest.mark.parametrize(
    ("radio", "found", "why"),
    [
        ("Oumako", "Oumako", "même titre"),
        (
            "L'accident est inivitable",
            "L'accident est inévitable",
            "titre à une faute près",
        ),
        ("Love having you a", "Love Having You Around", "titre coupé"),
        (
            "YOU KEEP TURNING ME",
            "You Keep On Turning Me On",
            "mots en plus ou en moins",
        ),
        # Deux mots ne suffisent pas à dire « mots manquants » (« Shattering
        # Journeys », « Shattering Inner Journeys »).
        ("Shattering Journeys feat Common", "Shattering Inner Journeys", None),
        # Trop court pour des mots manquants.
        ("I Love You", "I Love You Baby", None),
    ],
)
def test_close_title(radio, found, why):
    """Un titre fautif, coupé ou à mots manquants."""
    assert close_title(radio, found) == why


@pytest.mark.parametrize(
    ("radio", "found", "gap", "same"),
    [
        (
            "Constant Conversations (Chrome Canyon remix)",
            "Constant Conversations (Little Daylight Remix)",
            5,
            False,
        ),
        ("Song (Live)", "Song (Acoustic)", 0, False),
        (
            "Mexican Junkanoo Suite",
            "Mexican Junkanoo Suite (Part 1, Part 2 & Part 3)",
            0.8,
            True,
        ),
        (
            "Mexican Junkanoo Suite",
            "Mexican Junkanoo Suite (Part 1, Part 2 & Part 3)",
            5,
            False,
        ),
        ("Natural Mystic (Original Edit)", "Natural Mystic", 0, True),
        (
            "Ice Cream (Herve Goes Bananas Remix)",
            "Ice Cream (Hervé Goes Bananas Remix)",
            6,
            True,
        ),
        # Deux remixeurs nommés après « by » : deux remix.
        (
            "NOT_A_GOOD_PLACE_RMX_BY_RECHENZENTRUM",
            "Not a Good Place (remix by Apparat)",
            5,
            False,
        ),
        # Un mot de version hors parenthèses en est une ; une suite de titre, non.
        ("Fatty Boom Boom", "Fatty Boom Boom Remix", 5, False),
        ("Chest Fever", "Chest Fever Live", 1, True),
        ("you got the power", "You Got the Power - To Turn Me On", 4, True),
    ],
)
def test_never_another_remix(radio, found, gap, same):
    """Jamais un autre remix ; une mention d'un seul côté seulement à la même
    durée."""
    assert same_version(radio, found, gap) is same


GNONNAS = LooseCandidate("Oumako", ("Gnonnas Pedro",), duration_ms=596_100)


def test_a_loose_match_says_why():
    found = loose_match(RadioTrack("Gonnas Pedro", "Oumako"), GNONNAS, 596)
    assert found is not None
    assert (found.why, found.one_sided) == (
        ("artiste à une faute près", "même titre", "durée à 0 s"),
        False,
    )
    assert found.gap == pytest.approx(0.1, abs=5e-4)


def test_a_mention_on_one_side_is_noted():
    live = LooseCandidate("Oumako (Live)", ("Gnonnas Pedro",), duration_ms=596_100)
    found = loose_match(RadioTrack("Gnonnas Pedro", "Oumako"), live, 596)
    assert found is not None
    assert ONE_SIDED in found.why


@pytest.mark.parametrize(
    ("radio", "candidate", "radio_seconds"),
    [
        # 8 s d'écart.
        (RadioTrack("Gonnas Pedro", "Oumako"), GNONNAS, 588),
        # Sans durée d'un côté ou de l'autre, rien n'est rapproché.
        (
            RadioTrack("Gonnas Pedro", "Oumako"),
            LooseCandidate("Oumako", ("Gnonnas Pedro",)),
            596,
        ),
        (RadioTrack("Gonnas Pedro", "Oumako"), GNONNAS, None),
        # Un autre remix, à 5 s près : le seul faux de la mesure.
        (
            RadioTrack("Passion Pit", "Constant Conversations (Chrome Canyon remix)"),
            LooseCandidate(
                "Constant Conversations (Little Daylight Remix)",
                ("Passion Pit",),
                duration_ms=257_000,
            ),
            262,
        ),
        # Trop vague.
        (
            RadioTrack("Gotan Project Remix", "Piste 04"),
            LooseCandidate("Piste 04", ("Gotan Project",), duration_ms=232_000),
            232,
        ),
        # NaN, comme pour JavaScript : une durée inconnue.
        (
            RadioTrack("Gonnas Pedro", "Oumako"),
            LooseCandidate("Oumako", ("Gnonnas Pedro",), duration_ms=float("nan")),
            596,
        ),
        (RadioTrack("Gonnas Pedro", "Oumako"), GNONNAS, float("nan")),
        # « FEATURİNG », avec le « İ » turc, n'est pas une mention d'invité pour
        # JavaScript : le titre reste trop loin.
        (
            RadioTrack("TARKAN", "BU GECEE FEATUR\u0130NG G\u00d6KSEL"),
            LooseCandidate("Bu Gece", ("Tarkan",), duration_ms=200_000),
            201,
        ),
        # Un karaoké que le fichier ne nomme pas.
        (
            RadioTrack("The Space Lady", "Born to be wild"),
            LooseCandidate(
                "Born to Be Wild (Karaoke Version)",
                ("The Space Lady",),
                duration_ms=269_000,
            ),
            269,
        ),
    ],
)
def test_no_loose_match(radio, candidate, radio_seconds):
    """La durée est exigée, à 7 s près ; un titre trop vague est refusé."""
    assert loose_match(radio, candidate, radio_seconds) is None


@pytest.mark.parametrize("title", ["Intro", "Track 3"])
def test_generic_title(title):
    assert generic_title(title) is True


def test_a_file_number_is_removed_from_the_queries():
    variants = loose_variants(
        RadioTrack("FIRST_CHOICE", "Love_having_you_around_32915")
    )
    assert variants[0] == RadioTrack("FIRST CHOICE", "Love having you around")


def test_the_first_release_is_the_oldest_album():
    """Le plus ancien album qui n'est ni une compilation ni un live."""
    releases = [
        MbRelease("The Best of Soul Time", "2002", "Album", ("Compilation",)),
        MbRelease("Good, Bad & Funky", "1978", "Album"),
    ]
    assert first_release(releases) == "Good, Bad & Funky"


def test_the_best_candidate_has_the_same_version_first():
    """« Bara To Yajuu », 4:24 : plutôt le « Bara To Yaju » de 4:22 que le live de 4:24.

    Le cas de la recherche chez Deezer, dans Hopper, réduit à ce choix.
    """
    radio = RadioTrack("Haruomi Hosono", "Bara To Yajuu")
    live = LooseCandidate(
        "Bara to Yaju (Live at The Mayan Theatre, Los Angeles, July,2019)",
        ("Haruomi Hosono",),
        duration_ms=264_000,
    )
    studio = LooseCandidate("Bara To Yaju", ("Haruomi Hosono",), duration_ms=262_000)
    judged = [loose_match(radio, candidate, 264) for candidate in (live, studio)]
    assert all(isinstance(found, Found) for found in judged)
    assert best(judged) == Found(
        ("même artiste", "titre à une faute près", "durée à 2 s"), 2, False
    )
    assert best([]) is None
