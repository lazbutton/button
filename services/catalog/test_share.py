"""python test_share.py — écoute, comptes, dossiers du volume Finder."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy" / "share"))
sys.path.insert(0, str(ROOT / "deploy" / "scripts"))

import apply_share  # noqa: E402
import export_share_roles  # noqa: E402


class ShareTest(unittest.TestCase):
    def test_bind_refuses_every_interface(self) -> None:
        self.assertFalse(apply_share.bind_ok("", False))
        self.assertFalse(apply_share.bind_ok("0.0.0.0", False))
        self.assertFalse(apply_share.bind_ok("::", False))
        self.assertFalse(apply_share.bind_ok("", True))
        self.assertTrue(apply_share.bind_ok("0.0.0.0", True))
        self.assertTrue(apply_share.bind_ok("127.0.0.1", False))

    def test_plan_matches_roles(self) -> None:
        roles = {"ada": "admin", "bea": "programmateur", "cam": "animateur"}
        pending = {
            "ada": {"action": "set", "password": "secret-long"},
            "cam": {"action": "set", "password": "nope-nope"},
            "bea": {"action": "clear"},
        }
        plan = apply_share.account_plan(roles, pending)
        self.assertEqual(plan["enable"]["ada"]["groups"], ["deposer", "organiser"])
        self.assertEqual(plan["enable"]["ada"]["password"], "secret-long")
        self.assertNotIn("bea", plan["enable"])
        self.assertNotIn("cam", plan["enable"])
        self.assertEqual(plan["disable"], ["bea", "cam"])

    def test_conf_follows_symlinks_and_names_the_station(self) -> None:
        text = apply_share.smb_conf("Radio Nord")
        self.assertIn("[Radio-Nord]", text)
        self.assertIn("wide links = yes", text)
        self.assertIn("path = /media/.volume", text)
        self.assertNotIn("0.0.0.0", text)

    def test_sweep_removes_a_folder_and_keeps_files_and_emission_slots(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            rotation = media / "10-rotation"
            nested = rotation / "sous-dossier"
            nested.mkdir(parents=True)
            (rotation / "Ada - Song.mp3").write_bytes(b"a")
            show = media / "40-emissions" / "matin"
            (show / "entiere").mkdir(parents=True)
            (show / "brouillon").mkdir()
            removed = apply_share.sweep_media(media)
            self.assertEqual(removed, 2)
            self.assertFalse(nested.exists())
            self.assertTrue((rotation / "Ada - Song.mp3").is_file())
            self.assertTrue((show / "entiere").is_dir())
            self.assertFalse((show / "brouillon").exists())

    def test_roles_file_has_no_password(self) -> None:
        self.assertEqual(export_share_roles.role_of({"admin": True, "carts": True}), "admin")
        self.assertEqual(export_share_roles.role_of({"carts": True}), "programmateur")
        self.assertEqual(export_share_roles.role_of({"autodj": True}), "programmateur")
        self.assertEqual(export_share_roles.role_of({"live": True}), "animateur")
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / "roles.json"
            export_share_roles.write_roles(
                [{"username": "bea", "role": "programmateur"}],
                dest,
            )
            text = dest.read_text(encoding="utf-8")
            self.assertIn("bea", text)
            self.assertNotIn("password", text)


if __name__ == "__main__":
    unittest.main()
