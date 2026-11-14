"""FON-60: the forecast is drawn once, whoever draws it.

The scheduler draws the forecast at its tick, the interface at each reading of
the conducteur, every 3 s while a console has it open. At the start of a
station, both found it empty: each drew, thirty minutes or six hours, and wrote.
The second draw erased the lines the first still planned, not those the
scheduler had already sent to the playout: the antenna aired the start of both,
two jingles in a row. Seen on the rundown bench (TST-14), the console open
before the antenna starts: five starts out of thirty-two.

The draw of an empty conducteur is now written under the write lock of the
base, and only if the conducteur is still empty
(``features.forecast_drawn_once``).
"""

import asyncio
from datetime import datetime, timedelta
from time import monotonic

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import RundownStatus
from radiotomate.models import RundownItem, Setting
from radiotomate.models.cart import Cart
from radiotomate.quart import CustomQuart
from radiotomate.scheduler import execution, rundown
from radiotomate.scheduler.clock import PARIS
from radiotomate.scheduler.execution import (
    SETTING_FORECAST_ONCE,
    ensure_forecast,
    ensure_programming_version,
    reset_conducteur,
)

# A Monday night: the grid of the base plays a jingle, then three titles.
NOW = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
# The horizon of a console open on the conducteur, in minutes.
CONSOLE = 360
# The value of the switch, and whether it is on. A missing key: it is.
SWITCH = [(None, True), ("1", True), ("0", False), ("off", False)]


async def _station(dbsession: ormSession, value: str | None = None) -> None:
    """The switch, and the version of the programming, written before the
    processes draw: what they write of the forecast is what is looked at."""
    if value is not None:
        await Setting.upsert(dbsession, SETTING_FORECAST_ONCE, value)
    await ensure_programming_version(dbsession)
    await dbsession.commit()


class Draws:
    """The draws of the forecast, as the processes make them. The draw of a
    held session waits, made and not written, until it is let go: a process
    that has read the conducteur, then drawn while another wrote."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.build = rundown.build_rundown
        self.made: dict[object, asyncio.Event] = {}
        self.go: dict[object, asyncio.Event] = {}
        self.count = 0
        monkeypatch.setattr(rundown, "build_rundown", self._build)

    def hold(self, *sessions: ormSession) -> None:
        for session in sessions:
            self.made[session] = asyncio.Event()
            self.go[session] = asyncio.Event()

    async def drawn(self, *sessions: ormSession) -> None:
        for session in sessions:
            await asyncio.wait_for(self.made[session].wait(), timeout=10)

    def let_go(self, *sessions: ormSession) -> None:
        for session in sessions:
            self.go[session].set()

    async def _build(self, session: ormSession, *args, **kwargs) -> dict:
        forecast = await self.build(session, *args, **kwargs)
        self.count += 1
        if session in self.go and not self.made[session].is_set():
            self.made[session].set()
            await asyncio.wait_for(self.go[session].wait(), timeout=10)
        return forecast


class Written:
    """The lines each draw wrote to the base: on an empty conducteur
    (``replace_forecast_items``), or after its end (``append_forecast_items``)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.draws: list[list[str]] = []
        for name in ("replace_forecast_items", "append_forecast_items"):
            monkeypatch.setattr(execution, name, self._spy(getattr(execution, name)))

    def _spy(self, write):
        async def spy(*args, **kwargs) -> list[RundownItem]:
            items = await write(*args, **kwargs)
            if items:
                self.draws.append([item.id for item in items])
            return items

        return spy


async def _lines(app: CustomQuart) -> list[RundownItem]:
    """The lines of the base, as another process reads them."""
    async with app.extensions["sqlalchemy"].session() as session:
        return list(
            await session.scalars(
                select(RundownItem).order_by(
                    RundownItem.planned_at, RundownItem.sequence
                )
            )
        )


def _ids(answer: dict) -> set[str]:
    return {item["id"] for item in answer["items"]}


def _together(lines: list[RundownItem]) -> list[str]:
    """The lines of a queue planned while another of the same queue plays: the
    playout plays them one after the other, and the second airs late."""
    queues: dict[str, list[RundownItem]] = {}
    for line in lines:
        queues.setdefault(line.queue, []).append(line)
    found = []
    for rows in queues.values():
        for before, after in zip(rows, rows[1:]):
            end = before.planned_at + timedelta(seconds=before.duration or 0)
            if after.planned_at < end - timedelta(seconds=1):
                found.append(
                    f"« {after.resource} » à {after.planned_at:%H:%M:%S}, sous"
                    f" « {before.resource} » à {before.planned_at:%H:%M:%S}"
                )
    return found


async def _send_head(session: ormSession, answer: dict) -> RundownItem:
    """The clock sends the first line of the forecast to the playout."""
    row = await RundownItem.from_id(session, answer["items"][0]["id"])
    row.status = RundownStatus.SENT.value
    row.reserved_at = row.sent_at = datetime.now()
    await session.commit()
    return row


