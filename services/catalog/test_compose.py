"""python test_compose.py — compose.yml tel que Docker le lit.

Le premier `docker compose up` d'une station neuve démarre tout, et l'ancien
RT_TAG, posé, arrête docker compose. COMPOSE_IMAGE=<image de Docker> lit le
fichier avec le Compose de cette image, au lieu de celui de la machine : la CI
y passe Compose v2, qu'une station peut avoir encore (services.yml).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
INIT = "radiotomate-init"
IMAGE = os.environ.get("COMPOSE_IMAGE", "")


def compose(*args: str, rt_tag: str | None = None) -> subprocess.CompletedProcess[str]:
    """docker compose sur compose.yml, avec .env.example et tous les profils.
    RT_TAG vaut rt_tag, ou n'est pas posé, quel que soit le shell."""
    env = {name: value for name, value in os.environ.items() if name != "RT_TAG"}
    if rt_tag is not None:
        env["RT_TAG"] = rt_tag
    command = ["docker", "compose"]
    if IMAGE:
        # -e RT_TAG passe la variable au conteneur si elle est posée, même vide.
        command = ["docker", "run", "--rm", "-e", "RT_TAG", "-v", f"{DEPLOY}:/w:ro", "-w", "/w", IMAGE, *command]
    command += ["--env-file", ".env.example", "-f", "compose.yml"]
    for profile in ("share", "cloud", "vps"):
        command += ["--profile", profile]
    return subprocess.run([*command, *args], cwd=DEPLOY, env=env, capture_output=True, encoding="utf-8", check=False)


def compose_config() -> dict:
    """compose.yml tel que Docker le lit, avec .env.example et tous les profils."""
    result = compose("config", "--format", "json")
    if result.returncode != 0:
        raise AssertionError(f"docker compose config échoue : {result.stderr}")
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

    def test_init_gets_the_alerts_of_env(self) -> None:
        # station config règle ntfy et l'e-mail dans .env : radiotomate-init les
        # reçoit, avec le domaine qui nomme la station, et les écrit dans
        # radiotomate.yaml, que le scheduler relit. .env.example les dit.
        environment = compose_config()["services"][INIT]["environment"]
        script = (DEPLOY / "scripts" / "init-radiotomate.sh").read_text()
        example = (DEPLOY / ".env.example").read_text()
        suffixes = ("NTFY", "NTFY_TOKEN", "EMAIL", "FROM", "SMTP", "SMTP_USER", "SMTP_PASSWORD")
        for name in ["DOMAIN", *(f"BUTTON_ALERT_{suffix}" for suffix in suffixes)]:
            with self.subTest(variable=name):
                self.assertIn(name, environment)
                self.assertIn(f'"{name}"', script)
                self.assertIn(f"# {name}=", example)

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

    def test_rt_tag_stops_docker_compose(self) -> None:
        # RT_TAG n'est plus lu : posé, il arrête docker compose avant tout
        # changement, et dit quoi faire. Absent ou vide, il ne gêne rien :
        # Compose v2 évaluait l'ancien garde même sans RT_TAG, et refusait
        # alors toute commande.
        for rt_tag in (None, ""):
            with self.subTest(RT_TAG=rt_tag):
                result = compose("config", "--quiet", rt_tag=rt_tag)
                self.assertEqual(result.returncode, 0, result.stderr)
        # true : la phrase du garde ne se lit jamais comme un booléen.
        for rt_tag in ("20261015-abc1234", "true"):
            with self.subTest(RT_TAG=rt_tag):
                result = compose("config", "--quiet", rt_tag=rt_tag)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"RT_TAG={rt_tag} n'est plus lu. Le retirer de .env, et épingler la version par BUTTON_VERSION.",
                    result.stderr,
                )


if __name__ == "__main__":
    unittest.main()
