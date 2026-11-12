#!/usr/bin/env python3
"""Now Playing sidecar. Relais Radiotomate metadata_log → GET /now.json (CORS)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PORT = int(os.environ.get("RT_NOWPLAYING_PORT", "6820"))
SECRET = os.environ.get("RT_NOWPLAYING_SECRET", "button-dev-secret")
STATE = Path(os.environ.get("RT_NOWPLAYING_FILE", str(Path(__file__).resolve().parent / "now.json")))
PLAYOUT_URL = os.environ.get("RT_PLAYOUT_URL", "http://radiotomate-playout:6833").rstrip("/")
PLAYOUT_YAML = Path(os.environ.get("RT_PLAYOUT_YAML", "/config/radiotomate.yaml"))
MEDIA_CANDIDATES = (
    os.environ.get("BUTTON_MEDIA_ROOT", "").strip(),
    "/media",
)
LOCK = threading.Lock()
NEXT_KEYS = ("next_autodj", "next_jingle", "next_cart")
CLOCK_KEYS = ("remaining", "elapsed", "duration")
WAITING_TITLE = "En attente de métadonnées"

MOCK = {
    "artist": "BUTTON",
    "title": WAITING_TITLE,
    "album": "",
    "source": "autodj",
    "on_air": datetime.now(timezone.utc).isoformat(),
    "SOURCE_NAME": "button",
    "previous": None,
    "next_autodj": None,
    "next_jingle": None,
    "next_cart": None,
}


def unpack_playlist_as_artist(data: dict) -> dict:
    """Radiotomate / ancien streamer : artist = nom de cart, title = « Artiste - Titre »."""
    out = dict(data)
    title = str(out.get("title") or "").strip()
    artist = str(out.get("artist") or "").strip()
    album = str(out.get("album") or "").strip()
    if " - " not in title:
        return out
    left, right = (part.strip() for part in title.split(" - ", 1))
    if not left or not right:
        return out
    if not artist or (album and artist == album):
        if album or artist:
            out["album"] = album or artist
        out["artist"] = left
        out["title"] = right
    return out


def _as_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number or number <= 0:
        return None
    return number


def _as_int(value: object, default: int = -1) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def normalize_cue(value: object) -> dict | None:
    parsed = value
    if value is None or value == "" or value == {}:
        return None
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(parsed, dict):
        return None
    rid = _as_int(parsed.get("rid", -1))
    title = str(parsed.get("title") or "").strip()
    artist = str(parsed.get("artist") or "").strip()
    album = str(parsed.get("album") or "").strip()
    if rid < 0 and not title and not artist:
        return None
    cue: dict = {"title": title, "artist": artist, "rid": rid}
    if album:
        cue["album"] = album
    uri = str(parsed.get("initial_uri") or "").strip()
    if uri:
        cue["initial_uri"] = uri
    duration = _as_float(parsed.get("duration"))
    if duration:
        cue["duration"] = duration
    return cue


def _has_track(data: dict) -> bool:
    return bool(str(data.get("title") or "").strip() or str(data.get("artist") or "").strip())


def is_sidecar_merge(data: dict) -> bool:
    has_next = any(key in data for key in NEXT_KEYS)
    has_clock = any(key in data for key in CLOCK_KEYS)
    return (has_next or has_clock) and not _has_track(data)


def _identity(data: dict) -> tuple:
    sound_id = str(data.get("radiotomate_sound_id") or "").strip()
    if sound_id:
        return ("id", sound_id)
    return (
        "ta",
        str(data.get("title") or "").strip(),
        str(data.get("artist") or "").strip(),
    )


def _track_duration(data: dict) -> float | None:
    duration = _as_float(data.get("duration"))
    if duration:
        return duration
    elapsed = _as_float(data.get("elapsed")) or 0.0
    remaining = _as_float(data.get("remaining")) or 0.0
    artist = str(data.get("artist") or "").strip().lower()
    source = str(data.get("source") or "").strip().lower()
    if "jingle" in artist or "jingle" in source:
        return elapsed if elapsed > 0 else None
    total = elapsed + remaining
    return total if total > 0 else None


def _stash_previous(current: dict) -> dict | None:
    title = str(current.get("title") or "").strip()
    artist = str(current.get("artist") or "").strip()
    if not title and not artist:
        return None
    if title == WAITING_TITLE:
        return None
    previous = {
        "title": title,
        "artist": artist,
        "album": str(current.get("album") or "").strip(),
        "source": str(current.get("source") or "").strip(),
    }
    sound_id = str(current.get("radiotomate_sound_id") or "").strip()
    if sound_id:
        previous["radiotomate_sound_id"] = sound_id
    duration = _track_duration(current)
    if duration:
        previous["duration"] = round(duration, 3)
    return previous


def _merge_clock(out: dict, incoming: dict) -> None:
    for key in CLOCK_KEYS:
        if key not in incoming:
            continue
        try:
            value = float(incoming[key])
        except (TypeError, ValueError):
            continue
        out[key] = value
    duration = _as_float(out.get("duration"))
    elapsed = _as_float(out.get("elapsed")) or 0.0
    if duration is not None and duration + 0.5 < elapsed:
        out.pop("duration", None)


def apply_hook(current: dict, incoming: dict) -> dict:
    payload = dict(incoming)
    payload["received_at"] = datetime.now(timezone.utc).isoformat()
    if is_sidecar_merge(payload):
        out = dict(current)
        for key in NEXT_KEYS:
            if key in payload:
                out[key] = normalize_cue(payload[key])
        _merge_clock(out, payload)
        out["received_at"] = payload["received_at"]
        return out

    payload = unpack_playlist_as_artist(payload)
    if _identity(current) != _identity(payload):
        previous = _stash_previous(current)
        if previous is not None:
            payload["previous"] = previous
        elif "previous" not in payload:
            payload["previous"] = current.get("previous")
    elif "previous" not in payload:
        payload["previous"] = current.get("previous")

    for key in NEXT_KEYS:
        if key in payload:
            payload[key] = normalize_cue(payload[key])
        else:
            payload[key] = current.get(key)
    _merge_clock(payload, current)
    _merge_clock(payload, incoming)
    return payload


def load_state() -> dict:
    if STATE.exists():
        try:
            return unpack_playlist_as_artist(json.loads(STATE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return dict(MOCK)


def save_state(data: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _as_float(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def _as_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes"):
            return True
        if lowered in ("0", "false", "no"):
            return False
    return None


def _coerce_playout(data: dict) -> dict:
    """GET /health du playout dit ses nombres et ses booléens en texte."""
    parsed = _as_bool(data.get("on"))
    if parsed is not None:
        data["on"] = parsed
    for key in (
        "silence_s",
        "rms_db",
        "rms",
        "gain",
        "harbor_min",
        "harbor_max",
        "harbor_s",
        "rss_mb",
        "cpu_pct",
    ):
        if key not in data:
            continue
        parsed = _as_float(data.get(key))
        if parsed is not None:
            data[key] = parsed
    return data


def yaml_harbor() -> tuple[float, float]:
    min_s, max_s = 5.0, 30.0
    if not PLAYOUT_YAML.exists():
        return min_s, max_s
    in_block = False
    for raw in PLAYOUT_YAML.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0]
        stripped = line.strip()
        if stripped.startswith("playout_process_config"):
            in_block = True
            continue
        if in_block:
            if stripped and not line[:1].isspace() and stripped.endswith(":") and not stripped.startswith(
                "input_"
            ):
                in_block = False
                continue
            if stripped.startswith("input_min_buffer:"):
                parsed = _as_float(stripped.split(":", 1)[1].strip().strip("\"'"))
                if parsed is not None:
                    min_s = parsed
            elif stripped.startswith("input_max_buffer:"):
                parsed = _as_float(stripped.split(":", 1)[1].strip().strip("\"'"))
                if parsed is not None:
                    max_s = parsed
    return min_s, max_s


def media_root() -> Path | None:
    for raw in MEDIA_CANDIDATES:
        if not raw:
            continue
        path = Path(raw)
        if path.is_dir():
            return path
    return None


def disk_pct(path: Path) -> float | None:
    try:
        stat = os.statvfs(path)
    except OSError:
        return None
    total = stat.f_frsize * stat.f_blocks
    free = stat.f_frsize * stat.f_bavail
    if total <= 0:
        return None
    return round(100.0 * (1.0 - free / total), 1)


def machine_payload() -> tuple[int, bytes]:
    status, raw = playout_health()
    health: dict = {}
    try:
        parsed = json.loads(raw.decode("utf-8") or "{}")
        if isinstance(parsed, dict):
            health = _coerce_playout(parsed)
    except (UnicodeDecodeError, json.JSONDecodeError):
        health = {"error": "playout"}
    min_s, max_s = yaml_harbor()
    if _as_float(health.get("harbor_min")) is None:
        health["harbor_min"] = min_s
    if _as_float(health.get("harbor_max")) is None:
        health["harbor_max"] = max_s
    root = media_root()
    health["disk_pct"] = disk_pct(root) if root else None
    health["disk_path"] = str(root) if root else ""
    if "status" not in health:
        health["status"] = "down" if status >= 400 else "live"
    return (200 if status < 500 else status), json.dumps(health, ensure_ascii=False).encode("utf-8")


def playout_health() -> tuple[int, bytes]:
    """GET /health du playout, qui ne demande pas de jeton.

    nowplaying ne porte pas celui du playout : son port se joint sans session,
    et le prêterait à qui le joint.
    """
    try:
        with urlopen(Request(f"{PLAYOUT_URL}/health"), timeout=4) as res:
            return res.status, res.read()
    except HTTPError as exc:
        return int(exc.code), exc.read()
    except URLError as exc:
        return 502, json.dumps({"error": str(exc.reason)}).encode()


class Handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/machine.json":
            status, body = machine_payload()
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/now.json", "/now", "/"):
            with LOCK:
                body = json.dumps(load_state(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/hook":
            self.send_error(404)
            return
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {SECRET}"
        if SECRET and auth != expected:
            self.send_error(401)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")
        data: dict
        if "json" in ctype:
            data = json.loads(raw.decode("utf-8") or "{}")
        else:
            from urllib.parse import parse_qs

            parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
            data = {k: v[-1] if v else "" for k, v in parsed.items()}
        if not isinstance(data, dict):
            self.send_error(400)
            return
        with LOCK:
            save_state(apply_hook(load_state(), data))
        self.send_response(204)
        self._cors()
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        print(f"[nowplaying] {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    if not STATE.exists():
        save_state(dict(MOCK))
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Now Playing on http://127.0.0.1:{PORT}/now.json")
    httpd.serve_forever()
