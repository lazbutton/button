"""FON-58: the conducteur keeps its times around a hard anchor and a long sound.

Three faults put the conducteur minutes away from the antenna, replayed with the
scheduler in front of the real Liquidsoap:

- the conducteur planned a gap before a hard anchor, and the clock filled it with
  the title planned after the sound of the anchor, or left a blank. The title that
  runs into a hard anchor is now planned before it, and the anchor cuts it
  (``features.hard_anchors_cut_titles``);
- behind a long sound, the clock kept two titles queued, the queue cleaner took
  them out after ten minutes, and the clock pushed two more. It now keeps one
  title ready, which the cleaner of the playout leaves, and pushes a second one
  only when it should air soon (``features.titles_queued_close_to_air``);
- the as-run moved every line after the one on air by one delta, across the
  sound of an anchor, and refused a delta beyond ten minutes. It now stops at the
  next hard anchor, believes a line the playout names, and does not take the title
  a hard anchor cut, said again at the end of the sound, for a second airing.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.models import MetadataLog, RundownItem, Setting
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import (
    DEFAULT_QUEUE_MAX_AGE,
    PARIS,
    QUEUE_WAIT_SHARE,
    SETTING_HARD_ANCHORS_CUT,
    SETTING_QUEUE_CLOSE_TO_AIR,
    _queue_wait,
    set_queue_max_age,
    tick,
)
from radiotomate.scheduler.execution import (
    ensure_forecast,
    realign_rundown,
    reconcile_as_run,
)
from radiotomate.scheduler.rundown import build_rundown, item_end_at
from tests.scheduler.test_cart_draw import _clock_at, _music_on_air
from tests.scheduler.test_clock import (
    NIGHT,
    _client,
    _live,
    _night_music,
    _pushed_ids,
)
from tests.scheduler.test_wait_title_end import _payloads

# The value of a switch, and whether it is on. A missing key: it is.
SWITCH = [
    (None, True),
    ("1", True),
    ("true", True),
    ("0", False),
    ("false", False),
    ("Off", False),
]
# Tuesday, in the day clock: a pub break cuts at 10:20.
BEFORE_THE_BREAK = "2026-09-15T10:17:30+02:00"
THE_BREAK = datetime(2026, 9, 15, 10, 20)


async def _switch(dbsession: ormSession, key: str, value: str | None) -> None:
    if value is not None:
        await Setting.upsert(dbsession, key, value)
        await dbsession.commit()


def _at(item: dict) -> datetime:
    return datetime.fromisoformat(item["at"]).replace(tzinfo=None)


def _end(item: dict) -> datetime:
    return item_end_at(item).replace(tzinfo=None)


# ---- The conducteur plans the title a hard anchor cuts -----------------------


@pytest.mark.parametrize(("value", "cuts"), SWITCH)
async def test_the_title_that_runs_into_a_hard_break_is_planned_until_it(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    cuts: bool,
):
    """At 10:17:30 a jingle, then a title of three minutes: it would still play
    at 10:20. It is planned, until the break that cuts it. Switch off, the
    conducteur leaves it out, and has nothing between the jingle and the break."""
    await _switch(dbsession, SETTING_HARD_ANCHORS_CUT, value)
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime.fromisoformat(BEFORE_THE_BREAK),
        cursor=0,
    )
    items = data["items"]
    pub = next(item for item in items if item["kind"] == "pub")
    assert (_at(pub), pub["when"], pub["minute"]) == (THE_BREAK, "anchored", 20)
    before = items[: items.index(pub)]
    assert before[0]["kind"] == "jingle"
    if cuts:
        assert [item["kind"] for item in before] == ["jingle", "musique"]
        assert _at(before[1]) == _end(before[0])
        assert _end(before[1]) == THE_BREAK
        assert before[1]["status"] == "prévu"
    else:
        assert [item["kind"] for item in before] == ["jingle"]
        assert _end(before[0]) < THE_BREAK
    # The file goes on where the spot ends, with the next step of the motif.
    after = items[items.index(pub) + 1]
    assert _at(after) == _end(pub)
    if cuts:
        assert after["resource"] != before[1]["resource"]


@pytest.mark.parametrize(("value", "cuts"), SWITCH)
async def test_the_clock_pushes_the_title_a_hard_break_will_cut(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    cuts: bool,
):
    """The antenna plays music until the break. Switch off, the clock holds the
    title that would run into it: a blank until the break."""
    await _switch(dbsession, SETTING_HARD_ANCHORS_CUT, value)
    client = _client()
    with _clock_at(BEFORE_THE_BREAK):
        actions = await tick(
            dbsession, _live(BEFORE_THE_BREAK), client, beets_integration
        )
    assert actions[0] == "jingle"
    music = _payloads(client, "autodj")
    assert bool(music) is cuts
    if cuts:
        first = await RundownItem.from_id(dbsession, music[0]["radiotomate_item_id"])
        assert first.planned_at < THE_BREAK


async def test_a_title_keeps_going_before_a_hard_break_with_nothing_to_play(
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
):
    """Without the cart of its pubs, nor the one of its fallback, the break of
    10:20 cuts nothing: the title plays to its end, and the file goes on from
    there. The break keeps its line, « manquant », to be repaired."""
    data = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime.fromisoformat(BEFORE_THE_BREAK),
        cursor=0,
    )
    items = data["items"]
    pub = next(item for item in items if item["kind"] == "pub")
    assert (_at(pub), pub["status"]) == (THE_BREAK, "manquant")
    title = next(item for item in items if item["kind"] == "musique")
    assert title["duration"] == 180
    assert _at(title) < THE_BREAK < _end(title)
    after = items[items.index(pub) + 1]
    assert _at(after) == _end(title)


# ---- One title ready, a second one close to air ------------------------------


def _behind_a_long_sound(remaining: str, **queues) -> dict:
    """A recorded show of the carts queue is on air, the jingles queue is full."""
    return _live(
        NIGHT,
        source="carts",
        remaining=remaining,
        next_jingle={"rid": 1},
        jingles_queued=2,
        **queues,
    )


@pytest.mark.parametrize(("value", "close"), SWITCH)
async def test_one_title_waits_ready_behind_a_long_sound(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    close: bool,
):
    """Fifty minutes of a show are left. One title goes to the queue, where the
    cleaner of the playout leaves it; the next one would wait there until the
    cleaner takes it out. Switch off, two go, as before."""
    await _switch(dbsession, SETTING_QUEUE_CLOSE_TO_AIR, value)
    music = await _night_music(dbsession, beets_integration)
    client = _client()
    await tick(
        dbsession,
        _behind_a_long_sound("3000", autodj_queued=0),
        client,
        beets_integration,
    )
    sent = music[:1] if close else music[:2]
    assert _pushed_ids(client) == [line["id"] for line in sent]

    client = _client()
    await tick(
        dbsession,
        _behind_a_long_sound("3000", next_autodj={"rid": 1}, autodj_queued=1),
        client,
        beets_integration,
    )
    assert _pushed_ids(client) == ([] if close else [music[2]["id"]])


async def test_the_second_title_goes_when_the_long_sound_nears_its_end(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    music = await _night_music(dbsession, beets_integration)
    await tick(
        dbsession,
        _behind_a_long_sound("3000", autodj_queued=0),
        _client(),
        beets_integration,
    )
    client = _client()
    await tick(
        dbsession,
        _behind_a_long_sound("300", next_autodj={"rid": 1}, autodj_queued=1),
        client,
        beets_integration,
    )
    assert _pushed_ids(client) == [music[1]["id"]]


async def test_a_title_planned_far_ahead_waits_out_of_the_queue(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The conducteur plans the fourth title nine minutes ahead, after the sound
    of an anchor say: it does not go behind the one that waits."""
    music = await _night_music(dbsession, beets_integration)
    for line in music[:3]:
        row = await RundownItem.from_id(dbsession, line["id"])
        row.status = "played"
    await dbsession.commit()
    far = _live(
        NIGHT,
        source="autodj",
        remaining="100",
        next_jingle={"rid": 1},
        jingles_queued=2,
        autodj_queued=0,
    )
    client = _client()
    await tick(dbsession, far, client, beets_integration)
    # The first one goes all the same: the queue never stays empty.
    assert _pushed_ids(client) == [music[3]["id"]]


