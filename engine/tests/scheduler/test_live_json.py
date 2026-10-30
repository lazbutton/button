import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.interface import live as live_mod
from radiotomate.models import RundownItem, Sound, User
from radiotomate.quart import CustomQuart
from radiotomate.scheduler.execution import DESK_ORIGIN
from radiotomate.scheduler.playout import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)
from radiotomate.scheduler_api import Scheduler
from tests.scheduler.test_schedule import _playout
from tests.scheduler.test_studio_json import _interface_client, _login


def test_normalize_live_cues_and_simulating():
    payload = live_mod.normalize_live(
        {
            "status": "simulating",
            "source": "autodj",
            "artist": "Demo",
            "title": "Now",
            "kind": "musique",
            "remaining": "12.4",
            "elapsed": "3.1",
            "next_autodj": {"title": "Next", "artist": "A", "rid": 2},
            "next_jingle": {"rid": -1},
            "next_cart": '{"title": "Spot", "artist": "Pub", "rid": 5}',
        }
    )
    assert payload["status"] == "simulating"
    assert payload["kind"] == "musique"
    assert payload["remaining"] == 12.4
    assert payload["next_jingle"] is None
    assert payload["next_autodj"]["title"] == "Next"
    assert payload["next_cart"]["title"] == "Spot"


def test_normalize_live_ignores_initial_track_mark():
    payload = live_mod.normalize_live(
        {
            "status": "playing",
            "source": "INSERT_INITIAL_TRACK_MARK",
            "title": "dummy",
            "jingles_queued": "2",
            "autodj_queued": "3",
            "carts_queued": "1",
        }
    )
    assert payload["source"] == "autodj"
    assert payload["jingles_queued"] == 2
    assert payload["autodj_queued"] == 3
    assert payload["carts_queued"] == 1


async def test_live_json_unauthenticated(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
):
    live_mod.set_live_snapshot(None)
    client = _interface_client(app_configration, beets_integration)
    response = await client.get("/live.json")
    assert response.status_code == 401
    delete = await client.delete("/live.json")
    assert delete.status_code == 401
    post = await client.post("/carts/1/now.json")
    assert post.status_code == 401


async def test_live_json_offline_and_snapshot(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    live_mod.set_live_snapshot(None)
    user = User(username="live-json-read")
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "live-json-read", users_password)
    offline = await (await client.get("/live.json")).get_json()
    assert offline["status"] == "offline"

    live_mod.set_live_snapshot(
        live_mod.normalize_live(
            {
                "status": "playing",
                "source": "autodj",
                "artist": "BUTTON",
                "title": "On air",
                "remaining": 8,
                "elapsed": 2,
                "next_autodj": {"title": "Suite", "artist": "B", "rid": 3},
            }
        )
    )
    playing = await (await client.get("/live.json")).get_json()
    assert playing["status"] == "playing"
    assert playing["title"] == "On air"
    assert playing["next_autodj"]["title"] == "Suite"
    live_mod.set_live_snapshot(None)


async def test_skip_json_forbidden_without_live(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    user = User(username="live-json-nope")
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "live-json-nope", users_password)
    response = await client.delete("/live.json")
    assert response.status_code == 403
    payload = await response.get_json()
    assert payload["error"] == "forbidden"


async def test_skip_json_ok_with_scheduler_mock(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    user = User(username="live-json-skip")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "live-json-skip", users_password)
    mock = MagicMock()
    mock.skip = AsyncMock()
    with patch.object(Scheduler, "get", return_value=mock):
        response = await client.delete("/live.json")
    assert response.status_code == 200
    assert (await response.get_json())["ok"] is True
    mock.skip.assert_awaited_once()


def _scheduler_facing(handler) -> Scheduler:
    """The real client, in front of a fake scheduler: `handler` answers each order."""
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.client = httpx.AsyncClient(
        base_url="http://127.0.0.1:6822",
        transport=httpx.MockTransport(handler),
    )
    return scheduler


def _scheduler_down(error: type[httpx.TransportError], sent: list[str]) -> Scheduler:
    """The real client, facing a scheduler that does not answer. `sent` logs orders."""

    def no_answer(request: httpx.Request) -> httpx.Response:
        sent.append(f"{request.method} {request.url.path}")
        raise error("no answer", request=request)

    return _scheduler_facing(no_answer)


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
async def test_skip_json_502_when_scheduler_down(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    error: type[httpx.TransportError],
):
    user = User(username="live-json-down")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "live-json-down", users_password)
    sent: list[str] = []
    with patch.object(Scheduler, "get", return_value=_scheduler_down(error, sent)):
        response = await client.delete("/live.json")
    assert response.status_code == 502
    assert await response.get_json() == {"error": "scheduler_unavailable"}
    assert sent == ["DELETE /live"]


