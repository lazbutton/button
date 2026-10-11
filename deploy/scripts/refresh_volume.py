#!/usr/bin/env python3
"""Vue Finder de la médiathèque.

Les dossiers numérotés restent le stockage du moteur. Ce script reconstruit
des liens : Rotation, Banques, Habillage, Émissions, Bacs. Un fichier déposé
dans un lien arrive dans le dossier réel et y reste.

Idempotent. Stdlib seule, pour tourner dans la boucle Beets et dans le partage.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HABILLAGE = (
    ("jingles", "Jingles"),
    ("ids", "Idents"),
    ("pubs", "Pubs"),
    ("beds", "Beds"),
    ("stings", "Stings"),
    ("sfx", "Effets"),
)
VOLUME_DIRS = ("Banques", "Habillage", "Émissions")


def share_name(raw: str) -> str:
    """Nom du volume SMB : lettres, chiffres, point, tiret, souligné."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (raw or "").strip()).strip(".-")
    return (cleaned[:32] or "BUTTON")


def humanize(name: str) -> str:
    short = re.fullmatch(r"([a-z]{1,4})-?(\d+)", name)
    if short:
        return f"{short.group(1).upper()} {short.group(2)}"
    text = re.sub(r"[-_]+", " ", name).strip()
    return (text[:1].upper() + text[1:]) if text else name


def _label(folder: Path, slug: str) -> str:
    try:
        data = json.loads((folder / ".banque.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    label = " ".join(str(data.get("nom") or "").split()) if isinstance(data, dict) else ""
    return label or humanize(slug)


def _safe_entry(label: str, slug: str) -> str:
    text = label.replace("/", "-").replace("\\", "-").replace(":", " - ")
    text = " ".join(text.split()).strip(" .")
    if text in {"", ".", ".."}:
        text = slug
    return text[:80]


def _unique(label: str, slug: str, used: set[str]) -> str:
    base = _safe_entry(label, slug)
    if base not in used:
        used.add(base)
        return base
    alt = _safe_entry(f"{base} ({slug})", slug)
    if alt not in used:
        used.add(alt)
        return alt
    n = 2
    while f"{base} ({n})" in used:
        n += 1
    name = f"{base} ({n})"
    used.add(name)
    return name


def _banks(media: Path) -> list[tuple[str, Path]]:
    root = media / "20-archives"
    if not root.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    used: set[str] = set()
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or path.is_symlink():
            continue
        if not path.name or path.name.startswith((".", "_")) or path.name == "rotation":
            continue
        found.append((_unique(_label(path, path.name), path.name, used), path))
    return found


def _emissions(media: Path) -> list[tuple[str, Path]]:
    root = media / "40-emissions"
    if not root.is_dir():
        return []
    found: list[tuple[str, Path]] = []
    used: set[str] = set()
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or path.is_symlink():
            continue
        if not path.name or path.name.startswith((".", "_")):
            continue
        found.append((_unique(path.name, path.name, used), path))
    return found


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _link(link: Path, target: Path) -> None:
    """Pose un lien relatif. Ne remplace pas un vrai dossier."""
    rel = os.path.relpath(target, link.parent)
    if link.is_symlink():
        if os.readlink(link) == rel:
            return
        link.unlink()
    elif link.exists():
        return
    link.symlink_to(rel)


def _drop_stale(directory: Path, keep: set[str]) -> None:
    if not directory.is_dir():
        return
    for child in directory.iterdir():
        if child.is_symlink() and child.name not in keep:
            child.unlink()


def refresh(media: Path, volume: Path | None = None) -> Path:
    media = media.resolve()
    volume = volume or (media / ".volume")
    _ensure_dir(volume)
    for name in VOLUME_DIRS:
        _ensure_dir(volume / name)

    rotation = media / "10-rotation"
    _ensure_dir(rotation)
    _link(volume / "Rotation", rotation)

    carts = media / "Carts"
    _ensure_dir(carts)
    _link(volume / "Bacs", carts)

    banks = _banks(media)
    for name, target in banks:
        _link(volume / "Banques" / name, target)
    _drop_stale(volume / "Banques", {name for name, _target in banks})

    habillage: list[tuple[str, Path]] = []
    for slug, title in HABILLAGE:
        target = media / "30-habillage" / slug
        _ensure_dir(target)
        habillage.append((title, target))
        _link(volume / "Habillage" / title, target)
    _drop_stale(volume / "Habillage", {title for title, _target in habillage})

    emissions = _emissions(media)
    for name, target in emissions:
        _link(volume / "Émissions" / name, target)
    _drop_stale(volume / "Émissions", {name for name, _target in emissions})
    return volume


def main(argv: list[str]) -> int:
    media = Path(argv[1] if len(argv) > 1 else os.environ.get("MEDIA_ROOT", "/media"))
    volume = Path(argv[2]) if len(argv) > 2 else None
    refresh(media, volume)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
