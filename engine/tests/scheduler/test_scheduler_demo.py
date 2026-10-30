from asyncio import sleep

from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import CartMode, ScheduleMode
from radiotomate.interface import live as live_mod
from radiotomate.interface_app import app_factory as interface_factory
from radiotomate.models import Cart, Sound, User
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
