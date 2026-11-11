"""python test_media_tree.py — l'arbre de la banque, et à qui il appartient.

setup-media-tree.sh tourne en root dans radiotomate-init et le catalogue. Avec
MEDIA_OWNER, il donne la banque au moteur. Un faux chown note ce qu'il aurait
changé : le test ne tourne pas en root.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deploy" / "share"))
sys.path.insert(0, str(ROOT / "deploy" / "scripts"))

import apply_share  # noqa: E402

SCRIPT = ROOT / "deploy" / "scripts" / "setup-media-tree.sh"
INIT = ROOT / "deploy" / "scripts" / "init-radiotomate.sh"

# Un faux chown qui note ses arguments, un par ligne, puis une ligne vide.
# CHOWN_FAIL=1 : il refuse, comme un disque exFAT ou NFS en root_squash.
FAKE_CHOWN = """#!/bin/sh
for arg in "$@"; do printf '%s\\n' "$arg" >> "$CHOWN_LOG"; done
printf '\\n' >> "$CHOWN_LOG"
[ "${CHOWN_FAIL:-}" != 1 ] || { echo "chown: Operation not permitted" >&2; exit 1; }
"""


class MediaTreeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.media = root / "media"
        self.media.mkdir()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "chown"
        fake.write_text(FAKE_CHOWN, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.log = root / "chown.log"
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "CHOWN_LOG": str(self.log)}
        self.env.pop("MEDIA_OWNER", None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_script(self, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(SCRIPT), str(self.media)],
            env={**self.env, **env},
            capture_output=True,
            text=True,
            check=False,
        )

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [block.split("\n") for block in self.log.read_text(encoding="utf-8").split("\n\n") if block]

    def changed(self) -> set[str]:
        found: set[str] = set()
        for call in self.calls():
            self.assertEqual(call[:2], ["-h", "4242:4243"], call)
            found.update(os.path.relpath(path, self.media) for path in call[2:])
        return found

    def test_without_an_owner_nothing_changes_hands(self) -> None:
        # Le banc local, le catalogue d'une version d'avant.
        done = self.run_script()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.media / "00-inbox" / "rotation").is_dir())
        self.assertTrue((self.media / "90-trash").is_dir())
        self.assertEqual(self.calls(), [])

    def test_the_bank_goes_to_the_engine(self) -> None:
        # Une station existante : un son déposé par root, un lien de Carts/,
        # et ce que le dossier partagé tient, qui reste à lui.
        (self.media / "10-rotation").mkdir()
        (self.media / "10-rotation" / "Artiste - Titre.mp3").write_bytes(b"audio")
        (self.media / "Carts").mkdir()
        (self.media / "Carts" / "1-Jingles").symlink_to("../50-carts/1")
        (self.media / ".volume" / "Banques").mkdir(parents=True)
        (self.media / "lost+found").mkdir()
        done = self.run_script(MEDIA_OWNER="4242:4243")
        self.assertEqual(done.returncode, 0, done.stderr)
        changed = self.changed()
        for path in (
            ".",
            "00-inbox",
            "00-inbox/rotation",
            "10-rotation",
            "10-rotation/Artiste - Titre.mp3",
            "20-archives",
            "40-emissions/_modele/podcasts",
            "Carts/1-Jingles",
            "90-trash",
        ):
            self.assertIn(path, changed)
        self.assertFalse({path for path in changed if path.startswith((".volume", "lost+found"))})

    def test_what_the_engine_has_is_left_alone(self) -> None:
        self.run_script()
        mine = self.media.stat()
        done = self.run_script(MEDIA_OWNER=f"{mine.st_uid}:{mine.st_gid}")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_disk_that_refuses_chown_does_not_stop_the_start(self) -> None:
        done = self.run_script(MEDIA_OWNER="4242:4243", CHOWN_FAIL="1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("n'a pas pu être donnée en entier à 4242:4243", done.stderr)
        self.assertIn("chown -R 4242:4243 media", done.stderr)

    def test_the_share_group_is_the_one_of_apply_share(self) -> None:
        # Les dossiers que share ouvre au groupe deposer restent à lui.
        self.assertIn(f"DEPOSER_GID={apply_share.DEPOSER_GID}\n", SCRIPT.read_text(encoding="utf-8"))

    def test_init_gives_the_bank_to_rtuser(self) -> None:
        text = INIT.read_text(encoding="utf-8")
        self.assertIn('MEDIA_OWNER="$(id -u rtuser):$(id -g rtuser)" /bin/sh /setup-media-tree.sh "$MEDIA"', text)


if __name__ == "__main__":
    unittest.main()
