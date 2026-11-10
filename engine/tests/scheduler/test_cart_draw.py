"""
A random cart draws without repeat: a round plays each ready sound once, in a
random order, and no sound comes back early from one round to the next.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import RundownStatus
from radiotomate.models import Cart, Setting, Sound
from radiotomate.quart import CustomQuart
from radiotomate.scheduler.clock import PARIS, tick
from radiotomate.scheduler.execution import record_live_item
from radiotomate.scheduler.rundown import build_rundown
from radiotomate.services.cart_draw import (
    SETTING_DRAWN,
    SETTING_NO_REPEAT,
    cart_draw,
    draw_without_repeat,
    drawn_after,
    next_cart_sound,
    note_on_air,
)

# -- the rule, without a base ---------------------------------------------------


def _bac(count: int) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(id=n, available=True, last_played=None)
        for n in range(1, count + 1)
    ]


class _Antenna:
    """Plays what a cart draws, and notes it as the scheduler does on air."""

    def __init__(self, sounds: list[SimpleNamespace]):
        self.sounds = sounds
        self.drawn: list[int] = []
        self.now = datetime(2026, 9, 14, 8, 0)
        self.aired: list[int] = []

    def play(self, sound: SimpleNamespace | None = None) -> int:
        sound = sound or draw_without_repeat(self.sounds, self.drawn)
        self.now += timedelta(minutes=10)
        sound.last_played = self.now
        self.drawn = drawn_after(self.sounds, self.drawn, sound.id)
        self.aired.append(sound.id)
        return sound.id


@pytest.mark.parametrize("count", [2, 3, 5, 12])
def test_a_round_plays_each_ready_sound_once(count: int):
    antenna = _Antenna(_bac(count))
    for _ in range(4 * count):
        antenna.play()
    rounds = [antenna.aired[n : n + count] for n in range(0, 4 * count, count)]
    assert all(sorted(turn) == list(range(1, count + 1)) for turn in rounds)


@pytest.mark.parametrize("count", [2, 3, 4, 5, 8, 13])
def test_no_sound_comes_back_early(count: int):
    """Between two plays of a sound, half of the others at least have played."""
    antenna = _Antenna(_bac(count))
    for _ in range(30 * count):
        antenna.play()
    last_index: dict[int, int] = {}
    for index, sound_id in enumerate(antenna.aired):
        if sound_id in last_index:
            assert index - last_index[sound_id] - 1 >= count // 2
        last_index[sound_id] = index


def test_the_order_changes_from_round_to_round():
    antenna = _Antenna(_bac(6))
    for _ in range(6 * 20):
        antenna.play()
    orders = {tuple(antenna.aired[n : n + 6]) for n in range(0, 6 * 20, 6)}
    assert len(orders) > 1


def test_a_new_round_leaves_out_the_latest_half():
    sounds = _bac(6)
    antenna = _Antenna(sounds)
    first_round = [antenna.play() for _ in range(6)]
    with patch(
        "radiotomate.services.cart_draw.choice",
        side_effect=lambda pool: pool[0],
    ) as pick:
        draw_without_repeat(sounds, antenna.drawn)
    offered = {sound.id for sound in pick.call_args.args[0]}
    assert offered == set(first_round[:3])


def test_a_sound_not_ready_is_never_drawn():
    sounds = _bac(4)
    sounds[1].available = False
    antenna = _Antenna(sounds)
    for _ in range(12):
        antenna.play()
    assert 2 not in antenna.aired
    assert sorted(antenna.aired[:3]) == [1, 3, 4]


def test_a_sound_added_during_a_round_plays_in_it():
    sounds = _bac(4)
    antenna = _Antenna(sounds)
    antenna.play()
    antenna.play()
    sounds.append(SimpleNamespace(id=5, available=True, last_played=None))
    for _ in range(3):
        antenna.play()
    assert sorted(antenna.aired) == [1, 2, 3, 4, 5]


def test_a_sound_fired_by_hand_has_played_in_the_round():
    sounds = _bac(4)
    antenna = _Antenna(sounds)
    antenna.play(sounds[2])
    rest = [antenna.play() for _ in range(3)]
    assert sorted(rest) == [1, 2, 4]


def test_sounds_that_play_before_count_as_played():
    """The conducteur draws several sounds one after the other: none twice in
    a round, though none of them is on air yet."""
    sounds = _bac(5)
    planned: list[int] = []
    for _ in range(10):
        planned.append(draw_without_repeat(sounds, before=planned).id)
    assert sorted(planned[:5]) == [1, 2, 3, 4, 5]
    assert sorted(planned[5:]) == [1, 2, 3, 4, 5]
    assert all(planned[n] not in planned[n - 2 : n] for n in range(2, 10))


def test_a_sound_planned_after_keeps_its_turn():
    """A sound drawn to play now leaves out the ones the conducteur plans next."""
    sounds = _bac(4)
    antenna = _Antenna(sounds)
    antenna.play(sounds[0])
    for _ in range(20):
        assert draw_without_repeat(sounds, antenna.drawn, ahead=[2]).id in {3, 4}


def test_the_next_round_opens_early_when_the_last_sounds_are_planned():
    """Two of three have played, the third is planned next: the sound to play
    now is the one heard longest ago, not the one just heard."""
    sounds = _bac(3)
    antenna = _Antenna(sounds)
    antenna.play(sounds[0])
    antenna.play(sounds[1])
    for _ in range(20):
        assert draw_without_repeat(sounds, antenna.drawn, ahead=[3]) is sounds[0]


def test_one_sound_and_no_sound():
    assert draw_without_repeat([]) is None
    only = _bac(1)
    assert draw_without_repeat(only, drawn={1}) is only[0]
    asleep = SimpleNamespace(id=1, available=False, last_played=None)
    assert draw_without_repeat([asleep]) is None


def test_a_round_over_starts_the_next_one():
    sounds = _bac(3)
    assert drawn_after(sounds, [1], 2) == [1, 2]
    assert drawn_after(sounds, [1, 2], 3) == [1, 2, 3]
    # The round is over: the next sound on air opens a new one.
    assert drawn_after(sounds, [1, 2, 3], 1) == [1]


def test_a_sound_said_twice_on_air_counts_once():
    """The playout repeats what is on air after a cut: no new round for that."""
    sounds = _bac(3)
    assert drawn_after(sounds, [1, 2], 2) == [1, 2]
    assert drawn_after(sounds, [1, 2, 3], 3) == [1, 2, 3]
    assert drawn_after(sounds, [1, 2], 1) == [1, 2]


def test_a_sound_gone_is_forgotten_and_one_asleep_keeps_its_turn():
    sounds = _bac(3)
    sounds[0].available = False
    assert drawn_after(sounds, [1, 9], 2) == [1, 2]
    assert drawn_after(sounds, [1, 2], 3) == [1, 2, 3]
    assert drawn_after(sounds, [1, 2, 3], 2) == [2]


# -- with the base, as the scheduler does ---------------------------------------


async def _spots(dbsession: ormSession, cart: Cart, count: int) -> list[Sound]:
    """The cart's sounds, ``count`` in all, every one ready."""
    first = await dbsession.scalar(select(Sound).where(Sound.cart_id == cart.id))
    more = [
        Sound(
            cart_id=cart.id,
            path=cart.path / f"spot-{rank}.mp3",
            duration=20,
            title=f"Spot {rank}",
            rank=rank,
            gain=-1.0,
            peak=-0.5,
        )
        for rank in range(2, count + 1)
    ]
    dbsession.add_all(more)
    await dbsession.commit()
    return [first, *more]


