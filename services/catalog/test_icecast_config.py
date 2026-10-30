"""python test_icecast_config.py — mots de passe et e-mail tels quels dans icecast.xml."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ICECAST = Path(__file__).resolve().parents[1] / "icecast"
SCRIPT = ICECAST / "docker-entrypoint.sh"


def write_bin(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def start(root: Path, **values: str) -> list[str]:
    """Lance l'entrypoint avec un faux icecast2, et rend ses arguments."""
    bindir = root / "bin"
    bindir.mkdir()
    args = root / "icecast2.args"
    write_bin(bindir, "icecast2", f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{args}'\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("ICECAST_")}
    env.update(values)
    env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    env["ICECAST_TEMPLATE"] = str(ICECAST / "icecast.xml")
    env["ICECAST_CONFIG"] = str(root / "icecast.xml")
    subprocess.run(["sh", str(SCRIPT)], check=True, env=env)
    return args.read_text(encoding="utf-8").splitlines()


class IcecastConfigTest(unittest.TestCase):
    def test_passwords_and_email_arrive_as_typed(self) -> None:
        # Le playout envoie le mot de passe brut : Icecast doit lire le même.
        source = r'Ab3&Kx9\n<"$HOME">&amp;'
        admin = r"pa\\ss\&$1`id`'%s"
        email = "Radio & Co <contact@radio.example>"
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            args = start(
                root,
                ICECAST_SOURCE_PASSWORD=source,
                ICECAST_ADMIN_PASSWORD=admin,
                ICECAST_ADMIN_EMAIL=email,
            )
            config = root / "icecast.xml"
            self.assertEqual(args, ["-c", str(config)])
            tree = ET.parse(config)
        self.assertEqual(tree.findtext("authentication/source-password"), source)
        self.assertEqual(tree.findtext("authentication/relay-password"), source)
        self.assertEqual(tree.findtext("authentication/admin-password"), admin)
        self.assertEqual(tree.findtext("admin"), email)

    def test_defaults_fill_every_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            start(root)
            text = (root / "icecast.xml").read_text(encoding="utf-8")
        self.assertNotIn("__ICECAST_", text)
        config = ET.fromstring(text)
        self.assertEqual(config.findtext("authentication/source-password"), "buttonhackme")
        self.assertEqual(config.findtext("authentication/admin-password"), "buttonadmin")
        self.assertEqual(config.findtext("admin"), "admin@localhost")


if __name__ == "__main__":
    unittest.main()
