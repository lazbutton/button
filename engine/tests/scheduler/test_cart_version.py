"""
A cart's version says it was edited: a client sends the version it read, and
the engine refuses an edit made on a version gone by. Loading a cart with its
sounds, as a draw does, by the conducteur, the clock or « Diffuser
maintenant », is no edit (FON-45).
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.models import Cart, RundownItem, Sound
from radiotomate.quart import CustomQuart
from radiotomate.scheduler import schedule
from radiotomate.scheduler.clock import tick
from tests.scheduler.test_admin_json import _admin_client
from tests.scheduler.test_clock import NIGHT, _client, _live

# Long before the test: an UPDATE of the cart would write the time of now.
LONG_AGO = datetime(2026, 1, 5, 9, 0)


async def _stamp(session: ormSession, cart_id: int) -> tuple[int, datetime]:
    """The cart's version and modified date, as the base has them."""
    row = (
        await session.execute(
            select(Cart.version, Cart.modified).where(Cart.id == cart_id)
        )
    ).one()
    return row.version, row.modified


async def _modified_long_ago(session: ormSession, *carts: Cart) -> None:
    """Without the ORM, which would bump the version."""
    table = Cart.__table__
    for cart in carts:
        await session.execute(
            table.update().where(table.c.id == cart.id).values(modified=LONG_AGO)
        )
    await session.commit()


async def _sent_a_quarter_ago(session: ormSession) -> None:
    """The lines a tick sent, a quarter of an hour before the next one: the
    playout took them that long ago."""
    rows = await session.scalars(
        select(RundownItem).where(RundownItem.reserved_at.is_not(None))
    )
    for row in rows:
        for name in ("reserved_at", "sent_at", "queued_at"):
            if getattr(row, name) is not None:
                setattr(row, name, getattr(row, name) - timedelta(minutes=15))
    await session.commit()


async def _load(session: ormSession, cart_id: int, how: str) -> Cart:
    if how == "all":
        carts = await Cart.all(session, load_sounds=True)
        return next(cart for cart in carts if cart.id == cart_id)
    return await Cart.from_id(
        session, cart_id, load_sounds=True, load_uploaders=how == "uploaders"
    )


@pytest.mark.parametrize("how", ["one", "uploaders", "all"])
async def test_loading_a_cart_with_its_sounds_is_no_edit(  # noqa: PLR0913
    raw_app: CustomQuart,
    dbsession: ormSession,
    fake_cart: Cart,
    fake_sound,
    fake_sound2,
    how: str,
):
    """Its two counts are filled as if read from the base: the session has
    nothing to write, and committing it leaves the version and the modified
    date as they were."""
    await _modified_long_ago(dbsession, fake_cart)
    before = await _stamp(dbsession, fake_cart.id)
    async with raw_app.extensions["sqlalchemy"].session() as session:
        cart = await _load(session, fake_cart.id, how)
        # The second sound has no gain yet: it cannot play.
        assert (cart.sounds_count, cart.inactive_sounds_count) == (2, 1)
        assert not session.dirty
        await session.commit()
        assert (cart.sounds_count, cart.inactive_sounds_count) == (2, 1)
    assert await _stamp(dbsession, fake_cart.id) == before


async def test_the_counts_stay_after_an_edit(
    raw_app: CustomQuart,
    dbsession: ormSession,
    fake_cart: Cart,
    fake_sound,
    fake_sound2,
):
    """A real edit after the load bumps the version once, as before, and the
    counts stay after the commit: the page of the sounds shows them once an
    upload is written (add_sounds), and fails without them."""
    await _modified_long_ago(dbsession, fake_cart)
    version, _ = await _stamp(dbsession, fake_cart.id)
    async with raw_app.extensions["sqlalchemy"].session() as session:
        cart = await Cart.from_id(session, fake_cart.id, load_sounds=True)
        cart.recompute_duration()
        await session.commit()
        assert (cart.sounds_count, cart.inactive_sounds_count) == (2, 1)
    edited, modified = await _stamp(dbsession, fake_cart.id)
    assert edited == version + 1
    assert modified != LONG_AGO


async def test_a_cart_on_air_keeps_its_version(
    raw_app: CustomQuart,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """Four ticks of the night clock, a quarter of an hour apart and a session
    each, as on a station: each draws the conducteur further and pushes the
    jingle of its motif. Each bumped the cart's version before: from 1 to 5."""
    await _modified_long_ago(dbsession, jingles_cart)
    before = await _stamp(dbsession, jingles_cart.id)
    client = _client()
    night = datetime.fromisoformat(NIGHT)
    for minutes in (0, 15, 30, 45):
        at = (night + timedelta(minutes=minutes)).isoformat()
        async with raw_app.extensions["sqlalchemy"].session() as session:
            await _sent_a_quarter_ago(session)
            await tick(session, _live(at), client, beets_integration)
    queues = [call.args[0] for call in client.post.call_args_list]
    assert queues.count("/queue/jingles") == 4
    assert await _stamp(dbsession, jingles_cart.id) == before


async def test_a_cart_edited_after_a_tick_is_saved(  # noqa: PLR0913
    raw_app: CustomQuart,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart: Cart,
):
    """The cart is read, the clock pushes one of its sounds, then the edit comes
    with the version read: it passes. The version read before that edit is
    refused: the check still holds."""
    console = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "bacs"
    )
    listed = await (await console.get("/carts.json")).get_json()
    read = next(row for row in listed["carts"] if row["id"] == jingles_cart.id)
    client = _client()
    async with raw_app.extensions["sqlalchemy"].session() as session:
        await tick(session, _live(NIGHT), client, beets_integration)
    assert client.post.call_args_list[0].args[0] == "/queue/jingles"
    saved = await console.put(
        f"/carts/{read['id']}.json",
        json={"version": read["version"], "notes": "Les jingles de la nuit"},
    )
    assert saved.status_code == 200, await saved.get_data(as_text=True)
    cart = (await saved.get_json())["cart"]
    assert cart["notes"] == "Les jingles de la nuit"
    assert cart["version"] == read["version"] + 1
    stale = await console.put(
        f"/carts/{read['id']}.json",
        json={"version": read["version"], "notes": "Une autre note"},
    )
    assert stale.status_code == 409


