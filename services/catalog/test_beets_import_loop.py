"""python test_beets_import_loop.py — la bibliothèque Beets suit le disque.

La boucle indexe un fichier arrivé après coup, retire un fichier disparu, relit
un fichier changé, et réindexe un fichier remis au même chemin.

Un faux beet joue Beets, sur la bibliothèque et l'historique d'import de
BEETSDIR, dans les formats du vrai : library.db et state.pickle. Comme lui avec
`incremental`, il saute ce que son historique connaît déjà : un dossier quand il
importe par album, un fichier quand il importe par titre (-s). Le contenu d'un
fichier lui tient lieu de titre. Le passage avec le vrai Beets est dans
engine/tests/test_beets_import_loop.py.

Le faux update fait comme le vrai, 2.5.1 : il ne relit qu'un fichier plus récent
que la date notée, et ne note pas la nouvelle. Devant un fichier disparu, il
retire le titre et élague les dossiers vidés jusqu'à la racine de la
bibliothèque, la banque, sauf si `-d` en donne une autre. Après la relecture d'un
titre d'album, il donne à tous les titres de l'album le genre du premier.

Un lancement du script fait un tour : le faux sleep arrête la boucle. Elle
n'indexe un dossier que s'il n'a pas bougé pendant sa pause. Un dépôt demande
donc deux tours : elle le voit, puis l'indexe.

Comme le vrai, le faux modify écrit dans les fichiers des titres qu'il change,
et note leur nouvelle date. Comme ces tags, et ceux de promote-inbox.sh, ce que
la boucle écrit pendant son tour ne doit pas la faire attendre. Il lit aussi sa
requête comme le vrai, et ses valeurs comme un modèle, sans les fonctions : une
requête path: qui finit par une virgule prend toute la bibliothèque, et $champ,
dans une valeur, prend celle du titre.
"""

from __future__ import annotations

import json
import os
import pickle
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "deploy" / "scripts"
SCRIPT = SCRIPTS / "beets-import-loop.sh"
AUDIO = {".mp3", ".flac", ".ogg", ".opus", ".m4a"}
# Le code du faux sleep : il arrête la boucle, un lancement fait un tour.
ONE_TURN = 7
# Au-delà, SQLite refuse la requête du vrai beet : « Expression tree is too large ».
MOST_IDS = 998
# La date d'un fichier copié avec la sienne, plus ancienne que celle que Beets a notée.
OLD = 1_600_000_000


def write_bin(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def open_library(beetsdir: Path) -> sqlite3.Connection:
    con = sqlite3.connect(beetsdir / "library.db")
    con.execute(
        "create table if not exists items"
        " (id integer primary key, path blob, album_id integer, grouping text, genre text, title text, mtime real)"
    )
    return con


def read_file(path: bytes) -> dict[str, object]:
    """Ce que le faux beet lit d'un fichier : son contenu tient lieu de titre. Il
    n'a ni regroupement ni genre."""
    title = Path(os.fsdecode(path)).read_bytes().decode("utf-8", "replace")
    return {"title": title, "grouping": None, "genre": None}


def under(path: bytes, top: bytes) -> bool:
    return path == top or path.startswith(top + b"/")


def prune(folder: bytes, root: bytes) -> None:
    """Comme Beets : les dossiers vidés, de folder jusqu'à root, qui reste."""
    root = os.path.normpath(root)
    folder = os.path.normpath(folder)
    while folder.startswith(root + b"/") and os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)
        folder = os.path.dirname(folder)


def id_query(terms: list[str]) -> list[int] | None:
    """id:1 , id:2 : la virgule seule sépare les requêtes, qui s'ajoutent."""
    if not terms or len(terms) % 2 == 0 or any(term != "," for term in terms[1::2]):
        return None
    if not all(term.startswith("id:") and term[3:].isdigit() for term in terms[::2]):
        return None
    return [int(term[3:]) for term in terms[::2]]


def path_query(terms: list[str]) -> Callable[[int, bytes], bool] | None:
    """Une requête path: d'un seul terme, lue comme Beets 2.5.1 la lit. Une
    virgule finale la coupe en deux requêtes, la seconde vide, qui prend tout.
    Puis il retire les espaces des deux bouts, et le \\ de \\:."""
    if len(terms) != 1 or not terms[0].startswith("path:"):
        return None
    if terms[0].endswith(","):
        return lambda item_id, path: True
    top = os.fsencode(terms[0].strip().removeprefix("path:").replace("\\:", ":"))
    return lambda item_id, path: under(path, top)


