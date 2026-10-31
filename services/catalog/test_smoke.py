"""python test_smoke.py — le contrôle après déploiement (MAJ-03), sans station.

Un faux docker répond pour les services du moteur. Un petit serveur HTTP joue la
console, le flux, et l'intérieur des conteneurs que joint docker compose exec.
"""

from __future__ import annotations

import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "smoke.sh"
ENGINE = ("radiotomate-playout", "radiotomate-interface", "radiotomate-scheduler")
PS = ["compose", "ps", "--format", "{{.Service}} {{.State}} {{.Health}}"]
# Une station saine, dans l'ordre où le contrôle la lit : chemin, puis code,
# type et corps. Sous /<service>/, l'intérieur d'un conteneur.
HEALTHY = {
    "/": (200, "text/html", b"<!doctype html><title>BUTTON</title>"),
    "/health/ready": (200, "application/json", b'{"ready": true, "db": true}'),
    "/radiotomate-scheduler/health/ready": (200, "application/json", b'{"ready": true}'),
    "/library/search?q=a": (401, "text/html", b"<h1>401 Authorization Required</h1>"),
    "/button.mp3": (200, "audio/mpeg", bytes(64 * 1024)),
    "/nowplaying/now.json": (200, "application/json", b'{"title": "Jingle station"}'),
}


def write_bin(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def closed_port() -> int:
    """Un port de 127.0.0.1 où rien n'écoute."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fake_docker(bindir: Path, args: list[str]) -> int:
    """Le faux docker : compose ps et compose exec, réglés par docker.json."""
    with (bindir / "docker.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    settings = bindir / "docker.json"
    docker = json.loads(settings.read_text(encoding="utf-8"))
    if args[: len(PS)] == PS:
        if docker["ps_error"]:
            print(docker["ps_error"], file=sys.stderr)
            return 1
        for service in args[len(PS) :]:
            states = docker["ps"][service]
            # Arrêté, un service n'a pas de ligne. Une suite d'états se lit un
            # par appel, et le dernier reste.
            if states:
                print(f"{service} {states.pop(0) if len(states) > 1 else states[0]}")
        settings.write_text(json.dumps(docker), encoding="utf-8")
        return 0
    if args[:3] == ["compose", "exec", "-T"]:
        service, command = args[3], args[4:]
        if service in docker["stopped"]:
            print(f'service "{service}" is not running', file=sys.stderr)
            return 1
        # Le 127.0.0.1 d'un conteneur : le serveur du test, sous /<service>.
        url = re.sub(r"^http://127\.0\.0\.1:\d+", f"{docker['station']}/{service}", command[-1])
        python = sys.executable if command[0] == "python3" else command[0]
        return subprocess.run([python, *command[1:-1], url], check=False).returncode
    print(f"faux docker, appel inattendu : {args}", file=sys.stderr)
    return 2


class Station(BaseHTTPRequestHandler):
    """La console, le flux et l'intérieur des conteneurs, sur un seul port."""

    # Un corps None : un flux sans fin, comme celui d'Icecast.
    routes: dict[str, tuple[int, str, bytes | None]] = {}
    seen: list[str] = []
    cookies: list[str] = []

    def do_GET(self) -> None:  # noqa: N802
        Station.seen.append(self.path)
        if "Cookie" in self.headers:
            Station.cookies.append(self.headers["Cookie"])
        status, kind, body = Station.routes.get(self.path, (404, "text/plain", b"introuvable"))
        self.send_response(status)
        self.send_header("Content-Type", kind)
        if body is None:
            self.end_headers()
            try:
                while True:
                    self.wfile.write(bytes(4096))
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError):
                return
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


class SmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Station)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.station = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        self.root = Path(raw.name)
        self.bindir = self.root / "bin"
        self.bindir.mkdir()
        here = Path(__file__).resolve()
        write_bin(
            self.bindir,
            "docker",
            f'#!/bin/sh\nexec "{sys.executable}" "{here}" docker "{self.bindir}" "$@"\n',
        )
        # Une pause est notée, et ne dure rien.
        write_bin(self.bindir, "sleep", f'#!/bin/sh\necho "$@" >> "{self.bindir}/pauses"\n')
        self.docker = {
            "station": self.station,
            "ps": {service: ["running healthy"] for service in ENGINE},
            "ps_error": "",
            "stopped": [],
        }
        Station.routes = dict(HEALTHY)

    def smoke(self, console: str = "", **env: str) -> subprocess.CompletedProcess[str]:
        """Le contrôle, lancé depuis un dossier de station, avec les faux docker et sleep."""
        (self.bindir / "docker.json").write_text(json.dumps(self.docker), encoding="utf-8")
        for log in ("docker.log", "pauses"):
            (self.bindir / log).unlink(missing_ok=True)
        Station.seen.clear()
        Station.cookies.clear()
        return subprocess.run(
            ["bash", str(SCRIPT), console or self.station, f"{self.station}/button.mp3"],
            cwd=self.root,
            env={"PATH": f"{self.bindir}{os.pathsep}{os.environ.get('PATH', '')}", **env},
            capture_output=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )

    def docker_calls(self) -> list[list[str]]:
        lines = (self.bindir / "docker.log").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def pauses(self) -> list[str]:
        pauses = self.bindir / "pauses"
        return pauses.read_text(encoding="utf-8").splitlines() if pauses.exists() else []

    def read_until(self, path: str) -> list[str]:
        """Les adresses que lit le contrôle, dans l'ordre, jusqu'à celle-ci comprise."""
        paths = list(HEALTHY)
        return paths[: paths.index(path) + 1]

    def assert_fails_at(
        self, result: subprocess.CompletedProcess[str], point: str, *details: str
    ) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(f"Échec au point {point}.", result.stderr)
        for detail in details:
            self.assertIn(detail, result.stderr)
        self.assertNotIn("Contrôle réussi", result.stdout)

    def test_a_healthy_station_passes(self) -> None:
        result = self.smoke()

        self.assertEqual(result.returncode, 0, result.stderr)
        for point in ("1. Moteur", "2. Console", "3. Scheduler", "4. Catalogue", "5. Flux"):
            self.assertIn(point, result.stdout)
        self.assertIn("Contrôle réussi", result.stdout)
        # Les cinq points dans l'ordre, sans cookie, et sans attendre.
        self.assertEqual(Station.seen, list(HEALTHY))
        self.assertEqual(Station.cookies, [])
        self.assertEqual(self.pauses(), [])
        # Le scheduler et nowplaying, lus de l'intérieur, à leur adresse.
        calls = self.docker_calls()
        self.assertEqual(calls[0], PS + list(ENGINE))
        self.assertEqual(
            [(call[3], call[-1]) for call in calls if call[1] == "exec"],
            [
                ("radiotomate-scheduler", "http://127.0.0.1:6822/health/ready"),
                ("nowplaying", "http://127.0.0.1:6820/now.json"),
            ],
        )

    def test_an_endless_stream_is_read_for_5_s(self) -> None:
        # Icecast ne finit jamais sa réponse : curl coupe au bout de 5 s, et ce
        # qu'il a lu compte.
        Station.routes["/button.mp3"] = (200, "audio/mpeg", None)

        result = self.smoke()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("5. Flux : de l'audio (audio/mpeg, ", result.stdout)
        self.assertEqual(Station.seen, list(HEALTHY))

    def test_an_ogg_stream_is_audio_too(self) -> None:
        Station.routes["/button.mp3"] = (200, "application/ogg", bytes(64 * 1024))

        result = self.smoke()

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_waits_for_the_engine(self) -> None:
        self.docker["ps"]["radiotomate-interface"] = ["restarting ", "running healthy"]
        self.docker["ps"]["radiotomate-scheduler"] = [
            "running starting",
            "running starting",
            "running healthy",
        ]

        result = self.smoke()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("attente de la santé, 120 s au plus"), 1)
        self.assertIn(
            "radiotomate-interface (restarting), radiotomate-scheduler (starting)", result.stdout
        )
        self.assertEqual(self.pauses(), ["5", "5"])

    def test_an_unhealthy_engine_fails_after_the_wait(self) -> None:
        self.docker["ps"]["radiotomate-scheduler"] = ["running unhealthy"]

        result = self.smoke(SMOKE_WAIT="0")

        self.assert_fails_at(
            result,
            "1, moteur",
            "au bout de 0 s : radiotomate-scheduler (unhealthy)",
            "docker compose logs --since 10m radiotomate-scheduler",
        )
        self.assertEqual(self.pauses(), [])
        self.assertEqual(Station.seen, [])

    def test_the_wait_ends_on_time(self) -> None:
        # Le temps passe pour de vrai, mais les pauses ne durent rien : la
        # dernière ne dépasse jamais ce qui reste à attendre.
        self.docker["ps"]["radiotomate-scheduler"] = ["running starting"]

        result = self.smoke(SMOKE_WAIT="2")

        self.assert_fails_at(
            result, "1, moteur", "au bout de 2 s : radiotomate-scheduler (starting)"
        )
        self.assertTrue(self.pauses())
        self.assertLessEqual(set(self.pauses()), {"1", "2"})

    def test_a_stopped_engine_fails_at_once(self) -> None:
        # Arrêté, il n'a pas de ligne dans docker compose ps : rien à attendre.
        self.docker["ps"]["radiotomate-playout"] = []

        result = self.smoke()

        self.assert_fails_at(
            result,
            "1, moteur",
            "À l'arrêt : radiotomate-playout.",
            "docker compose logs radiotomate-init radiotomate-playout",
        )
        self.assertEqual(self.pauses(), [])
        self.assertEqual(Station.seen, [])

    def test_a_playout_never_healthy_is_named_too(self) -> None:
        # docker compose up -d n'a pas démarré l'interface ni le scheduler, qui
        # attendent un playout en bonne santé : la cause est dans le message.
        self.docker["ps"] = {
            "radiotomate-playout": ["running unhealthy"],
            "radiotomate-interface": [],
            "radiotomate-scheduler": [],
        }

        result = self.smoke()

        self.assert_fails_at(
            result,
            "1, moteur",
            "À l'arrêt : radiotomate-interface, radiotomate-scheduler. "
            "Pas en bonne santé : radiotomate-playout (unhealthy).",
        )
        self.assertEqual(self.pauses(), [])

    def test_docker_compose_must_answer(self) -> None:
        self.docker["ps_error"] = "no configuration file provided: not found"

        result = self.smoke()

        self.assert_fails_at(
            result, "1, moteur", "no configuration file provided", "dossier de la station"
        )
        self.assertEqual(Station.seen, [])

    def test_the_console_must_answer_200(self) -> None:
        for path, status in (("/", 502), ("/health/ready", 503)):
            with self.subTest(path=path):
                Station.routes = {**HEALTHY, path: (status, "text/html", b"<h1>Erreur</h1>")}

                result = self.smoke()

                self.assert_fails_at(
                    result, "2, console", f"{self.station}{path} répond {status}, il faut 200"
                )
                self.assertEqual(Station.seen, self.read_until(path))

    def test_an_unreachable_console_says_why(self) -> None:
        result = self.smoke(console=f"http://127.0.0.1:{closed_port()}")

        self.assert_fails_at(result, "2, console", "ne répond pas (", "il faut 200")
        self.assertEqual(Station.seen, [])

    def test_the_scheduler_must_be_ready(self) -> None:
        not_ready = b'{"ready": false, "db": true, "playout": false}'
        Station.routes["/radiotomate-scheduler/health/ready"] = (503, "application/json", not_ready)

        result = self.smoke()

        # Sa réponse dit ce qui manque.
        self.assert_fails_at(result, "3, scheduler", "503", '"playout": false')
        self.assertEqual(Station.seen, self.read_until("/radiotomate-scheduler/health/ready"))

    def test_the_library_must_refuse_without_cookie(self) -> None:
        Station.routes["/library/search?q=a"] = (200, "application/json", b'{"hits": []}')

        result = self.smoke()

        self.assert_fails_at(result, "4, catalogue", "répond 200, il faut 401")
        self.assertEqual(Station.seen, self.read_until("/library/search?q=a"))

    def test_the_stream_must_send_audio(self) -> None:
        streams = {
            # Icecast, quand le playout ne lui envoie rien.
            "répond 404, il faut 200": (404, "text/html", b"<b>Source does not exist</b>"),
            "répond en text/html, pas en audio": (200, "text/html", bytes(64 * 1024)),
            "n'a envoyé que 1024 octets": (200, "audio/mpeg", bytes(1024)),
        }
        for detail, stream in streams.items():
            with self.subTest(detail=detail):
                Station.routes = {**HEALTHY, "/button.mp3": stream}

                result = self.smoke()

                self.assert_fails_at(result, "5, flux", detail)
                self.assertEqual(Station.seen, self.read_until("/button.mp3"))

    def test_now_json_must_answer(self) -> None:
        with self.subTest("nowplaying arrêté"):
            self.docker["stopped"] = ["nowplaying"]

            result = self.smoke()

            self.assert_fails_at(
                result, "5, flux", "now.json ne répond pas 200", '"nowplaying" is not running'
            )
            self.assertEqual(Station.seen, self.read_until("/button.mp3"))
        with self.subTest("now.json en erreur"):
            self.docker["stopped"] = []
            Station.routes["/nowplaying/now.json"] = (500, "text/plain", b"disque plein")

            result = self.smoke()

            self.assert_fails_at(result, "5, flux", "now.json ne répond pas 200", "500")
            self.assertEqual(Station.seen, list(HEALTHY))

    def test_needs_two_addresses_and_a_wait_in_seconds(self) -> None:
        missing = subprocess.run(
            ["bash", str(SCRIPT), self.station], capture_output=True, encoding="utf-8", check=False
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("usage: smoke.sh CONSOLE_URL STREAM_URL", missing.stderr)

        result = self.smoke(SMOKE_WAIT="deux minutes")
        self.assertEqual(result.returncode, 2)
        self.assertIn("SMOKE_WAIT", result.stderr)
        self.assertFalse((self.bindir / "docker.log").exists())


if __name__ == "__main__":
    # Le faux docker, posé par setUp, rappelle ce fichier.
    if sys.argv[1:2] == ["docker"]:
        sys.exit(fake_docker(Path(sys.argv[2]), sys.argv[3:]))
    unittest.main()
