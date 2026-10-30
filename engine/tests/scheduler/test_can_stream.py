import pytest
from quart.testing import QuartClient
from sqlalchemy.orm import Session as ormSession

from radiotomate.models import Setting, User
from radiotomate.services.stream_token import SETTING_ACCOUNT_PASSWORD


async def test_can_stream(
    client: QuartClient,
    users_password: str,
    user_can_stream: User,
    auth: dict,
):
    result = await client.post(
        "/can_stream",
        json={
            # this must match the object passed by liquidsoap to input.harbor's "auth"
            "user": user_can_stream.username,
            "password": users_password,
        },
        headers=auth,
    )
    result_text = (await result.data).decode()
    assert result.status_code == 200, "got non-OK response:" + result_text


async def test_cannot_stream(
    client: QuartClient,
    users_password: str,
    user_can_stream: User,
    user_no_permission: User,
    auth: dict,
):
    result = await client.post(
        "/can_stream",
        json={
            "user": user_can_stream.username,
            "password": users_password + "nope",
        },
        headers=auth,
    )
    result_text = (await result.data).decode()
    assert result.status_code != 200, "got OK on a wrong password:" + result_text

    result = await client.post(
        "/can_stream",
        json={
            "user": user_no_permission.username,
            "password": users_password,
        },
        headers=auth,
    )
    result_text = (await result.data).decode()
    assert result.status_code != 200, (
        "got OK for a user that has no permissions" + result_text
    )


async def _post_login(client: QuartClient, auth: dict, username: str, secret: str):
    return await client.post(
        "/can_stream",
        json={"user": username, "password": secret},
        headers=auth,
    )


async def test_can_stream_with_token(
    client: QuartClient,
    dbsession: ormSession,
    user_can_stream: User,
    auth: dict,
):
    token = user_can_stream.renew_stream_token()
    await dbsession.commit()

    result = await _post_login(client, auth, user_can_stream.username, token)
    assert result.status_code == 200, await result.get_data(as_text=True)


async def test_wrong_token_refused(
    client: QuartClient,
    dbsession: ormSession,
    user_can_stream: User,
    user_no_permission: User,
    auth: dict,
):
    token = user_can_stream.renew_stream_token()
    other = user_no_permission.renew_stream_token()
    await dbsession.commit()

    for username, secret in (
        (user_can_stream.username, token[:-1] + ("0" if token[-1] != "0" else "1")),
        (user_can_stream.username, other),
        (user_no_permission.username, token),
        # the right token, but no Stream permission
        (user_no_permission.username, other),
    ):
        result = await _post_login(client, auth, username, secret)
        assert result.status_code == 401, (
            username,
            await result.get_data(as_text=True),
        )


async def test_renewed_token_cuts_the_old_one(
    client: QuartClient,
    dbsession: ormSession,
    user_can_stream: User,
    auth: dict,
):
    old = user_can_stream.renew_stream_token()
    await dbsession.commit()
    new = user_can_stream.renew_stream_token()
    await dbsession.commit()
    assert new != old

    assert (await _post_login(client, auth, "liveDJ", old)).status_code == 401
    assert (await _post_login(client, auth, "liveDJ", new)).status_code == 200


@pytest.mark.parametrize(
    ("value", "status"),
    [(None, 200), ("1", 200), ("true", 200), ("0", 401), ("false", 401), ("Off", 401)],
)
async def test_account_password_follows_the_setting(  # noqa: PLR0913
    client: QuartClient,
    dbsession: ormSession,
    users_password: str,
    user_can_stream: User,
    auth: dict,
    value: str | None,
    status: int,
):
    token = user_can_stream.renew_stream_token()
    if value is not None:
        await Setting.upsert(dbsession, SETTING_ACCOUNT_PASSWORD, value)
    await dbsession.commit()

    result = await _post_login(client, auth, "liveDJ", users_password)
    assert result.status_code == status, await result.get_data(as_text=True)
    # the token goes through either way
    assert (await _post_login(client, auth, "liveDJ", token)).status_code == 200