async def test_push_now_json_404_and_200(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
):
    user = User(username="live-json-fire")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "live-json-fire", users_password)

    missing = await client.post("/carts/99999/now.json")
    assert missing.status_code == 404

    mock = MagicMock()
    mock.push_cart = AsyncMock()
    with patch.object(Scheduler, "get", return_value=mock):
        ok = await client.post(f"/carts/{jingles_cart.id}/now.json")
    assert ok.status_code == 200
    assert (await ok.get_json())["ok"] is True
    mock.push_cart.assert_awaited_once_with(jingles_cart.id)


async def test_push_sound_now_json(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
):
    user = User(username="live-json-pad")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    sound = await dbsession.scalar(
        select(Sound).where(Sound.cart_id == jingles_cart.id)
    )
    assert sound is not None
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "live-json-pad", users_password)

    missing = await client.post(f"/carts/{jingles_cart.id}/sounds/99999/now.json")
    assert missing.status_code == 404

    mock = MagicMock()
    mock.push_sound = AsyncMock()
    with patch.object(Scheduler, "get", return_value=mock):
        ok = await client.post(
            f"/carts/{jingles_cart.id}/sounds/{sound.id}/now.json",
        )
    assert ok.status_code == 200
    assert (await ok.get_json())["ok"] is True
    mock.push_sound.assert_awaited_once_with(jingles_cart.id, sound.id)


async def test_now_json_conflict_when_harbor(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
):
    user = User(username="live-json-harbor")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "live-json-harbor", users_password)
    live_mod.set_live_snapshot(
        {
            "status": "playing",
            "source": "stream",
            "title": "Hop Pop Hop",
            "artist": "Marie",
        }
    )
    mock = MagicMock()
    mock.push_cart = AsyncMock()
    mock.push_sound = AsyncMock()
    mock.push_path = AsyncMock()
    try:
        with patch.object(Scheduler, "get", return_value=mock):
            cart = await client.post(f"/carts/{jingles_cart.id}/now.json")
            now = await client.post(
                "/autodj/conducteur/now.json",
                json={"path": "/media/x.mp3", "title": "X", "artist": "Y"},
            )
    finally:
        live_mod.set_live_snapshot(None)
    assert cart.status_code == 409
    assert (await cart.get_json())["code"] == "harbor_live"
    assert now.status_code == 409
    mock.push_cart.assert_not_called()
    mock.push_path.assert_not_called()


async def test_now_json_502_when_scheduler_down(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
):
    user = User(username="live-json-fire-down")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    sound = await dbsession.scalar(
        select(Sound).where(Sound.cart_id == jingles_cart.id)
    )
    assert sound is not None
    client = _interface_client(app_configration, beets_integration)
    await _login(client, "live-json-fire-down", users_password)
    live_mod.set_live_snapshot(None)
    sent: list[str] = []
    down = _scheduler_down(httpx.ConnectError, sent)
    with patch.object(Scheduler, "get", return_value=down):
        answers = {
            "cart": await client.post(f"/carts/{jingles_cart.id}/now.json"),
            "pad": await client.post(
                f"/carts/{jingles_cart.id}/sounds/{sound.id}/now.json",
            ),
            "desk sound": await client.post(
                "/autodj/conducteur/now.json",
                json={"path": str(sound.path)},
            ),
            "desk path": await client.post(
                "/autodj/conducteur/now.json",
                json={"path": "/media/x.mp3", "title": "X", "artist": "Y"},
            ),
        }
    for name, response in answers.items():
        assert response.status_code == 502, name
        assert await response.get_json() == {"error": "scheduler_unavailable"}, name
    assert sent == [
        f"POST /schedule/{jingles_cart.id}/now",
        f"POST /schedule/{jingles_cart.id}/sounds/{sound.id}/now",
        f"POST /schedule/{jingles_cart.id}/sounds/{sound.id}/now",
        "POST /schedule/path/now",
    ]


