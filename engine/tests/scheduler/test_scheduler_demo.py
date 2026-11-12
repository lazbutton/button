from asyncio import sleep
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.db import QuartAlchemy
from radiotomate.enums import CartMode, ScheduleMode
from radiotomate.interface import live as live_mod
from radiotomate.interface_app import app_factory as interface_factory
from radiotomate.models import Cart, RundownItem, Sound, User
from radiotomate.scheduler.execution import DESK_ORIGIN
from radiotomate.scheduler.rundown import DEFAULT_MUSIC_SEC
from radiotomate.scheduler_api import Scheduler
from tests.scheduler.test_studio_json import _login


def _demo_app(app_configration: dict, beets_integration: BeetsIntegration):
    Scheduler.reset_instance()
    # The live snapshot outlives a test: without this, _wait_simulating would
    # take the previous demo's for this one.
    live_mod.set_live_snapshot(None)
    iface = interface_factory(app_configration, False, beets_integration)
    iface.config["INTERFACE_NAME"] = "BUTTON"
    Scheduler.init(app_configration, iface, demo=True)
    return iface


async def _wait_simulating(client):
    payload = {"status": "offline"}
    for _ in range(80):
        payload = await (await client.get("/live.json")).get_json()
        if payload.get("status") == "simulating" and payload.get("title"):
            return payload
        await sleep(0.1)
    return payload


async def test_demo_live_skip_and_fire_sound(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    user = User(username="demo-overlay")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    sound = await dbsession.scalar(
        select(Sound).where(Sound.cart_id == jingles_cart.id)
    )
    assert sound is not None

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, "demo-overlay", users_password)
            first = await _wait_simulating(client)
            assert first["status"] == "simulating"
            assert first["title"]
            assert first["title"] != "Pas d'horloge"

            skipped = await client.delete("/live.json")
            assert skipped.status_code == 200
            second = await (await client.get("/live.json")).get_json()
            assert second["status"] == "simulating"
            assert second["title"]
            assert (second["title"], second["artist"]) != (
                first["title"],
                first["artist"],
            )

            fired = await client.post(
                f"/carts/{jingles_cart.id}/sounds/{sound.id}/now.json",
            )
            assert fired.status_code == 200
            now = await (await client.get("/live.json")).get_json()
            assert now["title"] == sound.title
            assert now["source"] == "jingles"
    finally:
        Scheduler.reset_instance()


async def test_demo_cart_without_sound_ready(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    """As the scheduler: no sound ready, nothing plays, and the console is told."""
    user = User(username="demo-cart-empty")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    spot = await dbsession.scalar(select(Sound).where(Sound.cart_id == pubs_cart.id))
    assert spot is not None
    spot.active = False
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, "demo-cart-empty", users_password)
            await _wait_simulating(client)
            fired = await client.post(f"/carts/{pubs_cart.id}/now.json")
            assert fired.status_code == 409
            assert await fired.get_json() == {
                "error": "Ce bac n'a aucun son prêt : rien n'est parti à l'antenne.",
                "code": "cart_empty",
            }
            # The demo used to play the cart's first sound, even disabled.
            now = await (await client.get("/live.json")).get_json()
            assert now["title"] != spot.title
    finally:
        Scheduler.reset_instance()


