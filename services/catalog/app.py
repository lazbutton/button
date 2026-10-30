#!/usr/bin/env python3
"""Banque BUTTON : promotion inbox, index Meilisearch, HTTP search + Range."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

import agenda_api
import inbox_api
import volume_api
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from mutagen import File as MutagenFile
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", "/media")).resolve()
MEILI_URL = os.environ.get("MEILI_URL", "http://meilisearch:7700").rstrip("/")
MEILI_KEY = os.environ.get("MEILI_MASTER_KEY", "")
INDEX = os.environ.get("MEILI_INDEX", "button_media")
PORT = int(os.environ.get("CATALOG_PORT", "30127"))
AUTOMATE_URL = os.environ.get("AUTOMATE_URL", "").rstrip("/")
TUSD_DIR = Path(os.environ.get("TUSD_DIR", "/tusd"))
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".aiff", ".aif", ".webm"}
SKIP_TOP = {"00-inbox", "90-trash"}
CARTS_ONLY_FLAG = ".library-carts-only"
CART_PATHS_FILE = ".library-cart-paths"
EMISSION_SLOTS = ("entiere", "podcasts")

PROMOTE = (
    ("00-inbox/rotation", "10-rotation", "music"),
    ("00-inbox/habillage/jingles", "30-habillage/jingles", "file"),
    ("00-inbox/habillage/ids", "30-habillage/ids", "file"),
    ("00-inbox/habillage/pubs", "30-habillage/pubs", "file"),
    ("00-inbox/habillage/beds", "30-habillage/beds", "file"),
    ("00-inbox/habillage/stings", "30-habillage/stings", "file"),
    ("00-inbox/habillage/sfx", "30-habillage/sfx", "file"),
)

def promote_rules() -> list[tuple[str, str, str]]:
    """The fixed rules, then one per archive bank: a folder of 20-archives."""
    archives = [
        (inbox, bank, "music")
        for key, (inbox, bank) in inbox_api.destinations(MEDIA_ROOT).items()
        if key != inbox_api.ROTATION
    ]
    return [*PROMOTE, *archives]


KIND_FOLDERS = {
    "30-habillage/jingles": "jingle",
    "30-habillage/ids": "jingle",
    "30-habillage/stings": "jingle",
    "30-habillage/pubs": "pub",
    "30-habillage/beds": "son",
    "30-habillage/sfx": "son",
    "10-rotation": "son",
}


def rel_of(path: Path) -> str:
    return path.resolve().relative_to(MEDIA_ROOT).as_posix()


def carts_only() -> bool:
    return (MEDIA_ROOT / CARTS_ONLY_FLAG).is_file()


def kept_cart_paths() -> set[str]:
    path = MEDIA_ROOT / CART_PATHS_FILE
    if not path.is_file():
        return set()
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def in_library(rel: str) -> bool:
    """After a prune, the search only keeps files that are still in a bac."""
    if rel.split("/", 1)[0] in SKIP_TOP:
        return False
    if not carts_only():
        return True
    if rel.startswith("50-carts/"):
        return True
    return rel in kept_cart_paths()


def doc_id(rel: str) -> str:
    return hashlib.sha256(rel.encode()).hexdigest()[:20]


def is_audio(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXT and not path.name.startswith(".")


def wait_stable(path: Path, rounds: int = 8) -> bool:
    """SMB / Nextcloud can still be writing when inotify fires."""
    last = -1
    for _ in range(rounds):
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size == last and size > 0:
            return True
        last = size
        time.sleep(0.35)
    return path.exists()


def grouping_of(rel: str) -> str:
    parts = rel.split("/")
    if parts[:1] == ["10-rotation"]:
        return "rotation"
    if len(parts) >= 2 and parts[0] == "20-archives":
        return parts[1]
    if len(parts) >= 2 and parts[0] == "40-emissions":
        return parts[1]
    return ""


def kind_of(rel: str) -> str:
    for prefix, kind in KIND_FOLDERS.items():
        if rel == prefix or rel.startswith(prefix + "/"):
            return kind
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "40-emissions" and parts[2] == "podcasts":
        return "podcast"
    if len(parts) >= 3 and parts[0] == "40-emissions" and parts[2] == "entiere":
        return "emission"
    if rel.startswith("20-archives/") or rel.startswith("40-emissions/"):
        return "son"
    return "son"


def is_safe_show(name: str) -> bool:
    if not name or name in {".", ".."} or name.startswith("."):
        return False
    return "/" not in name and "\\" not in name and "\x00" not in name


def tags_of(path: Path) -> tuple[str, str, float]:
    title = path.stem.replace("_", " ").strip()
    artist = ""
    duration = 0.0
    try:
        meta = MutagenFile(path)
    except Exception:
        meta = None
    if meta is not None:
        info = getattr(meta, "info", None)
        if info is not None and getattr(info, "length", None):
            duration = float(info.length)
        tags = getattr(meta, "tags", None) or {}
        def first(*keys: str) -> str:
            for key in keys:
                val = tags.get(key) if hasattr(tags, "get") else None
                if val:
                    item = val[0] if isinstance(val, list) else val
                    return str(item).strip()
            return ""
        artist = first("artist", "ARTIST", "TPE1", "©ART")
        titled = first("title", "TITLE", "TIT2", "©nam")
        if titled:
            title = titled
    if duration <= 0:
        try:
            out = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "csv=p=0",
                    str(path),
                ],
                text=True,
                timeout=20,
            ).strip()
            duration = float(out or 0)
        except Exception:
            duration = 0.0
    return artist, title, duration


def document_for(path: Path) -> dict | None:
    if not is_audio(path):
        return None
    try:
        rel = rel_of(path)
    except ValueError:
        return None
    top = rel.split("/", 1)[0]
    if top in SKIP_TOP:
        return None
    artist, title, duration = tags_of(path)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {
        "id": doc_id(rel),
        "path": rel,
        "filename": path.name,
        "title": title,
        "artist": artist,
        "kind": kind_of(rel),
        "grouping": grouping_of(rel),
        "folder": str(Path(rel).parent.as_posix()),
        "top": top,
        "duration": round(duration, 3),
        "bytes": path.stat().st_size,
        "mime": mime,
    }


def meili(method: str, url: str, body: dict | list | None = None) -> dict | list | None:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {MEILI_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        err = exc.read().decode()
        raise RuntimeError(f"meili {method} {url} {exc.code} {err[:300]}") from exc


def ensure_index() -> None:
    for _ in range(60):
        try:
            meili("GET", f"{MEILI_URL}/health")
            break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("Meilisearch injoignable")
    try:
        meili("GET", f"{MEILI_URL}/indexes/{INDEX}")
    except RuntimeError:
        meili("POST", f"{MEILI_URL}/indexes", {"uid": INDEX, "primaryKey": "id"})
        time.sleep(0.4)
    meili(
        "PATCH",
        f"{MEILI_URL}/indexes/{INDEX}/settings",
        {
            "searchableAttributes": ["title", "artist", "filename", "path", "folder"],
            "filterableAttributes": ["kind", "grouping", "folder", "top"],
            "sortableAttributes": ["path", "title", "duration"],
        },
    )


def upsert(doc: dict) -> None:
    meili("POST", f"{MEILI_URL}/indexes/{INDEX}/documents", [doc])


def delete_id(item_id: str) -> None:
    try:
        meili("DELETE", f"{MEILI_URL}/indexes/{INDEX}/documents/{item_id}")
    except RuntimeError:
        pass


def promote_file(path: Path) -> Path | None:
    try:
        rel = rel_of(path)
    except ValueError:
        return None
    for src, dest, mode in promote_rules():
        prefix = src + "/"
        if rel == src or not rel.startswith(prefix):
            continue
        name = Path(rel[len(prefix) :]).name
        if not name:
            return None
        if mode == "music":
            artist, title, _ = tags_of(path)
            if not artist or not title:
                print(f"inbox sans tags, on laisse : {rel}", flush=True)
                return None
        target = MEDIA_ROOT / dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            stem, ext = target.stem, target.suffix
            n = 2
            while target.exists():
                target = target.with_name(f"{stem}-{n}{ext}")
                n += 1
        shutil.move(str(path), str(target))
        try:
            os.chmod(target, 0o664)
        except OSError:
            pass
        print(f"promu {rel} -> {rel_of(target)}", flush=True)
        return target
    parts = rel.split("/")
    if (
        len(parts) >= 5
        and parts[0] == "00-inbox"
        and parts[1] == "emissions"
        and parts[3] in EMISSION_SLOTS
        and is_safe_show(parts[2])
    ):
        name = parts[-1]
        if not name or name in {".", ".."}:
            return None
        dest = Path("40-emissions") / parts[2] / parts[3]
        target = MEDIA_ROOT / dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            stem, ext = target.stem, target.suffix
            n = 2
            while target.exists():
                target = target.with_name(f"{stem}-{n}{ext}")
                n += 1
        shutil.move(str(path), str(target))
        try:
            os.chmod(target, 0o664)
        except OSError:
            pass
        print(f"promu {rel} -> {rel_of(target)}", flush=True)
        return target
    return None


def index_path(path: Path) -> None:
    if not path.exists():
        try:
            delete_id(doc_id(rel_of(path)))
        except Exception:
            pass
        return
    if path.is_dir():
        return
    promoted = None
    try:
        rel = rel_of(path)
        if rel.startswith("00-inbox/"):
            if not wait_stable(path):
                return
            promoted = promote_file(path)
    except ValueError:
        return
    target = promoted or path
    if not target.exists() or not is_audio(target):
        return
    try:
        rel = rel_of(target)
        if rel.split("/", 1)[0] in SKIP_TOP or not in_library(rel):
            delete_id(doc_id(rel))
            return
    except ValueError:
        return
    doc = document_for(target)
    if doc:
        upsert(doc)
        print(f"indexé {doc['path']}", flush=True)


def full_scan() -> None:
    n = 0
    for path in MEDIA_ROOT.rglob("*"):
        if not is_audio(path):
            continue
        try:
            rel = rel_of(path)
        except ValueError:
            continue
        if rel.split("/", 1)[0] in SKIP_TOP:
            if rel.startswith("00-inbox/"):
                index_path(path)
            continue
        if not in_library(rel):
            continue
        doc = document_for(path)
        if doc:
            upsert(doc)
            n += 1
    print(f"scan {n} fichiers", flush=True)


def indexed_rels() -> set[str]:
    rels: set[str] = set()
    offset = 0
    while True:
        page = meili(
            "GET",
            f"{MEILI_URL}/indexes/{INDEX}/documents?limit=200&offset={offset}&fields=path",
        )
        if not isinstance(page, dict):
            return rels
        results = page.get("results") or []
        for doc in results:
            path = str(doc.get("path") or "")
            if path:
                rels.add(path)
        if len(results) < 200:
            return rels
        offset += 200


def audio_on_disk() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in MEDIA_ROOT.rglob("*"):
        if not is_audio(path):
            continue
        try:
            rel = rel_of(path)
        except ValueError:
            continue
        if rel.split("/", 1)[0] in SKIP_TOP or not in_library(rel):
            continue
        found[rel] = path
    return found


def sync_library() -> None:
    """Index files the watcher missed, and drop entries whose file is gone.

    Copying a bac into the volume often overflows inotify, so the startup
    scan is the only pass those files would ever get.
    """
    on_disk = audio_on_disk()
    known = indexed_rels()
    added = 0
    for rel, path in on_disk.items():
        if rel in known:
            continue
        index_path(path)
        added += 1
    removed = 0
    for rel in known - set(on_disk):
        delete_id(doc_id(rel))
        removed += 1
    if added or removed:
        print(f"bibliothèque +{added} −{removed}", flush=True)


def library_loop() -> None:
    while True:
        time.sleep(20)
        try:
            sync_library()
        except Exception as exc:
            print(f"sync bibliothèque: {exc}", flush=True)


class Handler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.is_directory:
            return
        src = Path(event.src_path)
        if event.event_type in {"deleted", "moved"}:
            try:
                delete_id(doc_id(rel_of(src)))
            except Exception:
                pass
        dest = Path(getattr(event, "dest_path", event.src_path))
        time.sleep(0.25)
        index_path(dest)


def cors(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
    handler.send_header("Access-Control-Expose-Headers", "Content-Range, Accept-Ranges, Content-Length")


def any_of(field: str, raw: str) -> str:
    """grouping=ntf1,ntf2 reads as ntf1 OR ntf2."""
    values = [value.strip() for value in raw.split(",") if value.strip()]
    clauses = [f"{field} = {json.dumps(value, ensure_ascii=False)}" for value in values]
    if len(clauses) > 1:
        return "(" + " OR ".join(clauses) + ")"
    return clauses[0] if clauses else ""


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    cors(handler)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def resolve_media(item_id: str) -> Path | None:
    try:
        docs = meili("GET", f"{MEILI_URL}/indexes/{INDEX}/documents/{item_id}")
    except RuntimeError:
        return None
    if not isinstance(docs, dict):
        return None
    rel = str(docs.get("path") or "")
    if not rel or ".." in Path(rel).parts:
        return None
    path = (MEDIA_ROOT / rel).resolve()
    try:
        path.relative_to(MEDIA_ROOT)
    except ValueError:
        return None
    return path if path.is_file() else None


def send_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    size = path.stat().st_size
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    rng = handler.headers.get("Range")
    start, end = 0, size - 1
    status = 200
    if rng and rng.startswith("bytes=") and size:
        spec = rng.split("=", 1)[1]
        left, _, right = spec.partition("-")
        if left:
            start = int(left)
        if right:
            end = int(right)
        end = min(end, size - 1)
        if start > end or start >= size:
            handler.send_response(416)
            cors(handler)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.end_headers()
            return
        status = 206
    length = end - start + 1
    handler.send_response(status)
    cors(handler)
    handler.send_header("Content-Type", mime)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.end_headers()
    if handler.command == "HEAD":
        return
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining:
            chunk = fh.read(min(65536, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)


class CatalogHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("http", args[0] if args else fmt, flush=True)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        cors(self)
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)
        if path in {"/health", "/health/live"}:
            json_response(self, {"status": "live"})
            return
        # Any other route needs a session: the catalogue's port can be reached
        # without nginx. The POST routes need an admin, except tusd's /tus-hook.
        perms, why = account_permissions(self.headers.get("Cookie") or "")
        if perms is None:
            status = 401 if "session" in why else 502
            json_response(self, {"error": why}, status)
            return
        if path == "/search":
            query = (qs.get("q") or [""])[0]
            kind = (qs.get("kind") or [""])[0]
            grouping = (qs.get("grouping") or [""])[0]
            folder = (qs.get("folder") or [""])[0]
            top = (qs.get("top") or [""])[0]
            limit = min(int((qs.get("limit") or ["80"])[0] or 80), 200)
            filters = []
            if kind:
                token = "".join(c for c in kind if c.isalnum() or c in "-_")
                if token == "son":
                    filters.append('(kind = "son" OR kind = "emission" OR kind = "podcast")')
                elif token:
                    filters.append(f'kind = "{token}"')
            for field, raw in (("grouping", grouping), ("folder", folder), ("top", top)):
                clause = any_of(field, raw)
                if clause:
                    filters.append(clause)
            body = {
                "q": query,
                "limit": limit,
                "sort": ["path:asc"],
            }
            if filters:
                body["filter"] = " AND ".join(filters)
            try:
                result = meili("POST", f"{MEILI_URL}/indexes/{INDEX}/search", body) or {}
            except RuntimeError as exc:
                json_response(self, {"error": str(exc), "hits": []}, 503)
                return
            json_response(
                self,
                {
                    "hits": result.get("hits") if isinstance(result, dict) else [],
                    "estimatedTotalHits": result.get("estimatedTotalHits", 0)
                    if isinstance(result, dict)
                    else 0,
                },
            )
            return
        if path == "/volume.json":
            allowed, why = cookie_allowed(self.headers.get("Cookie") or "")
            if not allowed:
                status = 401 if "session" in why else 403
                json_response(self, {"error": why}, status)
                return
            json_response(
                self,
                {
                    "name": volume_api.share_name(os.environ.get("STATION_NAME", "BUTTON")),
                    "host": os.environ.get("SMB_HOST", "").strip(),
                },
            )
            return
        if path == "/inbox.json":
            json_response(self, inbox_api.inbox_status(MEDIA_ROOT, TUSD_DIR))
            return
        if path.startswith("/media/"):
            item_id = path.split("/", 2)[2]
            media = resolve_media(item_id)
            if media is None:
                json_response(self, {"error": "not_found"}, 404)
                return
            send_file(self, media)
            return
        json_response(self, {"error": "not_found"}, 404)

    def _volume_password(self, raw: bytes) -> None:
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            json_response(self, {"error": "JSON attendu"}, 415)
            return
        if (self.headers.get("Sec-Fetch-Site") or "same-origin") not in {"same-origin", "none"}:
            json_response(self, {"error": "requête d'un autre site"}, 403)
            return
        cookie = self.headers.get("Cookie") or ""
        allowed, why = session_admin(cookie)
        if not allowed:
            status = 401 if "session" in why else 403
            json_response(self, {"error": why}, status)
            return
        try:
            body = json.loads(raw.decode() or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = None
        if not isinstance(body, dict):
            json_response(self, {"error": "json illisible"}, 400)
            return
        username = str(body.get("username") or "").strip()
        if not volume_api.username_ok(username):
            json_response(self, {"error": "Identifiant refusé pour le dossier."}, 400)
            return
        host = os.environ.get("SMB_HOST", "").strip()
        root = Path(os.environ.get("SHARE_PRIVATE", "/share-private"))
        if not volume_api.published(host, root):
            json_response(self, {"error": "Le dossier réseau n'est pas publié sur cette station."}, 503)
            return
        users, why = fetch_users(cookie)
        if users is None:
            status = 401 if "session" in why else 502
            json_response(self, {"error": why}, status)
            return
        target = next((user for user in users if isinstance(user, dict) and user.get("username") == username), None)
        if target is None:
            json_response(self, {"error": "Compte introuvable."}, 404)
            return
        role = volume_api.finder_role(target.get("permissions") if isinstance(target.get("permissions"), dict) else {})
        clear = body.get("clear") is True or body.get("password") == ""
        if role == "animateur":
            json_response(self, {"error": "Ce compte n'a pas le dossier."}, 400)
            return
        if clear:
            volume_api.queue_password(root, username, None)
            json_response(self, {"ok": True})
            return
        password = body.get("password")
        if not isinstance(password, str):
            json_response(self, {"error": "Mot de passe manquant."}, 400)
            return
        problem = volume_api.password_problem(password)
        if problem:
            json_response(self, {"error": problem}, 400)
            return
        volume_api.queue_password(root, username, password)
        json_response(self, {"ok": True})

    def do_POST(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > 2_000_000:
            json_response(self, {"error": "corps trop gros"}, 413)
            return
        raw = self.rfile.read(length) if length else b""
        if path == "/prune":
            allowed, why = session_admin(self.headers.get("Cookie") or "")
            if not allowed:
                status = 401 if "session" in why else 403
                json_response(self, {"error": why}, status)
                return
            try:
                payload = prune_outside_carts(self.headers.get("Cookie") or "")
            except (OSError, json.JSONDecodeError, RuntimeError, urllib.error.URLError) as exc:
                json_response(self, {"error": str(exc) or "prune impossible"}, 502)
                return
            json_response(self, payload)
            return
        if path == "/volume-password.json":
            self._volume_password(raw)
            return
        if path == "/banks.json":
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                json_response(self, {"error": "JSON attendu"}, 415)
                return
            if (self.headers.get("Sec-Fetch-Site") or "same-origin") not in {"same-origin", "none"}:
                json_response(self, {"error": "requête d'un autre site"}, 403)
                return
            allowed, why = session_admin(self.headers.get("Cookie") or "")
            if not allowed:
                status = 401 if "session" in why else 403
                json_response(self, {"error": why}, status)
                return
            try:
                body = json.loads(raw.decode() or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = None
            if not isinstance(body, dict):
                json_response(self, {"error": "json illisible"}, 400)
                return
            status, payload = inbox_api.create_bank(MEDIA_ROOT, body.get("label", ""), body.get("folder", ""))
            json_response(self, payload, status)
            return
        if path != "/tus-hook":
            json_response(self, {"error": "not_found"}, 404)
            return
        try:
            event = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            json_response(self, {"error": "json illisible"}, 400)
            return
        if not isinstance(event, dict):
            json_response(self, {"error": "json illisible"}, 400)
            return
        hook, event = agenda_api.hook_event(event, self.headers)
        token = agenda_api.invite_token(event) or (
            self.headers.get(agenda_api.TOKEN_HEADER) or ""
        ).strip()
        if token:
            # A guest's set (Agenda): the engine decides, the folder is the date's.
            engine = agenda_api.engine_call(AUTOMATE_URL, agenda_api.playout_token())
            if hook == "pre-create":
                json_response(self, agenda_api.pre_create(event, token, MEDIA_ROOT, engine))
                return
            if hook == "post-finish":
                json_response(
                    self, agenda_api.finish(event, token, MEDIA_ROOT, TUSD_DIR, engine)
                )
                return
            json_response(self, {})
            return
        if hook == "pre-create":
            allowed, why = deposit_allowed(event)
            if not allowed:
                upload = event.get("Upload") if isinstance(event.get("Upload"), dict) else {}
                meta = upload.get("MetaData") if isinstance(upload.get("MetaData"), dict) else {}
                inbox_api.record_rejet(
                    MEDIA_ROOT,
                    inbox_api.safe_name(str(meta.get("filename") or "")),
                    str(meta.get("destination") or ""),
                    why,
                )
                json_response(self, inbox_api.reject_body(why), 200)
                return
            status, body = inbox_api.hook_decision(event, MEDIA_ROOT, TUSD_DIR)
            json_response(self, body, status)
            return
        if hook == "post-finish":
            status, body = inbox_api.finish_upload(event, MEDIA_ROOT, TUSD_DIR)
            json_response(self, body, status)
            return
        json_response(self, {})


def cookie_of(event: dict) -> str:
    header = (event.get("HTTPRequest") or {}).get("Header") or {}
    raw = header.get("Cookie") or header.get("cookie") or ""
    if isinstance(raw, list):
        return "; ".join(str(item) for item in raw)
    return str(raw)


def deposit_allowed(event: dict) -> tuple[bool, str]:
    return cookie_allowed(cookie_of(event))


def account_permissions(cookie: str) -> tuple[dict | None, str]:
    """The rights of the session behind the browser's cookie, or why there are none."""
    if not AUTOMATE_URL:
        return None, "catalogue non relié à l'automate"
    req = urllib.request.Request(
        f"{AUTOMATE_URL}/account.json",
        headers={"Cookie": cookie},
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return None, "session expirée"
        return None, "automate injoignable"
    except (OSError, json.JSONDecodeError):
        return None, "automate injoignable"
    perms = payload.get("permissions") if isinstance(payload, dict) else None
    if not isinstance(perms, dict):
        return None, "session expirée"
    return perms, ""


def cookie_allowed(cookie: str) -> tuple[bool, str]:
    """Dépôt de fichiers : admin, ou un droit sur les bacs ou l'auto-DJ."""
    perms, why = account_permissions(cookie)
    if perms is None:
        return False, why
    if perms.get("admin") or perms.get("carts") or perms.get("autodj"):
        return True, ""
    return False, "droit insuffisant"


def fetch_users(cookie: str) -> tuple[list | None, str]:
    if not AUTOMATE_URL:
        return None, "catalogue non relié à l'automate"
    req = urllib.request.Request(
        f"{AUTOMATE_URL}/users.json",
        headers={"Cookie": cookie},
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            return None, "session expirée"
        return None, "automate injoignable"
    except (OSError, json.JSONDecodeError):
        return None, "automate injoignable"
    users = payload.get("users") if isinstance(payload, dict) else None
    if not isinstance(users, list):
        return None, "automate injoignable"
    return users, ""


def session_admin(cookie: str) -> tuple[bool, str]:
    perms, why = account_permissions(cookie)
    if perms is None:
        return False, why
    if not perms.get("admin"):
        return False, "réservé à un admin"
    return True, ""


def cart_sound_paths(cookie: str) -> set[str]:
    req = urllib.request.Request(
        f"{AUTOMATE_URL}/carts.json",
        headers={"Cookie": cookie},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode() or "{}")
    carts = payload.get("carts") if isinstance(payload, dict) else None
    if not isinstance(carts, list):
        raise RuntimeError("carts.json illisible")
    keep: set[str] = set()
    for cart in carts:
        if not isinstance(cart, dict):
            continue
        sounds = cart.get("sounds")
        if not isinstance(sounds, list):
            continue
        for sound in sounds:
            if not isinstance(sound, dict):
                continue
            rel = str(sound.get("path") or "").strip().lstrip("/")
            if rel.startswith("media:"):
                rel = rel[6:]
            if rel and ".." not in Path(rel).parts:
                keep.add(rel)
    return keep


def prune_outside_carts(cookie: str) -> dict:
    """Drop search entries whose file is not a sound in a bac."""
    keep = cart_sound_paths(cookie)
    (MEDIA_ROOT / CART_PATHS_FILE).write_text("\n".join(sorted(keep)) + "\n")
    (MEDIA_ROOT / CARTS_ONLY_FLAG).write_text("1\n")
    removed = 0
    for rel in indexed_rels():
        if rel in keep:
            continue
        delete_id(doc_id(rel))
        removed += 1
    print(f"hors bacs −{removed}, gardés {len(keep)}", flush=True)
    return {"removed": removed, "kept": len(keep)}


def inbox_dirs() -> list[Path]:
    folders = [MEDIA_ROOT / src for src, _dest, _mode in promote_rules()]
    shows = MEDIA_ROOT / "00-inbox" / "emissions"
    if shows.is_dir():
        for show_dir in shows.iterdir():
            if not show_dir.is_dir() or not is_safe_show(show_dir.name):
                continue
            for slot in EMISSION_SLOTS:
                folders.append(show_dir / slot)
    return folders


def inbox_loop() -> None:
    """TrueNAS bind-mounts often skip inotify; poll the inbox so SMB dumps promote."""
    while True:
        time.sleep(8)
        for folder in inbox_dirs():
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                if is_audio(path):
                    try:
                        index_path(path)
                    except Exception as exc:
                        print(f"inbox {path}: {exc}", flush=True)


def main() -> None:
    subprocess.run(["/bin/sh", "/app/setup-media-tree.sh", str(MEDIA_ROOT)], check=False)
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    ensure_index()
    full_scan()
    observer = Observer()
    observer.schedule(Handler(), str(MEDIA_ROOT), recursive=True)
    observer.start()
    threading.Thread(target=inbox_loop, name="inbox", daemon=True).start()
    threading.Thread(target=library_loop, name="library", daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), CatalogHandler)
    print(f"button-catalog {PORT} media={MEDIA_ROOT}", flush=True)
    try:
        server.serve_forever()
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
