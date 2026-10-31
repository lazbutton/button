from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainConflict
from radiotomate.enums import RundownStatus
from radiotomate.interface_app import app_factory as interface_factory
from radiotomate.models import Sound
from radiotomate.models.execution import ProgrammingVersion, RundownItem
from radiotomate.scheduler.execution import (
    DESK_ORIGIN,
    attach_desk_pins,
    delete_desk_item,
    insert_desk_item,
    item_to_payload,
    reorder_desk_items,
    replace_forecast_items,
)
from radiotomate.scheduler_api import Scheduler
from tests.scheduler.test_admin_json import _admin_client


async def test_replace_forecast_keeps_desk_pins(dbsession: ormSession):
    dbsession.add(
        ProgrammingVersion(id="pv-desk-keep", source="test", description="desk")
    )
    await dbsession.flush()
    later = datetime.now() + timedelta(minutes=10)
    dbsession.add(
        RundownItem(
            id="ri-desk-pin",
            programming_version_id="pv-desk-keep",
            sequence=0,
            planned_at=later,
            duration=12,
            kind="son",
            when_mode="sequential",
            queue="carts",
            resource="Pin pupitre",
            path="/media/10-rotation/pin.mp3",
            status=RundownStatus.PLANNED.value,
            origin=DESK_ORIGIN,
        )
    )
    dbsession.add(
        RundownItem(
            id="ri-clock-planned",
            programming_version_id="pv-desk-keep",
            sequence=1,
            planned_at=later,
            duration=180,
            kind="musique",
            when_mode="sequential",
            queue="autodj",
            resource="Titre horloge",
            status=RundownStatus.PLANNED.value,
            origin="clock",
        )
    )
    await dbsession.commit()
    version = await dbsession.get(ProgrammingVersion, "pv-desk-keep")
    await replace_forecast_items(dbsession, version, [], now=datetime.now())
    await dbsession.commit()
    assert await dbsession.get(RundownItem, "ri-desk-pin") is not None
    assert await dbsession.get(RundownItem, "ri-clock-planned") is None


async def test_delete_clock_planned_item(dbsession: ormSession):
    dbsession.add(
        ProgrammingVersion(id="pv-clock-delete", source="test", description="del")
    )
    await dbsession.flush()
    dbsession.add(
        RundownItem(
            id="ri-clock-delete",
            programming_version_id="pv-clock-delete",
            sequence=0,
            planned_at=datetime.now() + timedelta(minutes=12),
            duration=180,
            kind="musique",
            when_mode="sequential",
            queue="autodj",
            resource="BUTTON Test — Rotation Recette",
            path="/media/10-rotation/BUTTON_Test_-_Rotation_Recette.mp3",
            status=RundownStatus.PLANNED.value,
            origin="clock",
        )
    )
    await dbsession.commit()
    await delete_desk_item(dbsession, "ri-clock-delete")
    assert await dbsession.get(RundownItem, "ri-clock-delete") is None


async def test_delete_hard_anchor_conflicts(dbsession: ormSession):
    dbsession.add(
        ProgrammingVersion(id="pv-desk-anchor", source="test", description="anchor")
    )
    await dbsession.flush()
    dbsession.add(
        RundownItem(
            id="ri-hard-anchor",
            programming_version_id="pv-desk-anchor",
            sequence=0,
            planned_at=datetime.now() + timedelta(minutes=5),
            duration=20,
            kind="pub",
            when_mode="anchored",
            queue="carts",
            resource="Pub :20",
            status=RundownStatus.PLANNED.value,
            origin="clock",
        )
    )
    await dbsession.commit()
    with pytest.raises(DomainConflict) as caught:
        await delete_desk_item(dbsession, "ri-hard-anchor")
    assert caught.value.status_code == 409
    assert await dbsession.get(RundownItem, "ri-hard-anchor") is not None