async def _drawn(dbsession: ormSession) -> dict:
    """What the base holds, even when another session has just written it."""
    row = await dbsession.scalar(
        select(Setting)
        .where(Setting.key == SETTING_DRAWN)
        .execution_options(populate_existing=True)
    )
    return json.loads(row.value) if row is not None else {}


async def _loaded(dbsession: ormSession, cart: Cart) -> Cart:
    return await Cart.from_id(dbsession, cart.id, load_sounds=True)


async def test_a_random_cart_draws_round_after_round(
    dbsession: ormSession,
    pubs_cart: Cart,
):
    spots = await _spots(dbsession, pubs_cart, 4)
    ids = sorted(sound.id for sound in spots)
    aired: list[int] = []
    now = datetime(2026, 9, 14, 8, 0)
    for _ in range(12):
        cart = await _loaded(dbsession, pubs_cart)
        sound = await next_cart_sound(dbsession, cart)
        now += timedelta(minutes=20)
        sound.last_played = now
        await note_on_air(dbsession, sound.id)
        await dbsession.commit()
        aired.append(sound.id)
    assert [sorted(aired[n : n + 4]) for n in (0, 4, 8)] == [ids, ids, ids]
    assert all(aired[n] not in aired[n - 2 : n] for n in range(2, 12))


