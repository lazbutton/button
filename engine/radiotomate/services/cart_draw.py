"""
The draw of a random cart: no sound comes back before its turn.

A round plays every ready sound once, in a random order, then a new round
starts. From one round to the next, the half heard last waits: a sound never
comes back right after itself.

The sounds played in the round under way are kept in the ``settings`` table,
with the scheduler's other runtime state. They are noted when the playout says
a sound is on air, whoever sent it: the clock, « Diffuser maintenant » or the
desk.

A cart that plays in order, a playlist or a loop, keeps the order of
``Cart.next_sound``. The conducteur plans it ahead from what it already holds
of the cart: ``CartOrder``. When the clock draws an anchor itself, the lines
it plans of the cart then follow the sound drawn: ``planned_in_order``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from random import choice
from typing import TYPE_CHECKING

from sqlalchemy import select

from radiotomate.domain.execution import ENGAGED_STATUSES
from radiotomate.enums import CartMode, RundownStatus, WhenMode
from radiotomate.models import RundownItem, Setting, Sound

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.orm import Session as ormSession

    from radiotomate.models import Cart

# ADR 0009: turned off, a random cart draws among all its ready sounds each
# time, as before.
SETTING_NO_REPEAT = "features.random_no_repeat"
_SETTING_OFF = {"0", "false", "off", ""}
# {"<cart id>": [ids of the sounds played in the round under way, oldest first]}
SETTING_DRAWN = "cart_drawn"
_PLANNED_STATUSES = {RundownStatus.PLANNED.value, RundownStatus.RESCUE.value}
_AIRED_STATUSES = {RundownStatus.ON_AIR.value, RundownStatus.PLAYED.value}
# How far back the conducteur is read for what a cart still has to play.
_HELD_ROWS = 200
_ORDERED_MODES = {CartMode.PLAYLIST, CartMode.PLAYLIST_LOOP}
# A desk line plays the sound chosen for it.
_DESK_ORIGIN = "desk"


def draw_without_repeat(
    sounds: Iterable[Sound],
    drawn: Iterable[int] = (),
    before: Sequence[int] = (),
    ahead: Sequence[int] = (),
) -> Sound | None:
    """
    One ready sound, drawn among those that have not played in the round under
    way. ``drawn`` are the ids played in it. ``before`` are the ids that play
    before this one and are not on air yet, oldest first; ``ahead`` those
    already planned after it, soonest first, which keep their turn.

    When the round has nothing left but sounds heard lately, every sound has
    played, is on its way or is planned: the next round opens early, with the
    sound farthest from its last play and its next one (``_farthest``).
    """
    ready = [sound for sound in sounds if sound.available]
    if len(ready) < 2:
        return ready[0] if ready else None
    ids = {sound.id for sound in ready}
    gone = set(drawn)
    for sound_id in before:
        if gone >= ids:
            gone = set()
        gone.add(sound_id)
    if gone >= ids:
        gone = set()
    # From one round to the next, the half heard last waits. A sound that plays
    # before this one comes after any sound played.
    turn = {sound_id: index for index, sound_id in enumerate(before)}
    heard = [sound for sound in ready if sound.id in turn or sound.last_played]
    heard.sort(
        key=lambda sound: (turn.get(sound.id, -1), _heard_at(sound)),
        reverse=True,
    )
    recent = {sound.id for sound in heard[: len(ready) // 2]}
    waiting = gone | set(ahead) | recent
    in_round = [sound for sound in ready if sound.id not in waiting]
    if in_round:
        return choice(in_round)
    return _farthest(ready, heard, ahead)


def _farthest(ready: list[Sound], heard: list[Sound], ahead: Sequence[int]) -> Sound:
    """
    The ready sound farthest from its last play and from its next one, counted
    in plays: the shorter of the two gaps first, then the one heard longest
    ago, then the one planned latest. ``heard`` are the sounds heard, the
    latest first; ``ahead`` the ids planned, soonest first. A sound never
    heard, or not planned, is as far as can be.

    With two sounds, one just heard and the other planned next, a repeat
    cannot be avoided: it falls on the break to come, not on the one just
    heard.

    A sound sent that the playout never says on air, a file gone unreadable
    say, stays in its round for ever: it is tried again only once half of the
    others have played, and the cart goes on with them meanwhile.
    """
    far = len(ready) + len(ahead)
    since = {sound.id: index for index, sound in enumerate(heard)}
    until: dict[int, int] = {}
    for index, sound_id in enumerate(ahead):
        until.setdefault(sound_id, index)

    def gaps(sound: Sound) -> tuple[int, int, int]:
        back, forth = since.get(sound.id, far), until.get(sound.id, far)
        return min(back, forth), back, forth

    best = max(gaps(sound) for sound in ready)
    return choice([sound for sound in ready if gaps(sound) == best])


def _heard_at(sound: Sound) -> datetime:
    """When a sound last played, without a zone: the playout may give one."""
    at = sound.last_played
    return at.replace(tzinfo=None) if at else datetime.min


def drawn_after(
    sounds: Iterable[Sound],
    drawn: Iterable[int],
    sound_id: int,
) -> list[int]:
    """
    The ids played in the round once ``sound_id`` has gone on air. A list that
    holds every ready sound is a round over: the next sound on air opens a new
    one. A sound said twice on air, replayed after a cut, counts once.
    """
    sounds = list(sounds)
    known = {sound.id for sound in sounds}
    ready = {sound.id for sound in sounds if sound.available}
    played = [played_id for played_id in drawn if played_id in known]
    if played and played[-1] == sound_id:
        return played
    if ready <= set(played):
        return [sound_id]
    return played if sound_id in played else [*played, sound_id]


@dataclass
class CartDraw:
    """
    What a random cart has drawn: the sounds played in its round, those sent
    to the antenna and not on air yet, and those the conducteur plans.
    """

    drawn: list[int] = field(default_factory=list)
    engaged: list[int] = field(default_factory=list)
    planned: list[int] = field(default_factory=list)

    def pick_now(self, cart: Cart) -> Sound | None:
        """A sound to play now: before the planned ones, which keep their turn."""
        return draw_without_repeat(
            cart.sounds, self.drawn, before=self.engaged, ahead=self.planned
        )

    def pick_ahead(self, cart: Cart) -> Sound | None:
        """A sound the conducteur plans after those it already holds."""
        sound = draw_without_repeat(
            cart.sounds, self.drawn, before=[*self.engaged, *self.planned]
        )
        if sound is not None:
            self.planned.append(sound.id)
        return sound


def next_in_order(cart: Cart, before: Sequence[int] = ()) -> Sound | None:
    """
    The sound a cart that plays in order gives once ``before`` have played,
    oldest first: what ``Cart.next_sound`` will give by then, and what it gives
    now when nothing plays before.
    """
    sounds = {sound.id: sound for sound in cart.sounds}
    last = next(
        (sounds[sound_id] for sound_id in reversed(before) if sound_id in sounds),
        None,
    )
    if last is None:
        return cart.next_sound()
    ready = [sound for sound in cart.sounds if sound.available]
    if cart.mode is CartMode.PLAYLIST:
        # As Cart.next_sound_playlist: first a sound never played, nor about to be.
        coming = set(before)
        for sound in ready:
            if not sound.last_played and sound.id not in coming:
                return sound
    # As Cart.next_sound_playlist_loop, after the sound that will have played last.
    if last.rank:
        for sound in ready:
            if sound.rank > last.rank:
                return sound
    return ready[0] if ready else None


@dataclass
class CartOrder:
    """
    What the conducteur holds of a cart that plays in order: its sounds sent to
    the antenna and not on air yet, then those it plans.
    """

    held: list[int] = field(default_factory=list)

    def pick_ahead(self, cart: Cart) -> Sound | None:
        """A sound the conducteur plans after those it already holds."""
        sound = next_in_order(cart, self.held)
        if sound is not None:
            self.held.append(sound.id)
        return sound


async def no_repeat_enabled(session: ormSession) -> bool:
    """Whether a random cart draws without repeat. A missing key says it does."""
    row = await Setting.from_key(session, SETTING_NO_REPEAT)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


def _ids(raw: object) -> list[int]:
    if not isinstance(raw, list):
        return []
    return [value for value in raw if type(value) is int]


async def _drawn_by_cart(session: ormSession) -> dict:
    row = await Setting.from_key(session, SETTING_DRAWN)
    if row is None:
        return {}
    try:
        state = json.loads(row.value)
    except (TypeError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


async def cart_draw(session: ormSession, cart: Cart | None) -> CartDraw | None:
    """
    The draw of a random cart, with what it has played in its round and what
    the conducteur holds of it. None for a cart that keeps its own order: any
    other mode, or the switch turned off.
    """
    if cart is None or cart.mode is not CartMode.RANDOM:
        return None
    if not await no_repeat_enabled(session):
        return None
    state = await _drawn_by_cart(session)
    draw = CartDraw(drawn=_ids(state.get(str(cart.id))))
    draw.engaged, draw.planned = await _held(session, cart)
    return draw


async def _held_lines(session: ormSession, cart: Cart) -> list[RundownItem]:
    """
    The lines of a cart the conducteur holds, oldest first: those sent to the
    antenna and not on air yet, and those it plans. Read as the base has them.
    """
    rows = await session.scalars(
        select(RundownItem)
        .where(
            RundownItem.cart_id == cart.id,
            RundownItem.sound_id.is_not(None),
            RundownItem.status.in_(
                list(ENGAGED_STATUSES | _PLANNED_STATUSES | _AIRED_STATUSES)
            ),
        )
        .order_by(RundownItem.planned_at.desc(), RundownItem.sequence.desc())
        .limit(_HELD_ROWS)
        .execution_options(populate_existing=True)
    )
    held: list[RundownItem] = []
    for row in rows:
        if row.status in _AIRED_STATUSES:
            # What comes before a sound heard has played, or was lost on its way.
            break
        held.append(row)
    return held[::-1]


async def _held(session: ormSession, cart: Cart) -> tuple[list[int], list[int]]:
    """
    The sounds of a cart the conducteur holds, oldest first: those sent to the
    antenna and not on air yet, and those it plans.
    """
    engaged: list[int] = []
    planned: list[int] = []
    for line in await _held_lines(session, cart):
        (planned if line.status in _PLANNED_STATUSES else engaged).append(line.sound_id)
    return engaged, planned


async def cart_ahead(
    session: ormSession,
    cart: Cart | None,
) -> CartDraw | CartOrder | None:
    """
    What the conducteur plans a cart ahead from: the draw of a random cart, or
    the order of a playlist with what it already holds of it. None for a cart
    that has neither: a relay, or a random cart with its switch turned off.
    """
    draw = await cart_draw(session, cart)
    if draw is not None or cart is None or cart.mode not in _ORDERED_MODES:
        return draw
    engaged, planned = await _held(session, cart)
    return CartOrder([*engaged, *planned])


async def planned_in_order(
    session: ormSession,
    cart: Cart | None,
    since: datetime | None = None,
) -> list[tuple[RundownItem, Sound]]:
    """
    The lines the conducteur plans of a cart in order that now name the wrong
    sound, each with the one it plays: the order of the forecast
    (``CartOrder``), counted again after the sounds sent to the antenna and not
    on air yet. A sound the clock has just drawn for an anchor it held no line
    for is one of them: the lines planned before would replay it. A desk line
    keeps the sound chosen for it, and takes its turn with it. An anchor line
    planned before ``since``, the time of that sound, neither moves nor counts:
    a hard anchor never goes after its minute, and a soft one still waiting is
    overtaken by the anchor drawn, or goes as planned. Nothing for any other
    cart.
    """
    if cart is None or cart.mode not in _ORDERED_MODES:
        return []
    lines = await _held_lines(session, cart)
    order = CartOrder(
        [line.sound_id for line in lines if line.status not in _PLANNED_STATUSES]
    )
    moved: list[tuple[RundownItem, Sound]] = []
    for line in lines:
        if line.status not in _PLANNED_STATUSES:
            continue
        if (
            since is not None
            and line.when_mode == WhenMode.ANCHORED.value
            and line.planned_at < since
        ):
            continue
        if line.origin == _DESK_ORIGIN:
            order.held.append(line.sound_id)
            continue
        sound = order.pick_ahead(cart)
        if sound is None:
            break
        if sound.id != line.sound_id:
            moved.append((line, sound))
    return moved


async def next_cart_sound(session: ormSession, cart: Cart | None) -> Sound | None:
    """
    The sound a cart plays now. A random cart draws without repeat. A one-shot
    playlist played through starts again (``Cart.next_sound_playlist``): clock
    jingle and pub carts keep filling.
    """
    if cart is None:
        return None
    draw = await cart_draw(session, cart)
    if draw is None:
        return cart.next_sound()
    return draw.pick_now(cart)


async def note_on_air(session: ormSession, sound_id: object) -> None:
    """A sound is on air: it has played in the round of its random cart."""
    try:
        sound = await Sound.from_id(session, int(sound_id))
    except (TypeError, ValueError):
        return
    if sound is None or sound.cart is None or sound.cart.mode is not CartMode.RANDOM:
        return
    if not await no_repeat_enabled(session):
        return
    key = str(sound.cart_id)
    sounds = await session.scalars(select(Sound).where(Sound.cart_id == sound.cart_id))
    state = await _drawn_by_cart(session)
    state[key] = drawn_after(sounds, _ids(state.get(key)), sound.id)
    await Setting.upsert(session, SETTING_DRAWN, json.dumps(state))
