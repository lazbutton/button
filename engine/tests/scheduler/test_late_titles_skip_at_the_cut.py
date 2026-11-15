"""FON-90: the title a cut « Coupe pile » was to cut does not air whole after it
(``features.hard_anchors_skip_late_titles``).

The day file of Tuesday: the title before the pub break of 10:20 runs into it,
its length stopped at the minute, and the break cuts it (FON-58). With the
antenna two or three seconds late, that title had not started at the minute,
and the break cut the one before; or it had started less than half a second
before, and the playout, which skips only a title that has played that long,
left it. It aired whole after the sound of the break, and the lines planned
after that sound went as late as it lasted. Decided on 14 November 2026: it
skips. Its line closes « sauté », « trop tard pour la coupure », the playout
takes it out of the queue of the Auto-DJ by the id of its line, and the lines
after the sound keep their time.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import RundownStatus
from radiotomate.models import RundownItem, Setting
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import (
    SETTING_SKIP_LATE_TITLES,
    TOO_LATE_FOR_THE_CUT,
    tick,
)
from tests.scheduler.test_clock import _client, _live
from tests.scheduler.test_hard_break_cuts import (
    THE_BREAK,
    _aired,
    _day_file,
    _says,
    _times,
)
from tests.scheduler.test_titles_sent_first import _sent
from tests.scheduler.test_wait_title_end import _payloads

# The value of the switch, and whether it is on. A missing key: it is.
SWITCH = [
    (None, True),
    ("1", True),
    ("true", True),
    ("0", False),
    ("false", False),
    ("Off", False),
]
# Tuesday, in the day clock: the pub break cuts at 10:20, and its sound lasts 8 s.
THE_MINUTE = "2026-09-15T10:20:00+02:00"
SOUND_ON_AIR = "2026-09-15T10:20:02+02:00"
# The sound of the break starts on its minute: the lines after it keep their time
# to the second.
SPOT_STARTS = THE_BREAK


async def _switch(dbsession: ormSession, value: str | None) -> None:
    if value is not None:
        await Setting.upsert(dbsession, SETTING_SKIP_LATE_TITLES, value)
        await dbsession.commit()


async def _the_last_two(
    dbsession: ormSession, beets: BeetsIntegration
) -> tuple[RundownItem, RundownItem, RundownItem, list[RundownItem]]:
    """The day file aired up to its last two titles before the break: the title
    before the one the break is to cut, and that one. Returns them, the line of
    the break, and the lines after its sound."""
    before, pub, after = await _day_file(dbsession, beets)
    await _aired(dbsession, before[:-2])
    return before[-2], before[-1], pub, after


def _beat(
    on_air: RundownItem,
    elapsed: float,
    remaining: float,
    *,
    queued: RundownItem | None = None,
) -> dict:
    """The beat at the minute: ``on_air`` has played ``elapsed`` seconds, and
    ``queued`` is loaded next in the queue of the Auto-DJ."""
    beat = {
        "source": "autodj",
        "title": on_air.resource.split(" — ")[-1],
        "artist": "Artiste",
        "radiotomate_item_id": on_air.id,
        "elapsed": str(elapsed),
        "remaining": str(remaining),
    }
    if queued is not None:
        beat.update(_loaded(queued))
    return _live(THE_MINUTE, **beat)


def _loaded(line: RundownItem) -> dict:
    """What the beat says of the queue of the Auto-DJ: ``line`` is loaded next,
    and one title counts in the queue."""
    uri = f'annotate:radiotomate_item_id="{line.id}":/media/t.mp3'
    return {
        "next_autodj": {"rid": 4, "title": "Titre", "initial_uri": uri},
        "autodj_queued": 1,
    }


def _sound_on_air(**said) -> dict:
    return _live(SOUND_ON_AIR, source="carts", remaining="6", **said)


def _skips(client) -> list[dict]:
    """What the clock asked the playout to skip."""
    return [
        call.kwargs.get("params") or {}
        for call in client.delete.call_args_list
        if call.args[0] == "/live"
    ]


async def _line(dbsession: ormSession, line: RundownItem) -> RundownItem:
    return await dbsession.get(RundownItem, line.id, populate_existing=True)


@pytest.mark.parametrize(("value", "skips"), SWITCH)
async def test_a_title_that_has_not_started_at_the_minute_skips(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    skips: bool,
):
    """At the minute, the title before the one the break was to cut still plays,
    and the break cuts it; that one waits in the queue of the Auto-DJ. It skips:
    its line closes, the playout takes it out of the queue with the cut title,
    and the lines after the sound keep their time. The switch off, it airs after
    the sound, and they go as late as it lasts."""
    await _switch(dbsession, value)
    previous, late, pub, after = await _the_last_two(dbsession, beets_integration)
    await _says(dbsession, previous, previous.planned_at + timedelta(seconds=3))
    _sent(late, timedelta(seconds=30))
    await dbsession.commit()
    planned = [row.planned_at for row in after[:3]]

    client = _client()
    beat = _beat(previous, elapsed=previous.duration - 1, remaining=1, queued=late)
    actions = await tick(dbsession, beat, client, beets_integration)
    assert "anchor:20" in actions
    row = await _line(dbsession, late)
    if skips:
        assert row.status == RundownStatus.SKIPPED.value
        assert row.reason == TOO_LATE_FOR_THE_CUT
    else:
        assert row.status == RundownStatus.IN_QUEUE.value
    # The title the break cut has played: its line stays on air until the sound.
    assert (await _line(dbsession, previous)).status == RundownStatus.ON_AIR.value

    client = _client()
    actions = await tick(dbsession, _sound_on_air(), client, beets_integration)
    assert "skip" in actions
    expected = {"queue": "autodj", "items": late.id} if skips else {"queue": "autodj"}
    assert _skips(client) == [expected]

    await _says(dbsession, pub, SPOT_STARTS, source="carts")
    spot_ends = SPOT_STARTS + timedelta(seconds=pub.duration)
    if skips:
        assert await _times(dbsession, after[:3]) == planned
    else:
        assert await _times(dbsession, [late, after[0]]) == [
            spot_ends,
            spot_ends + timedelta(seconds=late.duration),
        ]


@pytest.mark.parametrize("beat_left_before", [False, True])
async def test_a_title_started_less_than_half_a_second_before_skips(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    beat_left_before: bool,
):
    """The title the break was to cut started 0.4 s before the minute: the beat
    says it has played that long, or still names the title before it, having
    left before it started. It skips, and the playout takes it out though it is
    the title loaded in the queue."""
    previous, late, _pub, _after = await _the_last_two(dbsession, beets_integration)
    await _aired(dbsession, [previous])
    await _says(dbsession, late, THE_BREAK - timedelta(seconds=0.4))
    assert (await _line(dbsession, late)).status == RundownStatus.ON_AIR.value

    beat = (
        _beat(previous, elapsed=previous.duration - 0.6, remaining=0.6)
        if beat_left_before
        else _beat(late, elapsed=0.4, remaining=late.duration - 0.4)
    )
    actions = await tick(dbsession, beat, _client(), beets_integration)
    assert "anchor:20" in actions
    row = await _line(dbsession, late)
    assert row.status == RundownStatus.SKIPPED.value
    assert row.reason == TOO_LATE_FOR_THE_CUT

    client = _client()
    await tick(dbsession, _sound_on_air(), client, beets_integration)
    assert _skips(client) == [{"queue": "autodj", "items": late.id}]


async def test_a_title_that_has_played_is_cut_as_before(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The title the break was to cut has played two seconds: the break cuts it,
    its line stays played, and the playout skips it as the title it cut."""
    previous, late, _pub, _after = await _the_last_two(dbsession, beets_integration)
    await _aired(dbsession, [previous])
    await _says(dbsession, late, THE_BREAK - timedelta(seconds=2))

    beat = _beat(late, elapsed=2.0, remaining=late.duration - 2)
    actions = await tick(dbsession, beat, _client(), beets_integration)
    assert "anchor:20" in actions
    assert (await _line(dbsession, late)).status == RundownStatus.ON_AIR.value

    client = _client()
    await tick(dbsession, _sound_on_air(), client, beets_integration)
    assert _skips(client) == [{"queue": "autodj"}]


