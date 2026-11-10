"""python test_share.py — écoute, comptes, dossiers du volume Finder."""

from __future__ import annotations

import ast
import inspect
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy" / "share"))
sys.path.insert(0, str(ROOT / "deploy" / "scripts"))

import apply_share  # noqa: E402
import export_share_roles  # noqa: E402
import volume_api  # noqa: E402


def code_of(function) -> str:
    """Le code d'une fonction, sans sa docstring."""
    node = ast.parse(textwrap.dedent(inspect.getsource(function))).body[0]
    node.body = node.body[1:]
    return ast.dump(node)


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

    def test_share_takes_its_folders_before_opening_the_volume(self) -> None:
        # Ouvert d'abord, le volume laisserait la boucle Beets créer pending/
        # ou samba/ avant root.
        with tempfile.TemporaryDirectory() as raw:
            private = Path(raw)
            os.chmod(private, 0o755)
            inside = []
            chmod = os.chmod

            def opening(path, mode, *args, **kwargs) -> None:
                inside.append(sorted(child.name for child in Path(path).iterdir()))
                chmod(path, mode, *args, **kwargs)

            with mock.patch.object(apply_share.os, "chmod", side_effect=opening):
                self.assertEqual(apply_share.open_private(private), [])
            self.assertEqual(inside, [["pending", "samba"]])
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o1777)
            for name in apply_share.PRIVATE_DIRS:
                self.assertEqual(stat.S_IMODE((private / name).stat().st_mode), 0o700)

    def test_samba_does_not_start_on_a_folder_that_is_not_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            private = Path(raw)
            base = private / "base"
            base.mkdir()
            (private / "samba").symlink_to(base)
            with (
                mock.patch.dict(os.environ, {"SHARE_PRIVATE": str(private)}),
                self.assertRaises(SystemExit) as refused,
            ):
                apply_share.sync_once()
            self.assertIn(f"{private / 'samba'} n'est pas un dossier", str(refused.exception))
            self.assertIn("« Si pending/ ou samba/ n'est pas à root »", str(refused.exception))
            # Le volume s'ouvre quand même : la boucle y écrit les rôles.
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o1777)
            self.assertEqual(list(base.iterdir()), [])

    def test_share_and_the_catalog_claim_a_folder_alike(self) -> None:
        # Le catalogue prend les mêmes dossiers au démarrage, dans son image.
        self.assertEqual(code_of(apply_share.claim_dir), code_of(volume_api.claim_dir))
        self.assertEqual(apply_share.PRIVATE_DIRS, volume_api.PRIVATE_DIRS)
        self.assertEqual(apply_share.PRIVATE_DIRS_DOC, volume_api.PRIVATE_DIRS_DOC)


if __name__ == "__main__":
    unittest.main()
