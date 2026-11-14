"""Le nom d'un fichier de la banque d'après sa fiche (FON-68)."""

import unicodedata

import pytest

from radiotomate.services.bank_names import NAME_MAX, clean, file_name, fit, renamed

ADA = {"artist": "Ada", "album": "Nuits", "title": "Un"}


@pytest.mark.parametrize(
    ("model", "name"),
    [
        ("artiste-titre", "Ada - Un.mp3"),
        ("artiste-album-titre", "Ada - Nuits - Un.mp3"),
        ("titre", "Un.mp3"),
    ],
)
def test_each_model(model: str, name: str):
    assert file_name(ADA, model, ".mp3") == (name, "")


def test_a_fiche_without_its_field_names_nothing():
    assert file_name({"title": "Un"}, "artiste-titre", ".mp3") == (
        None,
        "la fiche n'a pas d'artiste",
    )
    no_album = {"artist": "Ada", "title": "Un"}
    assert file_name(no_album, "artiste-album-titre", ".mp3")[1] == (
        "la fiche n'a pas d'album"
    )
    assert file_name({"artist": "Ada", "title": "  "}, "titre", ".mp3")[1] == (
        "la fiche n'a pas de titre"
    )
    assert file_name(ADA, "autre", ".mp3") == (None, "modèle inconnu")


def test_the_signs_windows_refuses_are_replaced():
    assert clean('AC/DC: "Live" <1979>?*|\\') == "AC_DC_ _Live_ _1979_____"
    assert clean("Un\x00 titre\x1f\x7f") == "Un titre"
    assert clean(".cache") == "_cache"
    assert clean("-M-") == "_M-"
    assert clean("Vol.") == "Vol_"
    assert clean("  deux   espaces  ") == "deux espaces"


def test_decomposed_accents_are_composed():
    """Un Mac écrit souvent « É » en deux signes : E, puis l'accent."""
    fiche = {
        "artist": unicodedata.normalize("NFD", "Élodie"),
        "title": unicodedata.normalize("NFD", "Été"),
    }
    name, _why = file_name(fiche, "artiste-titre", unicodedata.normalize("NFD", ".mp3"))
    assert name == unicodedata.normalize("NFC", "Élodie - Été.mp3")
    assert len(name) == len("Elodie - Ete.mp3")


def test_a_name_holds_in_255_bytes_with_its_extension():
    name = fit("é" * 300, ".flac")
    assert len(name.encode("utf-8")) <= NAME_MAX
    assert name.endswith(".flac")
    # Never half a letter.
    assert name.encode("utf-8").decode("utf-8") == name


@pytest.mark.parametrize(
    ("rel", "by_artist", "new"),
    [
        ("10-rotation/03_un.mp3", False, "10-rotation/Ada - Un.mp3"),
        ("10-rotation/vieux/03_un.mp3", False, "10-rotation/vieux/Ada - Un.mp3"),
        ("10-rotation/vieux/03_un.mp3", True, "10-rotation/Ada/Ada - Un.mp3"),
        (
            "20-archives/jazz/live/03_un.flac",
            True,
            "20-archives/jazz/Ada/Ada - Un.flac",
        ),
        ("20-archives/jazz/03_un.flac", False, "20-archives/jazz/Ada - Un.flac"),
    ],
)
def test_a_title_stays_on_its_shelf(rel: str, by_artist: bool, new: str):
    assert renamed(rel, ADA, "artiste-titre", by_artist=by_artist) == (new, "")


def test_a_folder_of_its_artist_needs_an_artist():
    assert renamed("10-rotation/a.mp3", {"title": "Un"}, "titre", by_artist=True) == (
        None,
        "la fiche n'a pas d'artiste",
    )
    assert renamed("10-rotation", ADA, "titre")[0] is None