def _scheduler_refusing(status: int, text: str, sent: list[str]) -> Scheduler:
    """A scheduler that answers every order with an error. `sent` logs orders."""

    def refuse(request: httpx.Request) -> httpx.Response:
        sent.append(f"{request.method} {request.url.path}")
        return httpx.Response(status, text=text)

    return _scheduler_facing(refuse)


async def _live_client(
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    username: str,
):
    user = User(username=username)
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)
    await _login(client, username, users_password)
    live_mod.set_live_snapshot(None)
    return client


async def _desk_lines(dbsession: ormSession) -> list[str]:
    """Paths of the desk lines in the rundown."""
    rows = await dbsession.scalars(
        select(RundownItem.path).where(RundownItem.origin == DESK_ORIGIN)
    )
    return list(rows)


PLAYOUT_REJECTED = {
    "error": "Le playout a refusé ce son : rien n'est parti à l'antenne.",
    "code": "playout_rejected",
}


@pytest.mark.parametrize(
    ("status", "text"),
    [(502, "playout rejected path"), (404, "cart or sound not found")],
)
async def test_now_json_400_when_playout_rejects(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
    status: int,
    text: str,
):
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-json-refused",
    )
    sound = await dbsession.scalar(
        select(Sound).where(Sound.cart_id == jingles_cart.id)
    )
    assert sound is not None
    sent: list[str] = []
    refusing = _scheduler_refusing(status, text, sent)
    with patch.object(Scheduler, "get", return_value=refusing):
        answers = {
            "cart": await client.post(f"/carts/{jingles_cart.id}/now.json"),
            "pad": await client.post(
                f"/carts/{jingles_cart.id}/sounds/{sound.id}/now.json",
            ),
            "desk sound": await client.post(
                "/autodj/conducteur/now.json",
                json={"path": str(sound.path)},
            ),
            "desk path": await client.post(
                "/autodj/conducteur/now.json",
                json={"path": "/media/x.mp3", "title": "X", "artist": "Y"},
            ),
        }
    for name, response in answers.items():
        assert response.status_code == 400, name
        assert await response.get_json() == PLAYOUT_REJECTED, name
    assert sent == [
        f"POST /schedule/{jingles_cart.id}/now",
        f"POST /schedule/{jingles_cart.id}/sounds/{sound.id}/now",
        f"POST /schedule/{jingles_cart.id}/sounds/{sound.id}/now",
        "POST /schedule/path/now",
    ]


@pytest.mark.parametrize(
    ("scheduler", "status"),
    [
        (lambda sent: _scheduler_down(httpx.ConnectError, sent), 502),
        (lambda sent: _scheduler_refusing(502, "playout rejected path", sent), 400),
    ],
    ids=["down", "refused"],
)
async def test_now_json_failed_order_leaves_no_desk_line(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    scheduler,
    status: int,
):
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-json-orphan",
    )
    sent: list[str] = []
    with patch.object(Scheduler, "get", return_value=scheduler(sent)):
        answers = [
            await client.post(
                "/autodj/conducteur/now.json",
                json={"path": "/media/x.mp3", "title": "X", "artist": "Y"},
            )
            for _ in range(2)
        ]
    assert [answer.status_code for answer in answers] == [status, status]
    assert sent == ["POST /schedule/path/now"] * 2
    assert await _desk_lines(dbsession) == []


# A placement field means nothing for a title already sent: even a bad one is
# ignored, and cannot fail the route once the title is on air.
@pytest.mark.parametrize(
    "placement",
    [{}, {"replace_at": "x"}, {"suppress_at": "x"}],
    ids=["plain", "replace_at", "suppress_at"],
)
async def test_now_json_posts_desk_line_after_order(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    placement: dict,
):
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-json-fire-path",
    )
    orders: list[dict] = []
    lines_at_order: list[list[str]] = []

    async def accept(request: httpx.Request) -> httpx.Response:
        orders.append(json.loads(request.content))
        lines_at_order.append(await _desk_lines(dbsession))
        return httpx.Response(200)

    with patch.object(Scheduler, "get", return_value=_scheduler_facing(accept)):
        response = await client.post(
            "/autodj/conducteur/now.json",
            json={
                "path": "/media/x.mp3",
                "title": "X",
                "artist": "Y",
                "kind": "jingle",
                "duration": 9,
                **placement,
            },
        )
    assert response.status_code == 200, await response.get_data(as_text=True)
    assert orders == [
        {"path": "/media/x.mp3", "artist": "Y", "title": "X", "kind": "jingle"}
    ]
    assert lines_at_order == [[]]
    assert await _desk_lines(dbsession) == ["/media/x.mp3"]
    payload = await response.get_json()
    desk = [item for item in payload["items"] if item.get("origin") == DESK_ORIGIN]
    assert [item["path"] for item in desk] == ["/media/x.mp3"]