async def test_demo_relay_cart(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    """As the scheduler: a relay cart has no sound, its stream goes on air."""
    user = User(username="demo-relay")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    relay = Cart(
        title="Radio partenaire",
        path=raw_app.config["DATA_ROOT"] / "relay",
        url="https://radio.example/direct.mp3",
        max_duration=600,
        mode=CartMode.RELAY,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(relay)
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, "demo-relay", users_password)
            await _wait_simulating(client)
            fired = await client.post(f"/carts/{relay.id}/now.json")
            # The demo used to look for the relay's next sound: a 500.
            assert fired.status_code == 200
            assert await fired.get_json() == {"ok": True}
            now = await (await client.get("/live.json")).get_json()
            assert now["source"] == "relay"
            assert now["title"] == "Radio partenaire"
            # It lasts max_duration, as the scheduler's timer would cut it.
            assert 590 < now["remaining"] <= 600
    finally:
        Scheduler.reset_instance()


async def test_demo_playlist_played_through_starts_again(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    """As the scheduler: a one-shot playlist played through starts again."""
    user = User(username="demo-cart-again")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    pubs_cart.mode = CartMode.PLAYLIST
    spot = await dbsession.scalar(select(Sound).where(Sound.cart_id == pubs_cart.id))
    assert spot is not None
    spot.last_played = datetime(2026, 10, 30, 9, 0)
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, "demo-cart-again", users_password)
            await _wait_simulating(client)
            fired = await client.post(f"/carts/{pubs_cart.id}/now.json")
            assert fired.status_code == 200, await fired.get_data(as_text=True)
            now = await (await client.get("/live.json")).get_json()
            assert now["title"] == spot.title
    finally:
        Scheduler.reset_instance()


async def test_demo_conducteur_follows_live_queue(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    user = User(username="demo-conducteur")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, "demo-conducteur", users_password)
            live = await _wait_simulating(client)
            first = await (await client.get("/autodj/conducteur.json")).get_json()
            again = await (await client.get("/autodj/conducteur.json")).get_json()
            assert first["items"]
            assert first["summary"]["counts"]["items"] >= 1
            first_on_air = next(
                item for item in first["items"] if item.get("status_code") == "on_air"
            )
            assert again["items"][0]["resource"] == first["items"][0]["resource"]
            assert live["title"] in first_on_air["resource"]

            skipped = await client.delete("/live.json")
            assert skipped.status_code == 200
            after = await (await client.get("/autodj/conducteur.json")).get_json()
            assert after["items"]
            played = [
                item for item in after["items"] if item.get("status_code") == "played"
            ]
            assert played
            assert first_on_air["resource"] == played[-1]["resource"]
            after_on_air = next(
                item for item in after["items"] if item.get("status_code") == "on_air"
            )
            assert after_on_air["resource"] != first_on_air["resource"]
            second_live = await (await client.get("/live.json")).get_json()
            assert second_live["title"] in after_on_air["resource"]
    finally:
        Scheduler.reset_instance()


async def _desk_lines(dbsession: ormSession) -> dict[str, str]:
    """The status of each desk line, by path. Columns, not rows: the session
    would keep the status it read first."""
    rows = await dbsession.execute(
        select(RundownItem.path, RundownItem.status).where(
            RundownItem.origin == DESK_ORIGIN
        )
    )
    return dict(rows.all())


async def _play_now(client, title: str):
    """« Jouer tout de suite » on a title of the bank: its desk line is sent."""
    return await client.post(
        "/autodj/conducteur/now.json",
        json={
            "path": f"/media/{title}.wav",
            "title": title,
            "kind": "musique",
            "duration": 180,
        },
    )


@pytest.mark.parametrize("passage", ["path", "sound", "cart", "relay", "skip", "end"])
async def test_demo_closes_the_line_of_play_now(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
    passage: str,
):
    """
    As a station, whose rundown is reconciled with what airs: the line of « Jouer
    tout de suite » closes, played, once another title airs, whatever puts it on
    air: another title of the bank, a sound or a cart, a relay, « Suivant », or
    the end of its own title. The demo used to leave it sent: locked in the
    antenna file after its title, until its time was over.
    """
    user = User(username=f"demo-play-now-{passage}")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    relay = Cart(
        title="Radio partenaire",
        path=raw_app.config["DATA_ROOT"] / "relay",
        url="https://radio.example/direct.mp3",
        max_duration=600,
        mode=CartMode.RELAY,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(relay)
    sound = await dbsession.scalar(
        select(Sound).where(Sound.cart_id == jingles_cart.id)
    )
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, f"demo-play-now-{passage}", users_password)
            await _wait_simulating(client)
            fired = await _play_now(client, "Grande distance")
            assert fired.status_code == 200, await fired.get_data(as_text=True)
            assert await _desk_lines(dbsession) == {
                "/media/Grande distance.wav": "in_queue"
            }

            answer = None
            if passage == "path":
                answer = await _play_now(client, "Bande large")
            elif passage == "sound":
                answer = await client.post(
                    f"/carts/{jingles_cart.id}/sounds/{sound.id}/now.json"
                )
            elif passage == "cart":
                answer = await client.post(f"/carts/{pubs_cart.id}/now.json")
            elif passage == "relay":
                answer = await client.post(f"/carts/{relay.id}/now.json")
            elif passage == "skip":
                answer = await client.delete("/live.json")
            else:
                # Its title over, the loop of the demo passes to the next one.
                Scheduler.get()._on_air -= timedelta(seconds=DEFAULT_MUSIC_SEC + 1)
            if answer is not None:
                assert answer.status_code == 200, await answer.get_data(as_text=True)
            for _ in range(40):
                lines = await _desk_lines(dbsession)
                if lines["/media/Grande distance.wav"] == "played":
                    break
                await sleep(0.1)
            assert lines["/media/Grande distance.wav"] == "played"

            # Out of the antenna file: only the line of a new title of the bank.
            rundown = await (await client.get("/autodj/conducteur.json")).get_json()
            assert [
                item["path"]
                for item in rundown["items"]
                if item.get("origin") == DESK_ORIGIN
            ] == (["/media/Bande large.wav"] if passage == "path" else [])
    finally:
        Scheduler.reset_instance()


async def test_demo_play_now_when_the_line_cannot_close(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    """Closing the line is bookkeeping: a base that refuses it does not stop the
    next title, which goes on air all the same. The line waits for the next one."""
    user = User(username="demo-play-now-locked")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, "demo-play-now-locked", users_password)
            await _wait_simulating(client)
            fired = await _play_now(client, "Grande distance")
            assert fired.status_code == 200, await fired.get_data(as_text=True)

            locked = OperationalError("SELECT", {}, Exception("database is locked"))
            with patch("radiotomate.scheduler_api.select", side_effect=locked):
                answer = await _play_now(client, "Bande large")
            assert answer.status_code == 200, await answer.get_data(as_text=True)
            live = await (await client.get("/live.json")).get_json()
            assert live["title"] == "Bande large"
            assert await _desk_lines(dbsession) == {
                "/media/Grande distance.wav": "in_queue",
                "/media/Bande large.wav": "in_queue",
            }
    finally:
        Scheduler.reset_instance()


def _clock_at(moment: datetime) -> type[datetime]:
    """The clock the demo reads, still: the test moves it."""

    class Clock(datetime):
        at = moment

        @classmethod
        def now(cls, tz=None):
            return cls.at if tz is None else cls.at.astimezone(tz)

    return Clock


@pytest.mark.parametrize("apart", [1, 0], ids=["a second apart", "same second"])
async def test_demo_never_gives_back_a_line_it_left(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
    apart: int,
):
    """
    Nothing reconciles the demo's rundown with what airs: the base keeps planned
    the lines the demo has left. It used to give them back planned, at their
    planned time: aired ahead of it, after « Suivant », a line of the title on
    air was taken by the console for that title, and the line the demo plays fell
    to the head of the antenna file, locked. Its queue, reloaded from the base,
    also took back a line its log did not keep: aired more than twelve titles
    ago, or started in the same second as the title logged before it.
    """
    user = User(username="demo-left")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, "demo-left", users_password)
            await _wait_simulating(client)
            # Six hours of lines, as the console asks.
            await client.get("/autodj/conducteur.json?horizon=360")
            demo = Scheduler.get()
            # A second after the title on air started: each title then starts a
            # second after the one before, or all in that same second.
            clock = _clock_at(demo._on_air + timedelta(seconds=1))
            left = []
            with patch("radiotomate.scheduler_api.datetime", clock):
                # One more than the twelve titles of its log.
                for _ in range(13):
                    left.append(demo._items[0]["id"])
                    skipped = await client.delete("/live.json")
                    assert skipped.status_code == 200
                    clock.at += timedelta(seconds=apart)
                rundown = await (await client.get("/autodj/conducteur.json")).get_json()
                # Its queue reloaded from the base, as the demo does when it holds
                # fewer than twenty-four lines.
                async with (
                    iface.app_context(),
                    demo._lock,
                    QuartAlchemy.get().session() as session,
                ):
                    await demo._load_items(session)

            assert len(set(left)) == 13
            assert [
                (item["id"], item["status_code"])
                for item in rundown["items"]
                if item["id"] in left and item["status_code"] != "played"
            ] == []
            assert [item["id"] for item in demo._items if item["id"] in left] == []
    finally:
        Scheduler.reset_instance()


