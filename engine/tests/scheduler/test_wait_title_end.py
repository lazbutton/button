"""FON-53: a sound pushed at its turn tells the playout to wait for the end of the
title on air (``features.sounds_wait_for_title_end``).

The clock pushes a jingle of the motif, a soft anchor and a line of the desk in the
last seconds of the title on air. The jingles and carts queues of the playout cut
what plays: those seconds were cut, and came back after the sound. The push now
carries ``wait``, and the playout queues the sound where it goes at the end of the
title (``push_where_it_goes``, ``playout/radiotomate.liq``; the antenna bench plays
it). A hard anchor cuts, as before.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.models import Clock, Setting
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import SETTING_WAIT_TITLE_END, tick
from tests.scheduler.test_clock import JOURNEE_20, NIGHT, _client, _live
from tests.scheduler.test_desk_lines_air import _air, _put_next, _two_sent

# The value of the switch, and whether a sound then waits. A missing key: it does.
SWITCH = [
    (None, True),
    ("1", True),
    ("true", True),
    ("0", False),
    ("false", False),
    ("Off", False),
]
# The title of 10:20 ends: a minute later, one second left.
JOURNEE_21 = "2026-09-14T10:21:00+02:00"


def _payloads(client: AsyncMock, queue: str) -> list[dict]:
    """What a tick pushed to a queue of the playout."""
    return [
        call.kwargs["json"]
        for call in client.post.call_args_list
        if call.args[0] == f"/queue/{queue}"
    ]


async def _switch(dbsession: ormSession, value: str | None) -> None:
    if value is not None:
        await Setting.upsert(dbsession, SETTING_WAIT_TITLE_END, value)
        await dbsession.commit()


async def _soft_at_20(dbsession: ormSession) -> None:
    """The cut of 10:20 of the day clock waits for the end of the title."""
    clock = await Clock.from_name(dbsession, "Journée pubs")
    clock = await Clock.from_id(dbsession, clock.id)
    for pos in clock.anchored_positions():
        if pos.minute == 20:
            pos.sync = "molle"
    await dbsession.commit()


def _title_on_air(time: str, remaining: str) -> dict:
    return _live(
        time,
        source="autodj",
        remaining=remaining,
        next_jingle={"rid": 1},
        next_autodj={"rid": 1},
        jingles_queued=2,
        autodj_queued=3,
    )


@pytest.mark.parametrize(("value", "waits"), SWITCH)
async def test_a_jingle_of_the_motif_waits_for_the_end_of_the_title(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    waits: bool,
):
    """The music after it goes behind the title on air, in its own queue: it has
    nothing to wait for."""
    await _switch(dbsession, value)
    client = _client()
    actions = await tick(dbsession, _live(NIGHT), client, beets_integration)
    assert actions[0] == "jingle"
    [jingle] = _payloads(client, "jingles")
    assert jingle.get("wait", False) is waits
    music = _payloads(client, "autodj")
    assert music
    assert all("wait" not in payload for payload in music)


@pytest.mark.parametrize(("value", "waits"), SWITCH)
@pytest.mark.parametrize("forecast_at", ["2026-09-14T10:10:05+02:00", JOURNEE_20])
async def test_a_soft_anchor_waits_for_the_end_of_the_title(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
    forecast_at: str,
    value: str | None,
    waits: bool,
):
    """With the line the conducteur planned for it, ten minutes ahead, as with the
    sound the clock draws itself: a forecast built in the minute of the anchor does
    not plan it."""
    await _switch(dbsession, value)
    await _soft_at_20(dbsession)
    client = _client()
    before = await tick(
        dbsession, _title_on_air(forecast_at, "120"), client, beets_integration
    )
    assert not any(action.startswith("soft:") for action in before)
    assert not _payloads(client, "carts")

    client = _client()
    ready = await tick(
        dbsession, _title_on_air(JOURNEE_21, "1"), client, beets_integration
    )
    assert "soft:20" in ready
    [sound] = _payloads(client, "carts")
    assert sound["title"] == "Spot test"
    assert sound.get("wait", False) is waits


async def test_a_hard_anchor_cuts(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """« Coupe pile »: at its minute, whatever plays."""
    client = _client()
    actions = await tick(
        dbsession, _title_on_air(JOURNEE_20, "180"), client, beets_integration
    )
    assert "anchor:20" in actions
    [sound] = _payloads(client, "carts")
    assert sound["title"] == "Spot test"
    assert "wait" not in sound


@pytest.mark.parametrize(
    ("kind", "queue"), [("son", "carts"), ("pub", "carts"), ("jingle", "jingles")]
)
@pytest.mark.parametrize(("value", "waits"), SWITCH)
async def test_a_desk_line_at_its_turn_waits_for_the_end_of_the_title(  # noqa: PLR0913
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    kind: str,
    queue: str,
    value: str | None,
    waits: bool,
):
    """A sound put next at the desk goes in the last seconds of the title before
    it, as a jingle of the motif does."""
    await _switch(dbsession, value)
    music = await _two_sent(dbsession, beets_integration)
    line = await _put_next(dbsession, music[2]["at"], kind)

    client = _client()
    end = _air("2", head=music[2]["id"], autodj_queued=3)
    assert await tick(dbsession, end, client, beets_integration) == ["desk"]
    [sound] = _payloads(client, queue)
    assert sound["radiotomate_item_id"] == line.id
    assert sound.get("wait", False) is waits


async def test_a_music_line_put_next_has_nothing_to_wait_for(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """It goes in the queue of the Auto-DJ, behind the titles already there."""
    music = await _two_sent(dbsession, beets_integration)
    line = await _put_next(dbsession, music[2]["at"], "musique", duration=200)

    client = _client()
    assert await tick(dbsession, _air("120"), client, beets_integration) == ["desk"]
    [title] = _payloads(client, "autodj")
    assert title["radiotomate_item_id"] == line.id
    assert "wait" not in title