async def _reorder_version(dbsession: ormSession, version_id: str) -> None:
    dbsession.add(
        ProgrammingVersion(id=version_id, source="test", description="reorder")
    )
    await dbsession.flush()


def _reorder_row(  # noqa: PLR0913
    item_id: str,
    version_id: str,
    start: datetime,
    duration: float,
    *,
    status: str = RundownStatus.PLANNED.value,
    origin: str = DESK_ORIGIN,
) -> RundownItem:
    return RundownItem(
        id=item_id,
        programming_version_id=version_id,
        sequence=0,
        planned_at=start,
        duration=duration,
        kind="son",
        when_mode="sequential",
        queue="carts",
        resource=item_id,
        path=f"/media/10-rotation/{item_id}.mp3",
        status=status,
        origin=origin,
    )


async def test_reorder_packs_from_the_earliest_start(dbsession: ormSession):
    await _reorder_version(dbsession, "pv-reorder-future")
    later = (datetime.now() + timedelta(minutes=5)).replace(microsecond=0)
    dbsession.add_all(
        [
            _reorder_row("ri-song", "pv-reorder-future", later, 180),
            _reorder_row(
                "ri-jingle", "pv-reorder-future", later + timedelta(minutes=3), 4
            ),
        ]
    )
    await dbsession.commit()
    await reorder_desk_items(dbsession, ["ri-jingle", "ri-song"])
    jingle = await dbsession.get(RundownItem, "ri-jingle")
    song = await dbsession.get(RundownItem, "ri-song")
    assert jingle.planned_at == later
    assert song.planned_at == later + timedelta(seconds=4)


async def test_reorder_never_packs_into_the_past(dbsession: ormSession):
    """A short line moved above one that started 40 s ago starts now: it stays in
    the antenna file, and the expiry of past desk lines keeps it."""
    await _reorder_version(dbsession, "pv-reorder-past")
    now = datetime.now()
    dbsession.add_all(
        [
            _reorder_row(
                "ri-started", "pv-reorder-past", now - timedelta(seconds=40), 60
            ),
            _reorder_row("ri-short", "pv-reorder-past", now + timedelta(seconds=20), 4),
        ]
    )
    await dbsession.commit()
    before = datetime.now()
    await reorder_desk_items(dbsession, ["ri-short", "ri-started"])
    short = await dbsession.get(RundownItem, "ri-short")
    started = await dbsession.get(RundownItem, "ri-started")
    assert short.planned_at >= before
    assert started.planned_at == short.planned_at + timedelta(seconds=4)

    await attach_desk_pins(dbsession, {"items": []})
    assert await dbsession.get(RundownItem, "ri-short") is not None


async def test_reorder_waits_for_the_title_on_air(dbsession: ormSession):
    await _reorder_version(dbsession, "pv-reorder-air")
    now = datetime.now().replace(microsecond=0)
    on_air = _reorder_row(
        "ri-on-air",
        "pv-reorder-air",
        now - timedelta(seconds=10),
        180,
        status=RundownStatus.ON_AIR.value,
        origin="clock",
    )
    on_air.started_at = now - timedelta(seconds=10)
    dbsession.add_all(
        [
            on_air,
            _reorder_row("ri-early", "pv-reorder-air", now - timedelta(seconds=5), 20),
            _reorder_row("ri-next", "pv-reorder-air", now + timedelta(seconds=15), 4),
        ]
    )
    await dbsession.commit()
    await reorder_desk_items(dbsession, ["ri-next", "ri-early"])
    following = await dbsession.get(RundownItem, "ri-next")
    early = await dbsession.get(RundownItem, "ri-early")
    assert following.planned_at == now + timedelta(seconds=170)
    assert early.planned_at == now + timedelta(seconds=174)


