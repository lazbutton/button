"""Contenu de la banque : voir, écouter, retirer et déplacer les titres de la
rotation et des collections.

Le disque fait foi, pas l'index de la recherche : après « Retirer les titres
hors bacs », l'index n'a plus les titres de l'auto-DJ, et un fichier d'un format
qu'il ne prend pas reste sur le disque.

Rien n'est effacé : un titre retiré part dans la corbeille de la banque, comme
un son retiré d'un bac. Beets suit le disque à son tour suivant
(deploy/scripts/beets-import-loop.sh) : un titre retiré sort de sa
bibliothèque, un titre déplacé y revient sous un nouvel identifiant.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from mutagen import File as MutagenFile

import agenda_api
import inbox_api

# One page of the list, at most.
PAGE_MAX = 200
# What one removal or move may spend, under the 30 s nginx waits for an answer.
TIME_BUDGET = 20.0
# The sounds a pre-listen serves, and their type: AUDIO_SUFFIXES, in
# engine/radiotomate/services/media_bank.py. Nothing else is served.
AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".mp2": "audio/mpeg",
    ".wav": "audio/wav",
    ".wave": "audio/wav",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".wma": "audio/x-ms-wma",
    ".webm": "audio/webm",
}
# Titles removed or moved by one request, at most.
MAX_NAMES = 500
# What one search may spend reading tags it has not read yet. Past it, the
# answer says it is partial, and a thread reads the rest of the folder.
SEARCH_BUDGET = 2.5
TAGS_KEPT = 100_000

# One change at a time: two requests never take the same name in the trash.
_LOCK = threading.Lock()
# path -> (size, mtime_ns, artist, title, duration): a file is read once, until it changes.
_TAGS: dict[str, tuple[int, int, str, str, float | None]] = {}
_TAGS_LOCK = threading.Lock()
_WARMING: set[str] = set()


@dataclass(frozen=True)
class Entry:
    """A file of a collection: its path below the folder, as the list names it."""

    name: str
    path: Path
    size: int
    mtime_ns: int


def fold(text: str) -> str:
    """« Été » and « ete » are the same word to a search."""
    plain = unicodedata.normalize("NFD", text)
    return "".join(char for char in plain if not unicodedata.combining(char)).casefold()


def folder_of(media: Path, destination: str) -> Path | None:
    """The folder of rotation or of a collection. None for a name the bank does not have."""
    known = inbox_api.destinations(media)
    if destination not in known:
        return None
    return media / known[destination][1]


def destination_row(media: Path, destination: str) -> dict:
    """What inbox.json says of this destination: its name, its group, its folder."""
    for row in inbox_api.destination_list(media):
        if row["id"] == destination:
            return row
    # Gone between two readings of the disk: its folder name is all that is left.
    return {"id": destination, "label": inbox_api.humanize(destination), "group": "archives", "folder": ""}


def _inside(folder: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def scan(folder: Path) -> list[Entry]:
    """Every file below the folder, hidden ones aside, as Beets walks it.

    A link that leads out of the folder is not one of its files, as for a bac
    (media_bank.iter_bank_audio): its target is neither read nor touched.
    """
    entries: list[Entry] = []
    if not folder.is_dir():
        return entries
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            path = Path(dirpath) / name
            try:
                info = path.stat()
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            # os.walk does not follow a linked folder: only the file can be a link.
            if path.is_symlink() and not _inside(folder, path):
                continue
            entries.append(Entry(path.relative_to(folder).as_posix(), path, info.st_size, info.st_mtime_ns))
    return entries


def read_tags(path: Path) -> tuple[str, str, float | None]:
    """Artist, title and length as mutagen reads them. The title falls back on the file's name.

    No ffprobe here, unlike the index: a list never waits on a file that is not audio.
    """
    title = path.stem.replace("_", " ").strip()
    artist = ""
    duration: float | None = None
    try:
        meta = MutagenFile(path)
    except Exception:
        meta = None
    if meta is None:
        return artist, title, duration
    length = getattr(getattr(meta, "info", None), "length", None)
    if length:
        duration = round(float(length), 3)
    tags = getattr(meta, "tags", None) or {}

    def first(*keys: str) -> str:
        for key in keys:
            value = tags.get(key) if hasattr(tags, "get") else None
            if value:
                item = value[0] if isinstance(value, list) else value
                return str(item).strip()
        return ""

    artist = first("artist", "ARTIST", "TPE1", "©ART")
    return artist, first("title", "TITLE", "TIT2", "©nam") or title, duration


def _cached(entry: Entry) -> tuple[str, str, float | None] | None:
    with _TAGS_LOCK:
        known = _TAGS.get(str(entry.path))
    if known is None or known[:2] != (entry.size, entry.mtime_ns):
        return None
    return known[2], known[3], known[4]


def tags_of(entry: Entry) -> tuple[str, str, float | None]:
    known = _cached(entry)
    if known is not None:
        return known
    tags = read_tags(entry.path)
    with _TAGS_LOCK:
        if len(_TAGS) >= TAGS_KEPT:
            _TAGS.clear()
        _TAGS[str(entry.path)] = (entry.size, entry.mtime_ns, *tags)
    return tags


def _warm(folder: Path) -> None:
    """Read, in the background, the tags a search did not have the time to read."""
    key = str(folder)
    with _TAGS_LOCK:
        if key in _WARMING:
            return
        _WARMING.add(key)

    def run() -> None:
        try:
            for entry in scan(folder):
                tags_of(entry)
        finally:
            with _TAGS_LOCK:
                _WARMING.discard(key)

    threading.Thread(target=run, name="tags", daemon=True).start()


def _search(entries: list[Entry], words: list[str]) -> tuple[list[Entry], bool]:
    """The files whose name, artist or title hold every word. True when tags are still unread."""
    deadline = time.monotonic() + SEARCH_BUDGET
    kept: list[Entry] = []
    partial = False
    for entry in entries:
        text = fold(entry.name)
        if all(word in text for word in words):
            kept.append(entry)
            continue
        tags = _cached(entry)
        if tags is None:
            if time.monotonic() >= deadline:
                partial = True
                continue
            tags = tags_of(entry)
        text = f"{text} {fold(tags[0])} {fold(tags[1])}"
        if all(word in text for word in words):
            kept.append(entry)
    return kept, partial


def _row(entry: Entry) -> dict:
    artist, title, duration = tags_of(entry)
    return {
        "name": entry.name,
        "title": title,
        "artist": artist,
        "duration": duration,
        "bytes": entry.size,
        "modified": datetime.fromtimestamp(entry.mtime_ns / 1e9, timezone.utc).isoformat(timespec="seconds"),
    }


def list_files(
    media: Path,
    destination: str,
    *,
    query: str = "",
    offset: int = 0,
    limit: int = 100,
    sort: str = "name",
) -> tuple[int, dict]:
    """One page of what rotation or a collection holds, by name or newest first."""
    folder = folder_of(media, destination)
    if folder is None:
        return 404, {"error": "Collection introuvable."}
    entries = scan(folder)
    total = len(entries)
    weight = sum(entry.size for entry in entries)
    words = fold(query).split()
    partial = False
    if words:
        entries, partial = _search(entries, words)
        if partial:
            _warm(folder)
    if sort == "recent":
        entries.sort(key=lambda entry: (-entry.mtime_ns, entry.name))
    else:
        entries.sort(key=lambda entry: (fold(entry.name), entry.name))
    offset = max(0, offset)
    limit = max(1, min(limit, PAGE_MAX))
    return 200, {
        "destination": destination_row(media, destination),
        "files": [_row(entry) for entry in entries[offset : offset + limit]],
        "total": total,
        "matched": len(entries),
        "bytes": weight,
        "partial": partial,
    }


def summary(media: Path) -> dict:
    """Rotation and every collection, each with what it holds."""
    rows = []
    for row in inbox_api.destination_list(media):
        folder = folder_of(media, row["id"])
        entries = scan(folder) if folder is not None else []
        rows.append({**row, "count": len(entries), "bytes": sum(entry.size for entry in entries)})
    return {"destinations": rows}


def _file_in(folder: Path, name: object) -> Path | None:
    """The file a list named, or None: a name that leaves the folder, a hidden
    file, a file gone, or a link that leads out of the folder."""
    text = name if isinstance(name, str) else ""
    if not text or "\x00" in text or text.startswith("/"):
        return None
    parts = PurePosixPath(text).parts
    if not parts or any(part in {".", ".."} or part.startswith(".") for part in parts):
        return None
    path = folder.joinpath(*parts)
    try:
        path.parent.resolve().relative_to(folder.resolve())
        if not path.is_file():
            return None
    except (OSError, ValueError):
        return None
    return path if _inside(folder, path) else None


def audio_file(media: Path, destination: str, name: str) -> tuple[Path, str] | None:
    """A sound to pre-listen, and the audio type it is served as.

    Only a sound: anything else a collection holds, such as a page or a script
    dropped through the station folder, would run as the console, on its origin.
    """
    folder = folder_of(media, destination)
    path = _file_in(folder, name) if folder is not None else None
    kind = AUDIO_TYPES.get(path.suffix.lower()) if path is not None else None
    if path is None or kind is None:
        return None
    return path.resolve(), kind


def _names(raw: object) -> tuple[list[str] | None, str]:
    if not isinstance(raw, list) or not raw or not all(isinstance(name, str) for name in raw):
        return None, "Aucun titre choisi."
    if len(raw) > MAX_NAMES:
        return None, f"Trop de titres à la fois : {MAX_NAMES} au plus."
    return list(dict.fromkeys(raw)), ""


def _fit(name: str, limit: int = 240) -> str:
    """The name, shortened from the end of its stem to fit the file system."""
    if len(name.encode("utf-8", "surrogateescape")) <= limit:
        return name
    stem, suffix = os.path.splitext(name)
    room = limit - len(suffix.encode("utf-8", "surrogateescape"))
    short = stem.encode("utf-8", "surrogateescape")[: max(room, 1)].decode("utf-8", "ignore")
    return (short or "son") + suffix


def _quiet_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _copy_in(source: Path, target: Path) -> str | None:
    """Copy a file to another disk, never over one, and never half.

    The copy is written under a hidden name, which Beets and the list skip,
    and only takes its own name once whole.
    """
    try:
        size = source.lstat().st_size
    except OSError:
        return "fichier introuvable"
    free = inbox_api.disk_free(target.parent)
    if free is not None and size > free:
        return "pas assez de place sur le disque"
    partial = target.with_name(_fit(f".{target.name}.partial"))
    _quiet_unlink(partial)
    try:
        shutil.copy2(source, partial, follow_symlinks=False)
    except OSError as exc:
        _quiet_unlink(partial)
        return "pas assez de place sur le disque" if exc.errno == errno.ENOSPC else "copie impossible"
    try:
        os.link(partial, target, follow_symlinks=False)
    except FileExistsError:
        _quiet_unlink(partial)
        return "déjà là"
    except (OSError, NotImplementedError):
        # A file system without hard links: a rename, once sure the name is free.
        try:
            if os.path.lexists(target):
                _quiet_unlink(partial)
                return "déjà là"
            os.rename(partial, target)
        except OSError:
            _quiet_unlink(partial)
            return "copie impossible"
        return None
    _quiet_unlink(partial)
    return None


def _move(source: Path, target: Path) -> str | None:
    """Move a file without ever replacing one. Returns why it could not."""
    try:
        # A hard link fails on a name already taken, where rename would replace
        # it. A link inside the folder moves as a link: its target stays put.
        os.link(source, target, follow_symlinks=False)
    except FileExistsError:
        return "déjà là"
    except (OSError, NotImplementedError) as exc:
        if getattr(exc, "errno", None) == errno.ENAMETOOLONG:
            return "nom trop long"
        # Another disk, or a file system without hard links: a copy, then.
        reason = _copy_in(source, target)
        if reason:
            return reason
    try:
        os.unlink(source)
    except OSError:
        # Two copies of one title are worse than none moved: the copy goes.
        try:
            os.unlink(target)
        except OSError:
            pass
        return "déplacement impossible"
    return None


def _trash_name(path: Path, index: int, limit: int = 240) -> str:
    """The name of a file in the trash: its own, then « (2) », « (3) »…, the stem
    shortened before the counter, so that a long name still finds a free one."""
    tail = path.suffix if index == 1 else f" ({index}){path.suffix}"
    room = max(limit - len(tail.encode("utf-8", "surrogateescape")), 1)
    stem = path.stem.encode("utf-8", "surrogateescape")[:room].decode("utf-8", "ignore")
    return (stem or "son") + tail


def _to_trash(path: Path, trash: Path) -> str | None:
    """Move a file to the trash, under a name nothing there has."""
    for index in range(1, 10_000):
        reason = _move(path, trash / _trash_name(path, index))
        if reason != "déjà là":
            return reason
    return "corbeille pleine de ce nom"


def _each(
    wanted: list[str], act
) -> tuple[list[str], list[dict], list[str]]:
    """Act on each name until the time is up: done, failed, and left to send again.

    nginx waits 30 s for an answer. A copy to another disk can take longer, so
    the request stops at TIME_BUDGET, after its first title, and says what is left.
    """
    deadline = time.monotonic() + TIME_BUDGET
    done: list[str] = []
    failed: list[dict] = []
    for index, name in enumerate(wanted):
        if index and time.monotonic() > deadline:
            return done, failed, wanted[index:]
        try:
            reason = act(name)
        except OSError:
            reason = "déplacement impossible"
        if reason:
            failed.append({"name": name, "reason": reason})
        else:
            done.append(name)
    return done, failed, []


def remove_files(media: Path, destination: str, names: object) -> tuple[int, dict]:
    """Send titles to the bank's trash. Beets drops them at its next round."""
    folder = folder_of(media, destination)
    if folder is None:
        return 404, {"error": "Collection introuvable."}
    wanted, problem = _names(names)
    if wanted is None:
        return 400, {"error": problem}
    trash = media / agenda_api.TRASH_TOP

    def act(name: str) -> str | None:
        path = _file_in(folder, name)
        return "fichier introuvable" if path is None else _to_trash(path, trash)

    with _LOCK:
        try:
            trash.mkdir(parents=True, exist_ok=True)
        except OSError:
            return 500, {"error": "La corbeille de la banque ne s'ouvre pas : rien n'a été retiré."}
        removed, failed, left = _each(wanted, act)
    return 200, {"removed": removed, "failed": failed, "left": left}


