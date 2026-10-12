"""Agenda deposits: a guest drops a set through a private link.

The engine owns the guests and their dates; the catalog owns the files. The
tus hooks ask the engine (internal routes, X-Auth-Token) whether a deposit is
allowed, place the finished file in the broadcast's folder of 40-emissions,
then declare it. The guest's token only travels as a request header.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import inbox_api

TOKEN_HEADER = "X-Invite-Token"
EMISSIONS_TOP = "40-emissions"
TRASH_TOP = "90-trash"
PLAYOUT_YAML = Path(os.environ.get("RT_PLAYOUT_YAML", "/config/radiotomate.yaml"))

Engine = Callable[[str, dict], "dict | None"]


def hook_event(payload: dict, headers) -> tuple[str, dict]:
    """tusd v2 posts ``{"Type", "Event": {"Upload", "HTTPRequest"}}``.

    tusd v1 posted the event itself, its name in a ``Hook-Name`` header.
    """
    if isinstance(payload.get("Event"), dict):
        return str(payload.get("Type") or ""), payload["Event"]
    return str(headers.get("Hook-Name") or ""), payload


def header_of(event: dict, name: str) -> str:
    header = (event.get("HTTPRequest") or {}).get("Header") or {}
    raw = None
    for key, value in header.items():
        if str(key).lower() == name.lower():
            raw = value
            break
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return str(raw or "").strip()


def invite_token(event: dict) -> str:
    return header_of(event, TOKEN_HEADER)


def _upload(event: dict) -> tuple[dict, dict]:
    upload = event.get("Upload") if isinstance(event.get("Upload"), dict) else {}
    meta = upload.get("MetaData") if isinstance(upload.get("MetaData"), dict) else {}
    return upload, meta


def playout_token() -> str:
    env = os.environ.get("RT_PLAYOUT_TOKEN", "").strip()
    if env:
        return env
    if not PLAYOUT_YAML.exists():
        return ""
    in_block = False
    for raw in PLAYOUT_YAML.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0]
        stripped = line.strip()
        if stripped.startswith("playout_process_config"):
            in_block = True
            continue
        if in_block:
            if stripped and not line[:1].isspace() and stripped.endswith(":"):
                in_block = False
                continue
            if stripped.startswith("token:"):
                return stripped.split(":", 1)[1].strip().strip("\"'")
    return ""


def engine_call(base_url: str, token: str) -> Engine:
    """POST JSON to the engine's internal routes. None when unreachable."""

    def call(path: str, body: dict) -> dict | None:
        if not base_url or not token:
            return None
        request = urllib.request.Request(
            f"{base_url}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-Auth-Token": token},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode() or "{}")
            except (OSError, ValueError):
                payload = {}
            payload.setdefault("error", f"HTTP {exc.code}")
            payload["ok"] = False
            return payload
        except (OSError, ValueError):
            return None

    return call


def pre_create(event: dict, token: str, media: Path, engine: Engine) -> dict:
    """Accept or refuse a guest's upload; remember where it will go."""
    upload, meta = _upload(event)
    name = inbox_api.safe_name(str(meta.get("filename") or ""))
    if not name:
        return inbox_api.reject_body("nom refusé")
    answer = engine(
        "/internal/agenda/deposit-check.json",
        {
            "token": token,
            "diffusion_id": meta.get("diffusion"),
            "filename": name,
            "size": upload.get("Size"),
        },
    )
    if answer is None:
        return inbox_api.reject_body("dépôt indisponible, réessaie dans quelques minutes")
    if not answer.get("ok"):
        return inbox_api.reject_body(str(answer.get("reason") or "dépôt refusé"))
    size = upload.get("Size")
    try:
        nbytes = int(size) if size is not None else 0
    except (TypeError, ValueError):
        nbytes = 0
    if nbytes and inbox_api.used_bytes(media) + nbytes > inbox_api.quota_limit():
        return inbox_api.reject_body("quota dépassé")
    changed = {
        **{str(key): str(value) for key, value in meta.items()},
        "agenda_folder": str(answer.get("folder") or ""),
        "agenda_filename": str(answer.get("filename") or name),
    }
    return {"ChangeFileInfo": {"MetaData": changed}}


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def finish(event: dict, token: str, media: Path, tusd_dir: Path, engine: Engine) -> dict:
    """Move the finished file into its folder and declare it to the engine."""
    upload, meta = _upload(event)
    folder = str(meta.get("agenda_folder") or "").strip().strip("/")
    filename = inbox_api.safe_name(str(meta.get("agenda_filename") or ""))
    if not folder.startswith(EMISSIONS_TOP + "/") or ".." in Path(folder).parts:
        return {"error": "dossier refusé"}
    if not filename:
        return {"error": "nom refusé"}
    storage_info = upload.get("Storage") if isinstance(upload.get("Storage"), dict) else {}
    storage_raw = str(storage_info.get("Path") or "")
    storage = Path(storage_raw) if storage_raw else tusd_dir / str(upload.get("ID") or "")
    if not _inside(tusd_dir, storage) or not storage.is_file():
        return {"error": "fichier introuvable"}
    target_dir = media / folder
    if not _inside(media, target_dir):
        return {"error": "dossier refusé"}
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _unique(target_dir / filename)
    shutil.move(str(storage), str(target))
    info = Path(str(storage) + ".info")
    if info.is_file():
        info.unlink()
    rel = target.relative_to(media).as_posix()
    answer = engine(
        "/internal/agenda/files.json",
        {
            "token": token,
            "diffusion_id": meta.get("diffusion"),
            "path": rel,
            "original_name": inbox_api.safe_name(str(meta.get("filename") or "")),
        },
    )
    if answer is not None and answer.get("ok"):
        return {"ok": True, "path": rel}
    trash = media / TRASH_TOP
    trash.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(_unique(trash / target.name)))
    reason = "moteur injoignable" if answer is None else str(answer.get("error") or "refusé")
    return {"error": reason}