async def test_reorder_behind_a_started_line_keeps_its_start(dbsession: ormSession):
    """Two lines swapped behind one that has already started: it keeps its start,
    and the others follow its end. Nothing slides at each gesture."""
    await _reorder_version(dbsession, "pv-reorder-keep")
    now = datetime.now().replace(microsecond=0)
    dbsession.add_all(
        [
            _reorder_row("ri-head", "pv-reorder-keep", now - timedelta(seconds=40), 60),
            _reorder_row(
                "ri-second", "pv-reorder-keep", now + timedelta(seconds=20), 180
            ),
            _reorder_row(
                "ri-third", "pv-reorder-keep", now + timedelta(seconds=200), 4
            ),
        ]
    )
    await dbsession.commit()
    await reorder_desk_items(dbsession, ["ri-head", "ri-third", "ri-second"])
    head = await dbsession.get(RundownItem, "ri-head")
    third = await dbsession.get(RundownItem, "ri-third")
    second = await dbsession.get(RundownItem, "ri-second")
    assert head.planned_at == now - timedelta(seconds=40)
    assert third.planned_at == now + timedelta(seconds=20)
    assert second.planned_at == now + timedelta(seconds=24)


async def test_insert_above_a_started_head_starts_now(dbsession: ormSession):
    """Placed above a line still to come, a line starts half a second before it.
    Above the head of the file, already started, it starts now: half a second
    before the head, it would end before now, leave the antenna file, and the
    expiry of past desk lines would drop it."""
    await _reorder_version(dbsession, "pv-insert-above")
    now = datetime.now()
    dbsession.add_all(
        [
            _reorder_row("ri-head", "pv-insert-above", now - timedelta(seconds=10), 60),
            _reorder_row(
                "ri-later", "pv-insert-above", now + timedelta(seconds=50), 60
            ),
        ]
    )
    await dbsession.commit()
    above_later = await insert_desk_item(
        dbsession,
        {"path": "/media/10-rotation/above-later.mp3", "before_id": "ri-later"},
    )
    assert above_later.planned_at == now + timedelta(seconds=49.5)
    before = datetime.now()
    above_head = await insert_desk_item(
        dbsession,
        {"path": "/media/10-rotation/above-head.mp3", "before_id": "ri-head"},
    )
    assert above_head.planned_at >= before


async def test_insert_above_the_next_line_keeps_its_lead(dbsession: ormSession):
    """The title on air started 2 s late, too little for realign_rundown: the next
    line is still planned 2 s before its end. A line placed above that next line
    stays above it. Placed above the title on air, it waits for its end."""
    await _reorder_version(dbsession, "pv-insert-next")
    now = datetime.now().replace(microsecond=0)
    on_air = _reorder_row(
        "ri-on-air",
        "pv-insert-next",
        now - timedelta(seconds=12),
        60,
        status=RundownStatus.ON_AIR.value,
        origin="clock",
    )
    on_air.started_at = now - timedelta(seconds=10)
    dbsession.add_all(
        [
            on_air,
            _reorder_row(
                "ri-next",
                "pv-insert-next",
                now + timedelta(seconds=48),
                180,
                origin="clock",
            ),
        ]
    )
    await dbsession.commit()
    above_next = await insert_desk_item(
        dbsession,
        {"path": "/media/10-rotation/above-next.mp3", "before_id": "ri-next"},
    )
    assert above_next.planned_at == now + timedelta(seconds=47.5)
    above_air = await insert_desk_item(
        dbsession,
        {"path": "/media/10-rotation/above-air.mp3", "before_id": "ri-on-air"},
    )
    assert above_air.planned_at == now + timedelta(seconds=50)


async def test_insert_waits_for_the_title_on_air(dbsession: ormSession):
    await _reorder_version(dbsession, "pv-insert-air")
    now = datetime.now().replace(microsecond=0)
    on_air = _reorder_row(
        "ri-on-air",
        "pv-insert-air",
        now - timedelta(seconds=10),
        180,
        status=RundownStatus.ON_AIR.value,
        origin="clock",
    )
    on_air.started_at = now - timedelta(seconds=10)
    dbsession.add(on_air)
    await dbsession.commit()
    line = await insert_desk_item(dbsession, {"path": "/media/10-rotation/next.mp3"})
    assert line.planned_at == now + timedelta(seconds=170)


