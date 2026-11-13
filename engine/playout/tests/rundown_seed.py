"""
The base of the rundown bench: the first start of a station, in short, then
its settings, Beets, the sounds, the carts and a clock whose cuts on the minute
fall in the minutes that follow.

    python3 rundown_seed.py

It runs as root in the engine image, as `radiotomate-init` does on a station.
rundown.py and rundown_probe.py read its constants: nothing is imported up
here that only the image has. The sounds are sweeps made by ffmpeg, the
passwords are test ones: nothing comes from a station.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import sounds

DATA = Path("/data")
MEDIA = Path("/media")
CONFIG = DATA / "radiotomate.yaml"
# What the seed chose, for the probe and for rundown.py.
PLAN = DATA / "rundown.json"

# The console that reads the conducteur and makes the gestures, and the studio
# whose encoder sends the live.
CONSOLE = ("regie", "mot-de-passe-de-la-regie")
STUDIO = ("studio", "mot-de-passe-du-studio")

# The cleaner of the queues, at the lowest the scheduler and the playout take:
# a sound waits 30 s at most in a queue, and the cleaner looks every 15 s. On a
# station: ten minutes, every minute.
CLEAN_AGE = 30
CLEAN_INTERVAL = 15

# Seconds from the seed to the first cut on the minute, at least: the time for
# the antenna to start, then a minute of it. The conducteur has then said for a
# minute when the sounds around the cuts go.
LEAD = 75
# The cuts on the minute of the clock, in minutes after the first one.
# « Coupe pile »: a recorded show, longer than the cleaner lets a sound wait.
HARD = 0
# « Attend la fin »: a flash, at the end of the title astride its minute.
SOFT = 1
# « Coupe pile »: an ad, due while the live of rundown.py holds the antenna.
HELD = 2

# The rotation: artist, title, seconds, then the start pitch of its two tones.
# Short, for a bench of a few minutes, and never under 20 s: the first title
# after the show is astride the minute of the flash. More of them than the
# clock remembers (music_rules.TITLE_LAST_N): with fewer, it draws at random,
# and the same title twice in a row at times.
TITLES = [
    (
        f"Artiste {chr(64 + n)}",
        f"Titre {n:02d}",
        20 + n * 3 % 7,
        200 + 23 * n,
        900 + 41 * n,
    )
    for n in range(1, 23)
]
# The carts: title, mode, schedule mode, sounds as (title, seconds, pitches).
JINGLES = "Jingles"
SHOW = "Programme"
FLASH = "Flash"
ADS = "Pubs"
RELAY = "Relais"
SHOW_SECONDS = 48
CARTS = [
    (
        JINGLES,
        "RANDOM",
        "JINGLES",
        [
            ("Jingle 1", 3, 1900, 3100),
            ("Jingle 2", 4, 2100, 3400),
            ("Jingle 3", 3, 2300, 3700),
        ],
    ),
    (SHOW, "PLAYLIST", "CLOCK", [("Émission enregistrée", SHOW_SECONDS, 600, 1500)]),
    (FLASH, "RANDOM", "CLOCK", [("Flash info", 6, 1300, 2600)]),
    (ADS, "RANDOM", "CLOCK", [("Publicité", 8, 1700, 2900)]),
]
# The relay of the bench takes its own public mount, as the playout reaches it,
# and the scheduler stops it after this many seconds.
PUBLIC_MOUNT = "radio.mp3"
RELAY_URL = f"http://icecast:8000/{PUBLIC_MOUNT}"
RELAY_SECONDS = 12
# What the studio sends to the harbor, in a loop: bare MP3 frames, at the
# constant bit rate antenna.Studio sends them at.
LIVE = MEDIA / "live.mp3"


def run(*command: str, **options) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, **options)


def sweep(  # noqa: PLR0913
    path: Path,
    seconds: float,
    low: float,
    high: float,
    *,
    title: str = "",
    artist: str = "",
    bare: bool = False,
) -> None:
    """A stereo MP3 of two tones whose pitch keeps moving, as the sounds of the
    antenna bench (sounds.py). ``bare``: frames only, without a tag nor a
    header, at the bit rate of a live."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tones = [
        f"0.35*sin(2*PI*({a:.1f}+3*t)*t)+0.2*sin(2*PI*({b:.1f}-2*t)*t)"
        for a, b in ((low, high), (low * 1.07, high * 0.95))
    ]
    command = [
        "ffmpeg",
        "-nostdin",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"aevalsrc={'|'.join(tones)}:s=44100:d={seconds}",
        "-c:a",
        "libmp3lame",
    ]
    if bare:
        command += ["-b:a", f"{sounds.MP3_KBPS}k"]
        command += ["-id3v2_version", "0", "-write_xing", "0"]
    else:
        command += ["-b:a", "128k", "-metadata", f"title={title}"]
        command += ["-metadata", f"artist={artist}"]
    run(*command, str(path))


