# ruff: noqa: F811 - the fixtures of the bank come from test_cart_bank_titles
"""Move and copy sounds between carts, and apply a view's order (FON-70)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from radiotomate.models import (
    Cart,
    JournalEntry,
    ProgrammingVersion,
    RundownItem,
    Setting,
    Sound,
)
from radiotomate.services import bank_titles
from tests.scheduler.test_admin_json import ASSETS, _admin_client
from tests.scheduler.test_cart_bank_titles import ROTATION_A, beets, media  # noqa: F401

pytestmark = pytest.mark.usefixtures("media")


async def _client(app_configration, beets, dbsession, users_password, *, on=True):
    if on:
        dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
        await dbsession.commit()
    return await _admin_client(
        app_configration, beets, dbsession, users_password, "bacs-entre"
    )


async def _cart(client, title: str, mode: str = "playlist") -> dict:
    body = {"title": title, "mode": mode, "schedule_mode": "timed"}
    if mode == "relay":
        body["url"] = "https://radio.example/flux.mp3"
    created = await client.post("/carts.json", json=body)
    assert created.status_code == 201, await created.get_data(as_text=True)
    return (await created.get_json())["cart"]


async def _with_two_sounds(client, media: Path, title: str) -> tuple[dict, Path]:
    """A cart with a file of its own folder, and a title of the bank (FON-69)."""
    cart = await _cart(client, title)
    own = await client.post(
        f"/carts/{cart['id']}/sounds.json", json={"titles": [ROTATION_A]}
    )
    assert own.status_code == 201
    folder = media / "50-carts" / str(cart["id"])
    folder.mkdir(parents=True, exist_ok=True)
    mine = folder / "annonce.mp3"
    mine.write_bytes((ASSETS / "ohradiotomateoh.mp3").read_bytes())
    added = await client.post(
        f"/carts/{cart['id']}/sounds.json",
        json={"paths": [f"50-carts/{cart['id']}/annonce.mp3"]},
    )
    assert added.status_code == 201, await added.get_data(as_text=True)
    return (await added.get_json())["cart"], mine


async def _transfer(client, source: dict, target: dict, ids: list[int], *, copy: bool):
    return await client.post(
        f"/carts/{source['id']}/sounds/transfer.json",
        json={"ids": ids, "to": target["id"], "copy": copy},
    )


async def _journal(dbsession, gesture: str) -> list[JournalEntry]:
    dbsession.expire_all()
    return list(
        await dbsession.scalars(
            select(JournalEntry).where(JournalEntry.gesture == gesture)
        )
    )


async def test_switch_off_keeps_the_carts_apart(  # noqa: PLR0913
    raw_app,
    app_configration,
    beets,
    dbsession,
    users_password,
    media,
):
    client = await _client(app_configration, beets, dbsession, users_password, on=False)
    source = await _cart(client, "Soirée")
    target = await _cart(client, "Nuit")
    refused = await _transfer(client, source, target, [1], copy=True)
    assert refused.status_code == 409
    assert (await refused.get_json())["code"] == "bank_tidy_off"


async def test_a_copy_plays_the_same_file_in_both_carts(  # noqa: PLR0913
    raw_app,
    app_configration,
    beets,
    dbsession,
    users_password,
    media,
):
    client = await _client(app_configration, beets, dbsession, users_password)
    source, mine = await _with_two_sounds(client, media, "Soirée")
    target = await _cart(client, "Nuit")
    ids = [sound["id"] for sound in source["sounds"]]

    copied = await _transfer(client, source, target, ids, copy=True)
    assert copied.status_code == 200, await copied.get_data(as_text=True)
    payload = await copied.get_json()
    assert payload["done"] == 2
    assert [sound["path"] for sound in payload["target"]["sounds"]] == [
        sound["path"] for sound in source["sounds"]
    ]
    assert len(payload["cart"]["sounds"]) == 2
    (entry,) = await _journal(dbsession, "cart_copy")
    assert entry.titles == 2
    assert entry.details["to"] == {"id": target["id"], "title": "Nuit"}

    again = await (await _transfer(client, source, target, ids, copy=True)).get_json()
    assert again["done"] == 0
    assert {row["reason"] for row in again["skipped"]} == {"déjà dans le bac d'arrivée"}

    # The copy leaves the target: the file stays, the first cart plays it.
    copy_id = next(
        s["id"]
        for s in payload["target"]["sounds"]
        if s["path"].endswith("annonce.mp3")
    )
    gone = await client.delete(f"/carts/{target['id']}/sounds/{copy_id}.json")
    assert gone.status_code == 200
    assert mine.is_file()


async def test_a_move_takes_the_cart_s_own_file_along(  # noqa: PLR0913
    raw_app,
    app_configration,
    beets,
    dbsession,
    users_password,
    media,
):
    client = await _client(app_configration, beets, dbsession, users_password)
    source, mine = await _with_two_sounds(client, media, "Soirée")
    target = await _cart(client, "Nuit")
    third = await _cart(client, "Matin")
    own = next(s for s in source["sounds"] if s["path"].endswith("annonce.mp3"))
    borrowed = next(s for s in source["sounds"] if s["borrowed"])
    # A copy in a third cart follows the file it plays.
    await _transfer(client, source, third, [own["id"]], copy=True)

    moved = await _transfer(
        client, source, target, [own["id"], borrowed["id"]], copy=False
    )
    assert moved.status_code == 200, await moved.get_data(as_text=True)
    payload = await moved.get_json()
    assert payload["cart"]["sounds"] == []
    by_name = {Path(s["path"]).name: s for s in payload["target"]["sounds"]}
    assert by_name["annonce.mp3"]["path"] == f"50-carts/{target['id']}/annonce.mp3"
    assert by_name["orage - ete indien.mp3"]["path"] == ROTATION_A
    assert not mine.exists()
    assert (media / "50-carts" / str(target["id"]) / "annonce.mp3").is_file()
    assert (media / ROTATION_A).is_file()
    copy = await dbsession.scalar(select(Sound).where(Sound.cart_id == third["id"]))
    await dbsession.refresh(copy)
    assert Path(copy.path) == media / "50-carts" / str(target["id"]) / "annonce.mp3"
    (entry,) = await _journal(dbsession, "cart_move")
    assert entry.titles == 2


async def test_a_file_on_air_does_not_move(  # noqa: PLR0913
    raw_app,
    app_configration,
    beets,
    dbsession,
    users_password,
    media,
):
    client = await _client(app_configration, beets, dbsession, users_password)
    source, mine = await _with_two_sounds(client, media, "Soirée")
    target = await _cart(client, "Nuit")
    own = next(s for s in source["sounds"] if s["path"].endswith("annonce.mp3"))
    dbsession.add(ProgrammingVersion(id="pv-air", source="test", description="x"))
    await dbsession.flush()
    dbsession.add(
        RundownItem(
            id="ri-air",
            programming_version_id="pv-air",
            sequence=0,
            planned_at=datetime.now(),
            duration=4,
            kind="sound",
            when_mode="sequential",
            queue="carts",
            resource="Soirée",
            path=str(mine.resolve()),
            status="on_air",
        )
    )
    await dbsession.commit()
    payload = await (
        await _transfer(client, source, target, [own["id"]], copy=False)
    ).get_json()
    assert payload["done"] == 0
    assert payload["skipped"][0]["title"] == own["title"]
    assert mine.is_file()


@pytest.mark.parametrize("what", ["same", "relay", "stranger"])
async def test_a_wrong_transfer_is_refused(  # noqa: PLR0913
    raw_app,
    app_configration,
    beets,
    dbsession,
    users_password,
    media,
    what,
):
    client = await _client(app_configration, beets, dbsession, users_password)
    source, _ = await _with_two_sounds(client, media, "Soirée")
    ids = [sound["id"] for sound in source["sounds"]]
    if what == "same":
        response = await _transfer(client, source, source, ids, copy=True)
        assert response.status_code == 400
    elif what == "relay":
        relay = await _cart(client, "Flux", "relay")
        response = await _transfer(client, source, relay, ids, copy=True)
        assert response.status_code == 400
    else:
        other = await _cart(client, "Nuit")
        response = await _transfer(client, other, source, ids, copy=True)
        assert response.status_code == 404


async def test_the_order_of_a_view_is_noted_when_applied(  # noqa: PLR0913
    raw_app,
    app_configration,
    beets,
    dbsession,
    users_password,
    media,
):
    client = await _client(app_configration, beets, dbsession, users_password)
    source, _ = await _with_two_sounds(client, media, "Soirée")
    first, second = source["sounds"]
    path = f"/carts/{source['id']}/sounds/ranks.json"
    # A drag of today: nothing in the journal.
    dragged = await client.put(path, json={"ranks": [second["id"], first["id"]]})
    assert dragged.status_code == 200
    assert await _journal(dbsession, "cart_order") == []

    applied = await client.put(
        path, json={"ranks": [first["id"], second["id"]], "sorted_by": "title"}
    )
    assert applied.status_code == 200
    ranks = [sound["id"] for sound in (await applied.get_json())["cart"]["sounds"]]
    assert ranks == [first["id"], second["id"]]
    (entry,) = await _journal(dbsession, "cart_order")
    assert entry.details["sorted_by"] == "title"
    assert entry.titles == 2

    unknown = await client.put(
        path, json={"ranks": [first["id"], second["id"]], "sorted_by": "taille"}
    )
    assert unknown.status_code == 400


async def test_a_cart_listed_without_its_sounds_counts_a_title_gone(  # noqa: PLR0913
    raw_app,
    app_configration,
    beets,
    dbsession,
    users_password,
    media,
):
    from sqlalchemy import update as sql_update

    client = await _client(app_configration, beets, dbsession, users_password)
    source, _ = await _with_two_sounds(client, media, "Soirée")
    await dbsession.execute(sql_update(Sound).values(gain=-1.0, peak=-0.5))
    await dbsession.commit()
    dbsession.expire_all()
    ready = await Cart.from_id(dbsession, source["id"])
    assert ready.inactive_sounds_count == 0
    (media / ROTATION_A).unlink()
    dbsession.expire_all()
    cart = await Cart.from_id(dbsession, source["id"])
    assert cart.inactive_sounds_count == 1
    (listed,) = [c for c in await Cart.all(dbsession) if c.id == source["id"]]
    assert listed.inactive_sounds_count == 1
