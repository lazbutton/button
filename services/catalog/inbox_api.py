"""File d'attente, rejets, quota et banques du dépôt navigateur.

tusd appelle le hook. Les fichiers acceptés vont dans 00-inbox.
La promotion et l'indexation restent au dropbox et à Beets.

Une banque d'archives est un dossier de 20-archives : il est découvert
tout seul, et son nom affiché peut venir de son fichier .banque.json.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

ACCEPTED = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aif", ".aiff"}
ROTATION = "rotation"
ARCHIVES = "20-archives"
INBOX_ARCHIVES = "00-inbox/archives"
LABEL_FILE = ".banque.json"
BANK_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")
DEFAULT_QUOTA = 100 * 1024 * 1024 * 1024
_LOCK = threading.Lock()


def quota_limit() -> int:
    raw = os.environ.get("INBOX_QUOTA_BYTES", "").strip()
    if not raw:
        return DEFAULT_QUOTA
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_QUOTA
    return value if value > 0 else DEFAULT_QUOTA


def safe_name(raw: str) -> str:
    name = Path(raw or "").name.replace("\x00", "").strip()
    if not name or name in {".", ".."} or name.startswith("."):
        return ""
    if "/" in name or "\\" in name:
        return ""
    return name


def is_bank_folder(name: str) -> bool:
    if not name or name in {".", ".."} or name.startswith((".", "_")):
        return False
    return "/" not in name and "\\" not in name and "\x00" not in name


def archive_names(media: Path) -> list[str]:
    root = media / ARCHIVES
    if not root.is_dir():
        return []
    return sorted(
        path.name for path in root.iterdir() if path.is_dir() and is_bank_folder(path.name) and path.name != ROTATION
    )


def destinations(media: Path) -> dict[str, tuple[str, str]]:
    """Rotation, then one destination per folder of 20-archives: (inbox, bank)."""
    found = {ROTATION: ("00-inbox/rotation", "10-rotation")}
    for name in archive_names(media):
        found[name] = (f"{INBOX_ARCHIVES}/{name}", f"{ARCHIVES}/{name}")
    return found


def humanize(name: str) -> str:
    """ntf1 -> NTF 1, jazz-live -> Jazz live."""
    short = re.fullmatch(r"([a-z]{1,4})-?(\d+)", name)
    if short:
        return f"{short.group(1).upper()} {short.group(2)}"
    text = re.sub(r"[-_]+", " ", name).strip()
    return text[:1].upper() + text[1:]


def bank_label(media: Path, name: str) -> str:
    if name == ROTATION:
        return "Rotation"
    try:
        data = json.loads((media / ARCHIVES / name / LABEL_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    label = " ".join(str(data.get("nom") or "").split()) if isinstance(data, dict) else ""
    return label or humanize(name)


def destination_list(media: Path) -> list[dict]:
    rows = [{"id": ROTATION, "label": "Rotation", "group": "rotation", "folder": "10-rotation"}]
    archives = [
        {"id": name, "label": bank_label(media, name), "group": "archives", "folder": f"{ARCHIVES}/{name}"}
        for name in archive_names(media)
    ]
    archives.sort(key=lambda row: row["label"].casefold())
    return rows + archives


def create_bank(media: Path, label: str, folder: str) -> tuple[int, dict]:
    """A new archive bank: its folder in 20-archives, its inbox, its name."""
    label = " ".join(str(label or "").split())
    folder = str(folder or "").strip()
    if not label:
        return 400, {"error": "Donne un nom à la banque."}
    if len(label) > 60:
        return 400, {"error": "Nom trop long : 60 caractères au plus."}
    if not BANK_SLUG.fullmatch(folder):
        return 400, {"error": "Dossier : minuscules, chiffres et tirets, 40 caractères au plus."}
    if folder == ROTATION or label.casefold() == "rotation":
        return 409, {"error": "« rotation » est réservé à la musique de l'auto-DJ."}
    with _LOCK:
        existing = archive_names(media)
        if any(name.casefold() == folder for name in existing):
            return 409, {"error": f"Le dossier {ARCHIVES}/{folder} existe déjà."}
        if any(bank_label(media, name).casefold() == label.casefold() for name in existing):
            return 409, {"error": "Une banque porte déjà ce nom."}
        bank = media / ARCHIVES / folder
        try:
            bank.mkdir(parents=True)
        except FileExistsError:
            return 409, {"error": f"Le dossier {ARCHIVES}/{folder} existe déjà."}
        (media / INBOX_ARCHIVES / folder).mkdir(parents=True, exist_ok=True)
        (bank / LABEL_FILE).write_text(json.dumps({"nom": label}, ensure_ascii=False), encoding="utf-8")
    return 201, {"destination": {"id": folder, "label": label, "group": "archives", "folder": f"{ARCHIVES}/{folder}"}}


def judge_upload(
    name: str,
    destination: str,
    size: int | None,
    *,
    used: int,
    limit: int,
    in_inbox: bool,
    in_bank: bool,
    known: bool = True,
) -> str | None:
    if not known:
        return "destination inconnue"
    if not name:
        return "nom refusé"
    if Path(name).suffix.lower() not in ACCEPTED:
        return "format inconnu"
    if size is not None and size <= 0:
        return "fichier vide"
    if in_inbox or in_bank:
        return "déjà dans la banque"
    if size is not None and used + size > limit:
        return "quota dépassé"
    return None


def _tree_bytes(root: Path) -> int:
    total = 0
    if not root.is_dir():
        return 0
    for path in root.rglob("*"):
        if path.is_file() and not path.name.startswith("."):
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def used_bytes(media: Path) -> int:
    return sum(
        _tree_bytes(media / folder)
        for folder in ("00-inbox", "10-rotation", "20-archives")
    )


def _rejets_path(media: Path) -> Path:
    return media / "00-inbox" / "_rejets.json"


def read_rejets(media: Path) -> list[dict]:
    path = _rejets_path(media)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def record_rejet(media: Path, name: str, destination: str, reason: str) -> None:
    row = {
        "name": name or "sans nom",
        "dest": destination,
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _LOCK:
        rows = [row, *read_rejets(media)]
        path = _rejets_path(media)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows[:40], ensure_ascii=False), encoding="utf-8")


def _file_row(path: Path, dest: str, reason: str | None) -> dict:
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {"name": path.name, "dest": dest, "bytes": size, "reason": reason}


def inbox_status(media: Path, tusd_dir: Path | None) -> dict:
    limit = quota_limit()
    used = used_bytes(media)
    queue: list[dict] = []
    sitting: list[dict] = []
    for key, (inbox_rel, bank_rel) in destinations(media).items():
        folder = media / inbox_rel
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file() or path.name.startswith(".") or path.name.startswith("_"):
                continue
            bank = media / bank_rel / path.name
            if Path(path.name).suffix.lower() not in ACCEPTED:
                sitting.append(_file_row(path, key, "format inconnu"))
            elif bank.is_file():
                sitting.append(_file_row(path, key, "déjà dans la banque"))
            else:
                queue.append(_file_row(path, key, None))
    progress = _progress(tusd_dir) if tusd_dir else []
    return {
        "destinations": destination_list(media),
        "quota": {"used": used, "limit": limit},
        "queue": queue[:200],
        "rejected": sitting[:200] + read_rejets(media),
        "progress": progress[:40],
    }


def _progress(tusd_dir: Path) -> list[dict]:
    if not tusd_dir.is_dir():
        return []
    rows = []
    for info in tusd_dir.glob("*.info"):
        try:
            data = json.loads(info.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        size = int(data.get("Size") or 0)
        offset = int(data.get("Offset") or 0)
        if size and offset >= size:
            continue
        meta = data.get("MetaData") if isinstance(data.get("MetaData"), dict) else {}
        rows.append(
            {
                "name": str(meta.get("filename") or info.stem),
                "dest": str(meta.get("destination") or ""),
                "bytes": size,
                "offset": offset,
            }
        )
    return rows


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def place_upload(media: Path, tusd_dir: Path, storage: Path, name: str, destination: str) -> str | None:
    """Move a finished tus file into the inbox. Returns a rejection reason."""
    if not _inside(tusd_dir, storage) or not storage.is_file():
        return "fichier introuvable"
    known = destinations(media)
    if destination not in known:
        return "destination inconnue"
    inbox_rel, bank_rel = known[destination]
    target = media / inbox_rel / name
    bank = media / bank_rel / name
    reason = judge_upload(
        name,
        destination,
        storage.stat().st_size,
        used=used_bytes(media),
        limit=quota_limit(),
        in_inbox=target.exists(),
        in_bank=bank.exists(),
    )
    if reason:
        return reason
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(storage), str(target))
    info = Path(str(storage) + ".info")
    if info.is_file():
        info.unlink()
    return None


def finish_upload(event: dict, media: Path, tusd_dir: Path) -> tuple[int, dict]:
    upload = event.get("Upload") if isinstance(event.get("Upload"), dict) else {}
    meta = upload.get("MetaData") if isinstance(upload.get("MetaData"), dict) else {}
    name = safe_name(str(meta.get("filename") or ""))
    destination = str(meta.get("destination") or "").strip()
    storage_raw = ""
    storage_info = upload.get("Storage")
    if isinstance(storage_info, dict):
        storage_raw = str(storage_info.get("Path") or "")
    storage = Path(storage_raw) if storage_raw else tusd_dir / str(upload.get("ID") or "")
    if destination not in destinations(media):
        record_rejet(media, name, destination, "destination inconnue")
        return 200, {"error": "destination inconnue"}
    reason = place_upload(media, tusd_dir, storage, name, destination)
    if not reason:
        return 200, {"ok": True}
    record_rejet(media, name, destination, reason)
    if reason != "fichier introuvable" and storage.is_file() and _inside(tusd_dir, storage):
        storage.unlink()
        info = Path(str(storage) + ".info")
        if info.is_file():
            info.unlink()
    return 200, {"error": reason}


def reject_body(reason: str) -> dict:
    return {
        "RejectUpload": True,
        "HTTPResponse": {
            "StatusCode": 400,
            "Body": reason,
            "Header": {"Content-Type": "text/plain; charset=utf-8"},
        },
    }


def hook_decision(event: dict, media: Path, tusd_dir: Path) -> tuple[int, dict]:
    upload = event.get("Upload") if isinstance(event.get("Upload"), dict) else {}
    meta = upload.get("MetaData") if isinstance(upload.get("MetaData"), dict) else {}
    name = safe_name(str(meta.get("filename") or ""))
    destination = str(meta.get("destination") or "").strip()
    size = upload.get("Size")
    try:
        nbytes = int(size) if size is not None else None
    except (TypeError, ValueError):
        nbytes = None
    inbox_rel, bank_rel = destinations(media).get(destination, ("", ""))
    in_inbox = bool(inbox_rel) and name and (media / inbox_rel / name).exists()
    in_bank = bool(bank_rel) and name and (media / bank_rel / name).exists()
    reason = judge_upload(
        name,
        destination,
        nbytes,
        used=used_bytes(media),
        limit=quota_limit(),
        in_inbox=bool(in_inbox),
        in_bank=bool(in_bank),
        known=bool(inbox_rel),
    )
    if reason:
        record_rejet(media, name, destination, reason)
        return 200, reject_body(reason)
    return 200, {}
