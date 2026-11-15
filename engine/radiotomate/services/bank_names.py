"""The name of a file of the bank, after its fiche (FON-68).

A pure module: no Beets, no disk. It says what a title of the rotation or of a
collection would be called, after a model: « Artiste - Titre »,
« Artiste - Album - Titre » or « Titre », in its folder or in a folder of its
artist. The move itself, which keeps the title's identity, is ARC-09's
(``services/bank_moves.py``).

A name is one the station's folder can show on every machine that opens it,
a Mac, Windows through the shared folder, Linux: the signs Windows refuses are
replaced as Beets replaces them when it files a library, the control signs go,
the accents are composed (NFC: a Mac often writes them decomposed), and a name
holds in 255 bytes, its extension kept.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath

from radiotomate.services.media_bank import ROTATION_TOP

# The models, and the fields of the fiche each one joins.
MODELS = {
    "artiste-titre": ("artist", "title"),
    "artiste-album-titre": ("artist", "album", "title"),
    "titre": ("title",),
}
SEPARATOR = " - "
# One name of the file system, in bytes, as ext4 and APFS count it.
NAME_MAX = 255
# What Beets replaces when it files a library (its ``replace`` setting), the
# signs a Windows machine refuses through the shared folder.
_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_REPLACEMENT = "_"
# Why a title is not renamed, in French: the console shows it as it is.
MISSING = {
    "artist": "la fiche n'a pas d'artiste",
    "album": "la fiche n'a pas d'album",
    "title": "la fiche n'a pas de titre",
}
# A track number taken for the artist: promote-inbox.sh cuts a name at its
# first « - », and « 01 - Ana - Fado.mp3 » got the artist « 01 ». No name is
# built on it: « 01 - 01 - Ana - Fado.mp3 » would be worse than the file's own.
_TRACK_NUMBER = re.compile(r"[0-9]{1,2}")
NUMBERED = "l'artiste de la fiche est un numéro de piste"


def clean(value: object) -> str:
    """A field of the fiche, as a piece of a file name."""
    text = unicodedata.normalize("NFC", str(value or ""))
    text = _CONTROL.sub("", text)
    text = _FORBIDDEN.sub(_REPLACEMENT, text)
    text = " ".join(text.split())
    # Neither hidden, nor taken for an option, nor ending in a dot Windows drops.
    if text.startswith((".", "-")):
        text = _REPLACEMENT + text[1:]
    if text.endswith("."):
        text = text[:-1] + _REPLACEMENT
    return text


def fit(stem: str, suffix: str = "", limit: int = NAME_MAX) -> str:
    """The name in ``limit`` bytes: the stem shortened from its end, the suffix kept."""
    room = limit - len(suffix.encode("utf-8"))
    raw = stem.encode("utf-8")
    if len(raw) > room:
        stem = raw[: max(room, 1)].decode("utf-8", "ignore").rstrip(" .")
    return (stem or _REPLACEMENT) + suffix


def track_number(value: object) -> bool:
    """An artist that is only a track number, « 01 » or « 7 »."""
    return bool(_TRACK_NUMBER.fullmatch(clean(value)))


def fields_after_number(path: str) -> dict | None:
    """The artist and the title a file's name gives after its track number, cut
    as promote-inbox.sh cuts it: « 01 - Ana - Fado.mp3 » gives Ana and Fado.
    None for a name that starts with no track number, or gives no artist."""
    stem = unicodedata.normalize("NFC", PurePosixPath(path).stem)
    number, cut, rest = stem.partition(SEPARATOR)
    if not cut or not track_number(number):
        return None
    artist, cut, title = rest.partition(SEPARATOR)
    artist, title = " ".join(artist.split()), " ".join(title.split())
    if not cut or not artist or not title or track_number(artist):
        return None
    return {"artist": artist, "title": title}


def file_name(fields: dict, model: str, suffix: str) -> tuple[str | None, str]:
    """The file's name after its fiche, or why there is none."""
    keys = MODELS.get(model)
    if keys is None:
        return None, "modèle inconnu"
    values = []
    for key in keys:
        value = clean(fields.get(key))
        if not value:
            return None, MISSING[key]
        if key == "artist" and track_number(value):
            return None, NUMBERED
        values.append(value)
    suffix = unicodedata.normalize("NFC", suffix)
    return fit(SEPARATOR.join(values), suffix), ""


def renamed(
    rel: str, fields: dict, model: str, *, by_artist: bool = False
) -> tuple[str | None, str]:
    """Where a title of the bank goes after its fiche, below the bank, or why not.

    ``rel`` is its path below the bank, in the rotation or a collection. It
    stays on its shelf: the rotation, or its collection. In its own folder, or
    with ``by_artist``, in a folder of its artist, right on its shelf.
    """
    parts = PurePosixPath(rel).parts
    shelf = 1 if parts and parts[0] == ROTATION_TOP else 2
    if len(parts) <= shelf:
        return None, "fichier hors de la rotation et des collections"
    name, why = file_name(fields, model, PurePosixPath(rel).suffix)
    if name is None:
        return None, why
    if by_artist:
        artist = clean(fields.get("artist"))
        if not artist:
            return None, MISSING["artist"]
        if track_number(artist):
            return None, NUMBERED
        folder = (*parts[:shelf], fit(artist))
    else:
        folder = parts[:-1]
    return PurePosixPath(*folder, name).as_posix(), ""
