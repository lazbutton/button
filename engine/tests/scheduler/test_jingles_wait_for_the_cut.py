"""FON-89: a jingle of the motif planned after a cut « Coupe pile » does not go
before its minute (``features.jingles_wait_for_hard_anchors``).

The day file of Tuesday: the title before the pub break of 10:20 ends at the
minute, the break plays its sound, then come a jingle of the motif and a title.
The turn of a jingle comes when no title planned before it waits in the queue of
the Auto-DJ, and the title on air has less than three seconds to play: nothing
there looked at the break to come. In the last seconds before the minute, the
clock sent the jingle; the break cut the title, the jingle waited behind its
sound, and the queue cleaner took it out behind a sound longer than its delay.
The bench of the conducteur saw it twice in thirty passes, behind a program of
48 s; on a station, behind a program of more than ten minutes.

The jingle now waits for the sound of the break, then goes behind it at its turn,
near its end (FON-58). One that ends before the minute, on an antenna ahead of
the conducteur, goes at its turn, as before.
"""

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import RundownStatus
from radiotomate.models import RundownItem, Setting
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import SETTING_JINGLES_WAIT_FOR_CUT, tick
from tests.scheduler.test_clock import _client, _live
from tests.scheduler.test_hard_break_cuts import THE_BREAK, _day_file, _says
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
SECOND_BEFORE = "2026-09-15T10:19:59+02:00"
THE_MINUTE = "2026-09-15T10:20:00+02:00"
SOUND_ON_AIR = "2026-09-15T10:20:02+02:00"
# Ninety seconds before the break: a jingle of 8 s airs whole before it.
EARLY = "2026-09-15T10:18:30+02:00"


async def _switch(dbsession: ormSession, value: str | None) -> None:
    if value is not None:
        await Setting.upsert(dbsession, SETTING_JINGLES_WAIT_FOR_CUT, value)
        await dbsession.commit()


async def _before_the_break(
    dbsession: ormSession, beets: BeetsIntegration
) -> tuple[RundownItem, RundownItem, RundownItem]:
    """The day file, aired up to its last title before the break, which is on air.
    The title after the jingle waits ready in the queue of the Auto-DJ, as the
    clock keeps one there. Returns the lines of the break, of the jingle, and of
    that title."""
    before, pub, after = await _day_file(dbsession, beets)
    jingle, ready = after[0], after[1]
    assert jingle.kind == "jingle"
    assert ready.kind == "musique"
    for row in before[:-1]:
        row.status = RundownStatus.PLAYED.value
    before[-1].status = RundownStatus.ON_AIR.value
    _sent(ready, timedelta(minutes=1))
    await dbsession.commit()
    return pub, jingle, ready


def _beat(time: str, ready: RundownItem, **said) -> dict:
    """The beat of the playout: the title on air has two seconds to play, and
    ``ready`` is loaded next in the queue of the Auto-DJ."""
    beat = {
        "source": "autodj",
        "remaining": "2",
        "next_autodj": {
            "rid": 3,
            "title": "Titre",
            "initial_uri": f'annotate:radiotomate_item_id="{ready.id}":/media/t.mp3',
        },
        "autodj_queued": 1,
        **said,
    }
    return _live(time, **beat)


@pytest.mark.parametrize(("value", "waits"), SWITCH)
async def test_a_jingle_planned_after_a_hard_break_waits_for_its_sound(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    waits: bool,
):
    """The title on air has two seconds to play, the break is due within the
    second, and the jingle is planned after its sound. It does not go before the
    minute, nor in the tick the clock sends the break, while the beat still says
    the title on air; nor once the playout says the sound on air, until the beat
    shows it. Then it goes behind the sound. The switch off, it goes before the
    minute, as before."""
    await _switch(dbsession, value)
    pub, jingle, ready = await _before_the_break(dbsession, beets_integration)

    client = _client()
    actions = await tick(
        dbsession, _beat(SECOND_BEFORE, ready), client, beets_integration
    )
    assert ("jingle" in actions) is not waits
    if not waits:
        [sent] = _payloads(client, "jingles")
        assert sent["radiotomate_item_id"] == jingle.id
        return

    # The minute: the clock sends the sound of the break. The beat left before.
    client = _client()
    beat = _beat(THE_MINUTE, ready, remaining="1")
    actions = await tick(dbsession, beat, client, beets_integration)
    assert "anchor:20" in actions
    assert "jingle" not in actions

    # The playout says the sound on air before its beat shows it.
    await _says(dbsession, pub, THE_BREAK, source="carts")
    client = _client()
    beat = _beat(THE_MINUTE, ready, remaining="0")
    actions = await tick(dbsession, beat, client, beets_integration)
    assert "jingle" not in actions

    client = _client()
    beat = _beat(SOUND_ON_AIR, ready, source="carts", remaining="6")
    actions = await tick(dbsession, beat, client, beets_integration)
    assert "jingle" in actions
    [sent] = _payloads(client, "jingles")
    assert sent["radiotomate_item_id"] == jingle.id


@pytest.mark.parametrize("value", [None, "0"])
async def test_a_jingle_that_ends_before_the_break_goes_at_its_turn(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
):
    """On an antenna ahead of the conducteur, the title on air ends ninety seconds
    before the break: the jingle planned after it airs whole before the minute.
    It goes at its turn, as before, whatever the switch."""
    await _switch(dbsession, value)
    _, jingle, ready = await _before_the_break(dbsession, beets_integration)
    client = _client()
    actions = await tick(dbsession, _beat(EARLY, ready), client, beets_integration)
    assert "jingle" in actions
    [sent] = _payloads(client, "jingles")
    assert sent["radiotomate_item_id"] == jingle.id


async def test_a_break_that_does_not_go_holds_no_jingle(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """A break closed before its minute, held by a live say, cuts nothing: the
    jingle planned after it goes at its turn."""
    pub, jingle, ready = await _before_the_break(dbsession, beets_integration)
    pub.status = RundownStatus.SKIPPED.value
    await dbsession.commit()
    client = _client()
    actions = await tick(
        dbsession, _beat(SECOND_BEFORE, ready), client, beets_integration
    )
    assert "jingle" in actions
    [sent] = _payloads(client, "jingles")
    assert sent["radiotomate_item_id"] == jingle.id
