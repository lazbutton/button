"""python test_init_secrets.py — radiotomate-init refuse les secrets d'exemple (SEC-06)."""

from __future__ import annotations

import os
import secrets
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
SCRIPT = DEPLOY / "scripts" / "init-radiotomate.sh"
MACHINE_SECRETS = (
    "ICECAST_SOURCE_PASSWORD",
    "ICECAST_ADMIN_PASSWORD",
    "RT_NOWPLAYING_SECRET",
    "MEILI_MASTER_KEY",
)
# Le script appelle le moteur juste après le contrôle : un appel prouve que le
# contrôle est passé, et le code de sortie arrête le script là.
FAKE_RADIOTOMATE = '#!/bin/sh\necho "$@" > "$(dirname "$0")/appel"\nexit 3\n'


def example_secrets() -> dict[str, str]:
    """Chaque variable que .env.example laisse à change-me."""
    lines = (DEPLOY / ".env.example").read_text(encoding="utf-8").splitlines()
    values = dict(line.split("=", 1) for line in lines if "=" in line and line[0] != "#")
    return {name: value for name, value in values.items() if value == "change-me"}


def strong_secrets() -> dict[str, str]:
    strong = {name: secrets.token_hex(24) for name in example_secrets()}
    # Tapé par quelqu'un : pas de longueur minimale.
    return {**strong, "RT_ADMIN_PASSWORD": "court"}


class InitSecretsTest(unittest.TestCase):
    def setUp(self) -> None:
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        self.root = Path(raw.name)
        self.bindir = self.root / "bin"
        self.bindir.mkdir()
        fake = self.bindir / "radiotomate"
        fake.write_text(FAKE_RADIOTOMATE, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    def init(self, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        (self.bindir / "appel").unlink(missing_ok=True)
        return subprocess.run(
            ["sh", str(SCRIPT)],
            env={
                "PATH": f"{self.bindir}{os.pathsep}{os.environ.get('PATH', '')}",
                "RADIOTOMATE_DATA": str(self.root / "data"),
                "MEDIA_ROOT": str(self.root / "media"),
                **env,
            },
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    def engine_called(self) -> bool:
        return (self.bindir / "appel").exists()

    def existing_station(self) -> None:
        (self.root / "data").mkdir()
        (self.root / "data" / "radiotomate.db").touch()

    def test_example_secrets_are_refused(self) -> None:
        values = example_secrets()
        self.assertTrue(set(MACHINE_SECRETS) | {"RT_ADMIN_PASSWORD"} <= set(values))

        result = self.init(values)

        self.assertEqual(result.returncode, 1)
        for name in values:
            self.assertIn(f"{name} : vaut change-me", result.stderr)
        self.assertIn("openssl rand -hex 24", result.stderr)
        self.assertIn("docker compose up -d --force-recreate", result.stderr)
        # Refusé avant tout : ni dossier, ni installation, ni migration.
        self.assertFalse((self.root / "data").exists())
        self.assertFalse(self.engine_called())

    def test_strong_secrets_pass(self) -> None:
        result = self.init(strong_secrets())

        self.assertTrue(self.engine_called(), result.stderr)
        self.assertNotIn("refusés", result.stderr)
        self.assertNotIn("Attention", result.stderr)

    def test_machine_secret_needs_24_characters(self) -> None:
        for name in MACHINE_SECRETS:
            with self.subTest(name=name):
                short = secrets.token_hex(12)[:23]

                refused = self.init({**strong_secrets(), name: short})

                self.assertEqual(refused.returncode, 1)
                self.assertIn(f"{name} : 23 caractères, il en faut 24", refused.stderr)
                named = [other for other in example_secrets() if other in refused.stderr]
                self.assertEqual(named, [name])
                self.assertIn("RT_ALLOW_SHORT_SECRETS=1", refused.stderr)
                self.assertNotIn(short, refused.stderr)
                self.assertFalse(self.engine_called())

                passed = self.init({**strong_secrets(), name: f"{short}0"})
                self.assertTrue(self.engine_called(), passed.stderr)

    def test_check_only_stops_after_the_check(self) -> None:
        passed = self.init({**strong_secrets(), "RT_INIT_CHECK_ONLY": "1"})

        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertIn("rien ne bloque le démarrage", passed.stdout)
        # Ni dossier, ni moteur : la station en service ne voit rien.
        self.assertFalse((self.root / "data").exists())
        self.assertFalse(self.engine_called())

        refused = self.init({**example_secrets(), "RT_INIT_CHECK_ONLY": "1"})
        self.assertEqual(refused.returncode, 1)
        self.assertIn("ICECAST_SOURCE_PASSWORD : vaut change-me", refused.stderr)

    def test_length_counts_characters_not_bytes(self) -> None:
        # 23 « é » font 46 octets : dash les compterait comme 46.
        refused = self.init({**strong_secrets(), "ICECAST_ADMIN_PASSWORD": "é" * 23})

        self.assertEqual(refused.returncode, 1)
        self.assertIn("ICECAST_ADMIN_PASSWORD : 23 caractères", refused.stderr)

        passed = self.init({**strong_secrets(), "ICECAST_ADMIN_PASSWORD": "é" * 24})
        self.assertTrue(self.engine_called(), passed.stderr)

    def test_switch_lets_a_short_secret_through_with_a_warning(self) -> None:
        short = "0123456789abcdef"
        values = {**strong_secrets(), "MEILI_MASTER_KEY": short}

        result = self.init({**values, "RT_ALLOW_SHORT_SECRETS": "1"})

        self.assertTrue(self.engine_called(), result.stderr)
        self.assertIn("Attention", result.stderr)
        self.assertIn("MEILI_MASTER_KEY : 16 caractères", result.stderr)
        self.assertNotIn(short, result.stderr)

    def test_switch_never_lets_an_example_secret_through(self) -> None:
        for value in ("", "change-me"):
            with self.subTest(value=value):
                values = {**strong_secrets(), "ICECAST_SOURCE_PASSWORD": value}

                result = self.init({**values, "RT_ALLOW_SHORT_SECRETS": "1"})

                self.assertEqual(result.returncode, 1)
                self.assertIn("ICECAST_SOURCE_PASSWORD : ", result.stderr)
                self.assertFalse(self.engine_called())

    def test_empty_admin_password_is_refused_on_first_install_only(self) -> None:
        values = {**strong_secrets(), "RT_ADMIN_PASSWORD": ""}

        first = self.init(values)

        self.assertEqual(first.returncode, 1)
        self.assertIn("RT_ADMIN_PASSWORD : vide", first.stderr)
        self.assertFalse(self.engine_called())

        # Vidé après le premier démarrage : la base existe, aucun compte à créer.
        self.existing_station()
        later = self.init(values)
        self.assertTrue(self.engine_called(), later.stderr)

    def test_admin_example_password_is_refused_on_an_existing_station(self) -> None:
        self.existing_station()

        result = self.init({**strong_secrets(), "RT_ADMIN_PASSWORD": "change-me"})

        self.assertEqual(result.returncode, 1)
        # Le compte peut l'avoir encore : le journal dit où le changer.
        self.assertIn("Mon compte", result.stderr)
        # Seul radiotomate-init lit ce mot de passe : le relancer suffit.
        self.assertIn("lancer : docker compose up -d (", result.stderr)
        self.assertFalse(self.engine_called())


if __name__ == "__main__":
    unittest.main()