def install() -> None:
    """The instance itself, as `radiotomate-init` makes it: configuration,
    database and schema (deploy/scripts/init-radiotomate.sh)."""
    (DATA / "carts").mkdir(parents=True, exist_ok=True)
    Path(os.environ["BEETSDIR"]).mkdir(parents=True, exist_ok=True)
    # `radiotomate install` refuses RTCONFIG while the file does not exist.
    env = {key: value for key, value in os.environ.items() if key != "RTCONFIG"}
    run("radiotomate", "install", "--no-revert-on-failure", "-d", str(DATA), env=env)
    run("radiotomate", "-c", str(CONFIG), "update")


def configure() -> str:
    """The settings of the engine. Returns the token of the playout."""
    from ruamel.yaml import YAML

    yaml = YAML()
    yaml.preserve_quotes = True
    data = yaml.load(CONFIG)
    # The bench is reached in HTTP, on the machine.
    data.setdefault("interface", {})["cookie_secure"] = False
    playout = data["playout_process_config"]
    # The journal of the playout goes to its output: the Liquidsoap image has
    # its own user, which does not write in the data of the engine.
    playout.pop("log_path", None)
    playout["outputs"] = [
        {
            "driver": "icecast",
            "encoder": "mp3cbr",
            "quality": 128,
            "host": "icecast",
            "port": 8000,
            "mount": PUBLIC_MOUNT,
            "password": "antenne-source",
        }
    ]
    data["queue_cleaner"] = {
        "enabled": True,
        "max_age_seconds": CLEAN_AGE,
        "interval_seconds": CLEAN_INTERVAL,
    }
    # The journals of the interface and of the scheduler too: rundown.py shows
    # their end when the bench fails.
    for name in ("interface", "scheduler"):
        data["logging"]["handlers"][name] = {
            "formatter": "generic",
            "class": "logging.StreamHandler",
        }
    buffer = io.StringIO()
    yaml.dump(data, buffer)
    CONFIG.write_text(buffer.getvalue(), encoding="utf-8")

    # Beets, as radiotomate-init sets it: the bank where it is, ReplayGain by
    # ffmpeg.
    path = Path(os.environ["BEETSDIR"]) / "config.yaml"
    beets = (yaml.load(path) or {}) if path.exists() else {}
    beets["directory"] = str(MEDIA)
    beets["library"] = str(path.parent / "library.db")
    beets["import"] = {
        "move": False,
        "copy": False,
        "quiet_fallback": "asis",
        "write": True,
        "incremental": True,
    }
    beets["plugins"] = "info random replaygain"
    beets["replaygain"] = {"backend": "ffmpeg", "overwrite": True}
    buffer = io.StringIO()
    yaml.dump(beets, buffer)
    path.write_text(buffer.getvalue(), encoding="utf-8")
    return str(playout["token"])


def sound_path(cart: str, rank: int) -> Path:
    return MEDIA / "50-carts" / cart / f"{rank:02d}.mp3"


def make_sounds() -> None:
    """Every sound of the bench. The titles of the rotation go in the bank and
    in Beets: the category « Rotation » of a new station takes the folder
    10-rotation."""
    folder = MEDIA / "10-rotation"
    for artist, title, seconds, low, high in TITLES:
        path = folder / f"{artist} - {title}.mp3"
        sweep(path, seconds, low, high, title=title, artist=artist)
    run("beet", "import", "-A", "-q", "-s", str(folder))
    for cart, _mode, _schedule, cart_sounds in CARTS:
        for rank, (title, seconds, low, high) in enumerate(cart_sounds, 1):
            sweep(sound_path(cart, rank), seconds, low, high, title=title, artist=cart)
    sweep(LIVE, 8, 350, 1250, bare=True)


def first_cut() -> datetime:
    """
    The minute of the first cut: the first one that leaves the antenna the time
    to start. The cuts must fall in the hour the scheduler starts in: one that
    waits for the end of a title, and whose minute is already past in that
    hour, goes at once (clock._fire_due_soft_anchors). Near the end of an hour,
    the seed waits for the next one.
    """
    while True:
        now = datetime.now()
        first = (now + timedelta(seconds=LEAD + 59)).replace(second=0, microsecond=0)
        last = first + timedelta(minutes=max(HARD, SOFT, HELD))
        if (last.date(), last.hour) == (now.date(), now.hour):
            return first
        turn = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        sys.stdout.write(
            f"Le banc attend {turn:%H h %M} : ses coupures tombent toutes dans"
            " l'heure où l'antenne démarre.\n"
        )
        sys.stdout.flush()
        time.sleep((turn - now).total_seconds() + 1)


