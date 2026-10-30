"""python test_session.py — le catalogue ne répond qu'à une session ouverte."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import app as catalog

SONG = "10-rotation/Ada - Song.mp3"


class Engine(BaseHTTPRequestHandler):
    """Un faux moteur : 401 sans session ouverte, 200 avec, 503 en panne."""

    cookies: list[str] = []
    down = False

    def do_GET(self) -> None:  # noqa: N802
        cookie = self.headers.get("Cookie") or ""
        Engine.cookies.append(cookie)
        if Engine.down:
            self.send_response(503)
            self.end_headers()
            return
        if self.path != "/account.json" or cookie != "session=ouverte":
            self.send_response(401)
            self.end_headers()
            return
        # Un animateur : chercher et pré-écouter ne demandent aucun droit.
        _send_json(self, {"username": "cam", "permissions": {"live": True}})

    def log_message(self, fmt: str, *args) -> None:
        return


class Meili(BaseHTTPRequestHandler):
    """Un faux Meilisearch, qui ne connaît qu'un titre."""

    calls: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        Meili.calls.append(self.path)
        _send_json(self, {"id": "ada", "path": SONG})

    def do_POST(self) -> None:  # noqa: N802
        Meili.calls.append(self.path)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        _send_json(self, {"hits": [{"id": "ada", "path": SONG}], "estimatedTotalHits": 1})

    def log_message(self, fmt: str, *args) -> None:
        return


class CatalogSessionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.media = tempfile.TemporaryDirectory()
        root = Path(cls.media.name).resolve()
        (root / "10-rotation").mkdir()
        (root / SONG).write_bytes(b"ID3 une chanson")
        cls.servers = [_serve(Engine), _serve(Meili), _serve(catalog.CatalogHandler)]
        engine, meili, cls.base = (_url(server) for server in cls.servers)
        catalog.AUTOMATE_URL = engine
        catalog.MEILI_URL = meili
        catalog.MEDIA_ROOT = root
        catalog.TUSD_DIR = root / "tusd"

    @classmethod
    def tearDownClass(cls) -> None:
        for server in cls.servers:
            server.shutdown()
            server.server_close()
        cls.media.cleanup()

    def setUp(self) -> None:
        Engine.cookies.clear()
        Engine.down = False
        Meili.calls.clear()

    def test_the_engine_says_401_then_200(self) -> None:
        for cookie in (None, "session=fermee"):
            for path in ("/search?q=a", "/media/ada", "/inbox.json", "/volume.json"):
                status, body = _call(self.base + path, cookie=cookie)
                self.assertEqual((status, json.loads(body)), (401, {"error": "session expirée"}), path)
        # Rien n'est cherché ni lu, et le moteur a jugé le cookie du navigateur.
        self.assertEqual(Meili.calls, [])
        self.assertEqual(set(Engine.cookies), {"", "session=fermee"})

        status, body = _call(self.base + "/search?q=a", cookie="session=ouverte")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["hits"][0]["path"], SONG)
        status, body = _call(
            self.base + "/media/ada", cookie="session=ouverte", headers={"Range": "bytes=0-2"}
        )
        self.assertEqual((status, body), (206, b"ID3"))

    def test_probes_answer_without_a_session(self) -> None:
        for path in ("/health", "/health/live"):
            status, body = _call(self.base + path)
            self.assertEqual((status, json.loads(body)), (200, {"status": "live"}))
        self.assertEqual(Engine.cookies, [])

    def test_tusd_calls_its_hook_without_a_cookie(self) -> None:
        status, body = _call(self.base + "/tus-hook", payload={"Type": "post-receive", "Event": {}})
        self.assertEqual((status, json.loads(body)), (200, {}))
        self.assertEqual(Engine.cookies, [])

    def test_an_engine_down_is_not_an_expired_session(self) -> None:
        Engine.down = True
        status, body = _call(self.base + "/search?q=a", cookie="session=ouverte")
        self.assertEqual((status, json.loads(body)), (502, {"error": "automate injoignable"}))
        self.assertEqual(Meili.calls, [])

    def test_a_catalogue_without_engine_opens_nothing(self) -> None:
        engine, catalog.AUTOMATE_URL = catalog.AUTOMATE_URL, ""
        try:
            status, body = _call(self.base + "/search?q=a", cookie="session=ouverte")
        finally:
            catalog.AUTOMATE_URL = engine
        self.assertEqual((status, json.loads(body)), (502, {"error": "catalogue non relié à l'automate"}))
        self.assertEqual(Meili.calls, [])


def _serve(handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _url(server: ThreadingHTTPServer) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def _send_json(handler: BaseHTTPRequestHandler, payload: dict) -> None:
    data = json.dumps(payload).encode()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _call(
    url: str,
    *,
    cookie: str | None = None,
    headers: dict | None = None,
    payload: dict | None = None,
) -> tuple[int, bytes]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, headers=headers or {})
    if cookie is not None:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read()


if __name__ == "__main__":
    unittest.main()
