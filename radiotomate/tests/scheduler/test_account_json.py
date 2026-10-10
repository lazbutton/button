from radiotomate.beets import BeetsIntegration
from radiotomate.models import User
from tests.scheduler.test_studio_json import _interface_client, _login


async def test_account_json_requires_login(
    app_configration: dict,
    beets_integration: BeetsIntegration,
):
    client = _interface_client(app_configration, beets_integration)
    response = await client.get("/account.json")
    assert response.status_code == 401
    assert (await response.get_json())["error"] == "unauthenticated"


async def test_account_json_returns_permissions(
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession,
    users_password: str,
):
    user = User(username="animateur-json")
    user.update_password(users_password)
    user.update_permissions_map({"live": True, "carts": True})
    dbsession.add(user)
    await dbsession.commit()

    client = _interface_client(app_configration, beets_integration)
    await _login(client, "animateur-json", users_password)
    payload = await (await client.get("/account.json")).get_json()
    assert payload["username"] == "animateur-json"
    assert payload["permissions"]["admin"] is False
    assert payload["permissions"]["live"] is True
    assert payload["permissions"]["carts"] is True
    assert payload["permissions"]["autodj"] is False
    assert payload["permissions"]["stream"] is False