async def test_no_second_title_behind_a_relay(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """A relay ends when someone stops it: nothing tells how long a second title
    would wait behind it."""
    music = await _night_music(dbsession, beets_integration)
    relay = {"source": "relay", "remaining": "0"}
    client = _client()
    await tick(
        dbsession,
        {**_behind_a_long_sound("0", autodj_queued=0), **relay},
        client,
        beets_integration,
    )
    assert _pushed_ids(client) == [music[0]["id"]]
    client = _client()
    await tick(
        dbsession,
        {**_behind_a_long_sound("0", next_autodj={"rid": 1}, autodj_queued=1), **relay},
        client,
        beets_integration,
    )
    assert _pushed_ids(client) == []


async def test_a_station_without_the_queue_cleaner_keeps_two_titles_ahead(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """Nothing takes a title out of a queue there: it may wait."""
    set_queue_max_age(None)
    music = await _night_music(dbsession, beets_integration)
    client = _client()
    await tick(
        dbsession,
        _behind_a_long_sound("3000", autodj_queued=0),
        client,
        beets_integration,
    )
    assert _pushed_ids(client) == [music[0]["id"], music[1]["id"]]


def test_the_wait_follows_the_age_the_cleaner_allows():
    assert _queue_wait["limit"] == DEFAULT_QUEUE_MAX_AGE * QUEUE_WAIT_SHARE
    set_queue_max_age(120.0)
    assert _queue_wait["limit"] == 120.0 * QUEUE_WAIT_SHARE
    set_queue_max_age(None)
    assert _queue_wait["limit"] is None


@pytest.mark.parametrize(
    ("cleaning", "limit"), [(True, 300 * QUEUE_WAIT_SHARE), (False, None)]
)
async def test_the_scheduler_tells_the_clock_how_long_its_cleaner_allows(
    raw_app, cleaning: bool, limit: float | None
):
    """From `queue_cleaner` in the YAML, as the cleaner reads it. Without the
    cleaner, nothing takes a title out: no limit."""
    raw_app.config["QUEUE_CLEAN_ENABLED"] = cleaning
    raw_app.config["QUEUE_CLEAN_MAX_AGE"] = 300
    async with raw_app.test_app():
        assert _queue_wait["limit"] == limit


@pytest.mark.parametrize(("value", "close"), SWITCH)
async def test_a_jingle_of_the_motif_waits_out_of_its_queue_behind_a_long_sound(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    close: bool,
):
    """Behind a sound of the carts queue on air, a jingle goes at once, and waits
    its end in its queue: behind a show of fifty minutes, the cleaner would take
    it out. It goes when the show nears its end."""
    await _switch(dbsession, SETTING_QUEUE_CLOSE_TO_AIR, value)
    client = _client()
    actions = await tick(
        dbsession,
        _live(NIGHT, source="carts", remaining="3000"),
        client,
        beets_integration,
    )
    assert ("jingle" in actions) is not close
    client = _client()
    actions = await tick(
        dbsession,
        _live(NIGHT, source="carts", remaining="300"),
        client,
        beets_integration,
    )
    assert ("jingle" in actions) is close


def _behind_the_sound(cut: RundownItem, **said) -> dict:
    """The sound of a hard break is on air, or the jingle behind it. The title the
    break cut is still what the queue of the Auto-DJ has loaded."""
    beat = {
        "source": "carts",
        "remaining": "60",
        "next_autodj": {
            "rid": 3,
            "title": "Titre",
            "initial_uri": f'annotate:radiotomate_item_id="{cut.id}":/media/titre.mp3',
        },
        "autodj_queued": 2,
        **said,
    }
    return _live(NIGHT, **beat)


async def test_a_jingle_goes_behind_the_sound_of_a_hard_break(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The title a hard break cut stays loaded in the queue of the Auto-DJ until
    the end of the sound, where it is skipped: it is not a title still to air
    ahead of the jingle planned after the sound. It hides the title queued behind
    it, which is one: the jingle planned after that title waits for it."""
    await ensure_forecast(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 0, 30, tzinfo=PARIS),
        cursor=0,
    )
    rows = list(
        await dbsession.scalars(
            select(RundownItem).order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )
    jingles = [row for row in rows if row.kind == "jingle"]
    music = [row for row in rows if row.kind == "musique"]
    # The first jingle and two titles have aired; the break cut the third title,
    # and the fourth one, planned after the second jingle, waits in the queue.
    cut, queued = music[2], music[3]
    for row in [jingles[0], *music[:2]]:
        row.status = "played"
    cut.status = "in_queue"
    queued.status = "in_queue"
    await dbsession.commit()

    # Not cut yet: the third title is still to air, ahead of the second jingle.
    client = _client()
    actions = await tick(dbsession, _behind_the_sound(cut), client, beets_integration)
    assert "jingle" not in actions

    cut.status = "played"
    await dbsession.commit()
    client = _client()
    actions = await tick(dbsession, _behind_the_sound(cut), client, beets_integration)
    assert "jingle" in actions
    [sent] = _payloads(client, "jingles")
    assert sent["radiotomate_item_id"] == jingles[1].id

    # That jingle on air, its last seconds fill the queue with the three titles
    # of the motif: the third jingle, next in the file, stays behind them.
    for row in music[4:6]:
        row.status = "in_queue"
    await dbsession.commit()
    client = _client()
    on_air = _behind_the_sound(
        cut, source="jingles", remaining="2", jingles_queued=0, autodj_queued=3
    )
    actions = await tick(dbsession, on_air, client, beets_integration)
    assert "jingle" not in actions
    assert not client.post.called


# ---- The as-run around a hard anchor -----------------------------------------


async def _says(
    dbsession: ormSession,
    line: RundownItem,
    at: datetime,
    *,
    source: str = "autodj",
    named: bool = True,
) -> None:
    """The playout says a line is on air, as ``POST /metadata_log`` takes it in."""
    payload = {
        "source": source,
        "title": line.resource.split(" — ")[-1],
        "on_air": at.isoformat(sep=" "),
    }
    if named:
        payload["radiotomate_item_id"] = line.id
    elif line.sound_id is not None:
        payload["radiotomate_sound_id"] = line.sound_id
    log = await MetadataLog.from_playout(dbsession, payload)
    dbsession.add(log)
    await reconcile_as_run(dbsession, log)
    await dbsession.commit()


async def _day_file(
    dbsession: ormSession, beets_integration: BeetsIntegration
) -> tuple[list[RundownItem], RundownItem, list[RundownItem]]:
    """The file of Tuesday from 10:10: the lines before the pub break of 10:20,
    its line, and the lines after its spot."""
    await ensure_forecast(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 15, 10, 10, tzinfo=PARIS),
        cursor=0,
    )
    rows = list(
        await dbsession.scalars(
            select(RundownItem).order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )
    pub = next(row for row in rows if row.kind == "pub")
    assert pub.planned_at == THE_BREAK
    before = [row for row in rows if row.planned_at < THE_BREAK]
    after = [row for row in rows if row.planned_at > THE_BREAK]
    return before, pub, after


async def _aired(dbsession: ormSession, rows: list[RundownItem]) -> None:
    for row in rows:
        row.status = "played"
    await dbsession.commit()


async def _times(dbsession: ormSession, rows: list[RundownItem]) -> list[datetime]:
    return [
        (await dbsession.get(RundownItem, row.id, populate_existing=True)).planned_at
        for row in rows
    ]


async def test_what_is_planned_after_a_hard_break_does_not_slide_with_what_is_before(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The antenna runs forty seconds late at 10:10. The lines before the break
    of 10:20 follow; the break goes on its minute, and the lines after its spot
    keep their time."""
    before, pub, after = await _day_file(dbsession, beets_integration)
    planned_before = [row.planned_at for row in before]
    planned_after = [row.planned_at for row in after[:4]]
    late = timedelta(seconds=40)

    await _says(dbsession, before[0], before[0].planned_at + late)

    assert await _times(dbsession, before) == [at + late for at in planned_before]
    assert await _times(dbsession, [pub]) == [THE_BREAK]
    assert await _times(dbsession, after[:4]) == planned_after


async def test_a_title_aired_before_the_break_it_was_planned_after_moves_alone(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The antenna had nothing left before the break: the first title planned
    after its spot fills in. It takes its real time; the lines after it are still
    to come after the spot."""
    _before, _pub, after = await _day_file(dbsession, beets_integration)
    planned = [row.planned_at for row in after[:4]]
    early = datetime(2026, 9, 15, 10, 19, 30)

    await _says(dbsession, after[0], early)

    assert await _times(dbsession, after[:4]) == [early, *planned[1:]]


async def test_what_was_still_to_air_goes_after_the_spot_of_a_hard_break(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The antenna runs late: at 10:20 the title before the one the break was to
    cut is still on air, and that one waits in the queue. It airs after the
    spot, then the lines planned after the spot, one after the other."""
    before, pub, after = await _day_file(dbsession, beets_integration)
    await _aired(dbsession, before[:-1])
    waits = before[-1]
    waits.status = "in_queue"
    await dbsession.commit()
    spot_starts = THE_BREAK + timedelta(seconds=1)
    spot_ends = spot_starts + timedelta(seconds=pub.duration)

    await _says(dbsession, pub, spot_starts, source="carts")

    assert await _times(dbsession, [pub]) == [THE_BREAK]
    then = spot_ends + timedelta(seconds=waits.duration)
    assert await _times(dbsession, [waits, after[0], after[1]]) == [
        spot_ends,
        then,
        then + timedelta(seconds=after[0].duration),
    ]


async def test_a_title_cut_by_a_hard_break_is_not_on_air_again_when_said_again(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The break of 10:20 cuts a title. At the end of its spot the queue of the
    Auto-DJ says that title once more, then skips it. Its line stays played, and
    the lines after the spot stay where they are: they slid by the length of the
    spot, back and forth."""
    before, pub, after = await _day_file(dbsession, beets_integration)
    await _aired(dbsession, before[:-1])
    cut = before[-1]
    await _says(dbsession, cut, cut.planned_at)

    moment = "2026-09-15T10:20:01+02:00"
    on_air = {
        **_music_on_air(moment),
        "title": cut.resource.split(" — ")[-1],
        "artist": "Artiste",
        "radiotomate_item_id": cut.id,
    }
    with _clock_at(moment):
        assert "anchor:20" in await tick(
            dbsession, on_air, _client(), beets_integration
        )
    await _says(dbsession, pub, THE_BREAK + timedelta(seconds=1), source="carts")
    planned = await _times(dbsession, after[:4])

    spot_ends = THE_BREAK + timedelta(seconds=21)
    await _says(dbsession, cut, spot_ends)

    row = await dbsession.get(RundownItem, cut.id, populate_existing=True)
    assert row.status == "played"
    assert row.planned_at == cut.planned_at
    assert await _times(dbsession, after[:4]) == planned
    # The next title then starts on its time.
    await _says(dbsession, after[0], spot_ends)
    assert await _times(dbsession, after[:4]) == planned


async def test_a_line_the_playout_names_is_believed_long_after_its_time(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """After a live of half an hour, the file starts again where it stopped:
    its first line takes its real time, and the lines after it start one after
    the other from there."""
    music = await _night_music(dbsession, beets_integration)
    rows = [await RundownItem.from_id(dbsession, line["id"]) for line in music[:3]]
    planned = [row.planned_at for row in rows]
    late = timedelta(minutes=30)

    await _says(dbsession, rows[0], planned[0] + late)

    assert await _times(dbsession, rows) == [at + late for at in planned]


async def test_the_lines_planned_later_than_their_turn_keep_their_time(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """A title held behind a show of half an hour starts thirty minutes late. The
    lines after it were planned after the show: they start at the end of the
    title, as planned, not thirty minutes later."""
    await ensure_forecast(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 0, 30, tzinfo=PARIS),
        cursor=0,
    )
    rows = list(
        await dbsession.scalars(
            select(RundownItem).order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )
    held = next(row for row in rows if row.kind == "musique")
    index = rows.index(held)
    show = timedelta(minutes=30)
    for row in rows[index + 1 :]:
        row.planned_at += show
    # And a gap in the file, further on.
    for row in rows[index + 3 :]:
        row.planned_at += timedelta(minutes=5)
    await dbsession.commit()
    planned = [row.planned_at for row in rows[index + 1 : index + 5]]
    started = held.planned_at + show
    assert planned[0] == started + timedelta(seconds=held.duration)

    await _says(dbsession, held, started)

    assert await _times(dbsession, rows[index : index + 5]) == [started, *planned]


async def test_a_line_the_playout_names_is_believed_long_before_its_time(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The lines before it never aired: the lines after it come that much
    sooner."""
    music = await _night_music(dbsession, beets_integration)
    rows = [await RundownItem.from_id(dbsession, line["id"]) for line in music[4:7]]
    planned = [row.planned_at for row in rows]
    early = timedelta(minutes=12)

    await _says(dbsession, rows[0], planned[0] - early)

    assert await _times(dbsession, rows) == [at - early for at in planned]


async def test_a_line_found_by_its_sound_is_not_believed_far_from_its_time(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """A small rotation says its sounds again and again: linked by its sound, a
    line an hour away is another passage."""
    await ensure_forecast(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 0, 30, tzinfo=PARIS),
        cursor=0,
    )
    rows = list(
        await dbsession.scalars(
            select(RundownItem).order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )
    jingle = rows[0]
    assert jingle.sound_id is not None
    planned = [row.planned_at for row in rows[:3]]

    shift = await realign_rundown(
        dbsession, jingle, jingle.planned_at + timedelta(minutes=30)
    )

    assert shift == timedelta(0)
    assert [row.planned_at for row in rows[:3]] == planned


async def test_a_soft_break_goes_later_with_the_title_before_it(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The break of 10:20 waits for the end of the title: planned there, it
    follows that title when the antenna runs late, with the lines after it."""
    from tests.scheduler.test_wait_title_end import _soft_at_20

    await _soft_at_20(dbsession)
    await ensure_forecast(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 15, 10, 10, tzinfo=PARIS),
        cursor=0,
    )
    rows = list(
        await dbsession.scalars(
            select(RundownItem).order_by(RundownItem.planned_at, RundownItem.sequence)
        )
    )
    pub = next(row for row in rows if row.kind == "pub")
    assert pub.planned_at > THE_BREAK
    index = rows.index(pub)
    planned = [row.planned_at for row in rows[: index + 3]]
    late = timedelta(seconds=40)

    await _says(dbsession, rows[0], rows[0].planned_at + late)

    assert await _times(dbsession, rows[: index + 3]) == [at + late for at in planned]
