import asyncio
import logging

from quart import (
    Blueprint,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from quart_auth import current_user, login_user, logout_user
from werkzeug.exceptions import BadRequest, TooManyRequests, Unauthorized

from radiotomate.auth import RadiotomateAuth
from radiotomate.domain.login_guard import (
    LoginGuard,
    client_address,
    too_many_attempts_message,
)
from radiotomate.models import Session, User

_log = logging.getLogger(__name__)

blueprint = Blueprint("login", __name__, template_folder="templates")

# Each failed try waits that long, in seconds: good luck, bruteforcers !
FAILURE_DELAY = 1


@blueprint.record_once
def _start_guard(state):
    # One guard per app, in memory: a restart forgets every address.
    state.app.extensions["login_guard"] = LoginGuard()


def _guard() -> LoginGuard:
    return current_app.extensions["login_guard"]


def _address() -> str:
    # nginx hands on the client's address in X-Real-IP.
    return client_address(request.remote_addr, request.headers.get("X-Real-IP"))


async def _failed(address: str) -> int:
    """Counts a failed try, then says how long the address is now blocked."""
    _guard().failed(address)
    await asyncio.sleep(FAILURE_DELAY)
    retry_in = _guard().retry_in(address)
    if retry_in:
        _log.warning("login: %s blocked for %d s", address, retry_in)
    return retry_in


def _too_many_attempts(retry_in: int):
    return (
        jsonify({"error": "too_many_attempts", "retry_in": retry_in}),
        429,
        {"Retry-After": str(retry_in)},
    )


@blueprint.get("/login")
async def index():
    return await render_template("login/index.jinja")


@blueprint.post("/login")
async def log_in():
    address = _address()
    if retry_in := _guard().retry_in(address):
        raise TooManyRequests(too_many_attempts_message(retry_in))
    form = await request.form
    username = form.get("username")
    password = form.get("password")

    if not username:
        raise BadRequest("Please provide an username")
    if not password:
        raise BadRequest("Please provide a password")

    user = await User.check(g.dbsession, username, password)
    if not user:
        if retry_in := await _failed(address):
            raise TooManyRequests(too_many_attempts_message(retry_in))
        raise Unauthorized("Incorrect username or password")
    session = Session(
        user_id=user.id,
        user_agent=request.headers.get("User-Agent"),
        latest_address=request.remote_addr,
    )
    g.dbsession.add(session)
    await g.dbsession.commit()

    login_user(RadiotomateAuth(session.id))
    return (
        "",
        302,
        {
            "HX-Redirect": url_for("home.index"),
        },
    )


@blueprint.post("/login.json")
async def log_in_json():
    address = _address()
    if retry_in := _guard().retry_in(address):
        return _too_many_attempts(retry_in)
    data = await request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return jsonify({"error": "unauthenticated"}), 401

    user = await User.check(g.dbsession, username, password)
    if not user:
        if retry_in := await _failed(address):
            return _too_many_attempts(retry_in)
        return jsonify({"error": "unauthenticated"}), 401
    session = Session(
        user_id=user.id,
        user_agent=request.headers.get("User-Agent"),
        latest_address=request.remote_addr,
    )
    g.dbsession.add(session)
    await g.dbsession.commit()
    login_user(RadiotomateAuth(session.id))
    return jsonify(
        {
            "ok": True,
            "username": user.username,
            "permissions": user.permissions_payload(),
        },
    )


@blueprint.route("/logout")
async def log_out():
    current_user.session.active = False
    await g.dbsession.commit()
    logout_user()
    return redirect(url_for("login.log_in"))
