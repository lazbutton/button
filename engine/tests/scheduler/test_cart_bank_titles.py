"""Titles of the bank in a cart, without a copy (FON-69)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from beets.library import Item, Library
from sqlalchemy import select
from sqlalchemy import update as sql_update

from radiotomate.beets import BeetsIntegration
from radiotomate.models import Cart, Setting, Sound
from radiotomate.services import bank_moves, bank_titles
from radiotomate.services.carts import sync_bank_folder
from tests.scheduler.test_admin_json import ASSETS, _admin_client

ROTATION_A = "10-rotation/orage - ete indien.mp3"
ROTATION_B = "10-rotation/b.mp3"
NUIT = "20-archives/nuit/c.mp3"


@pytest.fixture
def media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = (tmp_path / "media").resolve()
    mp3 = (ASSETS / "ohradiotomateoh.mp3").read_bytes()
    for rel in (ROTATION_A, ROTATION_B, NUIT, "00-inbox/rotation/d.mp3"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(mp3)
    monkeypatch.setenv("MEDIA_ROOT", str(root))
    return root


@pytest.fixture
def beets(media: Path, tmp_path: Path) -> BeetsIntegration:
    lib = Library(str(tmp_path / "library.db"))
    lib.add(
        Item(path=str(media / ROTATION_A).encode(), artist="Orage", title="Été indien")
    )
    lib.add(Item(path=str(media / NUIT).encode(), artist="", title="Comète"))
    integration = object.__new__(BeetsIntegration)
    integration.lib = lib
    return integration


async def _sounds(client, cart_id: int) -> list[dict]:
    carts = (await (await client.get("/carts.json")).get_json())["carts"]
    return next(cart for cart in carts if cart["id"] == cart_id)["sounds"]


async def _cart(client) -> int:
    created = await client.post(
        "/carts.json",
        json={"title": "Soirée", "mode": "playlist", "schedule_mode": "timed"},
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    return (await created.get_json())["cart"]["id"]


async def _client(app_configration, beets, dbsession, users_password, *, on=True):
    if on:
        dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
        await dbsession.commit()
    return await _admin_client(
        app_configration, beets, dbsession, users_password, "bacs-banque"
    )


async def test_switch_off_keeps_the_titles_out(  # noqa: PLR0913
    raw_app, app_configration, beets, dbsession, users_password, media
):
    client = await _client(app_configration, beets, dbsession, users_password, on=False)
    cart_id = await _cart(client)
    refused = await client.post(
        f"/carts/{cart_id}/sounds.json", json={"titles": [ROTATION_A]}
    )
    assert refused.status_code == 409
    assert (await refused.get_json())["code"] == "bank_tidy_off"
    # The way of today still refuses a title of the rotation.
    by_path = await client.post(
        f"/carts/{cart_id}/sounds.json", json={"paths": [ROTATION_A]}
    )
    assert by_path.status_code == 400


async def test_a_cart_takes_titles_of_the_bank_without_a_copy(  # noqa: PLR0913
    raw_app, app_configration, beets, dbsession, users_password, media
):
    client = await _client(app_configration, beets, dbsession, users_password)
    cart_id = await _cart(client)
    added = await client.post(
        f"/carts/{cart_id}/sounds.json", json={"titles": [ROTATION_A, ROTATION_B, NUIT]}
    )
    assert added.status_code == 201, await added.get_data(as_text=True)
    sounds = (await added.get_json())["cart"]["sounds"]
    assert [sound["title"] for sound in sounds] == [
        "Orage - Été indien",
        "b.mp3",
        "Comète",
    ]
    assert [sound["path"] for sound in sounds] == [ROTATION_A, ROTATION_B, NUIT]
    assert all(sound["borrowed"] and not sound["missing"] for sound in sounds)
    # No copy: the cart's own folder holds nothing, each sound plays the bank's file.
    rows = list(await dbsession.scalars(select(Sound).where(Sound.cart_id == cart_id)))
    assert {Path(row.path) for row in rows} == {
        media / ROTATION_A,
        media / ROTATION_B,
        media / NUIT,
    }
    cart = await Cart.from_id(dbsession, cart_id)
    assert not any((media / str(cart.bank_folder)).rglob("*.mp3"))

    again = await client.post(
        f"/carts/{cart_id}/sounds.json", json={"titles": [ROTATION_A]}
    )
    assert again.status_code == 409

    # The table says which carts play a title, before it leaves the bank.
    table = await (await client.get("/media/titles.json?q=ete")).get_json()
    assert table["titles"][0]["carts"] == [{"id": cart_id, "title": "Soirée"}]


@pytest.mark.parametrize(
    "raw",
    ["00-inbox/rotation/d.mp3", "90-trash/x.mp3", "10-rotation/absent.mp3", "../x.mp3"],
)
async def test_a_title_outside_the_rotation_and_the_collections_is_refused(  # noqa: PLR0913
    raw_app, app_configration, beets, dbsession, users_password, media, raw
):
    client = await _client(app_configration, beets, dbsession, users_password)
    cart_id = await _cart(client)
    refused = await client.post(f"/carts/{cart_id}/sounds.json", json={"titles": [raw]})
    assert refused.status_code == 400
    assert (await refused.get_json())["code"] == "validation_error"


async def test_removing_the_sound_leaves_the_file_in_the_bank(  # noqa: PLR0913
    raw_app, app_configration, beets, dbsession, users_password, media
):
    client = await _client(app_configration, beets, dbsession, users_password)
    cart_id = await _cart(client)
    added = await client.post(
        f"/carts/{cart_id}/sounds.json", json={"titles": [ROTATION_A]}
    )
    sound_id = (await added.get_json())["cart"]["sounds"][0]["id"]
    gone = await client.delete(f"/carts/{cart_id}/sounds/{sound_id}.json")
    assert gone.status_code == 200
    assert (media / ROTATION_A).is_file()


async def test_a_title_moved_in_the_bank_stays_in_the_cart(  # noqa: PLR0913
    raw_app, app_configration, beets, dbsession, users_password, media
):
    client = await _client(app_configration, beets, dbsession, users_password)
    cart_id = await _cart(client)
    await client.post(f"/carts/{cart_id}/sounds.json", json={"titles": [ROTATION_A]})
    target = media / "20-archives/nuit/orage - ete indien.mp3"
    shutil.move(media / ROTATION_A, target)
    # What ARC-09 does of the paths the engine keeps, once the file moved.
    await bank_moves._retarget_rows(
        dbsession, media / ROTATION_A, target, [], check=False
    )
    await dbsession.commit()
    (sound,) = await _sounds(client, cart_id)
    assert sound["path"] == "20-archives/nuit/orage - ete indien.mp3"
    assert sound["missing"] is False


async def test_a_title_removed_from_the_bank_stays_unavailable(  # noqa: PLR0913
    raw_app, app_configration, beets, dbsession, users_password, media
):
    client = await _client(app_configration, beets, dbsession, users_password)
    cart_id = await _cart(client)
    await client.post(
        f"/carts/{cart_id}/sounds.json", json={"titles": [ROTATION_A, NUIT]}
    )
    # Both analysed, so both ready, until a file leaves the bank.
    await dbsession.execute(sql_update(Sound).values(gain=-1.0, peak=-0.5))
    await dbsession.commit()
    (media / ROTATION_A).unlink()

    cart = await Cart.from_id(dbsession, cart_id, load_sounds=True)
    # The cart's folder is read again, as the scheduler does: the title stays.
    await sync_bank_folder(dbsession, cart, cart.sounds[0].uploader_id)
    await dbsession.commit()
    by_path = {sound["path"]: sound for sound in await _sounds(client, cart_id)}
    assert by_path[ROTATION_A]["missing"] is True
    assert by_path[ROTATION_A]["available"] is False
    assert by_path[NUIT]["missing"] is False
    assert by_path[NUIT]["available"] is True
    # A cart never draws it.
    dbsession.expire_all()
    cart = await Cart.from_id(dbsession, cart_id, load_sounds=True)
    ready = [sound for sound in cart.sounds if sound.available]
    assert [Path(sound.path).name for sound in ready] == ["c.mp3"]
