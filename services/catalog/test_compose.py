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

    def test_the_catalog_hands_the_uploads_volume_to_tusd(self) -> None:
        # Le volume naît à root, et tusd ne tourne pas en root : le catalogue,
        # en root, le donne à tusd au démarrage. Sinon, chaque envoi échoue.
        services = compose_config()["services"]
        tusd, catalog = services["tusd"], services["catalog"]
        environment = catalog["environment"]
        self.assertEqual(catalog["user"], "0:0")
        self.assertEqual(environment["TUSD_USER"], tusd["user"])

        def volume_at(service: dict, target: str) -> str | None:
            return next((v["source"] for v in service["volumes"] if v["target"] == target), None)

        upload_dir = next(arg.split("=", 1)[1] for arg in tusd["command"] if arg.startswith("-upload-dir="))
        self.assertEqual(volume_at(tusd, upload_dir), "tusd-data")
        self.assertEqual(volume_at(catalog, environment["TUSD_DIR"]), "tusd-data")


if __name__ == "__main__":
    unittest.main()