async def _hold_the_antenna(client) -> None:
    """Passes to a title that holds the antenna a minute at least: the demo does
    not pass to the next one by itself meanwhile."""
    for _ in range(5):
        live = await (await client.get("/live.json")).get_json()
        if float(live["remaining"]) >= 60:
            return
        skipped = await client.delete("/live.json")
        assert skipped.status_code == 200
    raise AssertionError("no title holds the antenna")


@pytest.mark.parametrize("fired", ["path", "sound"])
async def test_demo_airs_no_line_of_the_clock_during_a_title_fired(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
    fired: str,
):
    """
    A title fired from the desk, from the bank or from a cart, cuts the line on
    air, which the demo leaves: the next line waits for the end of that title,
    and no line of the clock is on air meanwhile. The demo used to mark the first
    line of its base: not over, the console took it for the title on air, and
    the line of a title of the bank fell to the head of the antenna file, locked.
    Once the lines it left are out of the base, that first line is the next one,
    still to come, when no line of the desk comes before it: so with a sound of
    a cart, which has none.
    """
    user = User(username=f"demo-fired-{fired}")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    spot = await dbsession.scalar(select(Sound).where(Sound.cart_id == pubs_cart.id))
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, f"demo-fired-{fired}", users_password)
            await _wait_simulating(client)
            await _hold_the_antenna(client)
            following = Scheduler.get()._items[1]["id"]
            if fired == "path":
                answer = await _play_now(client, "Grande distance")
            else:
                # The spot lasts twenty seconds: the demo does not pass on by
                # itself before the test is over.
                answer = await client.post(
                    f"/carts/{pubs_cart.id}/sounds/{spot.id}/now.json"
                )
            assert answer.status_code == 200, await answer.get_data(as_text=True)
            rundown = await (await client.get("/autodj/conducteur.json")).get_json()
            assert [
                item["resource"]
                for item in rundown["items"]
                if item["status_code"] == "on_air"
            ] == []

            # The title over, the line after the one it cut airs.
            skipped = await client.delete("/live.json")
            assert skipped.status_code == 200
            rundown = await (await client.get("/autodj/conducteur.json")).get_json()
            assert [
                item["id"]
                for item in rundown["items"]
                if item["status_code"] == "on_air"
            ] == [following]
    finally:
        Scheduler.reset_instance()


