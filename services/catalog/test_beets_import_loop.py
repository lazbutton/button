"""python test_beets_import_loop.py — la boucle indexe aussi un fichier arrivé après coup.

Un faux beet joue Beets, sur la bibliothèque et l'historique d'import de
BEETSDIR, dans les formats du vrai : library.db et state.pickle. Comme lui avec
`incremental`, il saute ce que son historique connaît déjà : un dossier quand il
importe par album, un fichier quand il importe par titre (-s). Le passage avec
le vrai Beets est dans engine/tests/test_beets_import_loop.py.

Un lancement du script fait un tour : le faux sleep arrête la boucle. Elle
n'indexe un dossier que s'il n'a pas bougé pendant sa pause. Un dépôt demande
donc deux tours : elle le voit, puis l'indexe.

Le faux modify touche à chaque appel les fichiers de ses titres. Comme les tags
que Beets et promote-inbox.sh écrivent, ce que la boucle écrit pendant son tour
ne doit pas la faire attendre.
"""

from __future__ import annotations

import json
import os
import pickle
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "deploy" / "scripts"
SCRIPT = SCRIPTS / "beets-import-loop.sh"
AUDIO = {".mp3", ".flac", ".ogg", ".opus", ".m4a"}
# Le code du faux sleep : il arrête la boucle, un lancement fait un tour.
ONE_TURN = 7


