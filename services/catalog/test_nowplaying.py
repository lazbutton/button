"""python test_nowplaying.py — nowplaying ne touche jamais l'antenne.

Son port se joint sans session : sur une station qui laisse BIND_ADDRESS vide,
de tout le réseau local. Il ne demande donc au playout que GET /health, sans le
jeton du playout, et seul le moteur, avec son secret, lui écrit.
"""

from __future__ import annotations

import importlib
import json
import os
import select
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nowplaying"))

SECRET = "secret-du-hook"
TOKEN = "jeton-du-playout"


class Playout(BaseHTTPRequestHandler):
    """Un faux playout, l'API de son port 6833 : il note chaque appel, avec le jeton reçu."""

    calls: list[tuple[str, str, str]] = []

    def do_GET(self) -> None:  # noqa: N802
        self._answer()

    def do_POST(self) -> None:  # noqa: N802
        self._answer()

    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        token = self.headers.get("X-Auth-Token") or ""
        Playout.calls.append((self.command, self.path, token))
        if self.path == "/health":
            _send_json(self, {"status": "live", "on": "false", "gain": "1.", "harbor_min": "5.", "harbor_max": "30."})
        elif token == TOKEN:
            # POST /voiceover : le niveau de l'antenne descend à 0,18.
            _send_json(self, {"on": "true", "gain": "0.18"})
        else:
            self.send_response(401)
            self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        return


class NowplayingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        # Sur une station, radiotomate.yaml est monté dans nowplaying, avec le jeton du playout.
        (tmp / "radiotomate.yaml").write_text(
            f"playout_process_config:\n  token: {TOKEN}\n  input_min_buffer: 5\n", encoding="utf-8"
        )
        cls.playout = _serve(Playout)
        # L'entrée PCM du playout, que le playout mixe à l'antenne.
        cls.pcm = socket.create_server(("127.0.0.1", 0))
        env = {
            "RT_NOWPLAYING_SECRET": SECRET,
            "RT_NOWPLAYING_FILE": str(tmp / "now.json"),
            "RT_PLAYOUT_YAML": str(tmp / "radiotomate.yaml"),
            # Les deux adresses du playout, comme les pose encore le compose.yml de la 1.0.0.
            "RT_PLAYOUT_URL": _url(cls.playout),
            "RT_PLAYOUT_PCM": f"127.0.0.1:{cls.pcm.getsockname()[1]}",
        }
        with mock.patch.dict(os.environ, env):
            cls.nowplaying = importlib.import_module("nowplaying")
        cls.server = _serve(cls.nowplaying.Handler)
        cls.base = _url(cls.server)

    @classmethod
    def tearDownClass(cls) -> None:
        for server in (cls.server, cls.playout):
            server.shutdown()
            server.server_close()
        cls.pcm.close()
        cls.tmp.cleanup()

    def setUp(self) -> None:
        Playout.calls.clear()

    def test_nobody_lowers_the_antenna(self) -> None:
        on = json.dumps({"on": True}).encode()
        for method, data in (("POST", on), ("GET", None)):
            status, _ = _call(self.base + "/voiceover", method=method, data=data)
            self.assertEqual(status, 404, method)
        self.assertEqual(Playout.calls, [])

    def test_nobody_speaks_on_the_antenna(self) -> None:
        status = _websocket(self.server.server_address[1])
        self.assertEqual(status.split(" ")[1:2], ["404"], status)
        # Personne n'a ouvert l'entrée PCM du playout.
        ready, _, _ = select.select([self.pcm], [], [], 0.3)
        self.assertEqual(ready, [])

    def test_the_hook_still_wants_its_secret(self) -> None:
        track = json.dumps({"artist": "Ada", "title": "Song"}).encode()
        # Ni sans secret, ni avec le jeton du playout.
        for auth in ({}, {"Authorization": "Bearer faux"}, {"Authorization": f"Bearer {TOKEN}"}):
            headers = {"Content-Type": "application/json", **auth}
            status, _ = _call(self.base + "/hook", method="POST", data=track, headers=headers)
            self.assertEqual(status, 401, auth)

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {SECRET}"}
        status, _ = _call(self.base + "/hook", method="POST", data=track, headers=headers)
        self.assertEqual(status, 204)
        status, body = _call(self.base + "/now.json")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["title"], "Song")
        self.assertEqual(Playout.calls, [])

    def test_machine_json_reads_health_without_the_playout_token(self) -> None:
        status, body = _call(self.base + "/machine.json")
        self.assertEqual(status, 200)
        machine = json.loads(body)
        self.assertEqual((machine["status"], machine["on"], machine["harbor_min"]), ("live", False, 5.0))
        self.assertEqual(Playout.calls, [("GET", "/health", "")])


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
    url: str, *, method: str = "GET", data: bytes | None = None, headers: dict | None = None
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, exc.read()


def _websocket(port: int) -> str:
    """Ce que faisait le micro : un WebSocket sur /voiceover/pcm, une trame de PCM, puis la fermeture.

    Rend la ligne d'état de la réponse.
    """
    with socket.create_connection(("127.0.0.1", port), timeout=4) as sock:
        sock.sendall(
            b"GET /voiceover/pcm HTTP/1.1\r\nHost: nowplaying\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            b"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(4096)
            if not chunk:
                break
            head += chunk
        try:
            # Une trame binaire masquée de quatre octets, puis la trame de fermeture.
            sock.sendall(bytes([0x82, 0x84, 0, 0, 0, 0, 1, 2, 3, 4]))
            sock.sendall(bytes([0x88, 0x80, 0, 0, 0, 0]))
            # Jusqu'à ce que nowplaying ferme : une entrée PCM ouverte l'est alors déjà.
            while sock.recv(4096):
                pass
        except OSError:
            pass
    return head.split(b"\r\n", 1)[0].decode("latin-1")


if __name__ == "__main__":
    unittest.main()
