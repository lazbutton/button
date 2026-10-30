"""
Demo data for the console's end-to-end runs (``scripts/e2e.sh``).

    poetry run python -m tests.e2e.seed RUN_DIR

RUN_DIR is a new folder, ignored by git, for one run only. The seed fills it:

- ``radio_data/``: an instance made by ``radiotomate develop``, with one account
  per console role, the carts the default clocks name, a cart of music for the
  demo mode, and a clock for every slot of the week, so that the antenna does
  not depend on the time of the run;
- ``media/``: a small media bank, to start the engine with ``MEDIA_ROOT`` there
  and for the fake catalog (``console/e2e/stubs/``);
- ``comptes.json``: the accounts and their password, drawn for this run only.

The audio files are short sine tones. Nothing here comes from a station.
"""

from __future__ import annotations

import asyncio
import json
import math
import secrets
import subprocess
import sys
import wave
from pathlib import Path

from radiotomate.commands import load_config
from radiotomate.db import PathLike, QuartAlchemy
from radiotomate.enums import CartMode, ScheduleMode
from radiotomate.models import AutoDJSlot, Cart, Sound, User
from radiotomate.services.autodj import create_clock

# The flags the console writes for each role: permissionsFromRole() in
# console/src/api/roles.ts.
ROLES = {
    "admin": {"admin": True},
    "programmateur": {"live": True, "carts": True, "autodj": True},
    "animateur": {"live": True},
}

# title, mode, schedule mode, folder, sounds as (title, seconds, frequency).
# The demo mode airs as music the sounds of carts named neither jingle nor pub.
CARTS = (
    (
        "Jingles",
        CartMode.RANDOM,
        ScheduleMode.JINGLES,
        "jingles",
        (("Jingle grave", 4, 330), ("Jingle aigu", 4, 660)),
    ),
    (
        "Pubs",
        CartMode.RANDOM,
        ScheduleMode.CLOCK,
        "pubs",
        (("Annonce partenaire", 20, 495),),
    ),
    (
        "Musique de démo",
        CartMode.PLAYLIST,
        ScheduleMode.CLOCK,
        "musique",
        (
            ("Les Ondes Courtes - Première écoute", 180, 220),
            ("Trio Modulation - Nuit claire", 180, 262),
            ("Fréquence Libre - Signal faible", 180, 294),
        ),
    ),
)

CLOCK = "Horloge des parcours"

# Relative to the bank. Without tags, the catalog titles a file by its name.
BANK = (
    ("10-rotation/Quatuor Antenne - Grande distance.wav", 180, 349),
    ("10-rotation/Les Porteuses - Bande large.wav", 180, 392),
    ("30-habillage/jingles/Jingle station.wav", 4, 523),
    ("30-habillage/pubs/Annonce locale.wav", 20, 587),
)


def write_tone(path: Path, seconds: int, frequency: int, rate: int = 8000) -> None:
    """A quiet sine in 8-bit mono: 8 kB a second, played by any browser."""
    second = bytes(
        128 + round(24 * math.sin(2 * math.pi * frequency * index / rate))
        for index in range(rate)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(1)
        handle.setframerate(rate)
        handle.writeframes(second * seconds)


async def fill(db: QuartAlchemy, data_root: Path, password: str) -> None:
    async with db.session.begin() as session:
        users = {}
        for username, permissions in ROLES.items():
            user = User(username=username)
            user.update_password(password)
            user.update_permissions_map(permissions)
            session.add(user)
            users[username] = user
        await session.flush()

        for title, mode, schedule_mode, folder, sounds in CARTS:
            cart_path = data_root / "carts" / folder
            cart = Cart(
                title=title,
                path=cart_path,
                mode=mode,
                schedule_mode=schedule_mode,
            )
            session.add(cart)
            await session.flush()
            for rank, (sound_title, seconds, frequency) in enumerate(sounds, 1):
                path = cart_path / f"{rank:02d}.wav"
                write_tone(path, seconds, frequency)
                session.add(
                    Sound(
                        cart_id=cart.id,
                        rank=rank,
                        path=path,
                        duration=seconds,
                        title=sound_title,
                        gain=-1.0,
                        peak=-0.5,
                        uploader_id=users["admin"].id,
                    )
                )
        await session.flush()

        clock = await create_clock(
            session,
            {
                "name": CLOCK,
                "fallback_cart": "Jingles",
                "motif": [
                    {"kind": "jingle", "cart": "Jingles"},
                    {"kind": "musique", "category": "Rotation"},
                    {"kind": "musique", "category": "Rotation"},
                    {"kind": "musique", "category": "Rotation"},
                ],
            },
        )
        await session.flush()
        for slot in await AutoDJSlot.all(session):
            slot.clock_id = clock.id
            slot.title = clock.name
    await db.after_serving()


def seed(run_dir: Path) -> None:
    # The instance itself: configuration, database and schema, as a developer gets it.
    run_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "radiotomate.commands.main", "develop", "--quiet"],
        cwd=run_dir,
        check=True,
    )
    config = load_config(run_dir / "radio_data" / "radiotomate.yaml")
    data_root = Path(config["data"]["root"])
    PathLike.base_path = data_root
    db = QuartAlchemy()
    db.init_from_config(config["db"], {})
    password = secrets.token_urlsafe(18)
    asyncio.run(fill(db, data_root, password))

    for relative, seconds, frequency in BANK:
        write_tone(run_dir / "media" / relative, seconds, frequency)

    accounts = {"password": password, "accounts": {role: role for role in ROLES}}
    path = run_dir / "comptes.json"
    path.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
    path.chmod(0o600)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m tests.e2e.seed RUN_DIR")
    seed(Path(sys.argv[1]).resolve())
