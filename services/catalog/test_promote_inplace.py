"""python test_promote_inplace.py — tags et flac sans quitter le dossier."""

from __future__ import annotations

import json
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


# Un faux ffprobe qui lit les tags de chaque fichier dans TAGS, un JSON :
# {"nom": {"format": {...}, "streams": [{"type": "audio", "tags": {...}}]}}.
# Comme le vrai, -select_streams a:0 ne garde que le premier flux audio.
FAKE_FFPROBE = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
section, key = args[args.index("-show_entries") + 1].split("=")
info = json.load(open(os.environ["TAGS"])).get(os.path.basename(args[-1]), {})
if section == "format_tags":
    tags = [info.get("format", {})]
else:
    streams = info.get("streams", [])
    if "-select_streams" in args:
        streams = [s for s in streams if s["type"] == "audio"][:1]
    tags = [s.get("tags", {}) for s in streams]
for found in tags:
    for name, value in found.items():
        if name.lower() == key:
            print(value)
"""

# Un faux ffmpeg qui note ses arguments, une ligne JSON par appel, et échoue
# sur un fichier dont le nom commence par « Faux », en laissant une moitié.
FAKE_FFMPEG = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FFMPEG_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
source = args[args.index("-i") + 1]
if os.path.basename(source).startswith("Faux"):
    sys.stderr.write("Invalid data found when processing input\\n")
    open(args[-1], "w").write("moitié")
    sys.exit(1)
open(args[-1], "w").write("done")
"""


