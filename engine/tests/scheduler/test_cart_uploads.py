from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.orm import Session as ormSession
from werkzeug.datastructures import FileStorage, MultiDict
from werkzeug.test import encode_multipart

from radiotomate.beets import BeetsIntegration
from radiotomate.models import Cart
from radiotomate.scheduler_api import Scheduler
from radiotomate.services import media_bank
from tests.scheduler.test_admin_json import ASSETS, _admin_client, _mp3_upload

UNREADABLE = (
    "Un fichier n'a pas de nom lisible : son nom finit peut-être par « \\ ». "
    "Renomme-le, puis envoie-le à nouveau."
)


async def _new_cart(client, title: str) -> int:
    created = await client.post(
        "/carts.json",
        json={"title": title, "mode": "playlist", "schedule_mode": "timed"},
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    return (await created.get_json())["cart"]["id"]


async def _cart_sounds(client, cart_id: int) -> list[dict]:
    listed = await (await client.get("/carts.json")).get_json()
    return next(row for row in listed["carts"] if row["id"] == cart_id)["sounds"]


async def _cart_files(dbsession: ormSession, cart_id: int) -> list[str]:
    cart = await Cart.from_id(dbsession, cart_id)
    return sorted(path.name for path in media_bank.cart_upload_dir(cart).iterdir())


async def test_cart_sounds_htmx_upload(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "cart-htmx",
    )
    cart_id = await _new_cart(client, "HTMX Cart")
    mp3 = ASSETS / "ohradiotomateoh.mp3"
    scheduler = MagicMock()
    scheduler.queue_analysis = AsyncMock()
    with patch.object(Scheduler, "get", return_value=scheduler):
        # Depuis la liste des carts : la page des sons s'ouvre ensuite.
        first = await client.post(
            f"/carts/{cart_id}/sounds",
            files={"sounds": _mp3_upload(mp3)},
        )
        assert first.status_code == 200, await first.get_data(as_text=True)
        assert first.headers["HX-Redirect"] == f"/carts/{cart_id}/sounds"
        # Depuis la page des sons : la ligne du son ajouté revient.
        second = await client.post(
            f"/carts/{cart_id}/sounds?from_list=True",
            files={
                "sounds": FileStorage(
                    BytesIO(mp3.read_bytes()),
                    "two.mp3",
                    "audio/mpeg",
                ),
            },
        )
        assert second.status_code == 200, await second.get_data(as_text=True)
        assert "two.mp3" in await second.get_data(as_text=True)
    sounds = await _cart_sounds(client, cart_id)
    assert [row["title"] for row in sounds] == ["ohradiotomateoh.mp3", "two.mp3"]
    assert all(row["duration"] > 0 for row in sounds)
    assert await _cart_files(dbsession, cart_id) == ["ohradiotomateoh.mp3", "two.mp3"]
    queued = [call.args[0] for call in scheduler.queue_analysis.await_args_list]
    assert queued == [[row["id"]] for row in sounds]


async def test_cart_sounds_unreadable_name_refused(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    """
    Depuis multipart 1.3.1, `filename="son\\"` n'est plus lu comme un nom de
    fichier : le son arrive comme un champ de texte, qui n'est pas de l'UTF-8.
    """
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "cart-unreadable",
    )
    cart_id = await _new_cart(client, "Unreadable Cart")
    payload = (ASSETS / "ohradiotomateoh.mp3").read_bytes()
    boundary, body = encode_multipart(
        MultiDict(
            [
                ("sounds", FileStorage(BytesIO(payload), "one.mp3", "audio/mpeg")),
                ("sounds", FileStorage(BytesIO(payload), "son\\", "audio/mpeg")),
            ],
        ),
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    console = await client.post(
        f"/carts/{cart_id}/sounds.json",
        data=body,
        headers=headers,
    )
    assert console.status_code == 400, await console.get_data(as_text=True)
    assert (await console.get_json())["error"] == UNREADABLE
    assert await _cart_files(dbsession, cart_id) == []

    htmx = await client.post(
        f"/carts/{cart_id}/sounds",
        data=body,
        headers={**headers, "HX-Request": "true"},
    )
    assert htmx.status_code == 400, await htmx.get_data(as_text=True)
    assert await htmx.get_data(as_text=True) == UNREADABLE
    assert await _cart_files(dbsession, cart_id) == []
    assert await _cart_sounds(client, cart_id) == []