def switches() -> dict[str, str]:
    """The keys of the table `settings` this run asks for, on top of the ones of
    a new station: RUNDOWN_SETTINGS, as "key=value key=value"."""
    # A new station closes the harbor to the password of an account: an encoder
    # gets in with its token (deploy/scripts/init-radiotomate.sh).
    asked = {"features.allow_account_password": "0"}
    for pair in os.environ.get("RUNDOWN_SETTINGS", "").split():
        key, _, value = pair.partition("=")
        asked[key] = value
    return asked


async def fill(db, token: str, first: datetime) -> dict:
    """The accounts, the carts and the clock, whose cuts start at ``first``."""
    from sqlalchemy import select

    from radiotomate.enums import CartMode, ScheduleMode
    from radiotomate.models import AutoDJSlot, Cart, Setting, Sound, User
    from radiotomate.services.autodj import create_clock

    plan: dict = {"token": token, "carts": {}, "settings": switches()}
    cuts = {
        name: first + timedelta(minutes=after)
        for name, after in (("hard", HARD), ("soft", SOFT), ("held", HELD))
    }
    async with db.session.begin() as session:
        accounts = {}
        for (username, password), rights in (
            (CONSOLE, {"admin": True}),
            (STUDIO, {"stream": True}),
        ):
            user = User(username=username)
            user.update_password(password)
            user.update_permissions_map(rights)
            session.add(user)
            accounts[username] = user
        await session.flush()

        for title, mode, schedule_mode, cart_sounds in CARTS:
            cart = Cart(
                title=title,
                path=sound_path(title, 1).parent,
                mode=CartMode[mode],
                schedule_mode=ScheduleMode[schedule_mode],
            )
            session.add(cart)
            await session.flush()
            plan["carts"][title] = cart.id
            for rank, (sound_title, seconds, _low, _high) in enumerate(cart_sounds, 1):
                session.add(
                    Sound(
                        cart_id=cart.id,
                        rank=rank,
                        path=sound_path(title, rank),
                        # As a sound sent to a cart: whole seconds.
                        duration=seconds,
                        title=sound_title,
                        gain=-1.0,
                        peak=-0.5,
                        uploader_id=accounts[CONSOLE[0]].id,
                    )
                )
        relay = Cart(
            title=RELAY,
            path=sound_path(RELAY, 1).parent,
            mode=CartMode.RELAY,
            schedule_mode=ScheduleMode.CLOCK,
            url=RELAY_URL,
            max_duration=RELAY_SECONDS,
        )
        session.add(relay)
        await session.flush()
        plan["carts"][RELAY] = relay.id

        for key, value in plan["settings"].items():
            await Setting.upsert(session, key, value)

        clock = await create_clock(
            session,
            {
                "name": "Heure type du banc",
                "fallback_cart": JINGLES,
                "motif": [
                    {"kind": "jingle", "cart": JINGLES},
                    {"kind": "musique", "category": "Rotation"},
                    {"kind": "musique", "category": "Rotation"},
                ],
                "anchors": [
                    {
                        "kind": "son",
                        "cart": SHOW,
                        "minute": cuts["hard"].minute,
                        "sync": "dure",
                    },
                    {
                        "kind": "son",
                        "cart": FLASH,
                        "minute": cuts["soft"].minute,
                        "sync": "molle",
                    },
                    {
                        "kind": "pub",
                        "cart": ADS,
                        "minute": cuts["held"].minute,
                        "sync": "dure",
                    },
                ],
            },
        )
        await session.flush()
        for slot in await session.scalars(select(AutoDJSlot)):
            slot.clock_id = clock.id
            slot.title = clock.name
    await db.after_serving()
    # Seconds since the epoch: the same instant on the machine of rundown.py,
    # whatever its time zone.
    plan.update({name: at.timestamp() for name, at in cuts.items()})
    return plan


def seed() -> None:
    install()
    token = configure()
    make_sounds()

    from radiotomate.commands import load_config
    from radiotomate.db import PathLike, QuartAlchemy

    config = load_config(CONFIG)
    PathLike.base_path = Path(config["data"]["root"])
    db = QuartAlchemy()
    db.init_from_config(config["db"], {})
    # Last: the minutes of the cuts, as near as can be to the start.
    plan = asyncio.run(fill(db, token, first_cut()))

    # The engine runs as rtuser. The Liquidsoap image has its own user, which
    # only reads: the configuration, the start sound, the sounds.
    run("chown", "-R", "rtuser:rtuser", str(DATA), str(MEDIA))
    run("chmod", "-R", "a+rX", str(DATA), str(MEDIA))
    PLAN.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    PLAN.chmod(0o644)
    sys.stdout.write(
        "Banc prêt : coupures à "
        + ", ".join(
            f"{datetime.fromtimestamp(plan[name]):%H:%M}"
            for name in ("hard", "soft", "held")
        )
        + ".\n"
    )


if __name__ == "__main__":
    if PLAN.exists():
        sys.exit(0)
    seed()
