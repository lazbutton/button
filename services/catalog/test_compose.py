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


def volume_at(service: dict, target: str) -> str | None:
    """Ce qui est monté à ``target`` dans le service : un volume nommé, ou un chemin."""
    return next((v["source"] for v in service.get("volumes", []) if v["target"] == target), None)


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

        upload_dir = next(arg.split("=", 1)[1] for arg in tusd["command"] if arg.startswith("-upload-dir="))
        self.assertEqual(volume_at(tusd, upload_dir), "tusd-data")
        self.assertEqual(volume_at(catalog, environment["TUSD_DIR"]), "tusd-data")

    def test_the_catalog_opens_the_share_volume_to_the_beets_loop(self) -> None:
        # Le volume naît à root, et la boucle Beets du moteur, qui y écrit les
        # rôles du dossier partagé, ne tourne pas en root : le catalogue, en
        # root, l'ouvre au démarrage. Sinon, l'export échoue à chaque tour.
        services = compose_config()["services"]
        catalog, loop, share = services["catalog"], services["radiotomate-dropbox"], services["share"]
        self.assertEqual(catalog["user"], "0:0")
        self.assertEqual(volume_at(catalog, catalog["environment"]["SHARE_PRIVATE"]), "share-private")
        # export_share_roles.py écrit dans SHARE_PRIVATE, /share-private sans lui.
        roles_dir = loop["environment"].get("SHARE_PRIVATE", "/share-private")
        self.assertEqual(volume_at(loop, roles_dir), "share-private")
        self.assertEqual(volume_at(share, share["environment"]["SHARE_PRIVATE"]), "share-private")


if __name__ == "__main__":
    unittest.main()