def move_files(media: Path, destination: str, target: str, names: object) -> tuple[int, dict]:
    """Move titles to rotation or to another collection. A name already there is never replaced."""
    source = folder_of(media, destination)
    aim = folder_of(media, target)
    if source is None or aim is None:
        return 404, {"error": "Collection introuvable."}
    if destination == target:
        return 400, {"error": "Ces titres y sont déjà."}
    wanted, problem = _names(names)
    if wanted is None:
        return 400, {"error": problem}
    label = destination_row(media, target)["label"]

    def act(name: str) -> str | None:
        path = _file_in(source, name)
        if path is None:
            return "fichier introuvable"
        landed = aim / path.name
        reason = _move(path, landed)
        if reason == "déjà là":
            return f"déjà dans {label}"
        if not reason:
            inbox_api.give_like_folder(landed)
        return reason

    with _LOCK:
        try:
            aim.mkdir(parents=True, exist_ok=True)
        except OSError:
            return 500, {"error": f"Le dossier de {label} ne s'ouvre pas : rien n'a été déplacé."}
        moved, failed, left = _each(wanted, act)
    return 200, {"moved": moved, "failed": failed, "left": left}


# What a collection's folder keeps of itself, or what the Finder leaves there:
# deleting the collection deletes them. Any other hidden file goes to the trash.
JUNK = {inbox_api.LABEL_FILE, ".DS_Store", ".localized"}


