"""FON-63: where the conducteur ends is read on all its lines.

The scheduler at its tick, the interface at each reading of the conducteur, six
hours every 3 s while a console has it open, ask whether it reaches as far as
they need, and draw what follows its end when it does not. They read it on the
800 lines a reading answers with (``_visible_items``), and six hours of titles
of 20 s are more: the end of the 800th line passed for the end of the
conducteur. Each reading of the console drew again what follows it, at the same
times as the reading before, and wrote it. On the rundown bench, with its titles
of 22 s: 45 000 lines in 5 min, a scheduler grown from 90 to 390 MB.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets.demo import BeetsMockIntegration
from radiotomate.models import Clock, RundownItem
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import PARIS
from radiotomate.scheduler.execution import (
    ensure_forecast,
    ensure_programming_version,
    item_from_forecast,
)
from radiotomate.scheduler.rundown import MAX_ITEMS
from radiotomate.services.media_bank import ROTATION_TOP
from tests.scheduler.test_forecast_drawn_once import Draws, Written, _station, _together

# A Monday night: the grid of the base plays a jingle of 8 s, then three titles,
# until 10:00.
NOW = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
# The horizon of a console open on the conducteur, in minutes.
CONSOLE = 360
# Titles of 20 s, as on the bench, and 400 µs: the lines end between two
# milliseconds, where SQLite does not read a time.
TITLE = 20.0004


@pytest.fixture
def short_titles():
    """A Beets library of thirty titles of 20 s: six hours of them, with their
    jingles, are some 1 270 lines."""
    beets = BeetsMockIntegration()
    for item in list(beets.lib.items()):
        item.remove()
    for index in range(30):
        beets.helper.add_item(
            artist=f"Artiste {index:02d}",
            title=f"Titre {index:02d}",
            grouping="rotation",
            length=TITLE,
            path=f"/media/{ROTATION_TOP}/titre-{index:02d}.mp3",
        )
    yield beets
    beets.teardown()


async def _lines(session: ormSession) -> list[RundownItem]:
    return list(
        await session.scalars(
            select(RundownItem).order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )


def _end(line: RundownItem) -> datetime:
    return line.planned_at + timedelta(seconds=line.duration)


def _wall(moment: datetime) -> datetime:
    """The time as the conducteur keeps it: Paris, without its offset."""
    return moment.replace(tzinfo=None)


async def _console(
    session: ormSession, beets: BeetsMockIntegration, *seconds: float
) -> list[RundownItem]:
    """A console open on the conducteur reads six hours, at these seconds after
    ``NOW``; then the lines of the base."""
    for second in seconds:
        await ensure_forecast(
            session, beets, now=NOW + timedelta(seconds=second), horizon_min=CONSOLE
        )
    return await _lines(session)


async def test_four_readings_of_six_hours_write_what_follows_once(
    dbsession: ormSession,
    jingles_cart: Cart,
    short_titles: BeetsMockIntegration,
    monkeypatch: pytest.MonkeyPatch,
):
    """A console reads six hours, every 3 s. The first reading draws 800 lines,
    all a draw holds, short of six hours; the second, what follows them. The
    next two find six hours, and write nothing: each wrote again what follows
    the 800th line, as the second had, at the same times."""
    await _station(dbsession)
    written = Written(monkeypatch)
    lines = await _console(dbsession, short_titles, 0, 3, 6, 9)

    assert len(written.draws) == 2
    drawn, follows = written.draws
    assert len(drawn) == MAX_ITEMS
    assert len(lines) == len(drawn) + len(follows)
    assert lines[MAX_ITEMS].planned_at == _end(lines[MAX_ITEMS - 1])
    assert _end(lines[-1]) >= _wall(NOW + timedelta(seconds=9, hours=6))
    assert not _together(lines)


async def test_six_hours_past_800_lines_are_not_drawn_again(
    dbsession: ormSession,
    jingles_cart: Cart,
    short_titles: BeetsMockIntegration,
    monkeypatch: pytest.MonkeyPatch,
):
    """Six hours of conducteur, past 800 lines: neither the console nor the tick
    draws anything more, and the console is answered with the first 800."""
    await _station(dbsession)
    lines = await _console(dbsession, short_titles, 0, 3)
    draws = Draws(monkeypatch)
    later = NOW + timedelta(seconds=6)
    console = await ensure_forecast(
        dbsession, short_titles, now=later, horizon_min=CONSOLE
    )
    tick = await ensure_forecast(dbsession, short_titles, now=later)

    assert len(lines) > MAX_ITEMS
    assert draws.count == 0
    assert [item["id"] for item in console["items"]] == [
        line.id for line in lines[:MAX_ITEMS]
    ]
    assert tick["items"]
    assert [line.id for line in await _lines(dbsession)] == [line.id for line in lines]


async def test_a_conducteur_past_800_lines_goes_on_after_its_last_line(
    dbsession: ormSession,
    jingles_cart: Cart,
    short_titles: BeetsMockIntegration,
    monkeypatch: pytest.MonkeyPatch,
):
    """An hour later, six hours ahead are an hour more than the conducteur
    holds. It goes on at the microsecond its last line ends, not its 800th, and
    its motif with the position after the one of that line."""
    await _station(dbsession)
    before = await _console(dbsession, short_titles, 0, 3)
    last = before[-1]
    written = Written(monkeypatch)
    later = NOW + timedelta(hours=1)
    await ensure_forecast(dbsession, short_titles, now=later, horizon_min=CONSOLE)

    assert len(before) > MAX_ITEMS
    assert len(written.draws) == 1
    lines = await _lines(dbsession)
    first = next(line for line in lines if line.id in set(written.draws[0]))
    assert first.planned_at == _end(last)
    clock = await Clock.from_id(dbsession, last.clock_id)
    motif = [pos.id for pos in clock.sequential_positions()]
    after = motif[(motif.index(last.clock_position_id) + 1) % len(motif)]
    assert first.clock_position_id == after
    assert _end(lines[-1]) >= _wall(later + timedelta(hours=6))
    assert not _together(lines)


async def test_the_conducteur_ends_where_its_lines_end_the_latest(
    dbsession: ormSession,
    short_titles: BeetsMockIntegration,
    monkeypatch: pytest.MonkeyPatch,
):
    """A recorded programme of an hour, and a title planned ten minutes into
    it: the conducteur reaches the end of the programme, not of the title, the
    last line planned. The tick finds its thirty minutes, and draws nothing."""
    version = await ensure_programming_version(dbsession)
    start = _wall(NOW)
    lines = [
        {
            "at": start,
            "duration": 3600,
            "kind": "son",
            "queue": "carts",
            "resource": "Programme — Émission enregistrée",
        },
        {
            "at": start + timedelta(minutes=10),
            "duration": TITLE,
            "kind": "musique",
            "resource": "Artiste 00 — Titre 00",
        },
    ]
    dbsession.add_all(
        item_from_forecast({**line, "at": line["at"].isoformat()}, version, sequence)
        for sequence, line in enumerate(lines)
    )
    await dbsession.commit()
    draws = Draws(monkeypatch)
    await ensure_forecast(dbsession, short_titles, now=NOW + timedelta(minutes=5))

    assert draws.count == 0