async def test_insert_after_an_overrun_starts_now(dbsession: ormSession):
    """The title on air has outlasted its planned length: a line put after it
    starts now, not at the end that has already passed."""
    await _reorder_version(dbsession, "pv-insert-overrun")
    now = datetime.now()
    on_air = _reorder_row(
        "ri-overrun",
        "pv-insert-overrun",
        now - timedelta(seconds=200),
        180,
        status=RundownStatus.ON_AIR.value,
        origin="clock",
    )
    on_air.started_at = now - timedelta(seconds=200)
    dbsession.add(on_air)
    await dbsession.commit()
    before = datetime.now()
    line = await insert_desk_item(dbsession, {"path": "/media/10-rotation/next.mp3"})
    assert line.planned_at >= before


async def _shown_clock_ids(dbsession: ormSession) -> list[str]:
    """Clock lines of the antenna file, once the desk lines have hidden theirs."""
    rows = await dbsession.scalars(
        select(RundownItem)
        .where(RundownItem.origin != DESK_ORIGIN)
        .order_by(RundownItem.planned_at)
    )
    forecast = {"items": [item_to_payload(row) for row in rows]}
    payload = await attach_desk_pins(dbsession, forecast)
    return [item["id"] for item in payload["items"] if item["origin"] != DESK_ORIGIN]


@pytest.mark.parametrize("removal", ["suppress_at", "replace_at"])
async def test_reorder_onto_a_removed_line_time_keeps_it_shown(
    dbsession: ormSession, removal: str
):
    """B is removed from A B C D, or replaced by a desk line. Reordered as A D C,
    D takes the start of B, to the microsecond: the removal hides B only."""
    await _reorder_version(dbsession, "pv-reorder-hidden")
    start = datetime.now() + timedelta(minutes=5)
    dbsession.add_all(
        [
            _reorder_row(
                item_id,
                "pv-reorder-hidden",
                start + timedelta(seconds=30 * index),
                30,
                origin="clock",
            )
            for index, item_id in enumerate(["ri-a", "ri-b", "ri-c", "ri-d"])
        ]
    )
    await dbsession.commit()
    removed_at = (start + timedelta(seconds=30)).isoformat()
    if removal == "suppress_at":
        await insert_desk_item(dbsession, {"suppress_at": removed_at})
    else:
        await insert_desk_item(
            dbsession,
            {"path": "/media/10-rotation/ri-b.mp3", "replace_at": removed_at},
        )
    assert await _shown_clock_ids(dbsession) == ["ri-a", "ri-c", "ri-d"]

    await reorder_desk_items(dbsession, ["ri-a", "ri-d", "ri-c"])
    moved = await dbsession.get(RundownItem, "ri-d")
    assert moved.planned_at.isoformat() == removed_at
    assert await _shown_clock_ids(dbsession) == ["ri-a", "ri-d", "ri-c"]


async def test_removal_without_ids_still_hides_by_time(dbsession: ormSession):
    """A removal posted by an older engine knows no ids: it hides by time."""
    await _reorder_version(dbsession, "pv-hidden-older")
    start = datetime.now() + timedelta(minutes=5)
    removed = start + timedelta(seconds=30)
    pin = _reorder_row("ri-pin", "pv-hidden-older", removed, 0)
    pin.path = None
    pin.details = {"suppress_at": removed.isoformat()}
    dbsession.add_all(
        [
            _reorder_row("ri-kept", "pv-hidden-older", start, 30, origin="clock"),
            _reorder_row("ri-removed", "pv-hidden-older", removed, 30, origin="clock"),
            pin,
        ]
    )
    await dbsession.commit()
    assert await _shown_clock_ids(dbsession) == ["ri-kept"]


