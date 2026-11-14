"""
La base du moteur du banc : un bac qui suit un dossier de l'habillage, et une
diffusion de l'Agenda avec un set pris dans la banque.

Elle est semée comme celle des parcours de la console (`tests/e2e/seed.py`), par
les modèles, et se relit par SQL : le banc n'a pas besoin du moteur pour
vérifier que les bacs gardent leurs sons et l'Agenda ses fichiers.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from radiotomate.commands import load_config
from radiotomate.db import PathLike, QuartAlchemy
from radiotomate.domain.agenda import AIR_UPCOMING, KIND_SET, ORIGIN_BANK
from radiotomate.enums import CartMode, ScheduleMode
from radiotomate.models import Cart, Sound, User
from radiotomate.models.agenda import AgendaDiffusion, AgendaFile
from radiotomate.services.media_bank import AUDIO_SUFFIXES


def audio_in(folder: Path) -> list[Path]:
    """Les fichiers audio d'un dossier, à plat, par ordre de nom."""
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in AUDIO_SUFFIXES
    )


def pick_cart_folder(media: Path) -> Path | None:
    """Le premier dossier de l'habillage qui a de l'audio : celui que suit le bac."""
    top = media / "30-habillage"
    for folder in sorted(top.glob("*")) if top.is_dir() else []:
        if folder.is_dir() and audio_in(folder):
            return folder
    return None


def pick_set(media: Path) -> Path | None:
    """Le premier fichier audio des émissions : le set de la diffusion."""
    top = media / "40-emissions"
    if not top.is_dir():
        return None
    for path in sorted(top.rglob("*")):
        if (
            path.is_file()
            and not path.name.startswith(".")
            and path.suffix.lower() in AUDIO_SUFFIXES
        ):
            return path
    return None


async def _fill(
    db: QuartAlchemy,
    data_root: Path,
    cart_folder: Path | None,
    set_file: Path | None,
    media: Path,
) -> None:
    async with db.session.begin() as session:
        admin = User(username="admin")
        admin.update_password("banc")
        admin.update_permissions_map({"admin": True})
        session.add(admin)
        await session.flush()
        if cart_folder is not None:
            cart = Cart(
                title="Bac du banc",
                path=data_root / "carts" / "banc",
                mode=CartMode.PLAYLIST,
                schedule_mode=ScheduleMode.CLOCK,
                bank_folder=cart_folder.relative_to(media).as_posix(),
            )
            session.add(cart)
            await session.flush()
            for rank, path in enumerate(audio_in(cart_folder), 1):
                session.add(
                    Sound(
                        cart_id=cart.id,
                        rank=rank,
                        path=path,
                        duration=2,
                        title=path.stem,
                        gain=-1.0,
                        peak=-0.5,
                        uploader_id=admin.id,
                    )
                )
        if set_file is not None:
            starts = datetime.utcnow() + timedelta(days=1)
            diffusion = AgendaDiffusion(
                kind=KIND_SET,
                title="Set du banc",
                starts_at=starts,
                ends_at=starts + timedelta(hours=1),
                air_status=AIR_UPCOMING,
            )
            session.add(diffusion)
            await session.flush()
            session.add(
                AgendaFile(
                    diffusion_id=diffusion.id,
                    path=set_file.relative_to(media).as_posix(),
                    origin=ORIGIN_BANK,
                    original_name=set_file.name,
                    duration=2,
                    report={"status": "ok"},
                )
            )
    await db.after_serving()


def seed(moteur: Path, media: Path) -> Path:
    """Une instance neuve dans `moteur`, avec son bac et son set. Rend sa base."""
    moteur.mkdir(parents=True, exist_ok=True)
    os.environ["MEDIA_ROOT"] = str(media)
    subprocess.run(
        [sys.executable, "-m", "radiotomate.commands.main", "develop", "--quiet"],
        cwd=moteur,
        check=True,
        capture_output=True,
    )
    config = load_config(moteur / "radio_data" / "radiotomate.yaml")
    data_root = Path(config["data"]["root"])
    PathLike.base_path = data_root
    db = QuartAlchemy()
    db.init_from_config(config["db"], {})
    asyncio.run(_fill(db, data_root, pick_cart_folder(media), pick_set(media), media))
    files = sorted((moteur / "radio_data").rglob("*.db"))
    if not files:
        raise RuntimeError("Le moteur n'a pas créé sa base.")
    return files[0]


def read(db_file: Path) -> dict[str, list]:
    """Ce que la base dit des fichiers : les sons des bacs, ceux de l'Agenda."""
    with closing(sqlite3.connect(db_file)) as con:
        sounds = con.execute(
            "select cart_id, rank, path from sounds order by cart_id, rank"
        ).fetchall()
        agenda = con.execute(
            "select diffusion_id, path from agenda_files "
            "where replaced_at is null order by id"
        ).fetchall()
    return {"sons": sounds, "agenda": agenda}
