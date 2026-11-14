"""
Une banque fabriquée, au plus près de vrais fichiers en désordre.

Elle sert au banc quand on n'a pas de copie de vraie banque
(`BUTTON_BANQUE_ECHANTILLON`), et au test du banc, que la CI lance. Rien ici
ne vient d'une station : les noms sont inventés, et les sons sont deux petits
MP3 du dépôt, des sinus et des silences.

Le désordre qu'elle copie de ce qu'une banque associative accumule :

- des tags anciens : ID3v2.3 en latin-1 avec un ID3v1 qui dit autre chose, un
  APEv2 posé après l'ID3, un artiste en double (deux valeurs d'un même champ) ;
- des tags absents, ou « Artiste - Titre » entassé dans le seul titre ;
- des noms en forme décomposée (« e » puis son accent), une extension en
  majuscules, un nom à rallonge, des espaces doublés ;
- des formats variés : MP3, WAV, puis FLAC, Opus, AAC, AIFF si ffmpeg est là ;
- le même fichier en deux endroits, et ce qui n'est pas audio ou n'est pas lisible ;
- une collection au nom qui finit par une virgule, qu'une requête de Beets
  prendrait pour toute la bibliothèque.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import wave
from pathlib import Path

from mutagen.apev2 import APEv2
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TIT2, TPE1, TYER

ASSETS = Path(__file__).parents[1] / "assets"
SMALL = ASSETS / "ohradiotomateoh.mp3"
OTHER = ASSETS / "winamp-it-really-whips-the-llamas-ass.mp3"

# Les formats que ffmpeg fabrique : extension, puis ses options de sortie.
FFMPEG_FORMATS = {
    ".flac": ("-c:a", "flac"),
    ".opus": ("-c:a", "libopus"),
    ".m4a": ("-c:a", "aac"),
    ".aiff": ("-c:a", "pcm_s16be"),
}


def _wav(path: Path, seconds: int = 2, rate: int = 8000, tone: int = 0) -> None:
    """Un WAV en 16 bits mono : un carré lent, ou le silence."""
    period = max(rate // tone, 2) if tone else 0
    frames = bytearray()
    for index in range(rate * seconds):
        high = bool(period) and (index // (period // 2)) % 2 == 0
        frames += (6000 if high else 0).to_bytes(2, "little", signed=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))


def _transcode(source: Path, target: Path) -> bool:
    """Le WAV `source` dans le format de `target`. Faux sans ffmpeg ni encodeur."""
    options = FFMPEG_FORMATS[target.suffix.lower()]
    if shutil.which("ffmpeg") is None:
        return False
    done = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source), *options, str(target)],
        capture_output=True,
        check=False,
        timeout=60,
    )
    return done.returncode == 0 and target.is_file()


def _mp3(path: Path, source: Path = SMALL) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, path)
    return path


def _id3(path: Path, *, v1: bool = False, version: int = 4, **tags: str) -> None:
    """Des tags ID3 neufs : ceux d'avant s'en vont, comme ceux d'un fichier retaggué."""
    with contextlib.suppress(Exception):  # sans ID3, il n'y a rien à vider
        ID3(path).delete()
    frames = ID3()
    encoding = 0 if version == 3 else 3
    classes = {"artist": TPE1, "title": TIT2, "album": TALB, "year": TYER}
    for name, value in tags.items():
        frames.add(classes[name](encoding=encoding, text=[value]))
    frames.save(path, v1=2 if v1 else 0, v2_version=version)