async def test_now_json_checks_desk_line_before_order(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-json-bad-kind",
    )
    sent: list[str] = []
    down = _scheduler_down(httpx.ConnectError, sent)
    with patch.object(Scheduler, "get", return_value=down):
        response = await client.post(
            "/autodj/conducteur/now.json",
            json={"path": "/media/x.mp3", "kind": "cassette"},
        )
    assert response.status_code == 400
    payload = await response.get_json()
    assert (payload["code"], payload["field"]) == ("validation_error", "kind")
    assert sent == []
    assert await _desk_lines(dbsession) == []


def _scheduler_without_playout(sent: list[str]) -> Scheduler:
    """A scheduler that answers every order: its playout did not answer."""

    def no_playout(request: httpx.Request) -> httpx.Response:
        sent.append(f"{request.method} {request.url.path}")
        body = {"ok": False, "error": "playout_unavailable", "detail": "ReadTimeout"}
        return httpx.Response(502, json=body)

    return _scheduler_facing(no_playout)


async def test_gestures_502_when_playout_down(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    jingles_cart,
):
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-json-no-playout",
    )
    sound = await dbsession.scalar(
        select(Sound).where(Sound.cart_id == jingles_cart.id)
    )
    assert sound is not None
    sent: list[str] = []
    no_playout = _scheduler_without_playout(sent)
    with patch.object(Scheduler, "get", return_value=no_playout):
        answers = {
            "skip": await client.delete("/live.json"),
            "flush": await client.post("/antenne/flush.json"),
            "cart": await client.post(f"/carts/{jingles_cart.id}/now.json"),
            "pad": await client.post(
                f"/carts/{jingles_cart.id}/sounds/{sound.id}/now.json",
            ),
            "desk sound": await client.post(
                "/autodj/conducteur/now.json",
                json={"path": str(sound.path)},
            ),
            "desk path": await client.post(
                "/autodj/conducteur/now.json",
                json={"path": "/media/x.mp3", "title": "X", "artist": "Y"},
            ),
        }
    for name, response in answers.items():
        assert response.status_code == 502, name
        assert await response.get_json() == {"error": "playout_unavailable"}, name
    assert sent == [
        "DELETE /live",
        "POST /queues/flush",
        f"POST /schedule/{jingles_cart.id}/now",
        f"POST /schedule/{jingles_cart.id}/sounds/{sound.id}/now",
        f"POST /schedule/{jingles_cart.id}/sounds/{sound.id}/now",
        "POST /schedule/path/now",
    ]
    assert await _desk_lines(dbsession) == []


@pytest.mark.parametrize(
    ("status", "body"),
    [(502, {"ok": False, "error": "playout_rejected", "detail": "crash"}), (500, None)],
    ids=["playout", "scheduler"],
)
async def test_skip_and_flush_json_502_when_the_order_fails(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    status: int,
    body: dict | None,
):
    """Any other error says to check the antenna, never server_error."""
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-json-order-fails",
    )
    sent: list[str] = []

    def fail(request: httpx.Request) -> httpx.Response:
        sent.append(f"{request.method} {request.url.path}")
        if body is None:
            return httpx.Response(status, text="Internal Server Error")
        return httpx.Response(status, json=body)

    with patch.object(Scheduler, "get", return_value=_scheduler_facing(fail)):
        answers = {
            "skip": await client.delete("/live.json"),
            "flush": await client.post("/antenne/flush.json"),
        }
    for name, response in answers.items():
        assert response.status_code == 502, name
        assert await response.get_json() == {"error": "playout_unavailable"}, name
    assert sent == ["DELETE /live", "POST /queues/flush"]


