"""
The session cookie follows ``interface.cookie_secure``, which
``deploy/scripts/init-radiotomate.sh`` sets from ``RT_COOKIE_SECURE``.
"""

from copy import deepcopy
from http.cookies import SimpleCookie

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.models import User
from tests.scheduler.test_studio_json import _interface_client


@pytest.fixture
async def credentials(dbsession: ormSession, users_password: str) -> dict:
    user = User(username="cookie")
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    return {"username": "cookie", "password": users_password}


# Behind the reverse proxy, the engine only sees HTTP: Quart-Auth warns, but the
# cookie must keep Secure whatever the scheme of the request.
@pytest.mark.filterwarnings("ignore:Secure cookies will be ignored:UserWarning")
@pytest.mark.parametrize("secure", [True, False], ids=["https", "http-only"])
@pytest.mark.parametrize(
    ("path", "body"), [("/login.json", "json"), ("/login", "form")]
)
async def test_login_cookie_follows_cookie_secure(  # noqa: PLR0913
    secure: bool,
    path: str,
    body: str,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    credentials: dict,
):
    config = deepcopy(app_configration)
    config["interface"] = dict(config.get("interface") or {})
    config["interface"]["cookie_secure"] = secure
    client = _interface_client(config, beets_integration)

    response = await client.post(path, **{body: credentials})
    jar = SimpleCookie()
    for header in response.headers.getlist("Set-Cookie"):
        jar.load(header)
    assert "session" in jar, response.headers
    assert bool(jar["session"]["secure"]) is secure

    # The proxy hands the cookie on over HTTP: the session must still hold.
    account = await client.get("/account.json")
    assert account.status_code == 200