def fabricate(media: Path) -> dict[str, int]:
    """Remplit `media` d'une banque en désordre. Rend les fichiers par extension."""
    rotation = media / "10-rotation"
    collections = media / "20-archives"

    # Une rotation à plat, avec des tags de plusieurs âges.
    _id3(
        _mp3(rotation / "Ada Quartet - Premier jour.mp3"),
        artist="Ada Quartet",
        title="Premier jour",
    )
    # ID3v2.3 en latin-1 et ID3v1 qui dit autre chose : deux étiquettes dans un fichier.
    _id3(
        _mp3(rotation / "Bea Trio - Les Phares.mp3", OTHER),
        v1=True,
        version=3,
        artist="Bea Trio",
        title="Les Phares (vieille version)",
        album="Face A",
        year="1987",
    )
    # Un APEv2 posé après l'ID3, comme en laissent d'anciens logiciels.
    ape = _mp3(rotation / "Cy Orchestre - Sans fin.mp3")
    _id3(ape, artist="Cy Orchestre", title="Sans fin")
    tag = APEv2()
    tag["Artist"] = "Cy Orchestre (ape)"
    tag["Title"] = "Sans fin (ape)"
    tag.save(ape)
    # « Artiste - Titre » dans le seul titre, sans artiste.
    _id3(
        _mp3(rotation / "Dan Ensemble - Mer calme.mp3"),
        title="Dan Ensemble - Mer calme",
    )
    # Aucun tag.
    _mp3(rotation / "Eve et les Voix - Sans tags.mp3", OTHER)
    # Un nom en forme décomposée : « é » écrit « e » puis son accent.
    _id3(
        _mp3(rotation / "Élise Chorale - Éte indien.mp3"),
        artist="Élise Chorale",
        title="Éte indien",
    )
    # Une extension en majuscules, des espaces doublés.
    _mp3(rotation / "Fab  Duo -  Deux  espaces.MP3", OTHER)
    # Un nom qui frôle la limite du système de fichiers.
    _mp3(rotation / (("Gil Fanfare - " + "Très long titre " * 13).strip() + ".mp3"))

    # Une collection, des sous-dossiers, et le même fichier qu'en rotation.
    jazz = collections / "jazz"
    _id3(
        _mp3(jazz / "Hal Big Band - Live à Orléans.mp3"),
        artist="Hal Big Band",
        title="Live à Orléans",
    )
    _mp3(jazz / "1997" / "Ida Quintet - Nuit blanche.mp3", OTHER)
    _mp3(jazz / "Ada Quartet - Premier jour.mp3")
    # Une collection dont le nom finit par une virgule.
    _mp3(collections / "Foo," / "Jo Fanfare - Marche.mp3")
    # Une collection au nom décomposé.
    _mp3(collections / "Crème de la crème" / "Kim Solo - Seul.mp3", OTHER)

    # L'habillage : un dossier de jingles que suit un bac.
    for rank in (1, 2, 3):
        _wav(
            media / "30-habillage" / "jingles" / f"Jingle {rank}.wav",
            seconds=2,
            tone=300 * rank,
        )
    # Un set de l'Agenda, dans les émissions.
    _id3(
        _mp3(media / "40-emissions" / "Emission test" / "entiere" / "Set du soir.mp3"),
        title="Set du soir",
    )

    # Des formats variés, en rotation, avec ce que ffmpeg sait encoder.
    seed = media.parent / "fabrique-wav.wav"
    _wav(seed, seconds=2, tone=440)
    _wav(rotation / "Lou Studio - Sine wav.wav", seconds=2, tone=523)
    for suffix in FFMPEG_FORMATS:
        target = rotation / f"Max Atelier - Format {suffix[1:]}{suffix}"
        if _transcode(seed, target) and suffix == ".flac":
            flac = FLAC(target)
            flac["ARTIST"] = ["Max Atelier", "Max Atelier (doublon)"]
            flac["TITLE"] = "Format flac"
            flac.save()
    seed.unlink()

    # Ce qui n'est pas lisible ou pas audio.
    (rotation / "Zed Vide - Zéro octet.mp3").write_bytes(b"")
    (rotation / "Zoe Coupee - Fichier tronqué.mp3").write_bytes(
        SMALL.read_bytes()[:700]
    )
    (rotation / "notes.txt").write_text("pas de l'audio\n", encoding="utf-8")
    (rotation / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")

    counts: dict[str, int] = {}
    for path in media.rglob("*"):
        if path.is_file() and not path.name.startswith("."):
            counts[path.suffix.lower()] = counts.get(path.suffix.lower(), 0) + 1
    return counts
