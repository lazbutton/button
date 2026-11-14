"""
Le banc de la banque : les gestes qui écrivent dans les fichiers, rejoués sur
une copie de vraie banque avant d'aller sur une station (TST-16).

    cd engine
    # une copie de vraie banque
    poetry run python -m tests.banque.banc --echantillon DOSSIER
    # des fichiers fabriqués
    poetry run python -m tests.banque.banc --fabrique
    # le dossier que dit BUTTON_BANQUE_ECHANTILLON
    ../scripts/verifier.sh banque

L'échantillon est un dossier qui a le rangement d'une banque : `10-rotation`,
`20-archives/<collection>`, `30-habillage`, `40-emissions`. Le banc ne le
touche jamais : il en fait une copie dans un dossier temporaire, y monte la vraie
boucle de Beets (`deploy/scripts/beets-import-loop.sh`, comme sur une station) et
une base du moteur avec un bac et un set de l'Agenda, rejoue les gestes, puis
efface la copie. À la fin il relit l'échantillon : il doit être resté tel quel.

Rien de l'échantillon ne sort du banc dans le rapport : ni titre, ni chemin, ni
nom de collection. Un titre y est « rotation n° 4 », une collection
« collection 2 ». `--detail FICHIER` écrit, sur la machine seulement, ce que
ces numéros désignent.

Les gestes du catalogue (`services/catalog/bank_api.py`) : déplacer des titres
vers une collection, les ramener, en retirer. Le catalogue passe les déplacements
au moteur, qui garde l'identité de chaque titre (ARC-09), comme sur une station
où le rangement est allumé. Chaque fiche du chantier « Ranger la banque » qui
écrit dans un fichier ajoute le sien :

1. une fonction `geste_<nom>(banc)` qui fait le geste sur des titres choisis par
   `banc.choisir`, puis appelle `banc.controler(...)` ;
2. son nom dans `GESTES`.

Un défaut connu, que corrige une fiche à venir, s'écrit `connu="<fiche>"` dans
son contrôle : le banc le dit sans échouer. Une fois la fiche livrée, le contrôle
réussit, et le banc échoue pour qu'on en retire l'exception, comme `test.fixme`
dans les parcours.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from mediafile import MediaFile
from mutagen import File as MutagenFile

from radiotomate.services.media_bank import AUDIO_SUFFIXES
from tests.banque import fabrique, semis
from tests.test_beets_import_loop import _station, _turn

ENGINE = Path(__file__).parents[2]
REPO = ENGINE.parent
CATALOG = REPO / "services" / "catalog"
VARIABLE = "BUTTON_BANQUE_ECHANTILLON"
ABSENT = 75
# Les dossiers de tête que la boucle indexe, et ce que le banc en dit.
ROTATION = "10-rotation"
COLLECTIONS = "20-archives"
TRASH = "90-trash"
TOPS = {
    ROTATION: "rotation",
    COLLECTIONS: "collection",
    "30-habillage": "habillage",
    "40-emissions": "émissions",
    "50-carts": "bacs",
}
# Les tours de la boucle pour qu'une banque se pose : un pour voir un dossier,
# un pour l'indexer, un pour que ce qu'elle écrit ne compte plus.
TURNS_MIN = 3
TURNS_MAX = 8
# Les titres de chaque geste : peu, le banc compte la durée de la boucle.
MOVED = 3
REMOVED = 2
CORRECTED = 4
# Ce que le banc écrit dans les fiches corrigées : rien d'une station.
CORRECTION = {"album": "Banc", "year": "1999", "genre": "Banc", "famille": "jazz"}
# Ce que la bibliothèque en garde.
CORRECTED_FICHE = {"album": "Banc", "year": 1999, "genre": "Banc", "famille": "jazz"}


def reasons(status: int, answer: dict) -> str:
    """Pourquoi le catalogue n'a pas tout fait, sans le nom d'un titre."""
    if status != 200:
        return f"code {status}"
    return ", ".join(
        sorted({str(item.get("reason", "?")) for item in answer.get("failed", [])})
    )


def say(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_audio(path: Path) -> bool:
    return (
        path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in AUDIO_SUFFIXES
    )


def files_of(media: Path) -> dict[str, Path]:
    """Les fichiers de la banque, hors corbeille et fichiers cachés, par chemin."""
    found = {}
    for folder, dirs, names in os.walk(media):
        dirs[:] = sorted(name for name in dirs if not name.startswith("."))
        for name in sorted(names):
            if name.startswith("."):
                continue
            path = Path(folder) / name
            rel = path.relative_to(media).as_posix()
            if rel.split("/", 1)[0] != TRASH and path.is_file():
                found[rel] = path
    return found


def fingerprint(folder: Path) -> str:
    """Les noms, les tailles et les dates : ce qui dit qu'un dossier n'a pas bougé."""
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        try:
            info = path.lstat()
        except OSError:
            continue
        digest.update(
            os.fsencode(
                f"{path.relative_to(folder)}\0{info.st_size}\0{info.st_mtime_ns}\0"
            )
        )
    return digest.hexdigest()


@dataclass
class Verdict:
    geste: str
    controle: str
    ok: bool
    detail: str = ""
    connu: str = ""

    @property
    def etat(self) -> str:
        if self.connu:
            return "inattendu" if self.ok else "connu"
        return "ok" if self.ok else "échec"


@dataclass
class Banc:
    work: Path
    reader: str = "ffprobe"
    verdicts: list[Verdict] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    info: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.media = self.work / "media"
        self.library = self.work / "data" / "Beets" / "library.db"
        self.refs: dict[str, str] = {}
        self.readable: set[str] = set()
        self.hashes: dict[str, str] = {}
        self.base: dict[str, list] = {}
        self.db_file: Path | None = None
        self.hashes_copy: dict[str, str] = {}
        # L'identifiant de Beets qu'un titre avait au départ, suivi de chemin en chemin.
        self.identity: dict[str, int] = {}
        self.archives_count = 0
        # Ce que `déplacer` laisse à `ramener`.
        self.moved: dict[str, str] = {}
        self.tags_before: dict[str, dict] = {}
        self.destination = ""
        sys.path.insert(0, str(CATALOG))

    # -- la copie et la boucle ---------------------------------------------------

    def prepare(self, source: Path | None) -> None:
        """La station du banc, puis la banque : l'échantillon copié, ou fabriquée."""
        start = time.monotonic()
        _station(self.work)
        # Le dossier d'exemple de la station neuve n'est pas celui de l'échantillon.
        shutil.rmtree(self.media / COLLECTIONS / "jazz", ignore_errors=True)
        if source is None:
            self.info["formats"] = fabrique.fabricate(self.media)
        else:
            # Les liens sont suivis : la copie n'en garde aucun, et rien qu'elle
            # écrive ne peut revenir dans l'échantillon.
            shutil.copytree(
                source,
                self.media,
                symlinks=False,
                ignore_dangling_symlinks=True,
                dirs_exist_ok=True,
            )
        self.timings["copie"] = time.monotonic() - start
        (self.media / TRASH).mkdir(exist_ok=True)
        files = files_of(self.media)
        self.hashes_copy = {
            rel: sha(path) for rel, path in files.items() if is_audio(path)
        }
        self.name_refs(files)

    def name_refs(self, files: dict[str, Path]) -> None:
        """« rotation n° 4 », « collection 2 n° 7 » : un titre sans son nom."""
        archives = sorted(
            {
                rel.split("/")[1]
                for rel in files
                if rel.startswith(f"{COLLECTIONS}/") and rel.count("/") > 1
            },
            key=str.casefold,
        )
        self.archives_count = len(archives)
        counts: dict[str, int] = {}
        for rel in sorted(files):
            parts = rel.split("/")
            zone = TOPS.get(parts[0], "autre")
            if zone == "collection" and len(parts) > 2:
                zone = f"collection {archives.index(parts[1]) + 1}"
            counts[zone] = counts.get(zone, 0) + 1
            self.refs[rel] = f"{zone} n° {counts[zone]}"

    def ref(self, rel: str) -> str:
        return self.refs.get(rel, "un titre déplacé")

    def turns(self, *, minimum: int = TURNS_MIN) -> int:
        """La boucle jusqu'à ce que la bibliothèque se calme. Rend ses tours."""
        start = time.monotonic()
        before = self.snapshot()
        done = 0
        calm = 0
        while done < TURNS_MAX:
            _turn(self.work)
            done += 1
            after = self.snapshot()
            calm = calm + 1 if after == before else 0
            before = after
            if done >= minimum and calm >= 1:
                break
        self.timings["boucle"] = (
            self.timings.get("boucle", 0.0) + time.monotonic() - start
        )
        return done

    def snapshot(self) -> dict[str, tuple]:
        """La bibliothèque de Beets, par chemin relatif à la banque."""
        if not self.library.exists():
            return {}
        with closing(sqlite3.connect(f"file:{self.library}?mode=ro", uri=True)) as con:
            if not con.execute(
                "select 1 from sqlite_master where name = 'items'"
            ).fetchone():
                return {}
            rows = con.execute(
                # Beets 2.14 range le genre dans une liste, genres (ARC-06).
                "select path, id, album_id, grouping, genres, rg_track_gain, title "
                "from items"
            ).fetchall()
        return {
            Path(os.fsdecode(path)).relative_to(self.media).as_posix(): tuple(values)
            for path, *values in rows
        }

    def read_ok(self, path: Path) -> bool:
        """Le fichier se lit : ffprobe sait sa durée, ou à défaut mutagen son format."""
        if self.reader == "ffprobe":
            done = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "csv=p=0",
                    str(path),
                ],
                capture_output=True,
                encoding="utf-8",
                check=False,
                timeout=60,
            )
            return done.returncode == 0 and done.stdout.strip() not in {"", "N/A"}
        try:
            return MutagenFile(path) is not None
        except Exception:
            return False

    # -- le moteur ---------------------------------------------------------------

    def engine(self) -> None:
        self.db_file = semis.seed(self.work / "moteur", self.media)
        self.base = semis.read(self.db_file)

    # -- ce que le banc choisit --------------------------------------------------

    def unique(self, rel: str) -> bool:
        """Le nom du fichier est unique : un titre déplacé se suit par lui."""
        name = rel.rsplit("/", 1)[-1]
        return sum(1 for other in self.hashes if other.rsplit("/", 1)[-1] == name) == 1

    def choisir(
        self, folder: str, count: int, *, ignore: set[str] = frozenset()
    ) -> list[str]:
        """Des titres à plat dans un dossier : indexés, lisibles, au nom unique."""
        indexed = self.snapshot()
        chosen = [
            rel
            for rel in sorted(indexed)
            if rel.startswith(folder + "/")
            and rel.count("/") == folder.count("/") + 1
            and rel in self.readable
            and rel not in ignore
            and self.unique(rel)
        ]
        return chosen[:count]

    def archive(self) -> tuple[str, str] | None:
        """La première collection : son identifiant pour le catalogue, son dossier."""
        import inbox_api

        for row in inbox_api.destination_list(self.media):
            if row["group"] == "archives":
                return row["id"], row["folder"]
        return None

    # -- ce que le banc vérifie --------------------------------------------------

    def verdict(
        self, geste: str, controle: str, ok: bool, detail: str = "", *, connu: str = ""
    ) -> Verdict:
        verdict = Verdict(geste, controle, ok, detail, connu)
        self.verdicts.append(verdict)
        marque = {
            "ok": "ok   ",
            "échec": "ÉCHEC",
            "connu": "connu",
            "inattendu": "ÉCHEC",
        }[verdict.etat]
        say(f"  [{marque}] {geste} : {controle}{' — ' + detail if detail else ''}")
        return verdict

    def controler(
        self,
        geste: str,
        avant: dict[str, tuple],
        moved: dict[str, str],
        removed: dict[str, str],
        corrected: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        """Ce que doit être vrai après un geste, une fois la boucle passée.

        `moved` : ancien chemin → nouveau. `removed` : ancien chemin → empreinte.
        `corrected` : les titres dont la fiche a changé, qui restent à leur place.
        """
        for old, new in moved.items():
            self.refs[new] = self.refs.get(old, "un titre déplacé")
        self.turns()
        apres = self.snapshot()
        touched = set(moved) | set(removed) | set(corrected)
        gone = [self.ref(rel) for rel in set(moved) | set(removed) if rel in apres]
        self.verdict(
            geste,
            "les anciens chemins sont sortis de la bibliothèque",
            not gone,
            ", ".join(gone),
        )
        # Les titres que le geste n'a pas touchés gardent leur identifiant et leurs
        # champs.
        changed = [
            self.ref(rel)
            for rel, row in avant.items()
            if rel not in touched and apres.get(rel) != row
        ]
        self.verdict(
            geste,
            "aucun identifiant de Beets ne change hors des titres touchés",
            not changed,
            f"{len(changed)} titre(s), dont {', '.join(changed[:5])}"
            if changed
            else "",
        )
        files = files_of(self.media)
        edited = [
            self.ref(rel)
            for rel, digest in self.hashes.items()
            if rel not in touched and rel in files and sha(files[rel]) != digest
        ]
        self.verdict(
            geste,
            "les fichiers non touchés gardent leurs octets",
            not edited,
            ", ".join(edited[:5]),
        )
        if moved:
            absent = [self.ref(new) for new in moved.values() if new not in apres]
            self.verdict(
                geste,
                "les titres déplacés sont dans la bibliothèque",
                not absent,
                ", ".join(absent),
            )
            # Beets réutilise l'identifiant d'un titre retiré : seul celui du
            # départ dit si c'est le même titre.
            same = [
                old
                for old, new in moved.items()
                if new in apres and apres[new][0] == self.identity.get(old)
            ]
            self.verdict(
                geste,
                "un titre déplacé garde son identifiant de Beets",
                len(same) == len(moved),
                f"{len(same)} sur {len(moved)}",
            )
        if corrected:
            kept = [
                rel
                for rel in corrected
                if rel in apres and avant.get(rel, (None,))[0] == apres[rel][0]
            ]
            self.verdict(
                geste,
                "un titre corrigé garde son identifiant de Beets",
                len(kept) == len(corrected),
                f"{len(kept)} sur {len(corrected)}",
            )
        if removed:
            in_trash = {
                sha(path) for path in (self.media / TRASH).iterdir() if path.is_file()
            }
            missing = [
                self.ref(old)
                for old, digest in removed.items()
                if digest not in in_trash
            ]
            self.verdict(
                geste,
                "les titres retirés sont dans la corbeille",
                not missing,
                ", ".join(missing),
            )
        # Les chemins que suit le banc : ceux d'après le geste.
        for old, new in moved.items():
            self.hashes[new] = self.hashes.pop(old, "")
            if old in self.identity:
                self.identity[new] = self.identity.pop(old)
            if old in self.readable:
                self.readable.discard(old)
                self.readable.add(new)
        for old in removed:
            self.hashes.pop(old, None)
            self.readable.discard(old)
        # Les titres déplacés ou corrigés ont reçu des tags : leurs octets ont changé.
        for new in [*moved.values(), *corrected]:
            if new in files:
                self.hashes[new] = sha(files[new])
        unreadable = [
            self.ref(rel)
            for rel in sorted(self.readable)
            if rel not in files or not self.read_ok(files[rel])
        ]
        self.verdict(
            geste,
            "chaque fichier se lit encore",
            not unreadable,
            ", ".join(unreadable[:5]),
        )
        self.controler_moteur(geste)
        # La boucle suivante ne réimporte rien.
        self.turns(minimum=1)
        self.verdict(
            geste,
            "la boucle suivante ne réimporte rien",
            self.snapshot() == apres,
        )

    def controler_moteur(self, geste: str) -> None:
        """Les bacs gardent leurs sons, et l'Agenda ses fichiers."""
        assert self.db_file is not None
        now = semis.read(self.db_file)
        lost = []
        for _cart, _rank, path in now["sons"]:
            rel = path.removeprefix("media:")
            if not (self.media / rel).is_file():
                lost.append(self.ref(rel))
        for _diffusion, rel in now["agenda"]:
            if not (self.media / rel).is_file():
                lost.append(self.ref(rel))
        self.verdict(
            geste,
            "les bacs gardent leurs sons et l'Agenda ses fichiers",
            now == self.base and not lost,
            ", ".join(lost[:5]),
        )


# -- les gestes ------------------------------------------------------------------


def geste_deplacer(banc: Banc) -> None:
    """Des titres de la rotation vers une collection, par le catalogue."""
    import bank_api

    say("Geste : déplacer des titres de la rotation vers une collection")
    target = banc.archive()
    titles = banc.choisir(ROTATION, MOVED)
    if target is None or not titles:
        say("  (rien à déplacer : il manque une collection ou des titres)")
        banc.info["deplacer"] = False
        return
    banc.info["deplacer"] = True
    destination, folder = target
    names = [rel.rsplit("/", 1)[-1] for rel in titles]
    avant = banc.snapshot()
    banc.moved = {rel: f"{folder}/{rel.rsplit('/', 1)[-1]}" for rel in titles}
    banc.tags_before = {
        new: tags_of(banc.media / old) for old, new in banc.moved.items()
    }
    banc.destination = destination
    status, answer = bank_api.move_files(
        banc.media, "rotation", destination, names, engine=_par_le_moteur(banc)
    )
    banc.verdict(
        "déplacer",
        "le catalogue et le moteur déplacent les titres",
        status == 200 and not answer.get("failed"),
        reasons(status, answer),
    )
    banc.controler("déplacer", avant, banc.moved, {})


def geste_revenir(banc: Banc) -> None:
    """Les mêmes titres, ramenés à la rotation : les valeurs d'avant reviennent."""
    import bank_api

    if not banc.info.get("deplacer"):
        return
    say("Geste : ramener ces titres à la rotation")
    names = [new.rsplit("/", 1)[-1] for new in banc.moved.values()]
    avant = banc.snapshot()
    status, answer = bank_api.move_files(
        banc.media, banc.destination, "rotation", names, engine=_par_le_moteur(banc)
    )
    banc.verdict(
        "ramener",
        "le catalogue et le moteur ramènent les titres",
        status == 200 and not answer.get("failed"),
        reasons(status, answer),
    )
    back = {new: f"{ROTATION}/{new.rsplit('/', 1)[-1]}" for new in banc.moved.values()}
    banc.controler("ramener", avant, back, {})
    different = [
        banc.ref(new)
        for new_before, tags in banc.tags_before.items()
        for new in [back[new_before]]
        if tags_of(banc.media / new) != tags
    ]
    banc.verdict(
        "ramener",
        "les tags d'avant le déplacement reviennent",
        not different,
        ", ".join(different),
    )


def _par_le_moteur(banc: Banc):
    """Le moteur qui reçoit les déplacements du catalogue (`engine_move`), le
    rangement allumé : son service, sur la bibliothèque et la base du banc."""

    def moves(asked: list[dict]) -> tuple[int, dict]:
        report = asyncio.run(_deplacer(banc, [(m["from"], m["to"]) for m in asked]))
        banc.info["lot"] = report.entry
        return 200, report.payload()

    return moves


async def _engine_session(banc: Banc):
    from radiotomate.db import QuartAlchemy
    from radiotomate.models import Setting
    from radiotomate.services import bank_titles

    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{banc.db_file}"}, {})
    async with db.session() as session:
        await Setting.upsert(session, bank_titles.SETTING_BANK_TIDY, "1")
        await session.commit()
    return db


async def _deplacer(banc: Banc, moves: list[tuple[str, str]]) -> object:
    from radiotomate.services import bank_moves
    from radiotomate.services.bank_lock import BeetsPlace

    place = BeetsPlace.of(_beets(banc).lib)
    db = await _engine_session(banc)
    async with db.session() as session:
        report = await bank_moves.move_titles(session, place, moves, username="banc")
    await db.after_serving()
    return report


async def _annuler(banc: Banc, entry_id: int) -> object:
    from radiotomate.services import journal

    beets = _beets(banc)
    db = await _engine_session(banc)
    async with db.session() as session:
        outcome = await journal.undo(session, beets, entry_id, username="banc")
    await db.after_serving()
    return outcome


def geste_annuler(banc: Banc) -> None:
    """Des titres déplacés par le moteur, puis « Annuler » dans le journal (FON-71)."""
    say("Geste : déplacer des titres, puis annuler le déplacement")
    target = banc.archive()
    titles = banc.choisir(ROTATION, MOVED)
    if target is None or not titles:
        say("  (rien à déplacer : il manque une collection ou des titres)")
        return
    moved = {rel: f"{target[1]}/{rel.rsplit('/', 1)[-1]}" for rel in titles}
    avant = banc.snapshot()
    report = asyncio.run(_deplacer(banc, list(moved.items())))
    banc.verdict(
        "annuler",
        "le moteur déplace les titres, et note le lot au journal",
        not report.failed and report.entry is not None,
        ", ".join(sorted({row["reason"] for row in report.failed})),
    )
    if report.entry is None:
        return
    outcome = asyncio.run(_annuler(banc, report.entry))
    banc.verdict(
        "annuler",
        "« Annuler » ramène chaque titre",
        len(outcome.written) == len(titles) and not outcome.kept,
        f"{len(outcome.written)} sur {len(titles)}",
    )
    back = [banc.ref(rel) for rel in titles if not (banc.media / rel).is_file()]
    banc.verdict(
        "annuler",
        "chaque fichier est revenu à son chemin d'avant",
        not back,
        ", ".join(back[:5]),
    )
    # Entre les deux, la boucle n'a pas tourné : elle ne voit que l'aller-retour.
    banc.controler("déplacer puis annuler", avant, {}, {}, set(titles))


def geste_retirer(banc: Banc) -> None:
    """Des titres de la rotation et d'une collection, retirés par le catalogue."""
    import bank_api

    say("Geste : retirer des titres par le catalogue")
    titles = banc.choisir(ROTATION, REMOVED)
    target = banc.archive()
    others = banc.choisir(target[1], 1) if target else []
    if not titles and not others:
        say("  (rien à retirer dans cet échantillon)")
        return
    avant = banc.snapshot()
    removed = {}
    for destination, label, rels in (
        ("rotation", "de la rotation", titles),
        (target[0] if target else "", "d'une collection", others),
    ):
        if not rels:
            continue
        removed.update({rel: sha(banc.media / rel) for rel in rels})
        names = [rel.rsplit("/", 1)[-1] for rel in rels]
        status, answer = bank_api.remove_files(banc.media, destination, names)
        banc.verdict(
            "retirer",
            f"le catalogue retire les titres ({label})",
            status == 200 and not answer.get("failed"),
            reasons(status, answer),
        )
    banc.controler("retirer", avant, {}, removed)


def fiche_of(path: Path) -> dict[str, object]:
    """Ce que les tags d'un fichier disent des champs que FON-66 corrige."""
    track = MediaFile(path)
    return {
        "album": track.album or "",
        "year": track.year or 0,
        "genre": track.genre or "",
        "title": track.title or "",
        "artist": track.artist or "",
    }


def _beets(banc: Banc) -> object:
    """La bibliothèque du banc, écrite avec les réglages de Beets de sa station."""
    from beets import config as beets_config
    from beets.library import Library

    from radiotomate.beets import BeetsIntegration

    beets_config.set_file(str(banc.library.parent / "config.yaml"))
    beets = object.__new__(BeetsIntegration)
    # La racine que pose init-radiotomate.sh, comme sur une station : le dossier
    # de Beets depuis ARC-06, et la banque avant. Beets 2.14 lit une requête par
    # chemin relative à elle.
    beets.lib = Library(
        str(banc.library), directory=beets_config["directory"].as_filename()
    )
    return beets


async def _corriger(banc: Banc, rels: list[str]) -> tuple[object, object, dict]:
    """Corrige les fiches par le service du moteur, puis « Revenir » : rend les
    deux réponses, et ce que la bibliothèque disait après la correction."""
    from radiotomate.db import QuartAlchemy
    from radiotomate.models import Setting
    from radiotomate.services import bank_titles, title_edits

    beets = _beets(banc)
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{banc.db_file}"}, {})
    ids = {rel: row[0] for rel, row in banc.snapshot().items() if rel in rels}
    async with db.session() as session:
        await Setting.upsert(session, bank_titles.SETTING_BANK_TIDY, "1")
        await session.commit()
        edits = []
        for beets_id in ids.values():
            item = beets.lib.get_item(beets_id)
            expected = {
                name: title_edits.current_value(item, name) for name in CORRECTION
            }
            edits.append(title_edits.TitleEdit(beets_id, CORRECTION, expected))
        outcome = await title_edits.edit_titles(session, beets, edits, username="banc")
        library = {
            rel: {
                name: title_edits.current_value(beets.lib.get_item(beets_id), name)
                for name in CORRECTION
            }
            for rel, beets_id in ids.items()
        }
        undone = None
        if outcome.entry_id is not None:
            undone = await title_edits.undo_entry(
                session, beets, outcome.entry_id, username="banc"
            )
    await db.after_serving()
    return outcome, undone, library


def geste_corriger(banc: Banc) -> None:
    """Un lot de fiches corrigé par le service du moteur (FON-66), puis « Revenir »."""
    say("Geste : corriger un lot de fiches, puis revenir")
    target = banc.archive()
    titles = banc.choisir(ROTATION, CORRECTED)
    titles += banc.choisir(target[1], 2) if target else []
    if not titles:
        say("  (rien à corriger dans cet échantillon)")
        return
    avant = banc.snapshot()
    before = {rel: fiche_of(banc.media / rel) for rel in titles}
    outcome, undone, library = asyncio.run(_corriger(banc, titles))
    banc.verdict(
        "corriger",
        "le moteur écrit tout le lot",
        len(outcome.written) == len(titles)
        and not outcome.waiting
        and not outcome.refused,
        f"{len(outcome.written)} sur {len(titles)}",
    )
    in_library = [
        banc.ref(rel) for rel, values in library.items() if values != CORRECTED_FICHE
    ]
    banc.verdict(
        "corriger",
        "la bibliothèque porte la correction, famille comprise",
        not in_library,
        ", ".join(in_library[:5]),
    )
    # « Revenir » a déjà rendu les tags : la correction se lit dans le journal,
    # et ce que dit le fichier se compare à l'avant.
    after = {rel: fiche_of(banc.media / rel) for rel in titles}
    banc.verdict(
        "revenir",
        "« Revenir » remet le lot entier",
        undone is not None and len(undone.written) == len(titles) and not undone.kept,
        f"{len(undone.written) if undone else 0} sur {len(titles)}",
    )
    different = [banc.ref(rel) for rel in titles if after[rel] != before[rel]]
    banc.verdict(
        "revenir",
        "les tags d'avant la correction reviennent",
        not different,
        ", ".join(different[:5]),
    )
    famille = [
        banc.ref(rel)
        for rel in titles
        if "famille"
        in " ".join(map(str, (MutagenFile(banc.media / rel).tags or {}))).lower()
    ]
    banc.verdict(
        "corriger",
        "la famille ne va jamais dans le fichier",
        not famille,
        ", ".join(famille[:5]),
    )
    banc.controler("corriger et revenir", avant, {}, {}, set(titles))


def geste_corriger_puis_lire(banc: Banc) -> None:
    """Une correction gardée : le fichier la porte, et la boucle n'y voit rien."""
    say("Geste : corriger un lot de fiches, et le garder")
    titles = banc.choisir(ROTATION, CORRECTED)
    if not titles:
        return
    avant = banc.snapshot()
    outcome = asyncio.run(_garder(banc, titles))
    tags = {rel: fiche_of(banc.media / rel) for rel in titles}
    wrong = [
        banc.ref(rel)
        for rel, values in tags.items()
        if (values["album"], values["year"], values["genre"])
        != (CORRECTED_FICHE["album"], 1999, CORRECTED_FICHE["genre"])
    ]
    banc.verdict(
        "corriger",
        "les tags du fichier portent la correction",
        len(outcome.written) == len(titles) and not wrong,
        ", ".join(wrong[:5]),
    )
    banc.controler("corriger", avant, {}, {}, set(titles))


async def _garder(banc: Banc, rels: list[str]) -> object:
    from radiotomate.db import QuartAlchemy
    from radiotomate.models import Setting
    from radiotomate.services import bank_titles, title_edits

    beets = _beets(banc)
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{banc.db_file}"}, {})
    ids = [row[0] for rel, row in banc.snapshot().items() if rel in rels]
    async with db.session() as session:
        await Setting.upsert(session, bank_titles.SETTING_BANK_TIDY, "1")
        await session.commit()
        outcome = await title_edits.edit_titles(
            session,
            beets,
            [title_edits.TitleEdit(beets_id, CORRECTION) for beets_id in ids],
            username="banc",
        )
    await db.after_serving()
    return outcome


GESTES = [
    geste_deplacer,
    geste_revenir,
    geste_annuler,
    geste_retirer,
    geste_corriger,
    geste_corriger_puis_lire,
]


def tags_of(path: Path) -> dict[str, object]:
    track = MediaFile(path)
    return {
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "year": track.year,
        "length": round(track.length or 0, 1),
    }


# -- le banc ---------------------------------------------------------------------


def run(
    source: Path | None,
    work: Path,
    *,
    reader: str = "ffprobe",
    detail: Path | None = None,
) -> Banc:
    """Le banc entier, dans `work` : un dossier neuf, hors du dépôt."""
    banc = Banc(work, reader)
    before = fingerprint(source) if source else ""
    say("Copie et indexation")
    banc.prepare(source)
    files = files_of(banc.media)
    audio = {rel: path for rel, path in files.items() if is_audio(path)}
    banc.readable = {rel for rel, path in audio.items() if banc.read_ok(path)}
    banc.info["fichiers"] = len(files)
    banc.info["audio"] = len(audio)
    banc.info["illisibles"] = len(audio) - len(banc.readable)
    banc.info["octets"] = sum(path.stat().st_size for path in files.values())
    banc.info["archives"] = banc.archives_count
    banc.info["extensions"] = {}
    for rel in audio:
        ext = Path(rel).suffix.lower()
        banc.info["extensions"][ext] = banc.info["extensions"].get(ext, 0) + 1
    start = time.monotonic()
    turns = banc.turns()
    banc.info["tours"] = turns
    indexed = banc.snapshot()
    banc.info["indexes"] = len(indexed)
    banc.identity = {rel: row[0] for rel, row in indexed.items()}
    banc.info["non_indexes"] = len(
        [
            rel
            for rel in banc.readable
            if rel.split("/")[0] in (ROTATION, COLLECTIONS) and rel not in indexed
        ]
    )
    banc.hashes = {rel: sha(path) for rel, path in audio.items()}
    written = [
        rel
        for rel, digest in banc.hashes.items()
        if banc.hashes_copy.get(rel) != digest
    ]
    banc.info["tags_ecrits"] = len(written)
    banc.timings["indexation"] = time.monotonic() - start
    banc.engine()
    for geste in GESTES:
        geste(banc)
    if source is not None:
        banc.verdict(
            "échantillon",
            "l'échantillon est resté tel quel",
            fingerprint(source) == before,
        )
    if detail is not None:
        names = "".join(f"{ref}\t{rel}\n" for rel, ref in sorted(banc.refs.items()))
        detail.write_text(names, encoding="utf-8")
    return banc


def report(banc: Banc, *, fabricated: bool, seconds: float) -> str:
    """Le rapport : des nombres et des numéros, jamais un titre ni un chemin."""
    info = banc.info
    megabytes = int(info["octets"]) / (1 << 20)
    formats = ", ".join(
        f"{ext[1:]} {count}" for ext, count in sorted(info["extensions"].items())
    )
    lines = [
        "### Banc de la banque",
        "",
        f"- Banque : {'fabriquée' if fabricated else 'une copie de vraie banque'}, "
        f"{info['fichiers']} fichiers dont {info['audio']} audio ({formats}), "
        f"{megabytes:.0f} Mo, "
        f"{info['archives']} collection(s).",
        f"- Lecture : {info['audio'] - info['illisibles']} lisibles par {banc.reader}, "
        f"{info['illisibles']} illisibles dès la copie.",
        f"- Bibliothèque Beets : {info['indexes']} titres indexés en "
        f"{info['tours']} tours de la boucle ; "
        f"l'indexation a écrit des tags dans {info['tags_ecrits']} fichiers.",
        f"- Durée : {seconds:.0f} s, dont {banc.timings.get('boucle', 0):.0f} s "
        "de boucle.",
        "",
        "| Geste | Contrôle | Résultat |",
        "|---|---|---|",
    ]
    for verdict in banc.verdicts:
        result = {
            "ok": "ok",
            "échec": "**échec**",
            "connu": f"défaut connu ({verdict.connu})",
            "inattendu": f"**corrigé ?** ({verdict.connu})",
        }[verdict.etat]
        extra = f" : {verdict.detail}" if verdict.detail else ""
        lines.append(f"| {verdict.geste} | {verdict.controle} | {result}{extra} |")
    known = [verdict for verdict in banc.verdicts if verdict.etat == "connu"]
    if known:
        lines += ["", "Défauts connus, sans effet sur le résultat :"]
        lines += sorted(
            {
                f"- {verdict.connu} : {verdict.controle} ({verdict.detail})"
                for verdict in known
            }
        )
    return "\n".join(lines) + "\n"


def failed(banc: Banc) -> list[Verdict]:
    return [
        verdict for verdict in banc.verdicts if verdict.etat in {"échec", "inattendu"}
    ]


def check_source(source: Path) -> str | None:
    """Pourquoi cet échantillon ne convient pas, ou rien."""
    if not source.is_dir():
        return "L'échantillon n'est pas un dossier."
    resolved = source.resolve()
    if resolved == REPO or REPO in resolved.parents or resolved in REPO.parents:
        return (
            "L'échantillon est dans le dépôt, ou le contient : une copie de vraie "
            "banque reste hors du dépôt, "
            "sur la machine de développement."
        )
    if not any((resolved / top).is_dir() for top in (ROTATION, COLLECTIONS)):
        return (
            f"L'échantillon n'a ni {ROTATION} ni {COLLECTIONS} : il faut un dossier "
            "qui a le rangement d'une banque."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Le banc de la banque (TST-16).")
    parser.add_argument(
        "--echantillon",
        type=Path,
        default=os.environ.get(VARIABLE) or None,
        help=f"dossier d'une copie de banque (sinon {VARIABLE})",
    )
    parser.add_argument(
        "--fabrique",
        action="store_true",
        help="des fichiers fabriqués, sans copie de vraie banque",
    )
    parser.add_argument(
        "--rapport",
        type=Path,
        help="écrit le rapport dans ce fichier, en plus de l'afficher",
    )
    parser.add_argument(
        "--detail",
        type=Path,
        help="écrit sur cette machine ce que désignent les numéros du rapport",
    )
    options = parser.parse_args(argv)
    source = None if options.fabrique else options.echantillon
    if source is None and not options.fabrique:
        sys.stderr.write(
            f"Pas d'échantillon : donner un dossier à --echantillon, ou {VARIABLE}.\n"
        )
        return ABSENT
    if source is not None:
        problem = check_source(source)
        if problem:
            sys.stderr.write(problem + "\n")
            return 64
    if shutil.which("beet") is None:
        sys.stderr.write("beet absent : lancer le banc par « poetry run ».\n")
        return ABSENT
    # Une vraie banque se lit avec ffprobe, comme l'antenne. Des fichiers
    # fabriqués se passent de lui : le test du banc tourne aussi sans ffmpeg.
    reader = "ffprobe" if shutil.which("ffprobe") else "mutagen"
    if reader == "mutagen" and source is not None:
        sys.stderr.write("ffprobe absent : installer ffmpeg.\n")
        return ABSENT
    if source is not None:
        free = shutil.disk_usage(tempfile.gettempdir()).free
        size = sum(path.stat().st_size for path in source.rglob("*") if path.is_file())
        if size * 2 > free:
            sys.stderr.write(
                "Pas assez de place dans TMPDIR pour la copie de l'échantillon.\n"
            )
            return 1
    work = Path(tempfile.mkdtemp(prefix="banc-banque-")).resolve()
    start = time.monotonic()
    code = 1
    try:
        banc = run(source, work, reader=reader, detail=options.detail)
        text = report(banc, fabricated=source is None, seconds=time.monotonic() - start)
        say()
        say(text)
        if options.rapport:
            options.rapport.write_text(text, encoding="utf-8")
        bad = failed(banc)
        say(
            f"Banc de la banque : {len(bad)} échec(s) sur "
            f"{len(banc.verdicts)} contrôles."
        )
        code = 1 if bad else 0
    except Exception:
        traceback.print_exc()
        sys.stderr.write("Le banc s'est arrêté sur une erreur, au-dessus.\n")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
