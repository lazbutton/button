"""FON-61: a jingle of the motif waits for the title sent before it
(``features.titles_sent_go_first``).

The night file of the bench: a jingle, then three music lines, over and over. The
clock decides the turn of a jingle from the beat of the playout: when the beat
counted no title in the queue of the Auto-DJ, the jingle went to the jingles
queue, which plays first. Two beats count none there while the clock has sent a
title before the jingle:

- behind a jingle or a sound of a cart, the queue of the Auto-DJ has already taken
  its next title out, to play it after: it counts none, and names it
  (``next_autodj``), as after the sound of a cut « Attend la fin » on the bench of
  the conducteur;
- the beat may leave before the clock pushes a title, as right after a live: it
  neither counts nor names it.

The jingle went ahead of that title, twenty seconds before its time. It now waits
for it, and goes at its end. A sound of the desk waits as the jingle does.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import RundownStatus
from radiotomate.models import RundownItem, Setting
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import PARIS, SETTING_TITLES_SENT_FIRST, tick
from radiotomate.scheduler.execution import LOST_AFTER
from tests.scheduler.test_clock import _client, _live
from tests.scheduler.test_desk_lines_air import _pushes, _put_next
from tests.scheduler.test_motif_jingles import _cue, _file, _line

# The value of the switch, and whether it is on. A missing key: it is.
SWITCH = [
    (None, True),
    ("1", True),
    ("true", True),
    ("0", False),
    ("false", False),
    ("Off", False),
]
# What cuts in on the antenna while the title waits loaded: the sound of a cart
# that waited for the end of the title before it, or a jingle.
CUT_IN = ["carts", "jingles"]
# The push of a moment ago, and one the beat would have shown long since.
JUST_NOW = timedelta(seconds=2)
LONG_AGO = timedelta(minutes=5)


async def _switch(dbsession: ormSession, value: str | None) -> None:
    if value is not None:
        await Setting.upsert(dbsession, SETTING_TITLES_SENT_FIRST, value)
        await dbsession.commit()


def _sent(line: RundownItem, ago: timedelta) -> None:
    """The playout took ``line`` in the queue of the Auto-DJ, ``ago``."""
    line.status = RundownStatus.IN_QUEUE.value
    line.reserved_at = line.sent_at = line.queued_at = datetime.now() - ago


async def _before_j4(
    dbsession: ormSession, beets: BeetsIntegration, *, sent: timedelta
) -> dict[str, RundownItem]:
    """The night file, aired up to its second title. Its third title, « M3 », the
    last before the jingle « J4 », was sent ``sent`` ago. Returns its lines, by
    their name, up to « M5 »."""
    names = await _file(dbsession, beets)
    lines = {
        name: await _line(dbsession, names, name)
        for name in ("J0", "M1", "M2", "M3", "J4", "M5")
    }
    for name in ("J0", "M1", "M2"):
        lines[name].status = RundownStatus.PLAYED.value
    _sent(lines["M3"], sent)
    await dbsession.commit()
    return lines


def _beat(title: RundownItem, source: str, remaining: str = "10", **said) -> dict:
    """``remaining`` seconds before the time of ``title``: ``source`` is on air,
    and the beat counts no title in the queue of the Auto-DJ."""
    at = title.planned_at.replace(tzinfo=PARIS) - timedelta(seconds=float(remaining))
    return _live(
        at.isoformat(),
        source=source,
        remaining=remaining,
        jingles_queued=0,
        autodj_queued=0,
        **said,
    )


def _jingles(client) -> list[str]:
    """The lines a tick pushed to the jingles queue."""
    return [line for queue, line in _pushes(client) if queue == "/queue/jingles"]


@pytest.mark.parametrize("source", CUT_IN)
@pytest.mark.parametrize(("value", "waits"), SWITCH)
async def test_a_jingle_waits_for_the_title_loaded_behind_a_sound(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    source: str,
    value: str | None,
    waits: bool,
):
    """The queue of the Auto-DJ has loaded « M3 », sent a minute ago: it counts
    none, and names it. The jingle after it waits; the titles after the jingle go
    behind « M3 », and the jingle will go ahead of them, at the end of « M3 ».
    Turned off, the jingle goes at once, ahead of « M3 », as before."""
    await _switch(dbsession, value)
    lines = await _before_j4(dbsession, beets_integration, sent=timedelta(minutes=1))
    client = _client()
    beat = _beat(lines["M3"], source, next_autodj=_cue(lines["M3"].id))
    await tick(dbsession, beat, client, beets_integration)
    if waits:
        assert _jingles(client) == []
        assert [queue for queue, _ in _pushes(client)] == ["/queue/autodj"] * 2
    else:
        assert _pushes(client)[0] == ("/queue/jingles", lines["J4"].id)


@pytest.mark.parametrize("source", [*CUT_IN, "autodj"])
@pytest.mark.parametrize(("value", "waits"), SWITCH)
async def test_a_jingle_waits_for_a_title_the_beat_does_not_show_yet(  # noqa: PLR0913
    container_tz: str,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    source: str,
    value: str | None,
    waits: bool,
):
    """« M3 » was pushed two seconds ago, and the beat left before: it neither
    counts nor names it. The jingle after it waits, behind a sound as at the end
    of the title on air. Turned off, it goes ahead of « M3 », as before."""
    await _switch(dbsession, value)
    lines = await _before_j4(dbsession, beets_integration, sent=JUST_NOW)
    assert JUST_NOW < LOST_AFTER
    client = _client()
    await tick(dbsession, _beat(lines["M3"], source, "2"), client, beets_integration)
    assert (lines["J4"].id not in _jingles(client)) is waits


@pytest.mark.parametrize("source", [*CUT_IN, "autodj"])
async def test_a_title_the_beat_should_show_and_does_not_is_lost(
    container_tz: str,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    source: str,
):
    """« M3 » was pushed five minutes ago, and the beat says the queue of the
    Auto-DJ empty: the playout has lost it, as when it starts again. The jingle
    after it goes at its turn, as before."""
    lines = await _before_j4(dbsession, beets_integration, sent=LONG_AGO)
    assert LONG_AGO > LOST_AFTER
    client = _client()
    await tick(dbsession, _beat(lines["M3"], source, "2"), client, beets_integration)
    assert _jingles(client) == [lines["J4"].id]


@pytest.mark.parametrize("source", CUT_IN)
async def test_a_title_loaded_after_the_jingle_holds_nothing(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    source: str,
):
    """« M3 » has aired, and the queue of the Auto-DJ has loaded « M5 », after the
    jingle in the file: the jingle goes at once, behind the sound on air."""
    lines = await _before_j4(dbsession, beets_integration, sent=LONG_AGO)
    lines["M3"].status = RundownStatus.PLAYED.value
    _sent(lines["M5"], LONG_AGO)
    await dbsession.commit()
    client = _client()
    beat = _beat(lines["M3"], source, next_autodj=_cue(lines["M5"].id))
    await tick(dbsession, beat, client, beets_integration)
    assert _jingles(client) == [lines["J4"].id]


@pytest.mark.parametrize(("kind", "queue"), [("son", "carts"), ("jingle", "jingles")])
@pytest.mark.parametrize(("value", "waits"), SWITCH)
async def test_a_sound_of_the_desk_waits_for_the_title_loaded_behind_a_sound(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    kind: str,
    queue: str,
    value: str | None,
    waits: bool,
):
    """« Mettre à la suite » after « M3 », loaded behind the sound of a cart: the
    sound of the desk waits for « M3 », as the jingle does. Turned off, it goes
    behind the sound on air, ahead of « M3 », as before."""
    await _switch(dbsession, value)
    lines = await _before_j4(dbsession, beets_integration, sent=timedelta(minutes=1))
    at = lines["J4"].planned_at.replace(tzinfo=PARIS)
    line = await _put_next(dbsession, at.isoformat(), kind)
    client = _client()
    beat = _beat(lines["M3"], "carts", next_autodj=_cue(lines["M3"].id))
    await tick(dbsession, beat, client, beets_integration)
    assert ((f"/queue/{queue}", line.id) not in _pushes(client)) is waits


async def test_the_title_a_hard_anchor_cut_holds_nothing_alone_in_its_queue(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """« M3 » was cut by a hard anchor: the queue of the Auto-DJ keeps it loaded
    until the end of the sound, then skips it. It names it, and counts nothing
    behind it: the jingle goes behind the sound. « M2 », sent there long ago and
    never counted since, is lost: it holds nothing either."""
    lines = await _before_j4(dbsession, beets_integration, sent=LONG_AGO)
    lines["M3"].status = RundownStatus.PLAYED.value
    _sent(lines["M2"], LONG_AGO)
    await dbsession.commit()
    client = _client()
    beat = _beat(lines["M3"], "carts", next_autodj=_cue(lines["M3"].id))
    await tick(dbsession, beat, client, beets_integration)
    assert _jingles(client) == [lines["J4"].id]


@pytest.mark.parametrize(("value", "waits"), SWITCH)
async def test_the_title_a_hard_anchor_cut_hides_a_title_pushed_a_moment_ago(  # noqa: PLR0913
    container_tz: str,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    waits: bool,
):
    """« M2 » was cut by a hard anchor, and its queue keeps it loaded; « M3 » was
    pushed behind it two seconds ago, and the beat counts nothing yet. The
    jingle waits for « M3 ». Turned off, it goes ahead of it, as before."""
    await _switch(dbsession, value)
    lines = await _before_j4(dbsession, beets_integration, sent=JUST_NOW)
    client = _client()
    beat = _beat(lines["M3"], "carts", next_autodj=_cue(lines["M2"].id))
    await tick(dbsession, beat, client, beets_integration)
    assert (lines["J4"].id not in _jingles(client)) is waits


@pytest.mark.parametrize(("value", "waits"), SWITCH)
async def test_a_sound_of_the_desk_waits_for_a_jingle_the_beat_does_not_show_yet(  # noqa: PLR0913
    container_tz: str,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    waits: bool,
):
    """« J4 » was pushed to the jingles queue two seconds ago, and the beat does
    not show it yet. A sound of the desk put after it goes to the carts queue,
    which plays first: it waits for « J4 », at the end of « M3 » as behind a
    sound. Turned off, it goes ahead of « J4 », as before."""
    await _switch(dbsession, value)
    lines = await _before_j4(dbsession, beets_integration, sent=LONG_AGO)
    lines["M3"].status = RundownStatus.ON_AIR.value
    _sent(lines["J4"], JUST_NOW)
    _sent(lines["M5"], LONG_AGO)
    await dbsession.commit()
    at = lines["M5"].planned_at.replace(tzinfo=PARIS)
    line = await _put_next(dbsession, at.isoformat(), "son")
    client = _client()
    beat = _beat(lines["M3"], "autodj", "2", next_autodj=_cue(lines["M5"].id))
    beat["autodj_queued"] = 1
    beat["radiotomate_item_id"] = lines["M3"].id
    await tick(dbsession, beat, client, beets_integration)
    assert (("/queue/carts", line.id) not in _pushes(client)) is waits
