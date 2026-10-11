"""python test_volume_api.py — banque réservée à l'admin, mot de passe du dossier."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "scripts"))

import refresh_volume  # noqa: E402
import volume_api  # noqa: E402


class VolumeApiTest(unittest.TestCase):
    def test_share_name_matches_the_volume_script(self) -> None:
        for raw in ("BUTTON", "Radio Nord", "", "!!!", "a" * 40):
            self.assertEqual(volume_api.share_name(raw), refresh_volume.share_name(raw))

    def test_queue_writes_a_root_only_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            volume_api.queue_password(root, "bea", "secret-long")
            path = root / "pending" / "bea.json"
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["action"], "set")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            volume_api.queue_password(root, "bea", None)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["action"], "clear")


class CatalogVolumeHttpTest(unittest.TestCase):
    def test_programmer_deposits_but_cannot_create_a_bank(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media = root / "media"
            share = root / "share"
            media.mkdir()
            share.mkdir()
            users = {
                "ada": {"admin": True},
                "bea": {"live": True, "carts": True, "autodj": True},
                "cam": {"live": True},
            }

            class Automate(BaseHTTPRequestHandler):
                def do_GET(self) -> None:  # noqa: N802
                    cookie = self.headers.get("Cookie") or ""
                    if "admin=1" in cookie:
                        perms = users["ada"]
                    elif "prog=1" in cookie:
                        perms = users["bea"]
                    elif "anim=1" in cookie:
                        perms = users["cam"]
                    else:
                        self.send_response(401)
                        self.end_headers()
                        return
                    if self.path == "/account.json":
                        body = {"permissions": perms}
                    elif self.path == "/users.json":
                        body = {
                            "users": [
                                {"username": name, "permissions": flags} for name, flags in users.items()
                            ]
                        }
                    else:
                        self.send_response(404)
                        self.end_headers()
                        return
                    data = json.dumps(body).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)

                def log_message(self, fmt: str, *args) -> None:
                    return

            automate = ThreadingHTTPServer(("127.0.0.1", 0), Automate)
            threading.Thread(target=automate.serve_forever, daemon=True).start()
            os.environ["SMB_HOST"] = ""
            os.environ["STATION_NAME"] = "BUTTON"
            os.environ["SHARE_PRIVATE"] = str(share)
            import app as catalog

            catalog.AUTOMATE_URL = f"http://127.0.0.1:{automate.server_address[1]}"
            catalog.MEDIA_ROOT = media
            catalog.TUSD_DIR = root / "tusd"
            server = ThreadingHTTPServer(("127.0.0.1", 0), catalog.CatalogHandler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                volume = _json(base + "/volume.json", cookie="prog=1")
                self.assertEqual(volume["name"], "BUTTON")
                self.assertEqual(volume["host"], "")

                denied = _json(
                    base + "/banks.json",
                    cookie="prog=1",
                    payload={"label": "Jazz", "folder": "jazz"},
                    expect=403,
                )
                self.assertEqual(denied["error"], "réservé à un admin")

                created = _json(
                    base + "/banks.json",
                    cookie="admin=1",
                    payload={"label": "Jazz en public", "folder": "jazz"},
                    expect=201,
                )
                self.assertEqual(created["destination"]["folder"], "20-archives/jazz")
                self.assertTrue((media / "20-archives" / "jazz").is_dir())

                hook = _json(
                    base + "/tus-hook",
                    cookie="prog=1",
                    payload={
                        "HTTPRequest": {"Header": {"Cookie": "prog=1"}},
                        "Upload": {
                            "Size": 4,
                            "MetaData": {"filename": "Ada - Song.mp3", "destination": "rotation"},
                        },
                    },
                    headers={"Hook-Name": "pre-create"},
                )
                self.assertFalse(hook.get("RejectUpload"))

                unpublished = _json(
                    base + "/volume-password.json",
                    cookie="admin=1",
                    payload={"username": "bea", "password": "secret-long"},
                    expect=503,
                )
                self.assertIn("pas publié", unpublished["error"])

                os.environ["SMB_HOST"] = "station.example"
                saved = _json(
                    base + "/volume-password.json",
                    cookie="admin=1",
                    payload={"username": "bea", "password": "secret-long"},
                )
                self.assertTrue(saved["ok"])
                pending = json.loads((share / "pending" / "bea.json").read_text(encoding="utf-8"))
                self.assertEqual(pending["password"], "secret-long")
                self.assertNotIn("secret-long", json.dumps(created))

                animator = _json(
                    base + "/volume-password.json",
                    cookie="admin=1",
                    payload={"username": "cam", "password": "secret-long"},
                    expect=400,
                )
                self.assertEqual(animator["error"], "Ce compte n'a pas le dossier.")
            finally:
                server.shutdown()
                automate.shutdown()


def _json(
    url: str,
    *,
    cookie: str,
    payload: dict | None = None,
    expect: int = 200,
    headers: dict | None = None,
) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method="POST" if payload is not None else "GET")
    request.add_header("Cookie", cookie)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
        request.add_header("Sec-Fetch-Site", "same-origin")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            status = response.status
            body = json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = json.loads(exc.read().decode() or "{}")
    if status != expect:
        raise AssertionError(f"{url} -> {status} {body}, attendu {expect}")
    return body


if __name__ == "__main__":
    unittest.main()