async def test_two_processes_that_find_the_conducteur_empty_write_one_draw(
    raw_app: CustomQuart,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    monkeypatch: pytest.MonkeyPatch,
):
    """The scheduler and the interface read an empty conducteur at once, and
    both draw: one draw is written, and both answer with it."""
    await _station(dbsession)
    draws = Draws(monkeypatch)
    written = Written(monkeypatch)
    sessions = raw_app.extensions["sqlalchemy"].session
    async with sessions() as scheduler, sessions() as interface:
        draws.hold(scheduler, interface)
        calls = [
            asyncio.create_task(ensure_forecast(scheduler, beets_integration, now=NOW)),
            asyncio.create_task(
                ensure_forecast(
                    interface, beets_integration, now=NOW, horizon_min=CONSOLE
                )
            ),
        ]
        await draws.drawn(scheduler, interface)
        draws.let_go(scheduler, interface)
        tick, console = await asyncio.gather(*calls)

    assert draws.count == 2
    assert len(written.draws) == 1
    lines = await _lines(raw_app)
    assert {line.id for line in lines} == set(written.draws[0])
    assert _ids(tick) == _ids(console) == set(written.draws[0])
    assert not _together(lines)


@pytest.mark.parametrize(("value", "once"), SWITCH)
async def test_the_console_does_not_draw_over_what_the_scheduler_sent(  # noqa: PLR0913
    raw_app: CustomQuart,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    monkeypatch: pytest.MonkeyPatch,
    value: str | None,
    once: bool,
):
    """As on the bench: a console opens on the empty conducteur, the interface
    draws six hours. Meanwhile the scheduler draws its thirty minutes, writes
    them and sends their first line, a jingle. The interface's draw is dropped,
    and it answers with the scheduler's lines. Switch off, as before: its draw
    erases the lines still planned, and its own jingle goes at the time of the
    one sent, in the same queue."""
    await _station(dbsession, value)
    draws = Draws(monkeypatch)
    sessions = raw_app.extensions["sqlalchemy"].session
    async with sessions() as scheduler, sessions() as interface:
        draws.hold(interface)
        reading = asyncio.create_task(
            ensure_forecast(interface, beets_integration, now=NOW, horizon_min=CONSOLE)
        )
        await draws.drawn(interface)
        tick = await ensure_forecast(scheduler, beets_integration, now=NOW)
        sent = await _send_head(scheduler, tick)
        draws.let_go(interface)
        console = await reading

    lines = await _lines(raw_app)
    in_base = {line.id for line in lines}
    assert sent.id in in_base
    if once:
        assert in_base == _ids(tick)
        assert _ids(console) == _ids(tick)
        assert not _together(lines)
    else:
        assert in_base - _ids(tick)
        assert _together(lines)


async def test_a_reset_while_the_scheduler_beats_writes_one_draw(
    raw_app: CustomQuart,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    monkeypatch: pytest.MonkeyPatch,
):
    """« Réinitialiser le conducteur » empties it, then the interface draws six
    hours again. The scheduler beats meanwhile: its tick finds the conducteur
    empty too, draws, writes and sends. The interface's draw is dropped, and
    the reset answers with the scheduler's lines."""
    await _station(dbsession)
    await ensure_forecast(dbsession, beets_integration, now=NOW)
    later = NOW + timedelta(minutes=2)
    draws = Draws(monkeypatch)
    written = Written(monkeypatch)
    sessions = raw_app.extensions["sqlalchemy"].session
    async with sessions() as scheduler, sessions() as interface:
        draws.hold(interface)
        reset = asyncio.create_task(
            reset_conducteur(
                interface, beets_integration, horizon_min=CONSOLE, now=later
            )
        )
        await draws.drawn(interface)
        tick = await ensure_forecast(scheduler, beets_integration, now=later)
        await _send_head(scheduler, tick)
        draws.let_go(interface)
        answer = await reset

    lines = await _lines(raw_app)
    assert written.draws == [[item["id"] for item in tick["items"]]]
    assert {line.id for line in lines} == _ids(tick)
    assert answer["action"] == "reset"
    assert _ids(answer) == _ids(tick)
    assert not _together(lines)


async def test_a_draw_that_fails_to_write_leaves_the_base_to_the_others(
    raw_app: CustomQuart,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    monkeypatch: pytest.MonkeyPatch,
):
    """A draw that fails while it writes holds the write lock no more: what it
    wrote is taken back, and another process writes at once, not after the
    5 s the base waits for a lock."""
    await _station(dbsession)
    replace = execution.replace_forecast_items

    async def full(*args, **kwargs) -> list[RundownItem]:
        await replace(*args, **kwargs)
        raise OSError("disque plein")

    monkeypatch.setattr(execution, "replace_forecast_items", full)
    sessions = raw_app.extensions["sqlalchemy"].session
    async with sessions() as scheduler:
        with pytest.raises(OSError, match="disque plein"):
            await ensure_forecast(scheduler, beets_integration, now=NOW)
        async with sessions() as other:
            await Setting.upsert(other, "fon60_written_after", "1")
            started = monotonic()
            await other.commit()
            assert monotonic() - started < 1
    assert not await _lines(raw_app)