async def test_switched_off_a_random_cart_draws_as_before(
    dbsession: ormSession,
    pubs_cart: Cart,
):
    spots = await _spots(dbsession, pubs_cart, 3)
    await Setting.upsert(dbsession, SETTING_NO_REPEAT, "0")
    await dbsession.commit()
    cart = await _loaded(dbsession, pubs_cart)
    assert await cart_draw(dbsession, cart) is None
    with patch.object(Cart, "next_sound_random", return_value=spots[1]) as old_draw:
        assert await next_cart_sound(dbsession, cart) is spots[1]
    old_draw.assert_called_once()
    await note_on_air(dbsession, spots[1].id)
    await dbsession.commit()
    assert await _drawn(dbsession) == {}


async def test_only_a_random_cart_draws_this_way(
    dbsession: ormSession,
    fake_cart: Cart,
    fake_sound: Sound,
):
    cart = await _loaded(dbsession, fake_cart)
    assert await cart_draw(dbsession, cart) is None
    assert await next_cart_sound(dbsession, cart) is cart.next_sound()
    await note_on_air(dbsession, fake_sound.id)
    await dbsession.commit()
    assert await _drawn(dbsession) == {}
    assert await next_cart_sound(dbsession, None) is None


async def _conducteur_line(
    dbsession: ormSession,
    sound: Sound,
    minute: int,
    status: RundownStatus,
) -> None:
    """A pub break of the conducteur at 10:``minute``, in the given state."""
    await record_live_item(
        dbsession,
        payload={
            "at": datetime(2026, 9, 14, 10, minute, tzinfo=PARIS).isoformat(),
            "kind": "pub",
            "when": "anchored",
            "queue": "carts",
            "resource": sound.title,
            "path": str(sound.path),
            "cart_id": sound.cart_id,
            "sound_id": sound.id,
        },
        status=status.value,
    )
    await dbsession.commit()


async def test_a_sound_planned_ahead_waits(
    dbsession: ormSession,
    pubs_cart: Cart,
):
    """The conducteur has planned a spot: the next draws leave it out."""
    spots = await _spots(dbsession, pubs_cart, 3)
    await _conducteur_line(dbsession, spots[0], 40, RundownStatus.PLANNED)
    cart = await _loaded(dbsession, pubs_cart)
    draw = await cart_draw(dbsession, cart)
    assert (draw.engaged, draw.planned) == ([], [spots[0].id])
    for _ in range(20):
        sound = await next_cart_sound(dbsession, cart)
        assert sound.id != spots[0].id


async def test_a_sound_sent_and_not_heard_yet_counts(
    dbsession: ormSession,
    pubs_cart: Cart,
):
    """Sent to the antenna a moment ago, a spot is not planned again behind it."""
    spots = await _spots(dbsession, pubs_cart, 3)
    await _conducteur_line(dbsession, spots[0], 20, RundownStatus.SENT)
    cart = await _loaded(dbsession, pubs_cart)
    draw = await cart_draw(dbsession, cart)
    assert (draw.engaged, draw.planned) == ([spots[0].id], [])
    for _ in range(20):
        assert draw.pick_ahead(cart).id != spots[0].id
        draw.planned.clear()


async def test_a_line_lost_on_its_way_is_forgotten(
    dbsession: ormSession,
    pubs_cart: Cart,
):
    """A spot sent that never played must not wait for ever: once a later line
    has played, the conducteur holds nothing of it any more."""
    spots = await _spots(dbsession, pubs_cart, 3)
    await _conducteur_line(dbsession, spots[0], 0, RundownStatus.SENT)
    await _conducteur_line(dbsession, spots[1], 20, RundownStatus.PLAYED)
    await _conducteur_line(dbsession, spots[2], 40, RundownStatus.PLANNED)
    cart = await _loaded(dbsession, pubs_cart)
    draw = await cart_draw(dbsession, cart)
    assert (draw.engaged, draw.planned) == ([], [spots[2].id])


async def test_on_air_notes_the_draw(
    raw_app: CustomQuart,
    dbsession: ormSession,
    pubs_cart: Cart,
    auth: dict,
):
    """The playout says what is on air: that is when a sound has played."""
    spots = await _spots(dbsession, pubs_cart, 3)
    key = str(pubs_cart.id)
    async with raw_app.test_app():
        client = raw_app.test_client()

        async def on_air(sound: Sound) -> None:
            result = await client.post(
                "/metadata_log",
                json={
                    "source": "carts",
                    "radiotomate_sound_id": str(sound.id),
                    "on_air": datetime.now().isoformat(),
                },
                headers=auth,
            )
            assert result.status_code == 200, (await result.data).decode()

        first, second, third = (sound.id for sound in spots)
        await on_air(spots[1])
        assert await _drawn(dbsession) == {key: [second]}
        await on_air(spots[0])
        assert await _drawn(dbsession) == {key: [second, first]}
        await on_air(spots[2])
        assert await _drawn(dbsession) == {key: [second, first, third]}
        # Said again after a cut, the last sound of the round opens no new one.
        await on_air(spots[2])
        assert await _drawn(dbsession) == {key: [second, first, third]}
        await on_air(spots[0])
        assert await _drawn(dbsession) == {key: [first]}


