"""
``radiotomate maintenance``, the engine's commands for running a station: ``next-live``,
the next live that ``station status`` shows, and ``window``, whether ``station update``
may start now.

The commands run in a subprocess, like the station runs them: their ``asyncio.run``
would leave the tests that follow without an event loop.
"""

import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from radiotomate.commands.maintenance import (
    WINDOW_MINUTES,
    describe_next_live,
    named_lives,
    until,
    what_blocks,
)
from radiotomate.commands.update import do_update
from radiotomate.db import QuartAlchemy

PARIS = ZoneInfo("Europe/Paris")
MONDAY_NOON = datetime(2026, 9, 21, 12, 0, tzinfo=PARIS)
QG = {"title": "QG", "label": "QG 20:00-22:00"}
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


def test_what_blocks_nothing_on_an_empty_station():
    assert what_blocks(MONDAY_NOON, None, [], []) is None


def test_what_blocks_a_live_that_starts_within_the_window():
    soon = {**QG, "starts_in_s": 12 * 60, "active": False}
    assert (
        what_blocks(MONDAY_NOON, soon, [], [])
        == "QG, un direct, commence à 12:12, dans 12 min"
    )
    last = {**QG, "starts_in_s": WINDOW_MINUTES * 60, "active": False}
    assert what_blocks(MONDAY_NOON, last, [], []) == (
        f"QG, un direct, commence à 12:{WINDOW_MINUTES}, dans {WINDOW_MINUTES} min"
    )
    later = {**QG, "starts_in_s": WINDOW_MINUTES * 60 + 1, "active": False}
    assert what_blocks(MONDAY_NOON, later, [], []) is None


def test_what_blocks_a_live_on_air():
    on_air = {**QG, "starts_in_s": 0, "active": True}
    assert what_blocks(MONDAY_NOON, on_air, [], []) == "QG, un direct, en cours"
    untitled = {**on_air, "title": ""}
    assert what_blocks(MONDAY_NOON, untitled, [], []) == "Direct, un direct, en cours"


def test_what_blocks_the_agenda():
    # What forecast_windows gives: aware instants, in UTC.
    noon = MONDAY_NOON.astimezone(UTC)
    a_set = {
        "kind": "set",
        "title": "Mix de Léa",
        "start": noon - timedelta(minutes=5),
        "end": noon + timedelta(minutes=40),
    }
    assert (
        what_blocks(MONDAY_NOON, None, [a_set], [])
        == "Mix de Léa, un set de l'Agenda, en cours jusqu'à 12:40"
    )
    dated = {
        "kind": "live",
        "title": "Direct daté",
        "start": noon + timedelta(minutes=25),
        "end": noon + timedelta(hours=1),
    }
    assert (
        what_blocks(MONDAY_NOON, None, [dated], [])
        == "Direct daté, un direct de l'Agenda, commence à 12:25, dans 25 min"
    )
    over = {**a_set, "end": noon}
    assert what_blocks(MONDAY_NOON, None, [over], []) is None


def test_what_blocks_a_live_named_on_the_antenne_page():
    assert (
        what_blocks(MONDAY_NOON, None, [], [("Léa en direct", None)])
        == "Léa en direct, un direct, en cours"
    )
    one_o_clock = MONDAY_NOON + timedelta(hours=1)
    assert (
        what_blocks(MONDAY_NOON, None, [], [("", one_o_clock)])
        == "Direct, un direct, en cours jusqu'à 13:00"
    )
    assert what_blocks(MONDAY_NOON, None, [], [("Fini", MONDAY_NOON)]) is None


def test_what_blocks_what_is_on_air_first_then_the_soonest():
    noon = MONDAY_NOON.astimezone(UTC)
    later = {**QG, "starts_in_s": 20 * 60, "active": False}
    dated = {
        "kind": "live",
        "title": "Direct daté",
        "start": noon + timedelta(minutes=10),
        "end": noon + timedelta(hours=1),
    }
    assert what_blocks(MONDAY_NOON, later, [dated], []).startswith("Direct daté, ")
    on_air = what_blocks(MONDAY_NOON, later, [dated], [("Léa en direct", None)])
    assert on_air == "Léa en direct, un direct, en cours"
    # A dated live is also a live slot: the Agenda's name wins.
    same = {**QG, "title": "Direct daté", "starts_in_s": 10 * 60, "active": False}
    assert what_blocks(MONDAY_NOON, same, [dated], []) == (
        "Direct daté, un direct de l'Agenda, commence à 12:10, dans 10 min"
    )