async def test_demo_queues_only_lines_still_to_air(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    pubs_cart,
):
    """
    When the base draws more lines, it gives back every line it shows: played,
    as the line of a title fired from the desk, closed once the demo passes on,
    or sent, or failed. The demo used to queue them at the end of its queue, and
    would have aired them again, as lines of the clock.
    """
    user = User(username="demo-to-air")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()

    iface = _demo_app(app_configration, beets_integration)
    try:
        async with iface.test_app():
            client = iface.test_client()
            await _login(client, "demo-to-air", users_password)
            await _wait_simulating(client)
            fired = await _play_now(client, "Grande distance")
            assert fired.status_code == 200, await fired.get_data(as_text=True)
            skipped = await client.delete("/live.json")
            assert skipped.status_code == 200
            assert await _desk_lines(dbsession) == {
                "/media/Grande distance.wav": "played"
            }

            demo = Scheduler.get()
            # Further than the base holds: it draws more lines.
            async with (
                iface.app_context(),
                demo._lock,
                QuartAlchemy.get().session() as session,
            ):
                await demo._load_items(session, horizon_min=400)
            assert [
                (item["resource"], item["status_code"])
                for item in demo._items
                if item["status_code"] not in ("planned", "rescue")
            ] == []
    finally:
        Scheduler.reset_instance()
