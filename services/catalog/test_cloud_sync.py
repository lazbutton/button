"""python test_cloud_sync.py — le pont des bacs ouverts dans Dropbox (FON-15).

Un faux rclone joue Dropbox : le remote fake: est un dossier du test. La banque
temporaire a ses liens Carts/<id>-<titre>, absolus comme ceux du moteur.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "deploy" / "scripts" / "cloud-sync.sh"
MEDIA_BANK = REPO / "engine" / "radiotomate" / "services" / "media_bank.py"
LSF = ["lsf", "-R", "--format", "tsp", "--time-format", "unix", "--separator", "\t"]


def write_bin(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def fake_rclone(bindir: Path, args: list[str]) -> int:
    """Le faux rclone : listremotes, lsf et copyto, réglés par rclone.json."""
    with (bindir / "rclone.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    settings = json.loads((bindir / "rclone.json").read_text(encoding="utf-8"))
    remotes: dict[str, str] = settings["remotes"]

    def resolve(spec: str) -> Path:
        name, colon, rest = spec.partition(":")
        if colon and name in remotes:
            return Path(remotes[name]) / rest
        return Path(spec)

    if args == ["listremotes"]:
        for name in remotes:
            print(f"{name}:")
        return 0
    if args[:1] == ["cat"] and len(args) == 2:
        source = resolve(args[1])
        if not source.is_file():
            print("NOTICE: Failed to cat: directory not found", file=sys.stderr)
            return 3
        sys.stdout.buffer.write(source.read_bytes())
        return 0
    if args[:-1] == LSF:
        root = resolve(args[-1])
        if not root.is_dir():
            print("NOTICE: Failed to lsf: directory not found", file=sys.stderr)
            return 3
        lines = []
        for dirpath, dirnames, filenames in os.walk(root):
            for name in dirnames + filenames:
                path = Path(dirpath) / name
                rel = path.relative_to(root).as_posix()
                mtime = int(path.stat().st_mtime)
                if path.is_dir():
                    lines.append(f"{mtime}\t-1\t{rel}/")
                else:
                    lines.append(f"{mtime}\t{path.stat().st_size}\t{rel}")
        # rclone ne trie pas sa liste.
        for line in sorted(lines, reverse=True):
            print(line)
        return 0
    if args[:1] == ["copyto"]:
        flags = [arg for arg in args[1:] if arg.startswith("-")]
        paths = [arg for arg in args[1:] if not arg.startswith("-")]
        if set(flags) - {"--ignore-existing"} or len(paths) != 2:
            print(f"faux rclone, copyto inattendu : {args}", file=sys.stderr)
            return 2
        source, target = resolve(paths[0]), resolve(paths[1])
        if any(part in paths[0] for part in settings.get("fail", [])):
            # Comme rclone, le dossier de la copie est déjà créé.
            target.parent.mkdir(parents=True, exist_ok=True)
            print("NOTICE: Failed to copyto: disque plein", file=sys.stderr)
            return 1
        if any(part in paths[0] for part in settings.get("slow", [])):
            # Une longue copie : le test l'arrête, comme docker stop.
            def stopped(_signum, _frame) -> None:
                (bindir / "arrete").write_text("TERM", encoding="utf-8")
                sys.exit(143)

            signal.signal(signal.SIGTERM, stopped)
            (bindir / "copie-en-cours").write_text(paths[0], encoding="utf-8")
            time.sleep(30)
            return 0
        if not source.is_file():
            print("NOTICE: Failed to copyto: directory not found", file=sys.stderr)
            return 3
        if "--ignore-existing" in flags and target.exists():
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".0a1b2c3d.partial")
        shutil.copy2(source, partial)
        partial.replace(target)
        return 0
    print(f"faux rclone, appel inattendu : {args}", file=sys.stderr)
    return 2


def engine_suffixes() -> set[str]:
    tree = ast.parse(MEDIA_BANK.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "AUDIO_SUFFIXES" for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError("AUDIO_SUFFIXES introuvable dans media_bank.py")


class CloudSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        self.root = Path(raw.name)
        self.bindir = self.root / "bin"
        self.bindir.mkdir()
        here = Path(__file__).resolve()
        write_bin(
            self.bindir,
            "rclone",
            f'#!/bin/sh\nexec "{sys.executable}" "{here}" rclone "{self.bindir}" "$@"\n',
        )
        # Le pont tourne en root, pas le test : chown est noté, sans rien changer.
        write_bin(self.bindir, "chown", f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{self.bindir}/chown.log"\n')
        self.dropbox = self.root / "dropbox"
        self.bacs = self.dropbox / "BUTTON" / "Bacs"
        self.settings = {"remotes": {"fake": str(self.dropbox)}, "fail": [], "slow": []}
        self.save_settings()
        # Le bac 12, renommé depuis l'ouverture de son dossier Dropbox : le
        # lien a changé de nom, pas de numéro.
        self.media = self.root / "media"
        self.cart = self.media / "50-carts" / "12"
        self.cart.mkdir(parents=True)
        (self.media / "Carts").mkdir()
        (self.media / "Carts" / "12-nouveautes-ete").symlink_to(self.cart, target_is_directory=True)
        self.state = self.root / "state"
        self.folder = self.bacs / "12-nouveautes"
        self.folder.mkdir(parents=True)

    def save_settings(self) -> None:
        (self.bindir / "rclone.json").write_text(json.dumps(self.settings), encoding="utf-8")

    def env(self, **extra: str) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.bindir}{os.pathsep}{env.get('PATH', '')}"
        env.update(
            CLOUD_SYNC_REMOTE="fake:BUTTON",
            MEDIA_ROOT=str(self.media),
            CLOUD_SYNC_STATE=str(self.state),
            TZ="Europe/Paris",
        )
        env.update(extra)
        return env

    def sync(self, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["sh", str(SCRIPT), "--once"],
            env=self.env(**extra),
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def drop(self, rel: str, body: bytes, folder: Path | None = None) -> Path:
        path = (folder or self.folder) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return path

    def report(self) -> str:
        return (self.folder / "_compte-rendu.txt").read_text(encoding="utf-8")

    def calls(self) -> list[list[str]]:
        log = self.bindir / "rclone.log"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def report_uploads(self) -> int:
        return sum(1 for call in self.calls() if call[0] == "copyto" and call[-1].endswith("_compte-rendu.txt"))

    def test_a_new_file_is_copied_into_its_cart(self) -> None:
        song = self.drop("Ada - Song.mp3", b"mp3")
        os.utime(song, (1_700_000_000, 1_700_000_000))
        self.drop("Album/Bea - Live.FLAC", b"flac")
        self.drop(".cache.mp3", b"cache")
        self.drop("._Ada - Song.mp3", b"mac")

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        copied = self.cart / "Ada - Song.mp3"
        self.assertEqual(copied.read_bytes(), b"mp3")
        self.assertEqual(int(copied.stat().st_mtime), 1_700_000_000)
        self.assertEqual((self.cart / "Album" / "Bea - Live.FLAC").read_bytes(), b"flac")
        self.assertEqual(sorted(path.name for path in self.cart.iterdir()), ["Ada - Song.mp3", "Album"])
        self.assertIn("copié : Bacs/12-nouveautes/Ada - Song.mp3 -> 50-carts/12/Ada - Song.mp3", result.stdout)
        report = self.report()
        self.assertIn("Compte rendu de la station, pour Bacs/12-nouveautes.", report)
        self.assertRegex(report, r"Dernier changement : \d\d/\d\d/\d{4} à \d\d:\d\d\.")
        self.assertIn("Reçus (2) :\n- Ada - Song.mp3\n- Album/Bea - Live.FLAC\n", report)
        self.assertNotIn("cache", report)
        copies = [call for call in self.calls() if call[0] == "copyto" and "_compte-rendu" not in call[-1]]
        self.assertEqual(len(copies), 2)
        for call in copies:
            self.assertIn("--ignore-existing", call)
        self.assertFalse(any("--inplace" in call for call in self.calls()))

    def test_a_copied_file_never_comes_back(self) -> None:
        self.drop("Ada - Song.mp3", b"mp3")
        self.assertEqual(self.sync().returncode, 0)
        # Retiré dans la console : le moteur l'envoie dans 90-trash.
        (self.cart / "Ada - Song.mp3").unlink()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.cart.iterdir()), [])
        self.assertNotIn("copié", result.stdout)
        self.assertIn("- Ada - Song.mp3\n", self.report())
        self.assertEqual(self.report_uploads(), 1)

    def test_a_file_replaced_in_dropbox_enters_as_a_new_sound(self) -> None:
        self.drop("Ada - Song.mp3", b"mp3")
        self.assertEqual(self.sync().returncode, 0)
        self.drop("Ada - Song.mp3", b"mp3, en mieux")

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.cart / "Ada - Song.mp3").read_bytes(), b"mp3")
        self.assertEqual((self.cart / "Ada - Song-1.mp3").read_bytes(), b"mp3, en mieux")
        self.assertIn("-> 50-carts/12/Ada - Song-1.mp3", result.stdout)

    def test_a_lost_list_does_not_copy_twice(self) -> None:
        self.drop("Ada - Song.mp3", b"mp3")
        self.assertEqual(self.sync().returncode, 0)
        self.drop("Ada - Song.mp3", b"mp3, en mieux")
        self.assertEqual(self.sync().returncode, 0)
        (self.state / "copies").write_text("", encoding="utf-8")

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(path.name for path in self.cart.iterdir()), ["Ada - Song-1.mp3", "Ada - Song.mp3"])
        self.assertNotIn("copié", result.stdout)

    def test_a_lost_list_finds_a_copy_under_any_suffix(self) -> None:
        # Un autre son a déjà le nom : les deux versions de Dropbox prennent -1, puis -2.
        (self.cart / "Ada - Song.mp3").write_bytes(b"autre son")
        self.drop("Ada - Song.mp3", b"v1")
        self.assertEqual(self.sync().returncode, 0)
        self.drop("Ada - Song.mp3", b"v2, plus long")
        self.assertEqual(self.sync().returncode, 0)
        (self.cart / "Ada - Song-1.mp3").unlink()
        (self.state / "copies").write_text("", encoding="utf-8")

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(path.name for path in self.cart.iterdir()), ["Ada - Song-2.mp3", "Ada - Song.mp3"])
        self.assertNotIn("copié", result.stdout)

    def test_a_folder_left_by_a_failed_copy_goes_to_the_cart_owner(self) -> None:
        self.drop("Album/Ada - Song.mp3", b"mp3")
        self.settings["fail"] = ["Ada - Song.mp3"]
        self.save_settings()
        self.assertEqual(self.sync().returncode, 1)
        self.assertTrue((self.cart / "Album").is_dir())
        self.settings["fail"] = []
        self.save_settings()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        info = self.cart.stat()
        owner = f"{info.st_uid}:{info.st_gid}"
        cart = self.cart.resolve()
        chowned = (self.bindir / "chown.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(chowned, [f"-h {owner} {cart}/Album", f"-h {owner} {cart}/Album/Ada - Song.mp3"])

    def test_a_folder_without_cart_is_skipped(self) -> None:
        orphan = self.bacs / "99-sans-bac"
        other = self.bacs / "divers"
        self.drop("x.mp3", b"x", orphan)
        self.drop("y.mp3", b"y", other)
        self.drop("z.mp3", b"z", self.bacs)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.cart.iterdir()), [])
        self.assertIn("sauté : Bacs/99-sans-bac, la station n'a pas de bac 99.", result.stdout)
        self.assertIn("sauté : Bacs/divers n'est pas le nom d'un bac", result.stdout)
        self.assertIn("pas copié : Bacs/z.mp3 est posé dans Bacs/ même.", result.stdout)
        self.assertFalse((orphan / "_compte-rendu.txt").exists())
        self.assertFalse((other / "_compte-rendu.txt").exists())
        self.assertFalse(any(call[0] == "copyto" and "99-sans-bac" in call[-2] for call in self.calls()))

    def test_a_refused_format_is_not_copied_and_is_reported(self) -> None:
        self.drop("notes.pdf", b"pdf")
        self.drop("LISEZMOI", b"texte")
        self.drop("Ada - Song.mp3", b"mp3")

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([path.name for path in self.cart.iterdir()], ["Ada - Song.mp3"])
        report = self.report()
        self.assertIn(
            "Refusés (2) :\n"
            "- LISEZMOI : sans extension, la station ne sait pas si c'est un son.\n"
            "- notes.pdf : format .pdf, que la station ne prend pas.\n",
            report,
        )
        self.assertIn("Formats pris : aac, aif, aiff, flac, m4a, mp2, mp3,", report)
        self.assertIn("refusé : Bacs/12-nouveautes/notes.pdf : format .pdf", result.stdout)

    def test_the_report_is_rewritten_only_when_something_changes(self) -> None:
        self.drop("Ada - Song.mp3", b"mp3")
        self.sync()
        first = self.report()
        self.sync()
        self.assertEqual(self.report_uploads(), 1)

        self.drop("Bea - Live.mp3", b"mp3")
        self.sync()
        self.assertEqual(self.report_uploads(), 2)
        self.assertIn("Reçus (2) :", self.report())

        # Effacé dans Dropbox, il revient tel quel, avec la même date.
        written = self.report()
        (self.folder / "_compte-rendu.txt").unlink()
        self.sync()
        self.assertEqual(self.report_uploads(), 3)
        self.assertEqual(self.report(), written)
        self.assertNotEqual(first, written)

    def test_a_folder_renamed_without_its_number_says_it_is_closed(self) -> None:
        self.drop("Ada - Song.mp3", b"mp3")
        self.assertEqual(self.sync().returncode, 0)
        closed = self.bacs / "nouveautes-ferme"
        self.folder.rename(closed)
        self.drop("Bea - Live.mp3", b"mp3", closed)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([path.name for path in self.cart.iterdir()], ["Ada - Song.mp3"])
        report = (closed / "_compte-rendu.txt").read_text(encoding="utf-8")
        self.assertIn("Compte rendu de la station, pour Bacs/nouveautes-ferme.", report)
        self.assertIn(
            "Ce dossier n'ouvre plus de bac : son nom ne commence pas par le numéro d'un bac, comme 12-nouveautes. "
            "Rien de ce qu'on y dépose n'est copié.",
            report,
        )
        self.assertNotIn("Ce dossier est ouvert", report)
        self.assertEqual(self.report_uploads(), 2)
        self.sync()
        self.assertEqual(self.report_uploads(), 2)

    def test_a_folder_whose_cart_is_gone_says_it_is_closed(self) -> None:
        self.assertEqual(self.sync().returncode, 0)
        (self.media / "Carts" / "12-nouveautes-ete").unlink()

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ce dossier n'ouvre plus de bac : la station n'a pas de bac 12.", self.report())

    def test_a_report_the_station_did_not_write_is_left_alone(self) -> None:
        other = self.bacs / "divers"
        notes = self.drop("_compte-rendu.txt", b"mes notes", other)

        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(notes.read_bytes(), b"mes notes")
        self.assertFalse(any(call[0] == "copyto" and "divers" in call[-1] for call in self.calls()))

    def test_an_open_folder_without_files_gets_its_report(self) -> None:
        # Une barre à la fin du remote ne change rien.
        result = self.sync(CLOUD_SYNC_REMOTE="fake:BUTTON/")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ce dossier est ouvert", self.report())
        self.assertIn("Reçus : aucun pour l'instant.", self.report())
        self.assertIn([*LSF, "fake:BUTTON/Bacs"], self.calls())

    def test_a_failed_copy_is_reported_and_tried_again(self) -> None:
        self.drop("Ada - Song.mp3", b"mp3")
        self.settings["fail"] = ["Ada - Song.mp3"]
        self.save_settings()

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(list(self.cart.iterdir()), [])
        self.assertIn("pas copié : Bacs/12-nouveautes/Ada - Song.mp3 (NOTICE: Failed to copyto: disque plein)", result.stdout)
        self.assertIn("Pas encore copiés (1) :\n- Ada - Song.mp3 : la copie a échoué, nouvel essai dans 60 s.\n", self.report())

        self.settings["fail"] = []
        self.save_settings()
        result = self.sync()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.cart / "Ada - Song.mp3").read_bytes(), b"mp3")
        self.assertNotIn("Pas encore copiés", self.report())
        self.assertIn("Reçus (1) :\n- Ada - Song.mp3\n", self.report())

    def test_stopping_the_bridge_stops_the_copy(self) -> None:
        self.drop("gros.wav", b"wav")
        self.settings["slow"] = ["gros.wav"]
        self.save_settings()
        bridge = subprocess.Popen(
            ["sh", str(SCRIPT)],
            env=self.env(),
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(bridge.kill)
        deadline = time.monotonic() + 15
        while not (self.bindir / "copie-en-cours").exists():
            self.assertLess(time.monotonic(), deadline, "la copie n'a pas commencé")
            time.sleep(0.05)

        # docker stop : TERM au premier processus du conteneur, le script.
        bridge.send_signal(signal.SIGTERM)

        self.assertEqual(bridge.wait(timeout=10), 143)
        self.assertEqual((self.bindir / "arrete").read_text(encoding="utf-8"), "TERM")
        self.assertEqual((self.state / "copies").read_text(encoding="utf-8"), "")

    def test_missing_settings_stop_the_bridge_and_say_what_to_do(self) -> None:
        cases = [
            ({"CLOUD_SYNC_REMOTE": ""}, "CLOUD_SYNC_REMOTE manquant dans .env"),
            ({"CLOUD_SYNC_REMOTE": "BUTTON"}, "il faut le nom du remote de rclone"),
            ({"CLOUD_SYNC_REMOTE": "dropbox:BUTTON"}, "rclone ne connaît pas le remote dropbox"),
            ({"CLOUD_SYNC_INTERVAL": "une minute"}, "CLOUD_SYNC_INTERVAL=une minute : un nombre de secondes"),
            ({"CLOUD_SYNC_INTERVAL": "0"}, "un nombre de secondes"),
        ]
        for env, message in cases:
            with self.subTest(env=env):
                result = self.sync(**env)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)
        self.assertFalse(any(call[0] != "listremotes" for call in self.calls()))
        self.assertEqual(list(self.cart.iterdir()), [])

    def test_a_missing_bacs_folder_says_what_to_do(self) -> None:
        shutil.rmtree(self.bacs)

        result = self.sync()

        self.assertEqual(result.returncode, 1)
        self.assertIn("fake:BUTTON/Bacs n'existe pas : crée le dossier Bacs", result.stdout)

    def test_the_bridge_takes_the_engine_formats(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        match = re.search(r'^FORMATS="([^"]*)"$', text, re.M)
        self.assertIsNotNone(match, "FORMATS introuvable dans cloud-sync.sh")
        self.assertEqual({"." + name for name in match.group(1).split()}, engine_suffixes())


if __name__ == "__main__":
    # Le faux rclone, posé par setUp, rappelle ce fichier.
    if sys.argv[1:2] == ["rclone"]:
        sys.exit(fake_rclone(Path(sys.argv[2]), sys.argv[3:]))
    unittest.main()