async def test_desk_insert_survives_preview_refresh(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
):
    _ = jingles_cart
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "desk-insert-admin",
    )
    created = await client.post(
        "/autodj/conducteur/items.json",
        json={
            "path": "/media/10-rotation/pupitre-pin.mp3",
            "title": "Pin pupitre",
            "artist": "Desk",
            "kind": "son",
            "duration": 12,
        },
    )
    assert created.status_code == 200, await created.get_data(as_text=True)
    payload = await created.get_json()
    desk_hits = [
        item
        for item in payload["items"]
        if item.get("origin") == DESK_ORIGIN
        and item.get("path") == "/media/10-rotation/pupitre-pin.mp3"
    ]
    assert desk_hits, payload["items"][:6]
    pin_id = desk_hits[0]["id"]

    refresh = await client.post("/autodj/conducteur.json", json={})
    assert refresh.status_code == 200
    refreshed = await refresh.get_json()
    assert any(item.get("id") == pin_id for item in refreshed["items"])

    preview = await client.get("/autodj/conducteur.json?horizon=30")
    assert preview.status_code == 200
    shown = await preview.get_json()
    assert any(item.get("id") == pin_id for item in shown["items"])


async def test_desk_delete_anchor_json_409(
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
        "desk-anchor-admin",
    )
    dbsession.add(
        ProgrammingVersion(id="pv-desk-http-anchor", source="test", description="a")
    )
    await dbsession.flush()
    dbsession.add(
        RundownItem(
            id="ri-http-anchor",
            programming_version_id="pv-desk-http-anchor",
            sequence=0,
            planned_at=datetime.now() + timedelta(minutes=8),
            duration=20,
            kind="pub",
            when_mode="anchored",
            queue="carts",
            resource="Pub ancrée",
            status=RundownStatus.PLANNED.value,
            origin="clock",
        )
    )
    await dbsession.commit()
    response = await client.delete("/autodj/conducteur/items/ri-http-anchor.json")
    assert response.status_code == 409


async def test_skip_keeps_following_desk_pins(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "desk-skip-admin",
    )
    await insert_desk_item(
        dbsession,
        {
            "path": "/media/10-rotation/after-skip.mp3",
            "title": "Après skip",
            "artist": "Desk",
            "kind": "son",
            "duration": 9,
        },
    )
    pin = await dbsession.scalar(
        select(RundownItem).where(
            RundownItem.origin == DESK_ORIGIN,
            RundownItem.path == "/media/10-rotation/after-skip.mp3",
        )
    )
    assert pin is not None
    pin_id = pin.id

    Scheduler.reset_instance()
    iface = interface_factory(app_configration, False, beets_integration)
    Scheduler.init(app_configration, iface, demo=True)
    try:
        async with iface.test_app():
            client = iface.test_client()
            login = await client.post(
                "/login",
                form={"username": "desk-skip-admin", "password": users_password},
            )
            assert login.status_code == 302
            skipped = await client.delete("/live.json")
            assert skipped.status_code == 200, await skipped.get_data(as_text=True)
            shown = await (await client.get("/autodj/conducteur.json")).get_json()
            assert any(item.get("id") == pin_id for item in shown["items"])
    finally:
        Scheduler.reset_instance()


async def test_desk_insert_resolves_cart_sound(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
):
    sound = (await dbsession.scalars(select(Sound).limit(1))).first()
    assert sound is not None
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "desk-sound-admin",
    )
    created = await client.post(
        "/autodj/conducteur/items.json",
        json={
            "path": str(sound.path),
            "title": sound.title,
            "kind": "jingle",
            "duration": sound.duration,
        },
    )
    assert created.status_code == 200, await created.get_data(as_text=True)
    payload = await created.get_json()
    hit = next(item for item in payload["items"] if item.get("origin") == DESK_ORIGIN)
    assert hit["sound_id"] == sound.id
    assert hit["cart_id"] == jingles_cart.id
