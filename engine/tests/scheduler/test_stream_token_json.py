import re
from datetime import datetime

from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.models import User
from tests.scheduler.test_studio_json import _interface_client, _login

PARIS_MINUTE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d[+-]\d\d:\d\d")


async def _account(
    dbsession: ormSession, username: str, password: str, permissions: dict
) -> User:
    user = User(username=username)
    user.update_password(password)
    user.update_permissions_map(permissions)
    dbsession.add(user)
    await dbsession.commit()
    return user


async def test_stream_token_requires_login(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
):
    client = _interface_client(app_configration, beets_integration)
    for path in ("/users/me/stream-token.json", "/users/1/stream-token.json"):
        for response in (await client.get(path), await client.post(path)):
            assert response.status_code == 401, path
            assert (await response.get_json())["error"] == "unauthenticated"


async def test_own_stream_token_shown_once_and_stored_hashed(
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    user = await _account(
        dbsession, "animateur-token", users_password, {"stream": True}
    )
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "animateur-token", users_password)

    path = "/users/me/stream-token.json"
    assert await (await client.get(path)).get_json() == {"created_at": None}

    created = await client.post(path)
    assert created.status_code == 200, await created.get_data(as_text=True)
    assert created.headers["Cache-Control"] == "no-store"
    payload = await created.get_json()
    token = payload["token"]
    assert re.fullmatch(r"[0-9a-f]{32}", token)
    assert PARIS_MINUTE.fullmatch(payload["created_at"])
    # afterwards, only the date: the token can't be read again
    assert await (await client.get(path)).get_json() == {
        "created_at": payload["created_at"]
    }

    await dbsession.refresh(user)
    assert token not in (user.stream_token_hash, user.password)
    assert user.check_stream_token(token)
    assert isinstance(user.stream_token_created_at, datetime)

    renewed = await (await client.post(path)).get_json()
    assert renewed["token"] != token
    await dbsession.refresh(user)
    assert not user.check_stream_token(token)
    assert user.check_stream_token(renewed["token"])


async def test_admin_renews_the_token_of_another_account(
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    await _account(dbsession, "admin-token", users_password, {"admin": True})
    dj = await _account(dbsession, "dj-token", users_password, {"stream": True})
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "admin-token", users_password)

    path = f"/users/{dj.id}/stream-token.json"
    assert await (await client.get(path)).get_json() == {"created_at": None}
    created = await client.post(path)
    assert created.status_code == 200, await created.get_data(as_text=True)
    payload = await created.get_json()
    assert (await (await client.get(path)).get_json())["created_at"] == payload[
        "created_at"
    ]
    await dbsession.refresh(dj)
    assert dj.check_stream_token(payload["token"])

    missing = await client.post("/users/999999/stream-token.json")
    assert missing.status_code == 404


async def test_only_an_admin_handles_the_token_of_another_account(
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    await _account(dbsession, "dj-a", users_password, {"stream": True})
    other = await _account(dbsession, "dj-b", users_password, {"stream": True})
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "dj-a", users_password)

    path = f"/users/{other.id}/stream-token.json"
    for response in (await client.get(path), await client.post(path)):
        assert response.status_code == 403
        assert (await response.get_json())["error"] == "forbidden"
    await dbsession.refresh(other)
    assert other.stream_token_hash is None
