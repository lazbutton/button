"""La troisième passe : le bloc « troisième passe » de `tests/radio-catalogue.test.ts`,
dans Hopper.

Hopper a mesuré la passe sur 100 introuvables tirés au hasard : 26 trouvés, tous
justes. La recherche avec le texte relu, l'album du fichier, Tidal et MusicBrainz
viendra avec FON-24 ; les corrections que la passe propose sont dans
`test_proposals.py`.
"""

import pytest

from radiotomate.fiches.third import (
    Reading,
    ThirdCandidate,
    any_artist,
    any_title,
    damaged,
    readings,
    third_match,
)
from radiotomate.fiches.variants import RadioTrack


def read(artist: str, title: str, album: str = "") -> list[Reading]:
    return readings(RadioTrack(artist, title), album)


def test_an_annotation_in_brackets_is_removed():
    assert Reading(
        "Eric B. & Rakim", "My Melody", "annotation entre crochets retirée"
    ) in read("Eric B. & Rakim", "My Melody ['We Can Get Down']")


def test_a_version_in_brackets_stays():
    """« [Live] » n'est pas une annotation."""
    assert all(reading.title != "Song" for reading in read("X", "Song [Live]"))


@pytest.mark.parametrize(
    ("artist", "title", "read_title", "fix"),
    [
        (
            "CHOUK BWA & THE ÅNGSTRÖMERS",
            "02-MOVE TAN",
            "MOVE TAN",
            "numéro de piste collé",
        ),
        (
            "Mekon",
            "Yes Yes Yall (Sinden Baile Funk Mix) 8",
            "Yes Yes Yall (Sinden Baile Funk Mix)",
            "chiffre en trop",
        ),
        (
            "AM",
            "Self Preservation (Los Amparit",
            "Self Preservation",
            "parenthèse coupée retirée",
        ),
    ],
)
def test_the_file_s_text_is_read_again(artist, title, read_title, fix):
    """Un numéro de piste collé, un chiffre en trop, une parenthèse coupée."""
    assert any(
        reading.title == read_title and reading.fix == fix
        for reading in read(artist, title)
    )


def test_a_version_out_of_brackets_is_put_back_in():
    titles = [
        reading.title
        for reading in read(
            "melanie de biasio", "I'm gonna leave you the cinematic orchestra rmx"
        )
    ]
    assert "I'm gonna leave you (the cinematic orchestra rmx)" in titles


def test_the_artist_of_a_radio_campus_france_title():
    assert read("Radio Campus France", "FANFARE FOR 7.83Hz | PHOTAY")[0] == Reading(
        "PHOTAY", "FANFARE FOR 7.83Hz", "artiste lu dans le titre"
    )


@pytest.mark.parametrize(
    ("text", "damaged_text"),
    [
        ("Wśród pampasów", "W[rsd pampassw"),
        ("Marie-Thérèse", "Marie-Thirhse"),
    ],
)
def test_damaged_by_the_import(text, damaged_text):
    """Chaque signe hors ASCII réduit à ses 7 bits de poids faible."""
    assert damaged(text) == damaged_text


def test_a_title_damaged_by_the_import():
    assert any_title("W[rsd Pampassw", "Wśród pampasów") == "titre aux accents perdus"


def test_an_artist_damaged_by_the_import():
    assert (
        any_artist(
            "Gra|yna Aobaszewska & Ergo Band",
            ["Grażyna Łobaszewska", "Ergo Band"],
            "Za górą gór",
        )
        == "artiste aux accents perdus"
    )


def test_a_title_in_another_script():
    assert (
        any_title("apo limani se limani", "Από λιμάνι σε λιμάνι")
        == "titre dans une autre écriture"
    )


@pytest.mark.parametrize(
    ("radio", "found", "found_title", "why"),
    [
        (
            "Zorn Lewis Frisell",
            ["John Zorn", "George Lewis", "Bill Frisell"],
            "Sonny's Crib",
            "artistes par leur nom",
        ),
        (
            "GILAD AZMON AND THE ORIENT HOU",
            ["Gilad Atzmon & The Orient House Ensemble"],
            "Dal'ouna On The Return",
            "artiste coupé à 30 signes",
        ),
        ("KMTR", ["Sorarim"], "Sorarim (KMTR Edit)", "artiste remixeur"),
        ("Low", ["Low Leaf"], "Hold", None),
        # Tous dans un seul nom : seulement avec des mots d'ensemble en plus.
        (
            "SUPER_RAIL_BAMAKO",
            ["Super Rail Band de Bamako"],
            "Pirates",
            "artistes par leur nom",
        ),
        ("Lonnie Smith", ["Lonnie Liston Smith"], "I Can't Stand It", None),
    ],
)
def test_an_artist_cut_by_surnames_or_remixer(radio, found, found_title, why):
    """Un artiste coupé, par ses noms de famille, ou remixeur."""
    assert any_artist(radio, found, found_title) == why


GREEK = {
    "title": "Από λιμάνι σε λιμάνι",
    "artists": ("Νάντια Κωνσταντοπούλου",),
    "duration_ms": 163_000,
}
GREEK_READING = Reading("Nantia Kwnstantopoulou", "apo limani se limani")


def test_an_album_track_needs_no_artist_with_a_sure_title():
    """Un morceau de l'album du fichier se passe de l'artiste, avec un titre sûr."""
    found = third_match(
        GREEK_READING, ThirdCandidate(**GREEK, from_album=True), 163, album_ok=True
    )
    assert found is not None
    assert found.why == (
        "dans l'album de la radio",
        "titre dans une autre écriture",
        "durée à 0 s",
    )


@pytest.mark.parametrize(
    ("from_album", "radio_seconds", "album_ok"),
    [
        # Hors de l'album du fichier.
        (False, 163, True),
        # 7 s d'écart, au-delà de 5.
        (True, 170, True),
        # Un album au nom de l'artiste n'est pas une compilation.
        (True, 163, False),
    ],
)
def test_no_album_track_without_the_artist(from_album, radio_seconds, album_ok):
    candidate = ThirdCandidate(**GREEK, from_album=from_album)
    assert third_match(GREEK_READING, candidate, radio_seconds, album_ok) is None


@pytest.mark.parametrize(
    ("duration_ms", "radio_seconds"), [(None, 163), (163_000, None)]
)
def test_nothing_is_close_without_both_durations(duration_ms, radio_seconds):
    """Sans durée d'un côté ou de l'autre, rien n'est rapproché."""
    candidate = ThirdCandidate(**{**GREEK, "duration_ms": duration_ms}, from_album=True)
    assert third_match(GREEK_READING, candidate, radio_seconds, album_ok=True) is None


def test_the_artist_read_as_a_title_is_not_looked_for_in_the_album():
    swapped = next(
        reading
        for reading in read("THE WORLD", "THE ACHIEVEMENT", "THE WORLD")
        if reading.title == "THE WORLD"
    )
    assert swapped.swapped
    candidate = ThirdCandidate(
        "The World", ("J.Soul",), duration_ms=178_000, from_album=True
    )
    assert third_match(swapped, candidate, 181, album_ok=True) is None