async def test_skip_page_says_when_playout_down(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    """The HTMX page says it through its own error path, as for a cart."""
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-page-no-playout",
    )
    sent: list[str] = []
    no_playout = _scheduler_without_playout(sent)
    with patch.object(Scheduler, "get", return_value=no_playout):
        response = await client.delete("/live", headers={"HX-Request": "true"})
    assert response.status_code == 400
    message = json.loads(response.headers["HX-Trigger"])["radiotomateMessage"]
    assert message["text"] == "Le playout ne répond pas."
    assert sent == ["DELETE /live"]


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
async def test_flush_json_502_when_scheduler_down(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    error: type[httpx.TransportError],
):
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-json-flush-down",
    )
    sent: list[str] = []
    with patch.object(Scheduler, "get", return_value=_scheduler_down(error, sent)):
        response = await client.post("/antenne/flush.json")
    assert response.status_code == 502
    assert await response.get_json() == {"error": "scheduler_unavailable"}
    assert sent == ["POST /queues/flush"]


async def test_orders_wait_for_the_scheduler_attempts():
    """The scheduler's verdict on the playout arrives before the order gives up."""
    reads: list[float] = []

    def accept(request: httpx.Request) -> httpx.Response:
        reads.append(request.extensions["timeout"]["read"])
        return httpx.Response(200, json={"ok": True})

    scheduler = _scheduler_facing(accept)
    await scheduler.skip()
    await scheduler.flush_queues()
    await scheduler.push_cart(1)
    await scheduler.push_sound(1, 2)
    await scheduler.push_path("/media/x.mp3")
    # A cart pushes two sounds, one after the other: two timeouts on the playout
    # at most, or refused connections tried three times.
    gesture = 2 * DEFAULT_TIMEOUT_SECONDS + sum(DEFAULT_BACKOFF_SECONDS)
    assert len(reads) == 5
    assert all(read > gesture for read in reads)


async def test_gestures_through_the_scheduler(  # noqa: PLR0913
    app: CustomQuart,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    auth: dict,
    jingles_cart,
    monkeypatch: pytest.MonkeyPatch,
):
    """The interface reads what the real scheduler answers when the playout fails."""
    sent: list[str] = []

    def playout(request: httpx.Request) -> httpx.Response:
        sent.append(f"{request.method} {request.url.path}")
        if request.method == "DELETE":
            raise httpx.ConnectError("no answer", request=request)
        return httpx.Response(400, json={"error": "cannot resolve the sound"})

    monkeypatch.setitem(app.config, "PLAYOUT_CLIENT", _playout(playout))
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.client = httpx.AsyncClient(
        base_url="http://127.0.0.1:6822",
        transport=httpx.ASGITransport(app=app),
        headers=auth,
    )
    client = await _live_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "live-json-scheduler",
    )
    with patch.object(Scheduler, "get", return_value=scheduler):
        skipped = await client.delete("/live.json")
        fired = await client.post(f"/carts/{jingles_cart.id}/now.json")
    assert skipped.status_code == 502
    assert await skipped.get_json() == {"error": "playout_unavailable"}
    assert fired.status_code == 400
    assert await fired.get_json() == PLAYOUT_REJECTED
    assert sent == ["DELETE /live"] * 3 + ["POST /queue/jingles"]


async def test_antenne_state_and_flush_json(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    user = User(username="antenne-state")
    user.update_password(users_password)
    user.update_permissions({"can_live": "true"})
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets_integration)

    anonymous = await client.get("/antenne/state.json")
    assert anonymous.status_code == 401

    await _login(client, "antenne-state", users_password)
    mock = MagicMock()
    mock.state = AsyncMock(
        return_value={"playout": {"reachable": True}, "incidents": []}
    )
    mock.flush_queues = AsyncMock()
    with patch.object(Scheduler, "get", return_value=mock):
        state = await client.get("/antenne/state.json")
        assert state.status_code == 200
        assert (await state.get_json())["playout"]["reachable"] is True

        mock.state = AsyncMock(return_value=None)
        down = await client.get("/antenne/state.json")
        assert down.status_code == 502
        assert await down.get_json() == {"error": "scheduler_unavailable"}

        flushed = await client.post("/antenne/flush.json")
        assert flushed.status_code == 200
        mock.flush_queues.assert_awaited_once()


async def test_antenne_state_demo_scheduler():
    from radiotomate.scheduler_api import SchedulerDemo

    demo = SchedulerDemo.__new__(SchedulerDemo)
    demo._played = [
        {
            "at": "2026-09-21T21:00:00",
            "queue": "autodj",
            "artist": "nowave",
            "title": "Dahlia",
        },
    ]
    body = await demo.state()
    assert body["demo"] is True
    assert body["engine"]["heartbeat_ok"] is True
    assert body["listeners"][0]["mount"] == "button.mp3"
    assert body["asrun"][0]["title"] == "Dahlia"
