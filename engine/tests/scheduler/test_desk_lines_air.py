"""FON-14: the desk lines put next air at their turn (``features.desk_lines_air``).

The night file of the bench: a jingle, then three music lines, over and over. The
first tick sends the first two music lines: the clock keeps two titles ahead.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainConflict
from radiotomate.enums import RundownStatus
from radiotomate.models import PlayoutCommand, RundownItem, Setting
from radiotomate.models.cart import Cart
from radiotomate.scheduler.clock import PARIS, tick
from radiotomate.scheduler.desk import SENT_GRACE, SETTING_DESK_LINES_AIR
from radiotomate.scheduler.execution import (
    DESK_ORIGIN,
    delete_desk_item,
    ensure_forecast,
    expire_past_desk_items,
    insert_desk_item,
    patch_desk_item,
    realign_rundown,
)
from radiotomate.scheduler_api import Scheduler
from tests.scheduler.test_clock import (
    NIGHT,
    _autodj_wants_two,
    _client,
    _live,
    _night_music,
    _pushed_ids,
)
from tests.scheduler.test_desk_json import _reorder_row, _reorder_version
from tests.scheduler.test_live_json import _live_client, _scheduler_facing

OFF = [("0", False), ("false", False), ("Off", False)]


def _cue(line_id: str) -> dict:
    """The next title of a playout queue, annotated as the clock pushes it."""
    return {"rid": 7, "initial_uri": f'annotate:radiotomate_item_id="{line_id}":/x.mp3'}


def _air(
    remaining: str,
    *,
    source: str = "autodj",
    head: str | None = None,
    autodj_queued: int = 1,
) -> dict:
    """A title of the night on air. ``head``: the next title of the Auto-DJ."""
    return _live(
        NIGHT,
        source=source,
        remaining=remaining,
        next_autodj=_cue(head) if head else {"rid": 1},
        autodj_queued=autodj_queued,
    )


def _pushes(client: AsyncMock) -> list[tuple[str, str]]:
    """Each push of a tick: its queue, and its rundown line."""
    return [
        (call.args[0], call.kwargs["json"]["radiotomate_item_id"])
        for call in client.post.call_args_list
    ]


async def _switch(dbsession: ormSession, value: str | None) -> None:
    if value is not None:
        await Setting.upsert(dbsession, SETTING_DESK_LINES_AIR, value)
        await dbsession.commit()


async def _two_sent(dbsession: ormSession, beets: BeetsIntegration) -> list[dict]:
    """The music lines of the night file, the first two sent to the playout."""
    music = await _night_music(dbsession, beets)
    client = _client()
    await tick(dbsession, _autodj_wants_two(), client, beets)
    assert _pushed_ids(client) == [music[0]["id"], music[1]["id"]]
    return music


async def _put_next(
    dbsession: ormSession, at: str, kind: str, *, duration: float = 10
) -> RundownItem:
    """« Mettre à la suite », in the time of the night file: after the two lines
    sent, at the time of the next clock line."""
    line = await insert_desk_item(
        dbsession,
        {
            "path": f"/media/banque/{kind}.mp3",
            "kind": kind,
            "title": f"Pupitre {kind}",
            "artist": "Banque",
            "duration": duration,
        },
    )
    line.planned_at = datetime.fromisoformat(at).replace(tzinfo=None)
    await dbsession.commit()
    return line


async def _status_seen_by_another_session(raw_app, line_id: str) -> str | None:
    """The status the next tick reads: in production, each tick has its session."""
    async with raw_app.extensions["sqlalchemy"].session() as other:
        return await other.scalar(
            select(RundownItem.status).where(RundownItem.id == line_id)
        )


async def test_a_music_line_put_next_goes_once_at_its_place(
    raw_app,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """After the two titles already sent, in the Auto-DJ, before the clock line
    planned after it. Once: the next tick pushes that clock line."""
    music = await _two_sent(dbsession, beets_integration)
    line = await _put_next(dbsession, music[2]["at"], "musique", duration=200)

    client = _client()
    assert await tick(dbsession, _air("120"), client, beets_integration) == ["desk"]
    assert _pushes(client) == [("/queue/autodj", line.id)]
    assert await _status_seen_by_another_session(raw_app, line.id) == "in_queue"

    client = _client()
    await tick(dbsession, _air("120"), client, beets_integration)
    assert _pushes(client) == [("/queue/autodj", music[2]["id"])]


@pytest.mark.parametrize(
    ("kind", "queue"),
    [("son", "/queue/carts"), ("pub", "/queue/carts"), ("jingle", "/queue/jingles")],
)
async def test_a_sound_put_next_goes_at_the_end_of_the_title_before_it(  # noqa: PLR0913
    raw_app,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    kind: str,
    queue: str,
):
    """The carts and jingles queues cut what plays. The line waits until the title
    before it plays, and goes at its end, once. Meanwhile the clock queues the
    music after it in the Auto-DJ, which plays after the line all the same."""
    music = await _two_sent(dbsession, beets_integration)
    line = await _put_next(dbsession, music[2]["at"], kind)

    # The first title plays, the second waits in the Auto-DJ: the line would pass it.
    client = _client()
    await tick(dbsession, _air("120", head=music[1]["id"]), client, beets_integration)
    assert _pushes(client) == [("/queue/autodj", music[2]["id"])]

    # The second title plays: the line waits for its end, and does not cut it.
    client = _client()
    await tick(dbsession, _air("60", head=music[2]["id"]), client, beets_integration)
    assert line.id not in _pushed_ids(client)

    client = _client()
    end = _air("2", head=music[2]["id"], autodj_queued=3)
    assert await tick(dbsession, end, client, beets_integration) == ["desk"]
    assert _pushes(client) == [(queue, line.id)]
    assert await _status_seen_by_another_session(raw_app, line.id) == "in_queue"

    client = _client()
    on_air = _air(
        "8", source=queue.split("/")[-1], head=music[2]["id"], autodj_queued=3
    )
    await tick(dbsession, on_air, client, beets_integration)
    assert line.id not in _pushed_ids(client)


async def test_a_jingle_put_next_goes_behind_a_cart_on_air(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """A cart on air: Liquidsoap plays the carts before the jingles. A jingle put
    next waits behind the cart in its queue: it goes at once, and cuts nothing."""
    music = await _two_sent(dbsession, beets_integration)
    line = await _put_next(dbsession, music[2]["at"], "jingle")
    client = _client()
    cart = _air("120", source="carts", head=music[2]["id"], autodj_queued=2)
    await tick(dbsession, cart, client, beets_integration)
    assert _pushes(client) == [("/queue/jingles", line.id)]


async def test_a_line_removed_before_its_turn_is_not_pushed(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    music = await _two_sent(dbsession, beets_integration)
    line = await _put_next(dbsession, music[2]["at"], "musique")
    await delete_desk_item(dbsession, line.id)
    client = _client()
    await tick(dbsession, _air("120"), client, beets_integration)
    assert _pushes(client) == [("/queue/autodj", music[2]["id"])]


async def _journee_file(dbsession: ormSession, beets: BeetsIntegration) -> dict:
    """The day file at 10:18:30, its pubs at 10:20: its first sequential line."""
    now = datetime(2026, 9, 14, 10, 18, 30, tzinfo=PARIS)
    data = await ensure_forecast(dbsession, beets, now=now, cursor=0)
    return next(item for item in data["items"] if item["when"] == "sequential")


def _journee(time: str, *, jingles: int = 1, **queues) -> dict:
    """The day on air. ``jingles``: the titles in the jingles queue."""
    return _live(
        f"2026-09-14T{time}+02:00",
        source=queues.pop("source", "autodj"),
        next_jingle={"rid": 1 if jingles else -1},
        jingles_queued=jingles,
        **queues,
    )


async def test_a_music_line_never_delays_a_hard_anchor(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """It would still play at 10:20, when the pubs cut: it waits, and the lines
    after it wait with it. The pubs go at their minute, and the line right after."""
    first = await _journee_file(dbsession, beets_integration)
    line = await _put_next(dbsession, first["at"], "musique", duration=120)

    client = _client()
    late = _journee("10:18:30", remaining="5", autodj_queued=0)
    await tick(dbsession, late, client, beets_integration)
    assert _pushes(client) == []

    client = _client()
    pubs = _journee("10:20:05", remaining="100", autodj_queued=0)
    actions = await tick(dbsession, pubs, client, beets_integration)
    assert actions[:2] == ["anchor:20", "desk"]
    assert [queue for queue, _ in _pushes(client)][:2] == [
        "/queue/carts",
        "/queue/autodj",
    ]
    assert _pushes(client)[1] == ("/queue/autodj", line.id)


async def test_a_sound_never_delays_a_hard_anchor(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """A sound in the carts queue is not cut by the pubs: at its turn, it waits for
    them, and the lines after it wait with it. Once the pubs are on air, it goes
    behind them in the carts, before the music queued after it."""
    first = await _journee_file(dbsession, beets_integration)
    line = await _put_next(dbsession, first["at"], "son", duration=60)

    client = _client()
    turn = _journee("10:19:57", jingles=0, remaining="2", autodj_queued=0)
    await tick(dbsession, turn, client, beets_integration)
    assert _pushes(client) == []

    client = _client()
    pubs = _journee("10:20:05", jingles=0, remaining="100", autodj_queued=0)
    actions = await tick(dbsession, pubs, client, beets_integration)
    assert "anchor:20" in actions
    assert line.id not in _pushed_ids(client)
    after = [line_id for queue, line_id in _pushes(client) if queue == "/queue/autodj"]

    client = _client()
    behind = _journee(
        "10:20:10",
        jingles=0,
        source="carts",
        remaining="15",
        next_autodj=_cue(after[0]),
        autodj_queued=len(after),
    )
    await tick(dbsession, behind, client, beets_integration)
    assert _pushes(client) == [("/queue/carts", line.id)]


@pytest.mark.parametrize(("value", "airs"), [(None, True), ("1", True), *OFF])
async def test_desk_lines_follow_the_switch(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    airs: bool,
):
    """features.desk_lines_air turned off: the clock leaves the desk lines alone,
    as before, and they drop from the file once their time is over."""
    await _switch(dbsession, value)
    music = await _two_sent(dbsession, beets_integration)
    line = await _put_next(dbsession, music[2]["at"], "musique")
    client = _client()
    await tick(dbsession, _air("120"), client, beets_integration)
    assert _pushed_ids(client) == [line.id if airs else music[2]["id"]]

    past = line.planned_at + timedelta(seconds=31)
    await expire_past_desk_items(dbsession, now=past)
    kept = await dbsession.scalar(select(RundownItem).where(RundownItem.id == line.id))
    assert (kept is not None) == airs


@pytest.mark.parametrize("value", [None, "0"])
async def test_a_line_put_next_goes_after_the_lines_already_sent(
    dbsession: ormSession, value: str | None
):
    """Liquidsoap plays first the lines already sent, in the order it got them: put
    next, or above one of them, a line goes after them. Turned off, as before:
    after the title on air, or half a second above the line."""
    await _switch(dbsession, value)
    await _reorder_version(dbsession, "pv-after-sent")
    now = datetime.now().replace(microsecond=0)
    on_air = _reorder_row(
        "ri-air",
        "pv-after-sent",
        now - timedelta(seconds=10),
        60,
        status=RundownStatus.ON_AIR.value,
        origin="clock",
    )
    on_air.started_at = now - timedelta(seconds=10)
    sent = _reorder_row(
        "ri-sent",
        "pv-after-sent",
        now + timedelta(seconds=50),
        180,
        status=RundownStatus.IN_QUEUE.value,
        origin="clock",
    )
    sent.reserved_at = now - timedelta(minutes=3)
    # Sent long ago, the playout has lost it: its status no longer counts.
    lost = _reorder_row(
        "ri-lost",
        "pv-after-sent",
        now + timedelta(seconds=230),
        600,
        status=RundownStatus.IN_QUEUE.value,
        origin="clock",
    )
    lost.reserved_at = now - timedelta(minutes=20)
    dbsession.add_all([on_air, sent, lost])
    await dbsession.commit()

    line = await insert_desk_item(dbsession, {"path": "/media/10-rotation/next.mp3"})
    above = await insert_desk_item(
        dbsession, {"path": "/media/10-rotation/above.mp3", "before_id": "ri-sent"}
    )
    if value is None:
        after_sent = now + timedelta(seconds=230)
        assert (line.planned_at, above.planned_at) == (after_sent, after_sent)
    else:
        assert line.planned_at == now + timedelta(seconds=50)
        assert above.planned_at == now + timedelta(seconds=49.5)


@pytest.mark.parametrize("value", [None, "0"])
async def test_a_desk_line_slides_with_the_file(
    dbsession: ormSession, value: str | None
):
    """A clock line on air 10 s late takes the desk line after it along, and the
    desk line on air 20 s late takes the clock line after it, as clock lines do.
    Turned off, as before: the desk line keeps its time, and moves nothing."""
    await _switch(dbsession, value)
    await _reorder_version(dbsession, "pv-slide")
    at = datetime.now().replace(microsecond=0) + timedelta(minutes=2)
    first = _reorder_row("ri-first", "pv-slide", at, 60, origin="clock")
    desk = _reorder_row("ri-desk", "pv-slide", at + timedelta(seconds=60), 30)
    last = _reorder_row(
        "ri-last", "pv-slide", at + timedelta(seconds=90), 60, origin="clock"
    )
    dbsession.add_all([first, desk, last])
    await dbsession.commit()

    await realign_rundown(dbsession, first, at + timedelta(seconds=10))
    await realign_rundown(dbsession, desk, desk.planned_at + timedelta(seconds=20))
    if value is None:
        assert desk.planned_at == at + timedelta(seconds=90)
        assert last.planned_at == at + timedelta(seconds=120)
    else:
        assert desk.planned_at == at + timedelta(seconds=60)
        assert last.planned_at == at + timedelta(seconds=100)


async def test_a_sent_desk_line_waits_for_its_turn(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """Sent, a desk line no longer changes, and stays in the file past its time
    while it waits in Liquidsoap. An hour later it will not air: it goes, and its
    command no longer points at it."""
    music = await _two_sent(dbsession, beets_integration)
    line = await _put_next(dbsession, music[2]["at"], "musique")
    client = _client()
    await tick(dbsession, _air("120"), client, beets_integration)
    command_id = client.post.call_args.kwargs["json"]["radiotomate_command_id"]

    with pytest.raises(DomainConflict, match="ne se modifie plus"):
        await patch_desk_item(dbsession, line.id, {"title": "Autre"})
    with pytest.raises(DomainConflict, match="ne se retire plus"):
        await delete_desk_item(dbsession, line.id)

    end = line.planned_at + timedelta(seconds=30)
    await expire_past_desk_items(dbsession, now=end + timedelta(seconds=1))
    assert await dbsession.get(RundownItem, line.id) is not None
    await expire_past_desk_items(dbsession, now=end + SENT_GRACE + timedelta(seconds=1))
    gone = select(RundownItem).where(RundownItem.id == line.id)
    assert await dbsession.scalar(gone) is None
    command = await dbsession.get(PlayoutCommand, command_id)
    assert command.rundown_item_id is None


async def test_a_desk_line_the_playout_refuses_still_goes_from_the_file(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The playout refuses the file: the line fails, once, and its command points at
    it. « Retirer » still takes it off, and so does its time once over."""
    music = await _two_sent(dbsession, beets_integration)
    removed = await _put_next(dbsession, music[2]["at"], "musique")
    expired = await _put_next(dbsession, music[3]["at"], "musique")
    refusing = _client()
    refusing.post = AsyncMock(return_value=httpx.Response(400, json={"error": "x"}))
    await tick(dbsession, _air("120", autodj_queued=0), refusing, beets_integration)
    for line in (removed, expired):
        failed = await dbsession.get(RundownItem, line.id)
        assert failed.status == RundownStatus.FAILED.value
    client = _client()
    await tick(dbsession, _air("120"), client, beets_integration)
    assert {removed.id, expired.id}.isdisjoint(_pushed_ids(client))

    await delete_desk_item(dbsession, removed.id)
    await expire_past_desk_items(
        dbsession, now=expired.planned_at + timedelta(seconds=31)
    )
    left = select(RundownItem.id).where(RundownItem.origin == DESK_ORIGIN)
    assert list(await dbsession.scalars(left)) == []