async def test_a_broken_note_does_not_lose_the_log(
    raw_app: CustomQuart,
    dbsession: ormSession,
    pubs_cart: Cart,
    auth: dict,
):
    await Setting.upsert(dbsession, SETTING_DRAWN, "{not json")
    await dbsession.commit()
    spots = await _spots(dbsession, pubs_cart, 2)
    async with raw_app.test_app():
        client = raw_app.test_client()
        result = await client.post(
            "/metadata_log",
            json={"source": "carts", "radiotomate_sound_id": spots[0].id},
            headers=auth,
        )
        assert result.status_code == 200, (await result.data).decode()
    assert await _drawn(dbsession) == {str(pubs_cart.id): [spots[0].id]}


# -- the clock and its conducteur ----------------------------------------------

# A Monday: the day clock of the seed has a pub break at :20 and :40, 10:00-18:00.
MONDAY = "2026-09-14"


def _client() -> AsyncMock:
    client = AsyncMock()
    client.post = AsyncMock(return_value=httpx.Response(200, json={"ok": 1}))
    client.delete = AsyncMock(return_value=httpx.Response(200))
    return client


def _music_on_air(time: str) -> dict:
    return {
        "source": "autodj",
        "remaining": "180",
        "time": time,
        "next_jingle": {"rid": 1},
        "next_autodj": {"rid": 1},
        "next_cart": {"rid": -1},
        "jingles_queued": 2,
        "autodj_queued": 3,
    }


async def _pub_break(
    dbsession: ormSession,
    beets_integration: BeetsIntegration,
    time: str,
) -> str:
    """The spot the clock sends at a pub break, then on air."""
    client = _client()
    actions = await tick(dbsession, _music_on_air(time), client, beets_integration)
    assert any(action.startswith("anchor:") for action in actions)
    pushed = [
        call.kwargs["json"]
        for call in client.post.call_args_list
        if call.args[0] == "/queue/carts"
    ]
    assert len(pushed) == 1
    await note_on_air(dbsession, pushed[0]["radiotomate_sound_id"])
    await dbsession.commit()
    return pushed[0]["title"]


async def test_the_clock_draws_round_after_round(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """Six pub breaks drawn when their minute comes, three spots: two rounds."""
    spots = await _spots(dbsession, pubs_cart, 3)
    titles = sorted(sound.title for sound in spots)
    aired = [
        await _pub_break(dbsession, beets_integration, f"{MONDAY}T{hour}:40:05+02:00")
        for hour in range(10, 16)
    ]
    assert [sorted(aired[:3]), sorted(aired[3:])] == [titles, titles]
    assert all(aired[n] != aired[n - 1] for n in range(1, 6))


async def test_a_break_planned_ahead_gets_another_spot(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """At :20 the conducteur already holds the break of :40: the spot drawn for
    :20 is another one, and no spot plays twice in a row all day."""
    await _spots(dbsession, pubs_cart, 3)
    aired = [
        await _pub_break(
            dbsession, beets_integration, f"{MONDAY}T{hour}:{minute}:05+02:00"
        )
        for hour in range(10, 18)
        for minute in (20, 40)
    ]
    assert all(aired[n] != aired[n - 1] for n in range(1, len(aired)))


async def test_the_conducteur_plans_rounds(
    dbsession: ormSession,
    jingles_cart: Cart,
    pubs_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """Three spots of four have played this morning: the conducteur plans the
    fourth first, then a whole round where the two heard last wait."""
    spots = await _spots(dbsession, pubs_cart, 4)
    titles = [sound.title for sound in spots]
    for minute, sound in enumerate(spots[:3]):
        sound.last_played = datetime(2026, 9, 14, 9, minute)
        await note_on_air(dbsession, sound.id)
    await dbsession.commit()
    forecast = await build_rundown(
        dbsession,
        beets_integration,
        now=datetime(2026, 9, 14, 10, 5, tzinfo=PARIS),
        horizon_min=170,
    )
    planned = [item["title"] for item in forecast["items"] if item["kind"] == "pub"]
    assert len(planned) >= 5
    assert planned[0] == titles[3]
    assert planned[1] in titles[:2]
    assert sorted(planned[1:5]) == sorted(titles)
    assert all(planned[n] not in planned[n - 2 : n] for n in range(2, len(planned)))
