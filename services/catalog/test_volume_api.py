"""python test_volume_api.py — banque réservée à l'admin, mot de passe du dossier."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

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

    def test_the_share_volume_opens_to_the_beets_loop(self) -> None:
        # Docker crée le volume au nom de root, et la boucle Beets ne tourne pas en root.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            os.chmod(root, 0o755)
            self.assertIsNone(volume_api.open_share_private(root))
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o1777)
            # Déjà ouvert, ou sans dossier, comme en dev : rien ne change.
            with mock.patch.object(volume_api.os, "chmod") as chmod:
                self.assertIsNone(volume_api.open_share_private(root))
                self.assertIsNone(volume_api.open_share_private(root / "absent"))
                chmod.assert_not_called()

    def test_a_share_volume_left_closed_is_said(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            refused = PermissionError(1, "Operation not permitted")
            with mock.patch.object(volume_api.os, "chmod", side_effect=refused):
                warning = volume_api.open_share_private(root)
            self.assertIn(f"{root} n'a pas pu être ouvert à la boucle Beets", warning or "")
            self.assertIn("« Si les rôles n'arrivent pas au dossier »", warning or "")

    def test_root_takes_its_folders_before_opening_the_volume(self) -> None:
        # Ouvert d'abord, le volume laisserait la boucle Beets créer pending/
        # ou samba/ avant root.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            os.chmod(root, 0o755)
            inside = []
            chmod = os.chmod

            def opening(path, mode, *args, **kwargs) -> None:
                inside.append(sorted(child.name for child in Path(path).iterdir()))
                chmod(path, mode, *args, **kwargs)

            with mock.patch.object(volume_api.os, "chmod", side_effect=opening):
                self.assertIsNone(volume_api.open_share_private(root))
            self.assertEqual(inside, [["pending", "samba"]])
            for name in volume_api.PRIVATE_DIRS:
                self.assertEqual(stat.S_IMODE((root / name).stat().st_mode), 0o700)

    def test_a_folder_of_root_is_closed_and_kept(self) -> None:
        # samba/ naissait en 755, avec la base de Samba dedans.
        with tempfile.TemporaryDirectory() as raw:
            samba = Path(raw) / "samba"
            samba.mkdir()
            os.chmod(samba, 0o755)
            (samba / "passdb.tdb").write_bytes(b"base")
            self.assertIsNone(volume_api.claim_dir(samba))
            self.assertEqual(stat.S_IMODE(samba.stat().st_mode), 0o700)
            self.assertEqual((samba / "passdb.tdb").read_bytes(), b"base")

    def test_a_link_or_a_file_never_stands_for_a_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            elsewhere = root / "ailleurs"
            elsewhere.mkdir()
            os.chmod(elsewhere, 0o755)
            (root / "pending").symlink_to(elsewhere)
            (root / "samba").write_text("x", encoding="utf-8")
            for name in volume_api.PRIVATE_DIRS:
                self.assertIn(f"{root / name} n'est pas un dossier", volume_api.claim_dir(root / name) or "")
            refused = volume_api.queue_password(root, "bea", "secret-long")
            self.assertIn("Rien n'est enregistré", refused or "")
            self.assertIn("« Si pending/ ou samba/ n'est pas à root »", refused or "")
            # Ni suivis, ni retirés.
            self.assertTrue((root / "pending").is_symlink())
            self.assertEqual(list(elsewhere.iterdir()), [])
            self.assertEqual(stat.S_IMODE(elsewhere.stat().st_mode), 0o755)
            self.assertEqual((root / "samba").read_text(encoding="utf-8"), "x")
            # Le catalogue le dit au démarrage, et ouvre quand même le volume.
            warning = volume_api.open_share_private(root)
            self.assertIn("Ni le catalogue ni le service share ne s'en servent", warning or "")
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o1777)

    def test_a_folder_of_the_loop_is_taken_back_while_empty(self) -> None:
        # La boucle Beets a créé pending/ avant root. Le test ne tourne pas en
        # root : root y est un autre uid, et chown est simulé.
        with tempfile.TemporaryDirectory() as raw:
            pending = Path(raw) / "pending"
            pending.mkdir()
            os.chmod(pending, 0o777)
            root_uid = os.geteuid() + 1
            with (
                mock.patch.object(volume_api.os, "geteuid", return_value=root_uid),
                mock.patch.object(volume_api.os, "fchown") as fchown,
            ):
                self.assertIsNone(volume_api.claim_dir(pending))
                fchown.assert_called_once_with(mock.ANY, root_uid, os.getegid())
            self.assertEqual(stat.S_IMODE(pending.stat().st_mode), 0o700)

    def test_what_the_loop_left_keeps_its_folder_refused(self) -> None:
        # Un fichier que la boucle garde ouvert lui ferait lire ce que root y écrit.
        with tempfile.TemporaryDirectory() as raw:
            samba = Path(raw) / "samba"
            samba.mkdir()
            (samba / "passdb.tdb").write_bytes(b"")
            with (
                mock.patch.object(volume_api.os, "geteuid", return_value=os.geteuid() + 1),
                mock.patch.object(volume_api.os, "fchown"),
            ):
                # Repris, il reste refusé : le fichier de la boucle y est encore.
                for _ in range(2):
                    problem = volume_api.claim_dir(samba)
                    self.assertIn("contient des fichiers qui ne sont pas à root : passdb.tdb", problem or "")
            self.assertEqual(stat.S_IMODE(samba.stat().st_mode), 0o700)


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

                # Un lien à la place de pending/ : rien ne part, et la console le dit.
                (share / "pending").rename(share / "vu")
                (share / "pending").symlink_to(share / "vu")
                refused = _json(
                    base + "/volume-password.json",
                    cookie="admin=1",
                    payload={"username": "bea", "clear": True},
                    expect=503,
                )
                self.assertIn("Rien n'est enregistré", refused["error"])
                self.assertEqual(json.loads((share / "vu" / "bea.json").read_text(encoding="utf-8"))["action"], "set")
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
