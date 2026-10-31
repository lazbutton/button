"""Too many failed logins block the address, whatever the account typed (ADR
0013). nginx hands on the client's address in X-Real-IP: the engine believes it
only from the station's network."""

import json

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.login_guard import LoginGuard
from radiotomate.interface import login
from radiotomate.models import User
from tests.scheduler.test_login_guard import Clock
from tests.scheduler.test_studio_json import _interface_client

# nginx, on Docker's network, then two clients it hands on.
NGINX = {"client": ("172.18.0.5", 41000)}
CLIENT = {"X-Real-IP": "203.0.113.7"}
OTHER = {"X-Real-IP": "198.51.100.4"}
WRONG = {"username": "animateur", "password": "pas-le-bon"}


@pytest.fixture(autouse=True)
def no_delay(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(login, "FAILURE_DELAY", 0)


@pytest.fixture
async def host(raw_app, dbsession: ormSession, users_password: str) -> dict:
    user = User(username="animateur")
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    return {"username": "animateur", "password": users_password}


async def test_six_wrong_passwords_block_the_address_not_the_account(
    app_configration: dict,
    beets_integration: BeetsIntegration,
    host: dict,
):
    client = _interface_client(app_configration, beets_integration)
    clock = Clock()
    client.app.extensions["login_guard"] = LoginGuard(clock=clock)

    async def log_in(credentials: dict, address: dict):
        return await client.post(
            "/login.json", json=credentials, headers=address, scope_base=NGINX
        )

    for attempt in range(4):
        wrong = {"username": f"compte-{attempt}", "password": "pas-le-bon"}
        assert (await log_in(wrong, CLIENT)).status_code == 401
    fifth = await log_in(WRONG, CLIENT)
    assert fifth.status_code == 429
    assert await fifth.get_json() == {"error": "too_many_attempts", "retry_in": 900}
    assert fifth.headers["Retry-After"] == "900"
    clock.advance(60)
    sixth = await log_in(WRONG, CLIENT)
    assert sixth.status_code == 429
    assert await sixth.get_json() == {"error": "too_many_attempts", "retry_in": 840}

    # The right password waits for the end of the block…
    assert (await log_in(host, CLIENT)).status_code == 429
    # … but the same account logs in from another address.
    assert (await log_in(host, OTHER)).status_code == 200

    clock.advance(840)
    after = await log_in(host, CLIENT)
    assert after.status_code == 200, await after.get_data(as_text=True)
    assert (await after.get_json())["username"] == "animateur"


async def test_a_client_cannot_choose_its_address(
    app_configration: dict,
    beets_integration: BeetsIntegration,
    host: dict,
):
    client = _interface_client(app_configration, beets_integration)
    # Straight to the engine, around nginx.
    direct = {"client": ("203.0.113.50", 52000)}
    for attempt in range(5):
        forged = {"X-Real-IP": f"192.0.2.{attempt}"}
        response = await client.post(
            "/login.json", json=WRONG, headers=forged, scope_base=direct
        )
    assert response.status_code == 429
    again = await client.post(
        "/login.json", json=host, headers=OTHER, scope_base=direct
    )
    assert again.status_code == 429
    # No one else is blocked under the forged addresses.
    through_nginx = await client.post(
        "/login.json", json=host, headers={"X-Real-IP": "192.0.2.0"}, scope_base=NGINX
    )
    assert through_nginx.status_code == 200


async def test_the_login_page_says_it_too(
    app_configration: dict,
    beets_integration: BeetsIntegration,
    host: dict,
):
    client = _interface_client(app_configration, beets_integration)
    htmx = {"HX-Request": "true"}
    for _ in range(4):
        response = await client.post("/login", form=WRONG, headers=htmx)
        assert response.status_code == 401
    blocked = await client.post("/login", form=WRONG, headers=htmx)
    assert blocked.status_code == 429
    message = json.loads(blocked.headers["HX-Trigger"])["radiotomateMessage"]
    assert message["text"] == "Trop d'essais. Réessaie dans 15 minutes."

    # One count for both routes.
    assert (await client.post("/login", form=host, headers=htmx)).status_code == 429
    assert (await client.post("/login.json", json=host)).status_code == 429
