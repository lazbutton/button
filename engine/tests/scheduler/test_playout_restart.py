"""FON-59: after the playout starts again, the conducteur says what it holds.

An update of the station recreates the playout, whose queues start empty. The
lines the one before held stayed « en file » for good: never aired, they stood
first in the file with the time they had, and a station read that its next sound
went at 14:40 when it was 14:16. And the lines the engine before had planned kept
its times, an hour off on a station whose conducteur had drifted: a line that
starts sooner than planned does not move the ones planned after the next hard
anchor, so nothing brought them back.

- a line sent to a queue the playout says is empty is closed
  (``features.close_lines_lost_by_playout``);
- at its first tick, an engine that plans the conducteur another way than the one
  before rebuilds it (``features.rebuild_conducteur_after_upgrade``);
- a line sent ahead of the hard anchor it was planned after takes the time it
  airs at, and behind the sound of an anchor the file goes on from its end.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.models import RundownItem, Setting
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import (
    SETTING_CLOSE_LOST_LINES,
    SETTING_REBUILD_AFTER_UPGRADE,
    tick,
)
from radiotomate.scheduler.desk import PLAYED_NOW
from radiotomate.scheduler.execution import (
    FORECAST_REVISION,
    LOST_AFTER,
    LOST_REASON,
    SETTING_FORECAST_REVISION,
    close_lost_lines,
    forget_upgrade_check,
)
from tests.scheduler.test_cart_draw import _clock_at
from tests.scheduler.test_clock import NIGHT, _client, _live, _night_music
from tests.scheduler.test_hard_break_cuts import (
    BEFORE_THE_BREAK,
    THE_BREAK,
    _aired,
    _day_file,
    _says,
    _times,
)

# The value of a switch, and whether it is on. A missing key: it is.
SWITCH = [
    (None, True),
    ("1", True),
    ("true", True),
    ("0", False),
    ("false", False),
    ("Off", False),
]
LONG_AGO = timedelta(minutes=5)
# A title of the Auto-DJ is on air, and each queue holds a sound.
FULL = {
    "source": "autodj",
    "remaining": "100",
    "autodj_queued": 1,
    "next_autodj": {"rid": 7},
    "jingles_queued": 1,
    "next_jingle": {"rid": 8},
    "carts_queued": 1,
    "next_cart": {"rid": 9},
}
EMPTY = {
    "autodj": {"autodj_queued": 0, "next_autodj": {"rid": -1}},
    "jingles": {"jingles_queued": 0, "next_jingle": {"rid": -1}},
    "carts": {"carts_queued": 0, "next_cart": {"rid": -1}},
}


async def _switch(dbsession: ormSession, key: str, value: str | None) -> None:
    if value is not None:
        await Setting.upsert(dbsession, key, value)
        await dbsession.commit()


async def _sent(
    dbsession: ormSession,
    line: dict,
    *,
    queue: str = "autodj",
    ago: timedelta = LONG_AGO,
) -> RundownItem:
    """The playout took this line ``ago``: it waits in its queue."""
    row = await RundownItem.from_id(dbsession, line["id"])
    row.status = "in_queue"
    row.queue = queue
    row.reserved_at = row.sent_at = row.queued_at = datetime.now() - ago
    await dbsession.commit()
    return row


def _pushed(client: AsyncMock) -> list[str]:
    """The lines pushed to the playout, in their order."""
    return [
        call.kwargs["json"]["radiotomate_item_id"]
        for call in client.post.call_args_list
        if "radiotomate_item_id" in (call.kwargs.get("json") or {})
    ]


def _posted(client: AsyncMock) -> list[str]:
    return [str(call.args[0]) for call in client.post.call_args_list]


# ---- A line the playout has lost is closed -----------------------------------


@pytest.mark.parametrize(("value", "closes"), SWITCH)
async def test_the_lines_a_playout_held_before_it_started_again_are_closed(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    closes: bool,
):
    """Two titles waited in the playout. It starts again: its queues are empty,
    nothing is on air. Their lines are closed, and the clock sends the next one.
    Switch off, they stay « en file », as before."""
    await _switch(dbsession, SETTING_CLOSE_LOST_LINES, value)
    music = await _night_music(dbsession, beets_integration)
    rows = [await _sent(dbsession, line) for line in music[:2]]
    client = _client()
    await tick(dbsession, _live(NIGHT, autodj_queued=0), client, beets_integration)

    if closes:
        assert [(row.status, row.reason) for row in rows] == [
            ("skipped", LOST_REASON),
            ("skipped", LOST_REASON),
        ]
        assert all(row.closed_at is not None for row in rows)
    else:
        assert [(row.status, row.reason) for row in rows] == [
            ("in_queue", None),
            ("in_queue", None),
        ]
    # Either way the antenna gets a title: the next one still to push.
    pushed = _pushed(client)
    assert music[2]["id"] in pushed
    assert not {music[0]["id"], music[1]["id"]} & set(pushed)


@pytest.mark.parametrize("queue", ["autodj", "jingles", "carts"])
async def test_a_line_is_closed_when_its_own_queue_is_empty(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    queue: str,
):
    """Each queue is read on its own: the lines of the two that hold a sound
    stay."""
    music = await _night_music(dbsession, beets_integration)
    rows = {
        name: await _sent(dbsession, line, queue=name)
        for name, line in zip(["autodj", "jingles", "carts"], music, strict=False)
    }
    closed = await close_lost_lines(dbsession, {**FULL, **EMPTY[queue]})
    assert closed == 1
    assert {name: row.status for name, row in rows.items()} == {
        name: "skipped" if name == queue else "in_queue" for name in rows
    }


async def test_a_line_the_playout_has_just_taken_stays(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """Pushed two seconds ago: the beat that says the queue empty may have left
    before the push."""
    music = await _night_music(dbsession, beets_integration)
    row = await _sent(dbsession, music[0], ago=timedelta(seconds=2))
    assert timedelta(seconds=2) < LOST_AFTER
    assert await close_lost_lines(dbsession, {**FULL, **EMPTY["autodj"]}) == 0
    assert row.status == "in_queue"


async def test_the_line_on_air_stays(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The title has left its queue for the antenna: the beat names its line,
    before the as-run opens it."""
    music = await _night_music(dbsession, beets_integration)
    on_air = await _sent(dbsession, music[0])
    lost = await _sent(dbsession, music[1])
    live = {**FULL, **EMPTY["autodj"], "radiotomate_item_id": on_air.id}
    assert await close_lost_lines(dbsession, live) == 1
    assert (on_air.status, lost.status) == ("in_queue", "skipped")