@pytest.mark.parametrize(("value", "airs"), [(None, True), ("0", False)])
async def test_a_replacement_airs_in_place_of_its_clock_line(
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
    value: str | None,
    airs: bool,
):
    """A desk line put in the place of a clock line (replace_at) goes in its place:
    the clock line never airs, closed « remplacé ». Turned off, as before: the
    clock line airs, and the desk line does not."""
    await _switch(dbsession, value)
    music = await _two_sent(dbsession, beets_integration)
    replacement = await insert_desk_item(
        dbsession,
        {
            "path": "/media/banque/autre.mp3",
            "kind": "musique",
            "replace_at": music[2]["at"],
        },
    )
    client = _client()
    await tick(dbsession, _air("120"), client, beets_integration)
    assert _pushed_ids(client) == [replacement.id if airs else music[2]["id"]]
    if airs:
        replaced = await dbsession.get(RundownItem, music[2]["id"])
        assert (replaced.status, replaced.reason) == ("replaced", "remplacé au pupitre")
        client = _client()
        await tick(dbsession, _air("120"), client, beets_integration)
        assert music[2]["id"] not in _pushed_ids(client)


@pytest.mark.parametrize(("value", "status"), [(None, "in_queue"), ("0", "planned")])
async def test_play_now_does_not_send_its_line_twice(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    value: str | None,
    status: str,
):
    """« Jouer tout de suite » hands a title of the bank to the playout itself: its
    desk line is already in its queue, and the clock does not push it again.
    Turned off, as before: the line is planned, and the clock leaves it alone."""
    await _switch(dbsession, value)
    client = await _live_client(
        app_configration, beets_integration, dbsession, users_password, "desk-now"
    )

    async def accept(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    with patch.object(Scheduler, "get", return_value=_scheduler_facing(accept)):
        response = await client.post(
            "/autodj/conducteur/now.json",
            json={"path": "/media/x.mp3", "title": "X", "artist": "Y", "kind": "son"},
        )
    assert response.status_code == 200, await response.get_data(as_text=True)
    line = await dbsession.scalar(
        select(RundownItem).where(RundownItem.origin == DESK_ORIGIN)
    )
    assert line.status == status
    if value is None:
        # It plays at once, cutting the title on air, which resumes after it:
        # on air, it moves no other line.
        await _reorder_version(dbsession, "pv-play-now")
        after = _reorder_row(
            "ri-after", "pv-play-now", line.planned_at + timedelta(seconds=9), 60
        )
        dbsession.add(after)
        await dbsession.commit()
        early = line.planned_at - timedelta(seconds=90)
        assert await realign_rundown(dbsession, line, early) == timedelta(0)
        assert after.planned_at == line.planned_at + timedelta(seconds=9)
        # Its time says nothing of where the next line goes.
        put_next = await insert_desk_item(dbsession, {"path": "/media/y.mp3"})
        assert put_next.planned_at < line.planned_at + timedelta(seconds=8)