def write_bin(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def open_library(beetsdir: Path) -> sqlite3.Connection:
    con = sqlite3.connect(beetsdir / "library.db")
    con.execute(
        "create table if not exists items"
        " (id integer primary key, path blob, album_id integer, grouping text, genre text)"
    )
    return con


def fake_beet(beetsdir: Path, args: list[str]) -> int:
    """Le faux beet : import et modify, tels que la boucle les lance."""
    with (beetsdir / "beet.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    if args[:3] == ["import", "-A", "-q"] and args[3:-1] in ([], ["-s"]):
        singletons = args[3:-1] == ["-s"]
        top = args[-1]
        state_path = beetsdir / "state.pickle"
        try:
            state = pickle.loads(state_path.read_bytes())
        except Exception:
            # Comme le vrai : un état absent ou illisible vaut un état vide.
            state = {"tagprogress": {}, "taghistory": set()}
        history: set[tuple[bytes, ...]] = state["taghistory"]
        imported = skipped = 0
        with closing(open_library(beetsdir)) as con, con:
            for folder, subfolders, names in os.walk(top):
                subfolders[:] = sorted(name for name in subfolders if not name.startswith("."))
                tracks = [
                    os.path.join(folder, name)
                    for name in sorted(names)
                    if not name.startswith(".") and Path(name).suffix.lower() in AUDIO
                ]
                if not tracks:
                    continue
                # Par titre, une tâche par fichier. Sinon une par dossier, qui
                # fait un album de ses fichiers.
                tasks = [(track, [track]) for track in tracks] if singletons else [(folder, tracks)]
                for seen, paths in tasks:
                    entry = (os.fsencode(seen),)
                    if entry in history:
                        skipped += 1
                        continue
                    # Un titre réimporté remplace le sien : retiré, puis ajouté
                    # sous l'identifiant suivant.
                    for path in paths:
                        con.execute("delete from items where path = ?", (os.fsencode(path),))
                    album = None
                    if not singletons:
                        album = con.execute("select coalesce(max(album_id), 0) + 1 from items").fetchone()[0]
                    for path in paths:
                        con.execute("insert into items (path, album_id) values (?, ?)", (os.fsencode(path), album))
                    history.add(entry)
                    imported += 1
        state_path.write_bytes(pickle.dumps(state))
        if not imported:
            print(f"No files imported from {top}")
        if skipped:
            print(f"Skipped {skipped} paths.")
        return 0
    if args[:2] == ["modify", "-y"] and len(args) > 3 and args[-1].startswith("path:"):
        fields = dict(arg.split("=", 1) for arg in args[2:-1])
        if set(fields) - {"grouping", "genre"}:
            print(f"faux beet, modify inattendu : {args}", file=sys.stderr)
            return 2
        top = os.fsencode(args[-1].removeprefix("path:"))
        with closing(open_library(beetsdir)) as con, con:
            found = [
                (item_id, path)
                for item_id, path in con.execute("select id, path from items")
                if path == top or path.startswith(top + b"/")
            ]
            if not found:
                print("error: No matching items found.", file=sys.stderr)
                return 1
            for field, value in fields.items():
                con.executemany(f"update items set {field} = ? where id = ?", [(value, item_id) for item_id, _ in found])
        for _, path in found:
            if os.path.exists(path):
                os.utime(path)
        return 0
    print(f"faux beet, appel inattendu : {args}", file=sys.stderr)
    return 2


class BeetsImportLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        self.root = Path(raw.name)
        self.bindir = self.root / "bin"
        self.bindir.mkdir()
        here = Path(__file__).resolve()
        write_bin(
            self.bindir,
            "beet",
            f'#!/bin/sh\nexec "{sys.executable}" "{here}" beet "$BEETSDIR" "$@"\n',
        )
        # Le faux sleep arrête la boucle. S'il trouve entre-deux-tours, il le
        # lance d'abord, une fois, et la boucle fait un second tour.
        write_bin(
            self.bindir,
            "sleep",
            "#!/bin/sh\n"
            f'between="{self.root}/entre-deux-tours"\n'
            'if [ -f "$between" ]; then\n'
            '  mv "$between" "$between.fait"\n'
            '  . "$between.fait"\n'
            "  exit 0\n"
            "fi\n"
            f"exit {ONE_TURN}\n",
        )
        self.beetsdir = self.root / "data" / "Beets"
        self.beetsdir.mkdir(parents=True)
        self.media = self.root / "media"
        self.rotation = self.media / "10-rotation"
        self.rotation.mkdir(parents=True)
        (self.media / "20-archives").mkdir()
        (self.root / "tmp").mkdir()

    def env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.bindir}{os.pathsep}{env.get('PATH', '')}"
        # La boucle retient dans TMPDIR l'état des dossiers avant sa pause.
        env.update(MEDIA_ROOT=str(self.media), BEETSDIR=str(self.beetsdir), TMPDIR=str(self.root / "tmp"))
        return env

    def turn(self, **extra: str) -> subprocess.CompletedProcess[str]:
        """Un tour de la vraie boucle, jusqu'à son sleep."""
        result = subprocess.run(
            ["sh", str(SCRIPT)],
            env={**self.env(), **extra},
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, ONE_TURN, result.stderr)
        return result

    def between_two_turns(self, script: str) -> None:
        """Ce qui arrive pendant le sleep du prochain lancement, qui fait alors deux tours."""
        (self.root / "entre-deux-tours").write_text(script, encoding="utf-8")

    def beet(self, *args: str) -> None:
        subprocess.run(["beet", *args], env=self.env(), cwd=self.root, capture_output=True, check=True)

    def index_by_folder(self, folder: Path, *fields: str) -> None:
        """Ce que la boucle lançait avant d'importer par titre."""
        self.beet("import", "-A", "-q", str(folder))
        self.beet("modify", "-y", *fields, f"path:{folder}")

    def imports(self) -> list[str]:
        """Les dossiers que la boucle a donnés à beet import -s."""
        log = self.beetsdir / "beet.log"
        if not log.exists():
            return []
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        prefix = len(str(self.media)) + 1
        return [call[-1][prefix:] for call in calls if call[:4] == ["import", "-A", "-q", "-s"]]

    def items(self) -> dict[str, dict[str, object]]:
        with closing(open_library(self.beetsdir)) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute("select id, path, album_id, grouping, genre from items").fetchall()
        prefix = len(str(self.media)) + 1
        return {os.fsdecode(row["path"])[prefix:]: {key: row[key] for key in row.keys() if key != "path"} for row in rows}

    def groupings(self) -> dict[str, object]:
        return {path: item["grouping"] for path, item in self.items().items()}

    def test_a_file_added_to_an_indexed_folder_is_indexed(self) -> None:
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        self.turn()
        self.assertEqual(self.items(), {})
        self.turn()
        self.assertEqual(self.groupings(), {"10-rotation/Ada - Un.mp3": "rotation"})
        first = self.items()

        # Le dépôt suivant arrive à plat, dans le dossier déjà indexé.
        (self.rotation / "Bea - Deux.mp3").write_bytes(b"deux")
        self.turn()
        self.assertEqual(self.items(), first)
        self.turn()

        self.assertEqual(
            self.groupings(),
            {"10-rotation/Ada - Un.mp3": "rotation", "10-rotation/Bea - Deux.mp3": "rotation"},
        )
        self.assertEqual(self.items()["10-rotation/Ada - Un.mp3"], first["10-rotation/Ada - Un.mp3"])
        # Rien de neuf : rien ne bouge.
        indexed = self.items()
        self.turn()
        self.assertEqual(self.items(), indexed)

    def test_an_archive_bank_indexes_a_later_file_with_its_grouping(self) -> None:
        # Le nom du dossier devient le regroupement, espaces et apostrophe compris.
        bank = self.media / "20-archives" / "Nuit d'été 2"
        bank.mkdir()
        (bank / "Cy - Live à Orléans.flac").write_bytes(b"un")
        self.turn()
        self.turn()
        (bank / "Dan - Live deux.flac").write_bytes(b"deux")
        # Un dossier en _ n'est pas une banque.
        draft = self.media / "20-archives" / "_brouillon"
        draft.mkdir()
        (draft / "Eve - Essai.flac").write_bytes(b"essai")
        self.turn()
        self.turn()

        self.assertEqual(
            {path: (item["grouping"], item["genre"]) for path, item in self.items().items()},
            {
                "20-archives/Nuit d'été 2/Cy - Live à Orléans.flac": ("Nuit d'été 2", "Archive"),
                "20-archives/Nuit d'été 2/Dan - Live deux.flac": ("Nuit d'été 2", "Archive"),
            },
        )

    def test_a_file_still_being_copied_waits(self) -> None:
        song = self.rotation / "Ada - Un.mp3"
        song.write_bytes(b"un tiers")
        self.turn()
        # La copie avance, puis finit : le dossier bouge encore à chaque pause.
        song.write_bytes(b"un tiers, deux tiers")
        waiting = self.turn()
        song.write_bytes(b"un tiers, deux tiers, la fin")
        self.turn()
        self.assertEqual(self.imports(), [])
        self.assertEqual(self.items(), {})
        self.assertIn("a bougé pendant la pause", waiting.stdout)
        self.assertIn("Ada - Un.mp3", waiting.stdout)

        self.turn()

        self.assertEqual(self.imports(), ["10-rotation"])
        self.assertEqual(self.groupings(), {"10-rotation/Ada - Un.mp3": "rotation"})

    def test_a_file_whose_date_alone_changes_waits_too(self) -> None:
        # Une copie peut réserver sa taille d'entrée : seule sa date bouge ensuite.
        song = self.rotation / "Ada - Un.mp3"
        song.write_bytes(b"taille finale")
        self.turn()
        os.utime(song, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        self.turn()
        self.assertEqual(self.imports(), [])

        self.turn()
        self.assertEqual(self.imports(), ["10-rotation"])

    def test_the_loop_says_when_it_cannot_keep_the_state_of_the_folders(self) -> None:
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        # Un fichier là où la boucle attend son dossier d'état.
        full = self.root / "plein"
        full.write_bytes(b"")

        self.turn(TMPDIR=str(full))
        again = self.turn(TMPDIR=str(full))

        self.assertIn("État des dossiers : impossible de le noter", again.stderr)
        self.assertEqual(self.imports(), [])
        self.assertEqual(self.items(), {})

    def test_a_folder_that_moves_does_not_hold_the_others(self) -> None:
        bank = self.media / "20-archives" / "jazz"
        bank.mkdir()
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        archive = bank / "Cy - Live.flac"
        archive.write_bytes(b"un tiers")
        self.turn()
        archive.write_bytes(b"un tiers, deux tiers")
        self.turn()

        self.assertEqual(self.imports(), ["10-rotation"])
        self.assertEqual(self.groupings(), {"10-rotation/Ada - Un.mp3": "rotation"})

    def test_what_promote_inbox_rewrites_at_every_turn_does_not_hold_its_folder(self) -> None:
        # Sans tags lisibles, promote-inbox.sh réécrit un fichier à chaque tour :
        # ici tous, ce faux ffprobe n'en trouve jamais.
        write_bin(self.bindir, "ffprobe", "#!/bin/sh\n")
        write_bin(
            self.bindir,
            "ffmpeg",
            '#!/bin/sh\nout=\nfor arg in "$@"; do out=$arg; done\nprintf done > "$out"\n',
        )
        promote = {"PROMOTE_INBOX": str(SCRIPTS / "promote-inbox.sh")}
        (self.rotation / "Générique.mp3").write_bytes(b"un")
        first = self.turn(**promote)
        self.assertIn("sur place : Générique.mp3", first.stdout)
        self.turn(**promote)
        self.assertEqual(self.groupings(), {"10-rotation/Générique.mp3": "rotation"})

        (self.rotation / "Ada - Un.mp3").write_bytes(b"deux")
        self.turn(**promote)
        again = self.turn(**promote)

        self.assertIn("sur place : Générique.mp3", again.stdout)
        self.assertEqual(
            self.groupings(),
            {"10-rotation/Générique.mp3": "rotation", "10-rotation/Ada - Un.mp3": "rotation"},
        )

    def test_a_library_indexed_by_folder_takes_the_skipped_file_and_keeps_its_items(self) -> None:
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        (self.rotation / "Bea - Deux.mp3").write_bytes(b"deux")
        self.index_by_folder(self.rotation, "grouping=rotation")
        bank = self.media / "20-archives" / "jazz"
        bank.mkdir()
        (bank / "Cy - Live.flac").write_bytes(b"live")
        self.index_by_folder(bank, "grouping=jazz", "genre=Archive")
        # Le défaut : arrivé après coup, ce titre n'est jamais entré.
        (self.rotation / "Dan - Trois.mp3").write_bytes(b"trois")
        self.index_by_folder(self.rotation, "grouping=rotation")
        before = self.items()
        self.assertEqual(
            sorted(before),
            ["10-rotation/Ada - Un.mp3", "10-rotation/Bea - Deux.mp3", "20-archives/jazz/Cy - Live.flac"],
        )

        self.turn()
        self.turn()

        after = self.items()
        self.assertIn("10-rotation/Dan - Trois.mp3", after)
        self.assertEqual(after.pop("10-rotation/Dan - Trois.mp3")["grouping"], "rotation")
        # Les titres déjà indexés ne sont pas réimportés : mêmes identifiants.
        self.assertEqual(after, before)

    def test_a_lost_history_does_not_import_the_library_again(self) -> None:
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        (self.rotation / "Bea - Deux.mp3").write_bytes(b"deux")
        bank = self.media / "20-archives" / "jazz"
        bank.mkdir()
        (bank / "Cy - Live.flac").write_bytes(b"live")
        self.turn()
        self.turn()
        before = self.items()
        self.assertEqual(len(before), 3)

        # Perdu entre deux tours du même lancement, pas seulement au démarrage.
        broken = self.root / "state.pickle"
        for lost in (None, b"illisible", pickle.dumps(["pas un dictionnaire"])):
            with self.subTest(state=lost):
                if lost is None:
                    self.between_two_turns('rm "$BEETSDIR/state.pickle"\n')
                else:
                    broken.write_bytes(lost)
                    self.between_two_turns(f'cp "{broken}" "$BEETSDIR/state.pickle"\n')
                seen = len(self.imports())
                self.turn()
                # Deux tours, deux dossiers : Beets les a tous relus, sans rien réimporter.
                self.assertEqual(len(self.imports()), seen + 4)
                self.assertEqual(self.items(), before)

    def test_nothing_is_indexed_while_the_history_cannot_be_resumed(self) -> None:
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        (self.rotation / "Bea - Deux.mp3").write_bytes(b"deux")
        self.index_by_folder(self.rotation, "grouping=rotation")
        (self.rotation / "Cy - Trois.mp3").write_bytes(b"trois")
        before = self.items()
        # Le fichier que la reprise écrit avant de remplacer l'historique.
        obstacle = self.beetsdir / ".state.partial.pickle"
        obstacle.mkdir()

        self.turn()
        blocked = self.turn()

        self.assertIn("reprise impossible", blocked.stderr)
        self.assertEqual(self.imports(), [])
        self.assertEqual(self.items(), before)

        # L'obstacle levé, la boucle reprend seule, sans redémarrer.
        obstacle.rmdir()
        self.turn()
        self.turn()

        after = self.items()
        self.assertIn("10-rotation/Cy - Trois.mp3", after)
        del after["10-rotation/Cy - Trois.mp3"]
        self.assertEqual(after, before)


if __name__ == "__main__":
    # Le faux beet, posé par setUp, rappelle ce fichier.
    if sys.argv[1:2] == ["beet"]:
        sys.exit(fake_beet(Path(sys.argv[2]), sys.argv[3:]))
    unittest.main()