async def test_a_title_closed_too_late_stays_skipped_when_said(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The as-run of the title comes after the break closed its line: it had
    started 0.4 s before the minute. At the end of the sound, its queue says it
    once more as it takes the antenna back. Its line stays « sauté », and the
    lines after the sound keep their time."""
    previous, late, pub, after = await _the_last_two(dbsession, beets_integration)
    await _says(dbsession, previous, previous.planned_at + timedelta(seconds=3))
    _sent(late, timedelta(seconds=30))
    await dbsession.commit()
    planned = [row.planned_at for row in after[:3]]

    beat = _beat(previous, elapsed=previous.duration - 1, remaining=1, queued=late)
    await tick(dbsession, beat, _client(), beets_integration)
    await _says(dbsession, late, THE_BREAK - timedelta(seconds=0.4))
    await _says(dbsession, pub, SPOT_STARTS, source="carts")
    spot_ends = SPOT_STARTS + timedelta(seconds=pub.duration)
    await _says(dbsession, late, spot_ends)

    row = await _line(dbsession, late)
    assert row.status == RundownStatus.SKIPPED.value
    assert row.reason == TOO_LATE_FOR_THE_CUT
    assert await _times(dbsession, after[:3]) == planned


async def test_a_title_planned_after_the_break_does_not_skip(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The title ready in the queue of the Auto-DJ for after the sound of the
    break is not late: it stays, and its line too."""
    previous, late, _pub, after = await _the_last_two(dbsession, beets_integration)
    await _aired(dbsession, [previous])
    await _says(dbsession, late, THE_BREAK - timedelta(seconds=2))
    ready = next(row for row in after if row.kind == "musique")
    _sent(ready, timedelta(seconds=30))
    await dbsession.commit()

    beat = _beat(late, elapsed=2.0, remaining=late.duration - 2, queued=ready)
    await tick(dbsession, beat, _client(), beets_integration)
    assert (await _line(dbsession, ready)).status == RundownStatus.IN_QUEUE.value
    assert datetime(2026, 9, 15, 10, 20) < ready.planned_at


@pytest.mark.parametrize(("value", "goes"), [(None, True), ("0", False)])
async def test_the_jingle_after_the_sound_goes_while_the_queue_names_the_late_title(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    goes: bool,
):
    """Seen on the bench of the conducteur on 15 November 2026. During the sound
    of the break, the queue of the Auto-DJ keeps the title closed too late for it
    loaded, and the beat names it, until the queue takes the antenna back. The
    jingle planned after the sound goes behind it all the same, at its turn: it
    waited for that title as for a title ahead of it, never went, and closed
    « tour passé » when the title after it aired. The switch off, that title airs
    after the sound, and the jingle waits for it, as before."""
    await _switch(dbsession, value)
    previous, late, pub, after = await _the_last_two(dbsession, beets_integration)
    jingle = after[0]
    assert jingle.kind == "jingle"
    await _says(dbsession, previous, previous.planned_at + timedelta(seconds=3))
    _sent(late, timedelta(seconds=30))
    await dbsession.commit()

    beat = _beat(previous, elapsed=previous.duration - 1, remaining=1, queued=late)
    actions = await tick(dbsession, beat, _client(), beets_integration)
    assert "anchor:20" in actions
    await _says(dbsession, pub, SPOT_STARTS, source="carts")

    client = _client()
    actions = await tick(
        dbsession, _sound_on_air(**_loaded(late)), client, beets_integration
    )
    assert ("jingle" in actions) is goes
    if goes:
        [sent] = _payloads(client, "jingles")
        assert sent["radiotomate_item_id"] == jingle.id
