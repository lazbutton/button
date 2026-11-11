"""
``radiotomate maintenance``, the engine's commands for running a station: ``next-live``,
the next live that ``station status`` shows.

The command runs in a subprocess, like the station runs it: its ``asyncio.run`` would
leave the tests that follow without an event loop.
"""

import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from radiotomate.commands.maintenance import describe_next_live, until
from radiotomate.commands.update import do_update
from radiotomate.db import QuartAlchemy

PARIS = ZoneInfo("Europe/Paris")
MONDAY_NOON = datetime(2026, 9, 21, 12, 0, tzinfo=PARIS)
TEMPLATE = Path(__file__).parent / "scheduler" / "tests.yaml"
# A weekly show, on Wednesdays from 20:00 to 22:00.
WEEKLY = (
    "insert into emissions (scope, title, artist, host_username, day_of_week,"
    " start_minute, end_minute, version, created, modified)"
    " values ('weekly', 'QG', '', '', 2, 1200, 1320, 1,"
    " '2026-09-01 00:00:00', '2026-09-01 00:00:00')"
)


def test_until_says_it_as_the_console():
    # formatDuration, in console/src/api/antenneState.ts
    assert until(45) == "45 s"
    assert until(35 * 60) == "35 min"
    assert until(35 * 60 + 59) == "35 min"
    assert until(2 * 3600) == "2 h"
    assert until(2 * 3600 + 5 * 60) == "2 h 05"
    assert until((2 * 24 + 8) * 3600) == "2 j 8 h"
    assert until(3 * 24 * 3600) == "3 j 0 h"


def test_describe_next_live():
    assert describe_next_live(None, MONDAY_NOON) == "aucun de prévu d'ici 7 jours"
    slot = {"title": "QG", "label": "QG 20:00-22:00", "starts_in_s": 0}
    assert describe_next_live({**slot, "active": True}, MONDAY_NOON) == "QG, en cours"
    wednesday = {**slot, "starts_in_s": (2 * 24 + 8) * 3600, "active": False}
    assert (
        describe_next_live(wednesday, MONDAY_NOON)
        == "QG, mercredi 23 septembre à 20:00, dans 2 j 8 h"
    )
    untitled = describe_next_live({**wednesday, "title": ""}, MONDAY_NOON)
    assert untitled.startswith("Direct, mercredi 23 septembre")


async def _database(db_file: Path, *statements: str) -> None:
    """A database at the latest schema, with ``statements`` run on it."""
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{db_file}"}, {})
    try:
        await do_update(db.engine)
        async with db.engine.connect() as conn:
            for statement in statements:
                await conn.execute(text(statement))
            await conn.commit()
    finally:
        await db.after_serving()


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    db_file = tmp_path / "radiotomate.db"
    content = (
        TEMPLATE.read_text()
        .replace("db_url_goes_here", f"sqlite+aiosqlite:///{db_file}")
        .replace("/should/not/be/used", str(tmp_path))
    )
    path = tmp_path / "radiotomate.yaml"
    path.write_text(content)
    return path


def _next_live(config_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["radiotomate", "-c", str(config_path), "maintenance", "next-live"],
        capture_output=True,
        text=True,
        check=False,
    )


async def test_next_live_without_any_live(config_path: Path):
    await _database(config_path.parent / "radiotomate.db")
    result = _next_live(config_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "aucun de prévu d'ici 7 jours\n"


async def test_next_live_reads_the_weekly_shows(config_path: Path):
    await _database(config_path.parent / "radiotomate.db", WEEKLY)
    # Whatever the day: on a Wednesday at 20:00, never a minute before, or on
    # air now.
    result = _next_live(config_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "QG, en cours\n" or (
        result.stdout.startswith("QG, mercredi ") and " à 20:00, dans " in result.stdout
    ), result.stdout