async def test_an_edit_written_across_a_tick(
    raw_app: CustomQuart,
    dbsession: ormSession,
    jingles_cart: Cart,
    beets_integration: BeetsIntegration,
):
    """The console loads the cart to save an edit, with no version sent; the
    clock ticks meanwhile and pushes one of its sounds. The UPDATE of the edit
    checks the version it loaded: the tick bumped it before, and the edit failed
    (StaleDataError)."""
    sessions = raw_app.extensions["sqlalchemy"].session
    async with sessions() as interface:
        cart = await Cart.from_id(interface, jingles_cart.id, load_sounds=True)
        client = _client()
        async with sessions() as scheduler:
            await tick(scheduler, _live(NIGHT), client, beets_integration)
        assert client.post.call_args_list[0].args[0] == "/queue/jingles"
        cart.notes = "Les jingles de la nuit"
        await interface.commit()
    saved = await dbsession.execute(
        select(Cart.version, Cart.notes).where(Cart.id == jingles_cart.id)
    )
    assert tuple(saved.one()) == (2, "Les jingles de la nuit")


async def test_a_push_written_across_an_edit(
    raw_app: CustomQuart,
    dbsession: ormSession,
    fake_cart: Cart,
    fake_sound,
):
    """« Diffuser maintenant » loads the cart, then waits for the playout; an
    edit of the console is saved meanwhile. The push wrote the cart too, on the
    version it had loaded: its commit failed (StaleDataError), the sound went on
    air and its passage was not noted."""
    sessions = raw_app.extensions["sqlalchemy"].session
    enqueue = schedule._enqueue_sound

    async def edit_meanwhile(*args, **kwargs):
        async with sessions() as interface:
            edited = await Cart.from_id(interface, fake_cart.id, load_sounds=True)
            edited.notes = "Une note"
            await interface.commit()
        return await enqueue(*args, **kwargs)

    answer = httpx.Response(200, json={"OK": 1})
    with (
        patch.object(schedule, "_enqueue_sound", edit_meanwhile),
        patch("httpx.AsyncClient.post", return_value=answer),
    ):
        async with sessions() as session:
            result = await schedule.push_cart(session, raw_app, fake_cart.id)
    assert result is not None
    assert result.ok
    played = await dbsession.scalar(
        select(Sound.last_played).where(Sound.id == fake_sound.id)
    )
    assert played is not None
    assert (await _stamp(dbsession, fake_cart.id))[0] == 2


async def test_the_bac_that_loses_the_ident_pads_changes_version(
    raw_app: CustomQuart,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    """One bac at a time carries the ident pads: marking another takes the flag
    off the first, and its version moves too (FON-48). A console that read the
    first before, and saves its notes with the flag it read, is refused: it
    would set the flag back, and take it off the bac just marked."""
    console = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "pads"
    )
    created = await console.post(
        "/carts.json",
        json={
            "title": "Idents",
            "mode": "playlist_loop",
            "schedule_mode": "clock",
            "ident_pads": True,
        },
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    idents = (await created.get_json())["cart"]
    other = await console.post(
        "/carts.json",
        json={"title": "Jingles 2", "mode": "playlist_loop", "schedule_mode": "clock"},
    )
    jingles = (await other.get_json())["cart"]
    marked = await console.put(
        f"/carts/{jingles['id']}.json",
        json={"version": jingles["version"], "ident_pads": True},
    )
    assert marked.status_code == 200, await marked.get_data(as_text=True)
    listed = (await (await console.get("/carts.json")).get_json())["carts"]
    now = next(row for row in listed if row["id"] == idents["id"])
    assert now["ident_pads"] is False
    assert now["version"] == idents["version"] + 1

    stale = await console.put(
        f"/carts/{idents['id']}.json",
        json={"version": idents["version"], "notes": "Les idents", "ident_pads": True},
    )
    assert stale.status_code == 409
    assert (await stale.get_json())["field"] == "version"
    listed = (await (await console.get("/carts.json")).get_json())["carts"]
    flags = {row["title"]: row["ident_pads"] for row in listed}
    assert (flags["Idents"], flags["Jingles 2"]) == (False, True)
