"""python test_promote_inplace.py — tags et flac sans quitter le dossier."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "promote-inbox.sh"


def write_bin(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class PromoteInPlaceTest(unittest.TestCase):
    def test_tags_bare_file_converts_wav_and_leaves_tagged_mp3(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media = root / "media"
            rotation = media / "10-rotation"
            bank = media / "20-archives" / "jazz"
            rotation.mkdir(parents=True)
            bank.mkdir(parents=True)
            (rotation / "Keep - Me.mp3").write_bytes(b"tagged")
            (rotation / "Ada - Song.mp3").write_bytes(b"bare")
            (bank / "Bea - Live.wav").write_bytes(b"wav")
            bindir = root / "bin"
            bindir.mkdir()
            log = root / "ffmpeg.log"
            write_bin(
                bindir,
                "ffprobe",
                "#!/bin/sh\n"
                "file=\n"
                "for arg in \"$@\"; do file=$arg; done\n"
                "case \"$file\" in\n"
                "  *Keep*) printf 'oui\\n' ;;\n"
                "esac\n",
            )
            write_bin(
                bindir,
                "ffmpeg",
                "#!/bin/sh\n"
                "out=\n"
                "for arg in \"$@\"; do out=$arg; done\n"
                f"printf '%s\\n' \"$out\" >> {log}\n"
                "printf 'done' > \"$out\"\n",
            )
            env = os.environ.copy()
            env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
            env["MEDIA_ROOT"] = str(media)
            subprocess.run(["sh", str(SCRIPT)], check=True, env=env, cwd=root)
            self.assertEqual((rotation / "Keep - Me.mp3").read_bytes(), b"tagged")
            self.assertEqual((rotation / "Ada - Song.mp3").read_bytes(), b"done")
            self.assertFalse((bank / "Bea - Live.wav").exists())
            self.assertEqual((bank / "Bea - Live.flac").read_bytes(), b"done")
            called = log.read_text(encoding="utf-8")
            self.assertNotIn("Keep", called)
            self.assertIn(".Ada - Song.retag.mp3", called)
            self.assertIn(".Bea - Live.partial.flac", called)

    def test_dry_run_does_not_replace_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media = root / "media"
            rotation = media / "10-rotation"
            rotation.mkdir(parents=True)
            (rotation / "Ada - Song.wav").write_bytes(b"wav")
            env = os.environ.copy()
            env["MEDIA_ROOT"] = str(media)
            subprocess.run(["sh", str(SCRIPT), "--dry-run"], check=True, env=env, cwd=root)
            self.assertEqual((rotation / "Ada - Song.wav").read_bytes(), b"wav")
            self.assertFalse((rotation / "Ada - Song.flac").exists())


if __name__ == "__main__":
    unittest.main()
