"""The jingles of the motif air at their place in the file, after the start too
(``features.motif_jingles_air``).

The night file of the bench: a jingle, then three music lines, over and over. The
clock keeps two titles ahead in the Auto-DJ queue. A jingle of the motif waited for
an empty Auto-DJ queue: after the start, it never had one, and the music after it
aired in its place. It now goes at the end of the title before it, ahead of the
music already queued after it. A jingle whose turn has passed is skipped.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import RundownStatus
from radiotomate.models import MetadataLog, RundownItem, Setting
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import PARIS, SETTING_MOTIF_JINGLES_AIR, tick
from radiotomate.scheduler.execution import (
    TURN_PASSED_REASON,
    close_flushed_items,
    ensure_forecast,
    reconcile_as_run,
)

START = datetime(2026, 9, 14, 0, 30, tzinfo=PARIS)
# Three turns of the motif in the night file, named by their place: J for a jingle.
FILE = ["J0", "M1", "M2", "M3", "J4", "M5", "M6", "M7", "J8", "M9", "M10", "M11"]
ON = [(None, True), ("1", True)]
OFF = [("0", False), ("false", False), ("Off", False)]
# Liquidsoap plays the jingles before the Auto-DJ, as soon as they hold a title.
QUEUES = ("jingles", "autodj")
HEADS = {
    "jingles": ("next_jingle", "jingles_queued"),
    "autodj": ("next_autodj", "autodj_queued"),
}


def _cue(line_id: str) -> dict:
    """The next title of a playout queue, annotated as the clock pushes it."""
    return {"rid": 7, "initial_uri": f'annotate:radiotomate_item_id="{line_id}":/x.mp3'}


class Playout:
    """
    Liquidsoap as the clock sees it: the jingles and Auto-DJ queues, the title on
    air, and what it says has aired (``POST /metadata_log``). Time runs with the
    titles: each one lasts the duration of its line.
    """

    def __init__(self, dbsession: ormSession, beets: BeetsIntegration) -> None:
        self.dbsession = dbsession
        self.beets = beets
        self.queues: dict[str, list[str]] = {queue: [] for queue in QUEUES}
        self.source = "starting"
        self.on_air: RundownItem | None = None
        self.started = START
        self.aired: list[str] = []
        self.client = AsyncMock()
        self.client.post = AsyncMock(side_effect=self._push)

    async def _push(self, path: str, **kwargs) -> httpx.Response:
        self.queues[path.removeprefix("/queue/")].append(
            kwargs["json"]["radiotomate_item_id"]
        )
        return httpx.Response(200, json={"ok": 1})

    def _end(self) -> datetime:
        if self.on_air is None:
            return self.started
        return self.started + timedelta(seconds=float(self.on_air.duration or 0))

    def live(self, remaining: float) -> dict:
        """The heartbeat of ``/live``, ``remaining`` seconds before the title ends."""
        data = {
            "source": self.source,
            "remaining": str(remaining),
            "time": (self._end() - timedelta(seconds=remaining)).isoformat(),
            "radiotomate_item_id": self.on_air.id if self.on_air else "",
        }
        for queue, (cue_key, count_key) in HEADS.items():
            held = self.queues[queue]
            data[cue_key] = _cue(held[0]) if held else {"rid": -1}
            data[count_key] = len(held)
        return data

    async def tick(self, remaining: float) -> list[str]:
        return await tick(self.dbsession, self.live(remaining), self.client, self.beets)

    async def next_title(self, *, overlap: float = 0) -> None:
        """The title on air ends: the jingles first, then the Auto-DJ. With an
        ``overlap``, the title on air fades into the next one, which starts that
        many seconds before its end, as the Auto-DJ does."""
        self.started = self._end() - timedelta(seconds=overlap)
        queue = next((name for name in QUEUES if self.queues[name]), None)
        assert queue is not None, "blank: nothing left in the queues"
        line = await self.dbsession.get(RundownItem, self.queues[queue].pop(0))
        self.source = queue
        self.on_air = line
        self.aired.append(line.id)
        log = await MetadataLog.from_playout(
            self.dbsession,
            {
                "on_air": self.started.replace(tzinfo=None).isoformat(),
                "source": queue,
                "radiotomate_item_id": line.id,
            },
        )
        self.dbsession.add(log)
        await reconcile_as_run(self.dbsession, log)
        await self.dbsession.commit()

    async def play(self, titles: int) -> None:
        """Each title, the clock ticks while it plays, and when 2 s are left."""
        for _ in range(titles):
            await self.next_title()
            for remaining in (float(self.on_air.duration) / 2, 2.0):
                await self.tick(remaining)

    async def flush(self) -> None:
        """« Vider les files »: the playout names the lines it took out."""
        answer = {
            queue: {"item_ids": list(self.queues[queue]), "removed": 0}
            for queue in QUEUES
        }
        for held in self.queues.values():
            held.clear()
        await close_flushed_items(self.dbsession, answer, list(QUEUES))
        await self.dbsession.commit()


async def _switch(dbsession: ormSession, value: str | None) -> None:
    """Set ``features.motif_jingles_air``, or take the key out with None."""
    row = await Setting.from_key(dbsession, SETTING_MOTIF_JINGLES_AIR)
    if value is not None:
        await Setting.upsert(dbsession, SETTING_MOTIF_JINGLES_AIR, value)
    elif row is not None:
        await dbsession.delete(row)
    await dbsession.commit()


async def _file(dbsession: ormSession, beets: BeetsIntegration) -> dict[str, str]:
    """The lines of the night file, named by their place: « J0 », « M1 »…"""
    data = await ensure_forecast(dbsession, beets, now=START, cursor=0)
    names = {
        item["id"]: f"{item['kind'][0].upper()}{place}"
        for place, item in enumerate(data["items"])
    }
    assert list(names.values())[: len(FILE)] == FILE
    return names


async def _started(dbsession: ormSession, beets: BeetsIntegration) -> Playout:
    """The playout starts: the clock sends the first jingle and the music after it."""
    playout = Playout(dbsession, beets)
    await playout.tick(0)
    return playout


async def _line(dbsession: ormSession, names: dict[str, str], name: str) -> RundownItem:
    line_id = next(line_id for line_id, named in names.items() if named == name)
    line = await dbsession.get(RundownItem, line_id)
    await dbsession.refresh(line)
    return line


def _aired(playout: Playout, names: dict[str, str]) -> list[str]:
    return [names.get(line_id, "?") for line_id in playout.aired]


@pytest.mark.parametrize(("value", "airs"), [*ON, *OFF])
async def test_the_jingles_of_the_motif_air_at_their_place(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    airs: bool,
):
    """Three turns of the motif from the start: each jingle airs once, at the end
    of the title before it, ahead of the music queued after it. Turned off, only
    the first one airs: the next ones wait for an empty Auto-DJ queue."""
    await _switch(dbsession, value)
    names = await _file(dbsession, beets_integration)
    playout = await _started(dbsession, beets_integration)
    await playout.play(len(FILE))
    aired = _aired(playout, names)
    if airs:
        assert aired == FILE
    else:
        assert [name for name in aired if name.startswith("J")] == ["J0"]


@pytest.mark.parametrize(("value", "skips"), [*ON, *OFF])
async def test_a_jingle_that_missed_its_turn_is_skipped(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    skips: bool,
):
    """The clock misses the end of the title before the second jingle, and the
    Auto-DJ fades that title into the music after the jingle: it starts before the
    jingle's time, where the conducteur then sets it. The jingle's turn has passed:
    « sauté », it never airs. Turned off, it stays planned."""
    await _switch(dbsession, value)
    names = await _file(dbsession, beets_integration)
    playout = await _started(dbsession, beets_integration)
    await playout.play(3)
    await playout.next_title()
    await playout.tick(90)
    await playout.next_title(overlap=3)
    await playout.tick(2)
    await playout.play(3)
    jingle = await _line(dbsession, names, "J4")
    if skips:
        assert _aired(playout, names) == [name for name in FILE[:9] if name != "J4"]
        assert (jingle.status, jingle.reason) == (
            RundownStatus.SKIPPED.value,
            TURN_PASSED_REASON,
        )
    else:
        assert "J4" not in _aired(playout, names)
        assert jingle.status == RundownStatus.PLANNED.value


@pytest.mark.parametrize(("value", "skips"), [*ON, *OFF])
async def test_a_jingle_an_older_engine_held_back_never_airs_late(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    skips: bool,
):
    """The engine of before held the second jingle back, and the music after it
    aired. « Vider les files », at the end of a title, empties the Auto-DJ queue:
    the old jingle, « sauté » at the next tick, does not come back, and the next
    jingle goes at its place. Turned off, the old jingle airs, late."""
    await _switch(dbsession, "0")
    names = await _file(dbsession, beets_integration)
    playout = await _started(dbsession, beets_integration)
    await playout.play(7)
    assert _aired(playout, names)[-3:] == ["M5", "M6", "M7"]

    await _switch(dbsession, value)
    await playout.flush()
    await playout.tick(2)
    await playout.next_title()
    jingle = await _line(dbsession, names, "J4")
    if skips:
        assert names[playout.on_air.id] == "J8"
        assert (jingle.status, jingle.reason) == (
            RundownStatus.SKIPPED.value,
            TURN_PASSED_REASON,
        )
    else:
        assert names[playout.on_air.id] == "J4"