class Bench:
    """Une banque temporaire, avec de faux ffprobe et ffmpeg."""

    def __init__(self, root: Path, tags: dict | None = None) -> None:
        self.root = root
        self.media = root / "media"
        self.media.mkdir()
        self.bindir = root / "bin"
        self.bindir.mkdir()
        write_bin(self.bindir, "ffprobe", FAKE_FFPROBE)
        write_bin(self.bindir, "ffmpeg", FAKE_FFMPEG)
        (root / "tags.json").write_text(json.dumps(tags or {}), encoding="utf-8")
        self.log = root / "ffmpeg.log"
        self.env = os.environ.copy()
        self.env.update(
            PATH=f"{self.bindir}{os.pathsep}{self.env.get('PATH', '')}",
            MEDIA_ROOT=str(self.media),
            TAGS=str(root / "tags.json"),
            FFMPEG_LOG=str(self.log),
            PROMOTE_SETTLE="0",
        )

    def put(self, relative: str, body: bytes = b"audio") -> Path:
        path = self.media / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(SCRIPT)], env=self.env, cwd=self.root, capture_output=True, text=True
        )

    def outputs(self) -> list[str]:
        """Le fichier écrit par chaque appel à ffmpeg, par son nom."""
        if not self.log.exists():
            return []
        lines = self.log.read_text(encoding="utf-8").splitlines()
        return [Path(json.loads(line)[-1]).name for line in lines]

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]


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
            self.assertIn(".Ada - Song.partial.mp3", called)
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

    def test_upper_case_extensions_are_lowered(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media = root / "media"
            inbox = media / "00-inbox" / "rotation"
            rotation = media / "10-rotation"
            inbox.mkdir(parents=True)
            rotation.mkdir(parents=True)
            (inbox / "Eve - Hit.FLAC").write_bytes(b"flac")
            (rotation / "Cy - Tune.WAV").write_bytes(b"wav")
            bindir = root / "bin"
            bindir.mkdir()
            write_bin(bindir, "ffprobe", "#!/bin/sh\n")
            write_bin(
                bindir,
                "ffmpeg",
                "#!/bin/sh\n"
                "out=\n"
                "for arg in \"$@\"; do out=$arg; done\n"
                "printf 'done' > \"$out\"\n",
            )
            env = os.environ.copy()
            env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
            env["MEDIA_ROOT"] = str(media)
            subprocess.run(["sh", str(SCRIPT)], check=True, env=env, cwd=root)
            # Les noms, pas exists() : le disque du Mac ignore la casse.
            self.assertEqual(
                sorted(path.name for path in rotation.iterdir()),
                ["Cy - Tune.flac", "Eve - Hit.flac"],
            )
            self.assertEqual(
                [path.name for path in (media / "00-inbox" / "_sources").iterdir()],
                ["Eve - Hit.FLAC"],
            )


class RewriteOnlyToAddTest(unittest.TestCase):
    """Un fichier n'est réécrit que si la réécriture lui ajoute un tag."""

    # Opus et Ogg n'ont rien au niveau du fichier : les tags sont dans le flux.
    # La pochette passe avant le flux audio, avec son propre title.
    TAGS = {
        "Ada - Song.opus": {
            "streams": [
                {"type": "video", "tags": {"title": "Cover"}},
                {"type": "audio", "tags": {"ARTIST": "Ada", "TITLE": "Song"}},
            ]
        },
        "Cy - Tune.opus": {
            "streams": [
                {"type": "video", "tags": {"title": "Cover"}},
                {"type": "audio", "tags": {"artist": "Cyril"}},
            ]
        },
        "Untitled.mp3": {"format": {"title": "Untitled"}},
        "Dee - Hit.ogg": {"streams": [{"type": "audio", "tags": {"artist": "Dee", "title": "Hit"}}]},
    }

    def test_stream_tags_count_and_a_name_without_artist_adds_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bench = Bench(Path(raw), self.TAGS)
            tagged = bench.put("10-rotation/Ada - Song.opus", b"opus")
            bare = bench.put("10-rotation/Untitled.mp3", b"mp3")
            inbox = bench.put("00-inbox/rotation/Dee - Hit.ogg", b"ogg")
            for _ in range(2):
                result = bench.run()
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(tagged.read_bytes(), b"opus")
            self.assertEqual(bare.read_bytes(), b"mp3")
            # Déjà tagué : déplacé tel quel, sans copie dans _sources.
            self.assertFalse(inbox.exists())
            self.assertEqual((bench.media / "10-rotation" / "Dee - Hit.ogg").read_bytes(), b"ogg")
            self.assertEqual(list((bench.media / "00-inbox" / "_sources").glob("*")), [])
            self.assertEqual(bench.calls(), [])

    def test_the_title_comes_from_the_first_audio_stream_not_the_cover(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bench = Bench(Path(raw), self.TAGS)
            bench.put("10-rotation/Cy - Tune.opus", b"opus")
            result = bench.run()
            self.assertEqual(result.returncode, 0, result.stderr)
            [call] = bench.calls()
            # L'artiste du flux audio, pas celui du nom ; le titre du nom, pas celui de la pochette.
            self.assertIn("artist=Cyril", call)
            self.assertIn("title=Tune", call)


class UnreadableFileTest(unittest.TestCase):
    """Un fichier que ffmpeg ne lit pas est sauté ; le passage continue."""

    def assert_skipped(self, result: subprocess.CompletedProcess[str], name: str) -> None:
        # Le passage va au bout, puis dit qu'un fichier est resté.
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(f"illisible : {name}", result.stderr)
        self.assertIn("le remplacer", result.stderr)
        self.assertIn("promotion :", result.stdout)

    def test_a_bad_file_in_one_bank_leaves_the_others_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bench = Bench(Path(raw))
            bad = bench.put("20-archives/a/Faux - Mp3.mp3", b"bad")
            bench.put("20-archives/b/.keep", b"")
            inbox = bench.put("00-inbox/archives/b/Bob - Ok.mp3", b"mp3")
            result = bench.run()
            self.assert_skipped(result, "Faux - Mp3.mp3")
            self.assertEqual(bad.read_bytes(), b"bad")
            self.assertFalse(inbox.exists())
            self.assertEqual((bench.media / "20-archives" / "b" / "Bob - Ok.mp3").read_bytes(), b"done")
            self.assertEqual(sorted(p.name for p in (bench.media / "20-archives" / "a").iterdir()), ["Faux - Mp3.mp3"])

    def test_a_bad_inbox_file_stays_in_the_inbox_without_a_half_target(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bench = Bench(Path(raw))
            bad_wav = bench.put("00-inbox/rotation/Faux - Live.wav", b"bad")
            bad_mp3 = bench.put("00-inbox/rotation/Faux - Song.mp3", b"bad")
            bench.put("00-inbox/rotation/Gus - Calm.wav", b"wav")
            result = bench.run()
            self.assert_skipped(result, "Faux - Live.wav")
            self.assert_skipped(result, "Faux - Song.mp3")
            self.assertEqual(bad_wav.read_bytes(), b"bad")
            self.assertEqual(bad_mp3.read_bytes(), b"bad")
            # Rien de Faux dans la rotation, ni moitié de fichier, ni copie cachée.
            self.assertEqual(sorted(p.name for p in (bench.media / "10-rotation").iterdir()), ["Gus - Calm.flac"])

    def test_a_bad_file_is_skipped_when_reencoding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            bench = Bench(Path(raw))
            bench.env["BROADCAST_CODEC"] = "opus"
            bad = bench.put("00-inbox/rotation/Faux - Song.mp3", b"bad")
            bench.put("00-inbox/rotation/Gus - Calm.mp3", b"mp3")
            result = bench.run()
            self.assert_skipped(result, "Faux - Song.mp3")
            self.assertEqual(bad.read_bytes(), b"bad")
            self.assertEqual(sorted(p.name for p in (bench.media / "10-rotation").iterdir()), ["Gus - Calm.opus"])


if __name__ == "__main__":
    unittest.main()