def _junk(name: str) -> bool:
    return name in JUNK or name.startswith("._")


def _hidden(root: Path, path: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def _clear(root: Path, trash: Path) -> int | None:
    """Empty a folder that holds no title, then remove it.

    Nothing is erased: a hidden file that is not junk, such as a sound in a
    hidden folder, goes to the trash. None, and the folder stays, when a visible
    file is there, or when something cannot be moved.
    """
    if not root.exists():
        return 0
    if root.is_symlink() or not root.is_dir():
        return None
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        folder = Path(dirpath)
        for name in [*filenames, *(name for name in dirnames if (folder / name).is_symlink())]:
            if not _hidden(root, folder / name):
                return None
    trashed = 0
    try:
        for dirpath, dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
            folder = Path(dirpath)
            links = [name for name in dirnames if (folder / name).is_symlink()]
            for name in [*filenames, *links]:
                path = folder / name
                if _junk(name) and not path.is_symlink():
                    path.unlink()
                    continue
                if _to_trash(path, trash):
                    return None
                trashed += 1
            folder.rmdir()
    except OSError:
        return None
    return trashed


def delete_collection(media: Path, name: str) -> tuple[int, dict]:
    """Remove an empty collection: its folder and its inbox. A title never goes with it."""
    name = str(name or "")
    if name == inbox_api.ROTATION:
        return 400, {"error": "La Rotation ne se supprime pas."}
    # Never the other way round: neither lock is taken while holding the other.
    with inbox_api._LOCK, _LOCK:
        if name not in inbox_api.archive_names(media):
            return 404, {"error": "Collection introuvable."}
        bank = media / inbox_api.ARCHIVES / name
        inbox = media / inbox_api.INBOX_ARCHIVES / name
        if bank.is_symlink() or os.path.ismount(bank):
            return 409, {"error": "Ce dossier est un lien ou un disque monté : il se retire sur la machine, pas ici."}
        left = len(scan(bank))
        if left:
            files = "1 fichier" if left == 1 else f"{left} fichiers"
            return 409, {"error": f"La collection contient encore {files} : retire ou déplace d'abord ses titres."}
        waiting = len(scan(inbox))
        if waiting:
            files = "1 envoi attend" if waiting == 1 else f"{waiting} envois attendent"
            return 409, {"error": f"{files} encore dans le dépôt de la collection : réessaie une fois rangé."}
        trash = media / agenda_api.TRASH_TOP
        try:
            trash.mkdir(parents=True, exist_ok=True)
        except OSError:
            return 500, {"error": "La corbeille de la banque ne s'ouvre pas : rien n'a été supprimé."}
        trashed = 0
        for root in (inbox, bank):
            moved = _clear(root, trash)
            if moved is None:
                return 409, {
                    "error": "Un fichier, un lien ou un dossier verrouillé reste dans la collection : "
                    "elle n'a pas été supprimée. Regarde son dossier sur la machine."
                }
            trashed += moved
    return 200, {"deleted": name, "trashed": trashed}