@pytest.mark.parametrize("source", ["jingles", "carts", "relay", "stream"])
async def test_nothing_is_closed_behind_a_sound_that_cut_in(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    source: str,
):
    """A jingle is on air: the queue of the Auto-DJ has taken its next title out,
    to play it after. It counts none, and still holds one."""
    music = await _night_music(dbsession, beets_integration)
    row = await _sent(dbsession, music[0])
    live = {**FULL, **EMPTY["autodj"], "source": source}
    assert await close_lost_lines(dbsession, live) == 0
    assert row.status == "in_queue"


@pytest.mark.parametrize(
    "said",
    [
        # One title waits.
        {"autodj_queued": 1, "next_autodj": {"rid": 7}},
        # None counted, but the queue names its next: it is loaded.
        {"autodj_queued": 0, "next_autodj": {"rid": 7}},
        # An older playout says nothing of its next title.
        {"autodj_queued": 0, "next_autodj": None},
    ],
)
async def test_a_queue_that_holds_a_title_keeps_its_lines(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    said: dict,
):
    music = await _night_music(dbsession, beets_integration)
    row = await _sent(dbsession, music[0])
    assert await close_lost_lines(dbsession, {**FULL, **said}) == 0
    assert row.status == "in_queue"


async def test_the_line_of_a_title_played_at_once_stays(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """« Jouer tout de suite » sends the title, then writes its line: the
    playout does not name it on air, and its queue is empty while it plays."""
    music = await _night_music(dbsession, beets_integration)
    row = await _sent(dbsession, music[0])
    row.details = {**dict(row.details or {}), PLAYED_NOW: True}
    await dbsession.commit()
    assert await close_lost_lines(dbsession, {**FULL, **EMPTY["autodj"]}) == 0
    assert row.status == "in_queue"


async def test_a_line_still_to_send_is_not_lost(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """Planned, or its push still to go: the playout never held it."""
    music = await _night_music(dbsession, beets_integration)
    pending = await _sent(dbsession, music[1])
    pending.status = "pending_push"
    await dbsession.commit()
    assert await close_lost_lines(dbsession, {**FULL, **EMPTY["autodj"]}) == 0
    planned = await RundownItem.from_id(dbsession, music[0]["id"])
    assert (planned.status, pending.status) == ("planned", "pending_push")


# ---- An engine that plans another way rebuilds the conducteur ----------------


async def _drifted(
    dbsession: ormSession, beets_integration: BeetsIntegration
) -> set[str]:
    """The conducteur an engine before left: an hour late, two titles in its
    playout. Returns its lines."""
    music = await _night_music(dbsession, beets_integration)
    rows = list(await dbsession.scalars(select(RundownItem)))
    for row in rows:
        row.planned_at = row.planned_at + timedelta(hours=1)
    await dbsession.commit()
    for line in music[:2]:
        await _sent(dbsession, line)
    return {row.id for row in rows}


async def _lines(dbsession: ormSession) -> list[RundownItem]:
    return list(
        await dbsession.scalars(
            select(RundownItem).order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )


@pytest.mark.parametrize(("value", "rebuilds"), SWITCH)
async def test_the_first_tick_of_an_engine_that_plans_another_way_rebuilds(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    rebuilds: bool,
):
    """The base has no forecast revision: the engine before did not write one.
    The lines it left go, the queues of the playout are emptied, and the
    conducteur starts from now. Switch off, its lines stay. The revision is
    written either way: the next start does not ask again."""
    await _switch(dbsession, SETTING_REBUILD_AFTER_UPGRADE, value)
    before = await _drifted(dbsession, beets_integration)
    forget_upgrade_check()
    client = _client()
    await tick(dbsession, _live(NIGHT, autodj_queued=0), client, beets_integration)

    lines = await _lines(dbsession)
    now = datetime(2026, 9, 14, 0, 30)
    if rebuilds:
        assert not before & {row.id for row in lines}
        assert "/queue/flush" in _posted(client)
        assert timedelta(0) <= lines[0].planned_at - now < timedelta(minutes=1)
        # The first line of the new conducteur goes to the antenna at once.
        assert _pushed(client)[0] == lines[0].id
    else:
        assert before <= {row.id for row in lines}
        assert "/queue/flush" not in _posted(client)
    revision = await Setting.from_key(dbsession, SETTING_FORECAST_REVISION)
    assert revision.value == FORECAST_REVISION


async def test_an_engine_that_plans_the_same_way_keeps_the_conducteur(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The scheduler starts again, after a fault or an update that does not
    change the forecast: its lines stay, but for those its playout has lost."""
    await Setting.upsert(dbsession, SETTING_FORECAST_REVISION, FORECAST_REVISION)
    before = await _drifted(dbsession, beets_integration)
    forget_upgrade_check()
    client = _client()
    await tick(dbsession, _live(NIGHT, autodj_queued=0), client, beets_integration)
    assert before <= {row.id for row in await _lines(dbsession)}
    assert "/queue/flush" not in _posted(client)


async def test_the_conducteur_is_rebuilt_once(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The second tick finds the revision written: the lines of the first stay."""
    await _drifted(dbsession, beets_integration)
    forget_upgrade_check()
    await tick(dbsession, _live(NIGHT, autodj_queued=0), _client(), beets_integration)
    rebuilt = {row.id for row in await _lines(dbsession)}
    client = _client()
    await tick(
        dbsession,
        _live(NIGHT, autodj_queued=1, next_autodj={"rid": 1}, remaining="100"),
        client,
        beets_integration,
    )
    assert rebuilt <= {row.id for row in await _lines(dbsession)}
    assert "/queue/flush" not in _posted(client)
    # A scheduler that starts again reads the revision in the base.
    forget_upgrade_check()
    client = _client()
    await tick(
        dbsession,
        _live(NIGHT, autodj_queued=1, next_autodj={"rid": 1}, remaining="100"),
        client,
        beets_integration,
    )
    assert rebuilt <= {row.id for row in await _lines(dbsession)}
    assert "/queue/flush" not in _posted(client)


async def test_a_new_station_has_nothing_to_rebuild(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """No line in the base: the playout is not flushed, the revision is written,
    and the first tick draws the conducteur as it always did."""
    forget_upgrade_check()
    client = _client()
    await tick(dbsession, _live(NIGHT, autodj_queued=0), client, beets_integration)
    assert "/queue/flush" not in _posted(client)
    revision = await Setting.from_key(dbsession, SETTING_FORECAST_REVISION)
    assert revision.value == FORECAST_REVISION
    assert _pushed(client)


async def test_a_playout_that_does_not_answer_does_not_stop_the_rebuild(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The flush fails: the conducteur is rebuilt all the same. The playout of an
    update has nothing to flush."""
    before = await _drifted(dbsession, beets_integration)
    forget_upgrade_check()
    client = _client()

    async def post(path, **_kwargs):
        if path == "/queue/flush":
            return httpx.Response(404)
        return httpx.Response(200, json={"ok": 1})

    client.post = AsyncMock(side_effect=post)
    await tick(dbsession, _live(NIGHT, autodj_queued=0), client, beets_integration)
    assert not before & {row.id for row in await _lines(dbsession)}


# ---- An antenna ahead of the conducteur, around a hard anchor ----------------


def _a_title_ends_in(seconds: str) -> dict:
    """10:17:30, a title of the Auto-DJ is on air, nothing waits behind it. The
    jingles queue is full: the clock has a title to send."""
    return _live(
        BEFORE_THE_BREAK,
        source="autodj",
        remaining=seconds,
        autodj_queued=0,
        next_jingle={"rid": 1},
        jingles_queued=2,
    )


async def _nothing_left_before_the_break(
    dbsession: ormSession, beets_integration: BeetsIntegration
) -> list[RundownItem]:
    """The lines before the break of 10:20 have all aired: the antenna is ahead.
    Returns the titles planned after its spot."""
    before, _pub, after = await _day_file(dbsession, beets_integration)
    await _aired(dbsession, before)
    return [row for row in after if row.kind == "musique"]


async def test_a_title_sent_ahead_of_the_break_it_was_planned_after_takes_its_time(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """Twenty seconds of a title are left at 10:17:30, and nothing is planned
    before the break of 10:20: the first title planned after its spot goes, and
    will air at 10:17:50. Its line says so. The ones after it are still to come
    after the spot."""
    music = await _nothing_left_before_the_break(dbsession, beets_integration)
    planned = [row.planned_at for row in music[:3]]
    assert planned[0] > THE_BREAK
    client = _client()
    with _clock_at(BEFORE_THE_BREAK):
        await tick(dbsession, _a_title_ends_in("20"), client, beets_integration)
    # A second title goes too, close to its turn: it airs behind the first one,
    # after the break if that one runs into it.
    assert _pushed(client) == [music[0].id, music[1].id]
    airs = datetime(2026, 9, 15, 10, 17, 50)
    then = airs + timedelta(seconds=music[0].duration)
    assert await _times(dbsession, music[:3]) == [
        airs,
        then if then < THE_BREAK else planned[1],
        planned[2],
    ]


async def test_a_title_sent_behind_a_title_that_ends_after_the_break_keeps_its_time(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The title on air ends at 10:20:50: the break cuts it, and the title sent
    behind it airs after the spot, as planned."""
    music = await _nothing_left_before_the_break(dbsession, beets_integration)
    planned = [row.planned_at for row in music[:2]]
    client = _client()
    with _clock_at(BEFORE_THE_BREAK):
        await tick(dbsession, _a_title_ends_in("200"), client, beets_integration)
    assert _pushed(client)[0] == music[0].id
    assert await _times(dbsession, music[:2]) == planned


async def test_a_title_sent_behind_another_one_counts_it(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """One title already waits in the queue, sent ahead of the break too: the
    second one airs after it."""
    music = await _nothing_left_before_the_break(dbsession, beets_integration)
    first = await _sent(dbsession, {"id": music[0].id}, ago=timedelta(seconds=30))
    first.planned_at = datetime(2026, 9, 15, 10, 17, 50)
    first.duration = 40.0
    await dbsession.commit()
    live = {**_a_title_ends_in("20"), "autodj_queued": 1, "next_autodj": {"rid": 4}}
    client = _client()
    with _clock_at(BEFORE_THE_BREAK):
        await tick(dbsession, live, client, beets_integration)
    assert _pushed(client) == [music[1].id]
    assert await _times(dbsession, [music[1]]) == [datetime(2026, 9, 15, 10, 18, 30)]


async def test_behind_the_spot_of_a_break_the_file_goes_on_from_its_end(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The first line planned after the spot has aired ahead of the break. When
    the spot goes on air, the ones after it start at its end, one after the
    other: sooner than planned, no title waits for the time it had."""
    before, pub, after = await _day_file(dbsession, beets_integration)
    await _aired(dbsession, [*before, after[0]])
    assert after[1].planned_at > after[0].planned_at
    spot_starts = THE_BREAK + timedelta(seconds=1)
    spot_ends = spot_starts + timedelta(seconds=pub.duration)

    await _says(dbsession, pub, spot_starts, source="carts")

    assert await _times(dbsession, after[1:4]) == [
        spot_ends,
        spot_ends + timedelta(seconds=after[1].duration),
        spot_ends + timedelta(seconds=after[1].duration + after[2].duration),
    ]