def test_what_blocks_a_live_on_the_harbor_named_or_not():
    # What the playout says of its source: a live on the harbor, named or not.
    assert what_blocks(MONDAY_NOON, None, [], [], True) == "Direct, un direct, en cours"
    named = [("Léa en direct", None)]
    assert (
        what_blocks(MONDAY_NOON, None, [], named, True)
        == "Léa en direct, un direct, en cours"
    )
    # The harbor off: a named live is a row the next title has not cleared yet.
    assert what_blocks(MONDAY_NOON, None, [], named, False) is None
    # The playout says nothing: the named live counts.
    assert (
        what_blocks(MONDAY_NOON, None, [], named, None)
        == "Léa en direct, un direct, en cours"
    )
    # A weekly show on air names the live on the harbor.
    on_air = {**QG, "starts_in_s": 0, "active": True}
    assert what_blocks(MONDAY_NOON, on_air, [], [], True) == "QG, un direct, en cours"


async def test_named_lives_come_from_the_database(tmp_path: Path):
    db_file = tmp_path / "radiotomate.db"
    named = (
        "insert into emissions (scope, title, artist, host_username, starts_at,"
        " ends_at, version, created, modified) values ('session', {title}, '', '',"
        " '2026-09-21 09:00:00', {end}, 1, '2026-09-21 09:00:00',"
        " '2026-09-21 09:00:00')"
    )
    await _database(
        db_file,
        WEEKLY,
        named.format(title="'Léa en direct'", end="'2026-09-21 11:00:00'"),
        named.format(title="'Sans fin'", end="null"),
    )
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{db_file}"}, {})
    try:
        async with db.session() as session:
            lives = await named_lives(session)
    finally:
        await db.after_serving()
    # 11:00 in UTC, as stored: 13:00 in Paris, in September.
    assert sorted(lives, key=lambda live: live[0]) == [
        ("Léa en direct", datetime(2026, 9, 21, 13, 0, tzinfo=PARIS)),
        ("Sans fin", None),
    ]
    assert (
        what_blocks(MONDAY_NOON, None, [], lives[:1])
        == "Léa en direct, un direct, en cours jusqu'à 13:00"
    )


def _window(
    config_path: Path, timezone: str = "Europe/Paris"
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["radiotomate", "-c", str(config_path), "maintenance", "window"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "TZ": timezone},
    )


async def test_window_is_free_on_an_empty_station(config_path: Path):
    await _database(config_path.parent / "radiotomate.db")
    result = _window(config_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"libre : ni direct ni diffusion de l'Agenda d'ici {WINDOW_MINUTES} min\n"
    )


@pytest.mark.parametrize("timezone", ["Europe/Paris", "America/Montreal"])
async def test_window_is_taken_before_a_dated_live(config_path: Path, timezone: str):
    # The Agenda stores naive UTC; the live starts in ten minutes, whatever the day.
    start = datetime.now(UTC).replace(tzinfo=None, microsecond=0) + timedelta(
        minutes=10
    )
    end = start + timedelta(hours=1)
    await _database(
        config_path.parent / "radiotomate.db",
        "insert into agenda_diffusions"
        " (kind, title, starts_at, ends_at, created, modified)"
        f" values ('live', 'Direct de test', '{start}', '{end}',"
        " '2026-09-01 00:00:00', '2026-09-01 00:00:00')",
    )
    # A station in another time zone reads the same instant.
    result = _window(config_path, timezone)
    assert result.returncode == 1, result.stderr
    assert result.stdout.startswith(
        "occupée : Direct de test, un direct de l'Agenda, commence à "
    ), result.stdout
