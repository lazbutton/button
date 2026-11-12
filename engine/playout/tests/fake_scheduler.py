"""
The scheduler of the antenna bench: it answers the playout, and keeps what the
playout says.

The playout posts its heartbeat to /live every second, and each title that airs
to /metadata_log. `GET /journal` gives both back to antenne.py. Nothing else:
the bench pushes the titles itself. Standard library only.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 6822

_lock = threading.Lock()
_journal: dict[str, list[dict]] = {"live": [], "metadata": []}


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _beat(data: dict) -> dict:
    return {
        "at": time.time(),
        "source": str(data.get("source") or ""),
        "title": str(data.get("title") or ""),
        "remaining": _number(data.get("remaining")),
        "elapsed": _number(data.get("elapsed")),
        "autodj_queued": int(_number(data.get("autodj_queued"))),
        "jingles_queued": int(_number(data.get("jingles_queued"))),
    }


def _aired(data: dict) -> dict:
    return {
        "at": time.time(),
        "source": str(data.get("source") or ""),
        "title": str(data.get("title") or ""),
    }


class Handler(BaseHTTPRequestHandler):
    def _answer(self, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/journal":
            self.send_error(404)
            return
        with _lock:
            self._answer(_journal)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        with _lock:
            if self.path == "/live":
                _journal["live"].append(_beat(data))
            elif self.path == "/metadata_log":
                _journal["metadata"].append(_aired(data))
        self._answer({})

    def log_message(self, fmt: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
