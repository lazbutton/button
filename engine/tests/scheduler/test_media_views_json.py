"""The saved views of the bank's table, one account's own (FON-65)."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select

from radiotomate.models import BankView, Setting, User
from radiotomate.models import Session as LoginSession
from radiotomate.services import bank_titles
from tests.scheduler.test_studio_json import _interface_client, _login

JAZZ = {
    "ranking": "famille",
    "group": "jazz",
    "q": "",
    "sort": "year",
    "order": "desc",
    "columns": ["title", "artist", "year", "fiche"],
}


async def _account(dbsession, users_password: str, username: str) -> None:
    user = User(username=username)
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()


async def _client(app_configration, beets_integration, users_password, username):
    client = _interface_client(app_configration, beets_integration)
    await _login(client, username, users_password)
    return client


@pytest.fixture
async def switched_on(dbsession):
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
    await dbsession.commit()


async def test_views_ask_for_a_session(raw_app, app_configration, beets_integration):
    client = _interface_client(app_configration, beets_integration)
    assert (await client.get("/media/views.json")).status_code == 401


async def test_switch_off_keeps_the_views_closed(
    raw_app, app_configration, beets_integration, dbsession, users_password
):
    await _account(dbsession, users_password, "nadia")
    client = await _client(app_configration, beets_integration, users_password, "nadia")
    assert (await client.get("/media/views.json")).status_code == 409
    response = await client.post(
        "/media/views.json", json={"name": "Jazz", "state": JAZZ}
    )
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_tidy_off"


@pytest.mark.usefixtures("switched_on")
async def test_a_view_comes_back_at_the_next_login(
    raw_app, app_configration, beets_integration, dbsession, users_password
):
    await _account(dbsession, users_password, "nadia")
    client = await _client(app_configration, beets_integration, users_password, "nadia")
    created = await client.post(
        "/media/views.json", json={"name": " Jazz  à relire ", "state": JAZZ}
    )
    assert created.status_code == 201
    view = (await created.get_json())["view"]
    assert view["name"] == "Jazz à relire"
    assert view["state"] == JAZZ

    # Another computer: another session of the same account.
    other = await _client(app_configration, beets_integration, users_password, "nadia")
    views = (await (await other.get("/media/views.json")).get_json())["views"]
    assert [(row["id"], row["name"], row["state"]) for row in views] == [
        (view["id"], "Jazz à relire", JAZZ)
    ]


@pytest.mark.usefixtures("switched_on")
async def test_an_account_never_sees_another_ones_views(
    raw_app, app_configration, beets_integration, dbsession, users_password
):
    await _account(dbsession, users_password, "nadia")
    await _account(dbsession, users_password, "samir")
    nadia = await _client(app_configration, beets_integration, users_password, "nadia")
    samir = await _client(app_configration, beets_integration, users_password, "samir")
    created = await nadia.post(
        "/media/views.json", json={"name": "Jazz", "state": JAZZ}
    )
    view_id = (await created.get_json())["view"]["id"]

    assert (await (await samir.get("/media/views.json")).get_json())["views"] == []
    path = f"/media/views/{view_id}.json"
    assert (await samir.put(path, json={"name": "À moi"})).status_code == 404
    assert (await samir.delete(path)).status_code == 404
    # The same name is free for another account.
    taken = await samir.post("/media/views.json", json={"name": "Jazz", "state": JAZZ})
    assert taken.status_code == 201
    assert len((await (await nadia.get("/media/views.json")).get_json())["views"]) == 1


@pytest.mark.usefixtures("switched_on")
async def test_a_view_is_renamed_changed_and_deleted(
    raw_app, app_configration, beets_integration, dbsession, users_password
):
    await _account(dbsession, users_password, "nadia")
    client = await _client(app_configration, beets_integration, users_password, "nadia")
    first = await client.post("/media/views.json", json={"name": "Jazz", "state": JAZZ})
    view_id = (await first.get_json())["view"]["id"]
    await client.post("/media/views.json", json={"name": "Nuit", "state": {}})

    same = await client.post("/media/views.json", json={"name": "Jazz", "state": {}})
    assert same.status_code == 409
    assert (await same.get_json())["field"] == "name"
    clash = await client.put(f"/media/views/{view_id}.json", json={"name": "Nuit"})
    assert clash.status_code == 409

    state = {**JAZZ, "columns": ["artist", "title"], "group": ""}
    changed = await client.put(
        f"/media/views/{view_id}.json",
        json={"name": "Jazz sans famille", "state": state},
    )
    assert changed.status_code == 200
    assert (await changed.get_json())["view"]["state"] == state
    # Ranged by the station's tags, their column shown (FON-74).
    tagged = {
        **JAZZ,
        "ranking": "etiquette",
        "group": "nuit",
        "columns": ["title", "etiquettes"],
    }
    kept = await client.put(f"/media/views/{view_id}.json", json={"state": tagged})
    assert kept.status_code == 200, await kept.get_data()
    assert (await kept.get_json())["view"]["state"] == tagged

    assert (await client.delete(f"/media/views/{view_id}.json")).status_code == 200
    views = (await (await client.get("/media/views.json")).get_json())["views"]
    assert [row["name"] for row in views] == ["Nuit"]
    assert views[0]["state"]["columns"][0] == "title"


@pytest.mark.usefixtures("switched_on")
@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "state": JAZZ},
        {"name": "x" * 61, "state": JAZZ},
        {"name": "Jazz", "state": "jazz"},
        {"name": "Jazz", "state": {**JAZZ, "ranking": "genre"}},
        {"name": "Jazz", "state": {**JAZZ, "sort": "size"}},
        {"name": "Jazz", "state": {**JAZZ, "columns": ["artist"]}},
        {"name": "Jazz", "state": {**JAZZ, "columns": ["title", "title"]}},
        {"name": "Jazz", "state": {**JAZZ, "columns": ["title", "taille"]}},
    ],
)
async def test_a_wrong_view_is_refused(  # noqa: PLR0913
    raw_app, app_configration, beets_integration, dbsession, users_password, body
):
    await _account(dbsession, users_password, "nadia")
    client = await _client(app_configration, beets_integration, users_password, "nadia")
    response = await client.post("/media/views.json", json=body)
    assert response.status_code == 400
    assert (await response.get_json())["code"] == "validation_error"


@pytest.mark.usefixtures("switched_on")
async def test_the_views_leave_with_their_account(
    raw_app, app_configration, beets_integration, dbsession, users_password
):
    await _account(dbsession, users_password, "nadia")
    client = await _client(app_configration, beets_integration, users_password, "nadia")
    await client.post("/media/views.json", json={"name": "Jazz", "state": JAZZ})
    user = await User.from_username(dbsession, "nadia")
    await dbsession.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    await User.delete(dbsession, user.id)
    await dbsession.commit()
    assert await dbsession.scalar(select(func.count()).select_from(BankView)) == 0
