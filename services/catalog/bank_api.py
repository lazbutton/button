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


def file_path(media: Path, destination: str, name: str) -> Path | None:
    """A file to play, as the list shows it."""
    folder = folder_of(media, destination)
    path = _file_in(folder, name) if folder is not None else None
    return path.resolve() if path is not None else None


def _names(raw: object) -> tuple[list[str] | None, str]:
    if not isinstance(raw, list) or not raw or not all(isinstance(name, str) for name in raw):
        return None, "Aucun titre choisi."
    if len(raw) > MAX_NAMES:
        return None, f"Trop de titres à la fois : {MAX_NAMES} au plus."
    return list(dict.fromkeys(raw)), ""


def _move(source: Path, target: Path) -> str | None:
    """Move a file without ever replacing one. Returns why it could not."""
    try:
        # A hard link fails on a name already taken, where rename would replace
        # it. A link inside the folder moves as a link: its target stays put.
        os.link(source, target, follow_symlinks=False)
    except FileExistsError:
        return "déjà là"
    except (OSError, NotImplementedError):
        # Another disk, or a file system without hard links: a copy, then.
        if os.path.lexists(target):
            return "déjà là"
        return inbox_api.move_in(source, target)
    try:
        os.unlink(source)
    except OSError:
        os.unlink(target)
        return "déplacement impossible"
    return None


def _to_trash(path: Path, trash: Path) -> str | None:
    index = 1
    while True:
        name = path.name if index == 1 else f"{path.stem} ({index}){path.suffix}"
        reason = _move(path, trash / name)
        if reason != "déjà là":
            return reason
        index += 1


def remove_files(media: Path, destination: str, names: object) -> tuple[int, dict]:
    """Send titles to the bank's trash. Beets drops them at its next round."""
    folder = folder_of(media, destination)
    if folder is None:
        return 404, {"error": "Collection introuvable."}
    wanted, problem = _names(names)
    if wanted is None:
        return 400, {"error": problem}
    trash = media / agenda_api.TRASH_TOP
    removed: list[str] = []
    failed: list[dict] = []
    with _LOCK:
        try:
            trash.mkdir(parents=True, exist_ok=True)
        except OSError:
            return 500, {"error": "La corbeille de la banque ne s'ouvre pas : rien n'a été retiré."}
        for name in wanted:
            path = _file_in(folder, name)
            reason = "fichier introuvable" if path is None else _to_trash(path, trash)
            if reason:
                failed.append({"name": name, "reason": reason})
            else:
                removed.append(name)
    return 200, {"removed": removed, "failed": failed}


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
    moved: list[str] = []
    failed: list[dict] = []
    with _LOCK:
        try:
            aim.mkdir(parents=True, exist_ok=True)
        except OSError:
            return 500, {"error": f"Le dossier de {label} ne s'ouvre pas : rien n'a été déplacé."}
        for name in wanted:
            path = _file_in(source, name)
            if path is None:
                failed.append({"name": name, "reason": "fichier introuvable"})
                continue
            landed = aim / path.name
            reason = _move(path, landed)
            if reason == "déjà là":
                reason = f"déjà dans {label}"
            if reason:
                failed.append({"name": name, "reason": reason})
                continue
            inbox_api.give_like_folder(landed)
            moved.append(name)
    return 200, {"moved": moved, "failed": failed}
