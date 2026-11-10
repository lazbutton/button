"""python test_compose.py — le premier `docker compose up` d'une station neuve démarre tout."""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
INIT = "radiotomate-init"


def compose_config() -> dict:
    """compose.yml tel que Docker le lit, avec .env.example et tous les profils."""
    command = ["docker", "compose", "--env-file", ".env.example", "-f", "compose.yml"]
    for profile in ("share", "cloud", "vps"):
        command += ["--profile", profile]
    result = subprocess.run(
        [*command, "config", "--format", "json"],
        cwd=DEPLOY,
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(result.stdout)


@unittest.skipUnless(shutil.which("docker"), "docker absent")
class ComposeTest(unittest.TestCase):
    def test_who_mounts_the_engine_yaml_waits_for_init(self) -> None:
        # radiotomate-init écrit radiotomate.yaml. Un service qui monte le
        # fichier avant lui fait créer par Docker un dossier à sa place, et le
        # premier `docker compose up` d'une station neuve échoue.
        services = compose_config()["services"]
        mounting = [
            name
            for name, service in services.items()
            if name != INIT
            and any(
                Path(volume.get("source", "")).name == "radiotomate.yaml"
                for volume in service.get("volumes", [])
            )
        ]
        self.assertIn("catalog", mounting)
        self.assertIn("nowplaying", mounting)
        for name in mounting:
            with self.subTest(service=name):
                condition = services[name].get("depends_on", {}).get(INIT, {}).get("condition")
                self.assertEqual(condition, "service_completed_successfully")


if __name__ == "__main__":
    unittest.main()