def evaluate(template: str, values: dict[str, object]) -> str:
    """Comme le vrai, modify lit une valeur comme un modèle : $champ y prend la
    valeur du titre, et $$, $%, $} et $, gardent leur caractère. Un } seul arrête
    le modèle : la suite reste telle quelle, $$ compris. Le faux ne joue ni les
    fonctions, %nom{…}, ni un ${ qui n'est pas suivi d'un nom."""
    read = []
    pos = 0
    for match in re.finditer(r"\$([$%},])|\$\{(\w+)\}|\$(\w+)|\}", template):
        read.append(template[pos : match.start()])
        pos = match.end()
        if match.group(0) == "}":
            return "".join(read) + template[match.start() :]
        field = match.group(2) or match.group(3)
        if match.group(1):
            read.append(match.group(1))
        elif field in values:
            read.append(str(values[field] or ""))
        else:
            # Un champ que le titre n'a pas reste écrit tel quel.
            read.append(match.group(0))
    return "".join(read) + template[pos:]


def fake_beet(beetsdir: Path, args: list[str]) -> int:  # noqa: PLR0911, PLR0912
    """Le faux beet : import, modify, update et remove, tels que la boucle les lance."""
    with (beetsdir / "beet.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    # La racine de la bibliothèque : la banque, comme la règle init-radiotomate.sh.
    directory = os.fsencode(os.environ["MEDIA_ROOT"])
    if args[:1] == ["-d"] and len(args) > 2:
        directory = os.fsencode(args[1])
        args = args[2:]
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
                        con.execute(
                            "insert into items (path, album_id, title, mtime) values (?, ?, ?, ?)",
                            (
                                os.fsencode(path),
                                album,
                                read_file(os.fsencode(path))["title"],
                                int(os.stat(path).st_mtime),
                            ),
                        )
                    history.add(entry)
                    imported += 1
        state_path.write_bytes(pickle.dumps(state))
        if not imported:
            print(f"No files imported from {top}")
        if skipped:
            print(f"Skipped {skipped} paths.")
        return 0
    if args[:2] == ["modify", "-y"]:
        # Comme le vrai : champ=valeur est un changement, le reste la requête.
        fields = {}
        terms = []
        for arg in args[2:]:
            key, equal, value = arg.partition("=")
            if equal and ":" not in key:
                fields[key] = value
            else:
                terms.append(arg)
        ids = id_query(terms)
        wanted = (lambda item_id, path: item_id in ids) if ids is not None else path_query(terms)
        if not fields or set(fields) - {"grouping", "genre"} or wanted is None:
            print(f"faux beet, modify inattendu : {args}", file=sys.stderr)
            return 2
        if ids is not None and len(ids) > MOST_IDS:
            print("sqlite3.OperationalError: Expression tree is too large (maximum depth 1000)", file=sys.stderr)
            return 1
        with closing(open_library(beetsdir)) as con, con:
            found = [
                (item_id, path, {"title": title, "grouping": grouping, "genre": genre})
                for item_id, path, title, grouping, genre in con.execute(
                    "select id, path, title, grouping, genre from items"
                )
                if wanted(item_id, path)
            ]
            if not found:
                print("error: No matching items found.", file=sys.stderr)
                return 1
            for item_id, path, values in found:
                new = {field: evaluate(template, values) for field, template in fields.items()}
                if all(values[field] == value for field, value in new.items()):
                    continue
                for field, value in new.items():
                    con.execute(f"update items set {field} = ? where id = ?", (value, item_id))
                # Il écrit les tags dans le fichier, et note sa nouvelle date.
                if os.path.exists(path):
                    os.utime(path)
                    con.execute("update items set mtime = ? where id = ?", (int(os.stat(path).st_mtime), item_id))
        return 0
    if args[:2] == ["update", "-M"]:
        terms = args[2:]
        excluded = set()
        while terms[:1] == ["-e"] and len(terms) > 1:
            excluded.add(terms[1])
            terms = terms[2:]
        ids = id_query(terms)
        if ids is None or excluded - {"grouping", "genre"}:
            print(f"faux beet, update inattendu : {args}", file=sys.stderr)
            return 2
        if len(ids) > MOST_IDS:
            print("sqlite3.OperationalError: Expression tree is too large (maximum depth 1000)", file=sys.stderr)
            return 1
        # Ce que le test fait arriver pendant que Beets relit.
        during = beetsdir / "pendant-update"
        if during.exists():
            subprocess.run(["sh", str(during)], check=True)
            during.unlink()
        albums = set()
        with closing(open_library(beetsdir)) as con, con:
            found = [row for row in con.execute("select id, path, mtime, album_id from items") if row[0] in ids]
            for item_id, path, mtime, album in found:
                if not os.path.exists(path):
                    con.execute("delete from items where id = ?", (item_id,))
                    prune(os.path.dirname(path), directory)
                    print(f"{os.fsdecode(path)}\n  deleted")
                    continue
                if int(os.stat(path).st_mtime) <= (mtime or 0):
                    continue
                read = {field: value for field, value in read_file(path).items() if field not in excluded}
                # La date relue n'est pas notée : elle n'est pas un champ du fichier.
                con.execute(
                    f"update items set {', '.join(f'{field} = ?' for field in read)} where id = ?",
                    (*read.values(), item_id),
                )
                if album is not None:
                    albums.add(album)
                with (beetsdir / "relus.log").open("a", encoding="utf-8") as reads:
                    reads.write(os.fsdecode(path) + "\n")
            # Puis l'album d'un titre relu prend le genre de son premier titre, et
            # le donne à tous ses titres.
            for album in albums:
                first = con.execute("select genre from items where album_id = ? order by id", (album,)).fetchone()
                if first is not None:
                    con.execute("update items set genre = ? where album_id = ?", (first[0], album))
        return 0
    if args[:2] == ["remove", "-f"]:
        ids = id_query(args[2:])
        if ids is None:
            print(f"faux beet, remove inattendu : {args}", file=sys.stderr)
            return 2
        if len(ids) > MOST_IDS:
            print("sqlite3.OperationalError: Expression tree is too large (maximum depth 1000)", file=sys.stderr)
            return 1
        # Sans -d : les fichiers restent.
        with closing(open_library(beetsdir)) as con, con:
            con.executemany("delete from items where id = ?", [(item_id,) for item_id in ids])
        return 0
    print(f"faux beet, appel inattendu : {args}", file=sys.stderr)
    return 2


def note_selection(beetsdir: Path) -> None:
    """Après chaque appel, le regroupement et le genre de chaque titre : ce que
    les catégories de l'auto-DJ verraient."""
    with closing(open_library(beetsdir)) as con:
        rows = con.execute("select path, grouping, genre from items")
        selection = {os.fsdecode(path): [grouping, genre] for path, grouping, genre in rows}
    with (beetsdir / "selection.log").open("a", encoding="utf-8") as log:
        log.write(json.dumps(selection) + "\n")


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
            rows = con.execute("select id, path, album_id, grouping, genre, title from items").fetchall()
        prefix = len(str(self.media)) + 1
        return {os.fsdecode(row["path"])[prefix:]: {key: row[key] for key in row.keys() if key != "path"} for row in rows}

    def rereads(self) -> list[str]:
        """Les fichiers que beet update a relus, une ligne par lecture."""
        log = self.beetsdir / "relus.log"
        if not log.exists():
            return []
        prefix = len(str(self.media)) + 1
        return sorted(line[prefix:] for line in log.read_text(encoding="utf-8").splitlines())

    def selections_seen(self) -> list[dict[str, list[object]]]:
        """Le regroupement et le genre de chaque titre, après chaque appel à beet."""
        log = self.beetsdir / "selection.log"
        if not log.exists():
            return []
        prefix = len(str(self.media)) + 1
        return [
            {path[prefix:]: fields for path, fields in json.loads(line).items()}
            for line in log.read_text(encoding="utf-8").splitlines()
        ]

    def groupings(self) -> dict[str, object]:
        return {path: item["grouping"] for path, item in self.items().items()}

    def modifies(self) -> int:
        """Combien de fois la boucle a lancé beet modify."""
        log = self.beetsdir / "beet.log"
        if not log.exists():
            return 0
        return sum(json.loads(line)[:1] == ["modify"] for line in log.read_text(encoding="utf-8").splitlines())

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

    def test_a_bank_named_like_a_beets_query_keeps_its_name_and_its_own_tracks(self) -> None:
        # Beets lit à sa façon une requête et une valeur. Par path:, une virgule
        # finale prenait toute la bibliothèque, et l'espace final, la banque
        # voisine. Dans la valeur, $title prenait le titre de chaque fichier, et
        # un } arrêtait le modèle.
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        names = ["jazz", "Foo,", "Bar", "Bar ", "Prix $title", "Live}$2024", "A\\:B"]
        for name in names:
            bank = self.media / "20-archives" / name
            bank.mkdir()
            (bank / "Cy - Live.flac").write_bytes(name.encode())
        self.turn()
        self.turn()

        expected = {
            "10-rotation/Ada - Un.mp3": ["rotation", None],
            **{f"20-archives/{name}/Cy - Live.flac": [name, "Archive"] for name in names},
        }
        self.assertEqual({path: [item["grouping"], item["genre"]] for path, item in self.items().items()}, expected)

        # Rien de neuf : rien ne bouge, et la boucle ne relance pas Beets pour
        # reposer ce qui est déjà là.
        seen = len(self.selections_seen())
        modifies = self.modifies()
        self.turn()
        self.turn()
        for selection in self.selections_seen()[seen:]:
            self.assertEqual(selection, expected)
        self.assertEqual(self.modifies(), modifies)

    def test_a_bank_larger_than_one_query_gets_its_grouping(self) -> None:
        bank = self.media / "20-archives" / "jazz"
        bank.mkdir()
        # Plus que SQLite n'en prend dans une requête : la boucle les désigne par paquets.
        count = MOST_IDS + 2
        for number in range(count):
            (bank / f"Cy - Live {number}.flac").write_bytes(b"%d" % number)
        self.turn()
        self.turn()

        self.assertEqual(set(self.groupings().values()), {"jazz"})
        self.assertEqual(len(self.items()), count)

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

    def test_a_file_removed_from_the_disk_leaves_the_library(self) -> None:
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        (self.rotation / "Bea - Deux.mp3").write_bytes(b"deux")
        jazz = self.media / "20-archives" / "jazz"
        jazz.mkdir()
        (jazz / "Cy - Live.flac").write_bytes(b"live")
        blues = self.media / "20-archives" / "blues"
        blues.mkdir()
        (blues / "Dan - Live.flac").write_bytes(b"live")
        soul = self.media / "20-archives" / "soul"
        soul.mkdir()
        (soul / "Eve - Live.flac").write_bytes(b"live")
        self.turn()
        self.turn()
        before = self.items()
        self.assertEqual(len(before), 5)

        # Un titre supprimé, une banque vidée, une autre supprimée en entier.
        (self.rotation / "Bea - Deux.mp3").unlink()
        (jazz / "Cy - Live.flac").unlink()
        shutil.rmtree(blues)
        removed = self.turn()

        # Au tour suivant, sans attendre que les dossiers se calment.
        kept = ["10-rotation/Ada - Un.mp3", "20-archives/soul/Eve - Live.flac"]
        self.assertEqual(self.items(), {path: before[path] for path in kept})
        self.assertIn("3 titre(s) retiré(s)", removed.stdout)
        # La banque vidée garde son dossier.
        self.assertTrue(jazz.is_dir())

    def test_nothing_leaves_the_library_while_its_folder_is_missing(self) -> None:
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        archives = self.media / "20-archives"
        (archives / "jazz").mkdir()
        (archives / "jazz" / "Cy - Live.flac").write_bytes(b"live")
        self.turn()
        self.turn()
        before = self.items()
        self.assertEqual(len(before), 2)

        # Une banque qui n'est pas montée : ses dossiers manquent, ses fichiers ne
        # sont pas partis.
        away = self.root / "pas-monte"
        away.mkdir()
        archives.rename(away / "20-archives")
        self.rotation.rename(away / "10-rotation")
        self.turn()
        self.assertEqual(self.items(), before)

        (away / "20-archives").rename(archives)
        (away / "10-rotation").rename(self.rotation)
        self.turn()
        self.turn()
        self.assertEqual(self.items(), before)

    def test_a_file_put_back_at_the_same_path_is_indexed_again(self) -> None:
        ada = self.rotation / "Ada - Un.mp3"
        ada.write_bytes(b"un")
        (self.rotation / "Bea - Deux.mp3").write_bytes(b"deux")
        self.turn()
        self.turn()
        before = self.items()
        ada.unlink()
        self.turn()
        self.assertNotIn("10-rotation/Ada - Un.mp3", self.items())

        ada.write_bytes(b"un")
        self.turn()
        self.turn()

        after = self.items()
        self.assertEqual(after.pop("10-rotation/Ada - Un.mp3")["grouping"], "rotation")
        self.assertEqual(after, {"10-rotation/Bea - Deux.mp3": before["10-rotation/Bea - Deux.mp3"]})

    def test_a_file_put_back_before_the_loop_saw_it_missing_keeps_its_id(self) -> None:
        ada = self.rotation / "Ada - Un.mp3"
        ada.write_bytes(b"un")
        self.turn()
        self.turn()
        before = self.items()

        # Retiré puis remis pendant une seule pause.
        self.between_two_turns(f'rm "{ada}"\nprintf un > "{ada}"\n')
        self.turn()
        self.turn()

        self.assertEqual(self.items(), before)

    def test_a_changed_file_is_read_again_once_and_keeps_its_id(self) -> None:
        ada = self.rotation / "Ada - Un.mp3"
        ada.write_bytes(b"un")
        (self.rotation / "Bea - Deux.mp3").write_bytes(b"deux")
        jazz = self.media / "20-archives" / "jazz"
        jazz.mkdir()
        cy = jazz / "Cy - Live.flac"
        cy.write_bytes(b"live")
        self.turn()
        self.turn()
        before = self.items()
        seen = len(self.selections_seen())

        # Un tag corrigé sur place, plus tard. Un fichier remplacé par une copie
        # qui garde sa date, plus ancienne que celle que Beets a notée.
        ada.write_bytes(b"un, corrige")
        later = int(time.time()) + 60
        os.utime(ada, (later, later))
        cy.write_bytes(b"live, remasterise")
        os.utime(cy, (OLD, OLD))
        self.turn()
        # Les dossiers ont bougé pendant la pause : rien n'est encore relu.
        self.assertEqual(self.items(), before)
        self.turn()

        after = self.items()
        self.assertEqual(after["10-rotation/Ada - Un.mp3"], {**before["10-rotation/Ada - Un.mp3"], "title": "un, corrige"})
        # Le regroupement et le genre d'une banque viennent de son dossier.
        self.assertEqual(
            after["20-archives/jazz/Cy - Live.flac"],
            {**before["20-archives/jazz/Cy - Live.flac"], "title": "live, remasterise"},
        )
        self.assertEqual(after["10-rotation/Bea - Deux.mp3"], before["10-rotation/Bea - Deux.mp3"])
        # À aucun moment un titre relu ne quitte la sélection de l'auto-DJ.
        for selection in self.selections_seen()[seen:]:
            self.assertEqual(selection["10-rotation/Ada - Un.mp3"][0], "rotation")
            self.assertEqual(selection["20-archives/jazz/Cy - Live.flac"], ["jazz", "Archive"])

        # Relus une fois : la boucle note la date que Beets ne note pas.
        self.turn()
        self.turn()
        self.assertEqual(self.rereads(), ["10-rotation/Ada - Un.mp3", "20-archives/jazz/Cy - Live.flac"])

    def test_a_file_deleted_while_beets_reads_its_folder_does_not_take_the_folder(self) -> None:
        jazz = self.media / "20-archives" / "jazz"
        jazz.mkdir()
        cy = jazz / "Cy - Live.flac"
        cy.write_bytes(b"live")
        self.turn()
        self.turn()
        cy.write_bytes(b"live, remasterise")
        os.utime(cy, (OLD, OLD))
        self.turn()

        # Beets retire alors le titre, et élague les dossiers vidés jusqu'à la
        # racine de sa bibliothèque : la banque.
        (self.beetsdir / "pendant-update").write_text(f'rm "{cy}"\n', encoding="utf-8")
        self.turn()

        self.assertEqual(self.items(), {})
        self.assertTrue(jazz.is_dir())

        # Remis : l'historique l'a oublié avec lui.
        cy.write_bytes(b"live")
        self.turn()
        self.turn()
        self.assertEqual(self.groupings(), {"20-archives/jazz/Cy - Live.flac": "jazz"})

    def test_a_file_deleted_while_another_is_read_comes_back_when_put_back(self) -> None:
        ada = self.rotation / "Ada - Un.mp3"
        bea = self.rotation / "Bea - Deux.mp3"
        ada.write_bytes(b"un")
        bea.write_bytes(b"deux")
        self.turn()
        self.turn()
        ada.write_bytes(b"un, corrige")
        os.utime(ada, (OLD, OLD))
        self.turn()

        # Supprimé pendant que Beets relit Ada, puis remis avant le tour suivant,
        # comme un fichier que Finder remplace.
        (self.beetsdir / "pendant-update").write_text(f'rm "{bea}"\n', encoding="utf-8")
        self.between_two_turns(f'printf deux > "{bea}"\n')
        self.turn()
        self.turn()

        self.assertEqual(
            self.groupings(),
            {"10-rotation/Ada - Un.mp3": "rotation", "10-rotation/Bea - Deux.mp3": "rotation"},
        )

    def test_a_tree_recreated_on_a_disk_that_is_not_mounted_removes_nothing(self) -> None:
        (self.rotation / "Ada - Un.mp3").write_bytes(b"un")
        jazz = self.media / "20-archives" / "jazz"
        jazz.mkdir()
        (jazz / "Cy - Live.flac").write_bytes(b"live")
        self.turn()
        self.turn()
        before = self.items()

        # Le disque de la banque n'est pas monté, et setup-media-tree.sh a recréé
        # l'arbre, vide, au démarrage.
        disk = self.root / "disque"
        self.media.rename(disk)
        (self.media / "10-rotation").mkdir(parents=True)
        (self.media / "20-archives").mkdir()
        unmounted = self.turn()

        self.assertEqual(self.items(), before)
        self.assertIn("aucun des 1 titre(s) indexé(s)", unmounted.stderr)

        # Monté : rien n'est réimporté.
        shutil.rmtree(self.media)
        disk.rename(self.media)
        self.turn()
        self.turn()
        self.assertEqual(self.items(), before)

    def test_a_changed_track_of_a_folder_album_leaves_the_others_alone(self) -> None:
        ada = self.rotation / "Ada - Un.mp3"
        bea = self.rotation / "Bea - Deux.mp3"
        ada.write_bytes(b"un")
        bea.write_bytes(b"deux")
        # Indexée par dossier, la rotation est un album.
        self.index_by_folder(self.rotation, "grouping=rotation")
        self.beet("modify", "-y", "genre=Rock", f"path:{ada}")
        self.beet("modify", "-y", "genre=Jazz", f"path:{bea}")
        before = self.items()
        self.assertEqual(before["10-rotation/Ada - Un.mp3"]["album_id"], before["10-rotation/Bea - Deux.mp3"]["album_id"])

        bea.write_bytes(b"deux, corrige")
        os.utime(bea, (OLD, OLD))
        self.turn()
        self.turn()

        after = self.items()
        self.assertEqual(after["10-rotation/Ada - Un.mp3"], before["10-rotation/Ada - Un.mp3"])
        # Relu hors de son album : son id ne change pas.
        self.assertEqual(after["10-rotation/Bea - Deux.mp3"]["id"], before["10-rotation/Bea - Deux.mp3"]["id"])
        self.assertEqual(after["10-rotation/Bea - Deux.mp3"]["title"], "deux, corrige")
        self.assertIsNone(after["10-rotation/Bea - Deux.mp3"]["album_id"])

    def test_a_whole_bank_removed_at_once_leaves_the_library(self) -> None:
        bank = self.media / "20-archives" / "jazz"
        bank.mkdir()
        # Plus que SQLite n'en prend dans une requête : la boucle les retire par paquets.
        count = MOST_IDS + 2
        for number in range(count):
            (bank / f"Cy - Live {number}.flac").write_bytes(b"%d" % number)
        self.index_by_folder(bank, "grouping=jazz", "genre=Archive")
        soul = self.media / "20-archives" / "soul"
        soul.mkdir()
        (soul / "Eve - Live.flac").write_bytes(b"live")
        self.index_by_folder(soul, "grouping=soul", "genre=Archive")
        self.assertEqual(len(self.items()), count + 1)

        shutil.rmtree(bank)
        removed = self.turn()

        self.assertEqual(self.groupings(), {"20-archives/soul/Eve - Live.flac": "soul"})
        self.assertIn(f"{count} titre(s) retiré(s)", removed.stdout)


if __name__ == "__main__":
    # Le faux beet, posé par setUp, rappelle ce fichier.
    if sys.argv[1:2] == ["beet"]:
        code = fake_beet(Path(sys.argv[2]), sys.argv[3:])
        note_selection(Path(sys.argv[2]))
        sys.exit(code)
    unittest.main()
