"""« Retrouver ce titre » (FON-84): the link service is played by a fake transport,
and no real service is ever called. Off by default; a failure or a slow answer
leaves the track without a link; the partner key is never returned."""

import asyncio
import json
import logging

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainValidationError
from radiotomate.interface import live as live_mod
from radiotomate.models import Setting
from radiotomate.services import listen_link
from radiotomate.services.listen_link import Settings
from tests.scheduler.test_admin_json import _admin_client

SERVICE = "https://liens.radio.example"
KEY = "change-me"
LINK = "https://liens.radio.example/l/abc123"


@pytest.fixture(autouse=True)
def fresh_state():
    listen_link.reset_state()
    yield
    listen_link.reset_state()


class FakeService:
    """The listening link service: records each request, answers as told."""

    def __init__(self, handler=None) -> None:
        self.requests: list[httpx.Request] = []
        self.handler = handler or (
            lambda _request: httpx.Response(200, json={"id": "abc123", "url": LINK})
        )

    @property
    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.handler(request)

        return httpx.MockTransport(handle)


def on(key: str | None = None) -> Settings:
    return Settings(enabled=True, url=SERVICE, key=key)


async def test_a_sure_answer_gives_the_link_and_asks_the_way_the_service_wants():
    service = FakeService()
    link = await listen_link.resolve(
        on(KEY), "Ada", "Chanson", transport=service.transport
    )
    assert link == LINK
    (request,) = service.requests
    assert (request.method, str(request.url)) == ("POST", f"{SERVICE}/api/resolve")
    assert json.loads(request.content) == {
        "track": {"artist": "Ada", "title": "Chanson"}
    }
    assert request.headers["X-Hopper-Key"] == KEY


async def test_without_a_partner_key_no_key_header_leaves():
    service = FakeService()
    await listen_link.resolve(on(), "Ada", "Chanson", transport=service.transport)
    assert "x-hopper-key" not in service.requests[0].headers


async def test_a_422_means_no_link_and_is_not_asked_again():
    service = FakeService(lambda _r: httpx.Response(422, json={"error": "unresolved"}))
    assert (
        await listen_link.resolve(on(), "Ada", "Inconnu", transport=service.transport)
        is None
    )
    assert (
        await listen_link.resolve(
            on(), "  ada ", "INCONNU", transport=service.transport
        )
        is None
    )
    assert len(service.requests) == 1


async def test_a_sure_link_is_kept_so_a_title_played_again_is_not_asked_again():
    service = FakeService()
    for _ in range(3):
        assert (
            await listen_link.resolve(
                on(), "Ada", "Chanson", transport=service.transport
            )
            == LINK
        )
    assert len(service.requests) == 1


@pytest.mark.parametrize("status", [500, 502, 503, 429, 401, 404])
async def test_a_failing_service_gives_no_link_and_nothing_is_kept(status: int):
    service = FakeService(lambda _r: httpx.Response(status))
    assert (
        await listen_link.resolve(on(), "Ada", "Chanson", transport=service.transport)
        is None
    )
    # A failure is not an answer: the title is asked again.
    service.handler = lambda _r: httpx.Response(200, json={"id": "1", "url": LINK})
    assert (
        await listen_link.resolve(on(), "Ada", "Chanson", transport=service.transport)
        == LINK
    )


async def test_a_network_failure_or_a_late_answer_gives_no_link():
    def down(_request: httpx.Request):
        raise httpx.ConnectError("refused")

    def slow(_request: httpx.Request):
        raise httpx.ReadTimeout("too slow")

    for handler in (down, slow):
        service = FakeService(handler)
        assert (
            await listen_link.resolve(
                on(), "Ada", "Chanson", transport=service.transport
            )
            is None
        )
        listen_link.reset_state()


async def test_the_deadline_is_short(monkeypatch: pytest.MonkeyPatch):
    # The client is given the module's short timeout: the antenna's background
    # task never waits longer for the service.
    seen: list[httpx.Timeout] = []
    real = httpx.AsyncClient

    def spy(*args, **kwargs):
        seen.append(kwargs["timeout"])
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", spy)
    await listen_link.resolve(on(), "Ada", "Chanson", transport=FakeService().transport)
    assert listen_link.TIMEOUT <= 5
    assert seen[0].read == listen_link.TIMEOUT


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        "{}",
        '{"url": "javascript:alert(1)"}',
        '{"url": "https://a b/x"}',
    ],
)
async def test_an_answer_that_is_not_a_web_link_gives_no_link(body: str):
    service = FakeService(lambda _r: httpx.Response(200, content=body))
    assert (
        await listen_link.resolve(on(), "Ada", "Chanson", transport=service.transport)
        is None
    )


async def test_the_breaker_stops_asking_after_three_failures_then_resumes():
    service = FakeService(lambda _r: httpx.Response(503))
    for number in range(3):
        await listen_link.resolve(
            on(), "Ada", f"T{number}", transport=service.transport, now=100.0
        )
    assert len(service.requests) == 3
    await listen_link.resolve(on(), "Ada", "T9", transport=service.transport, now=110.0)
    assert len(service.requests) == 3
    service.handler = lambda _r: httpx.Response(200, json={"id": "1", "url": LINK})
    assert (
        await listen_link.resolve(
            on(), "Ada", "T9", transport=service.transport, now=200.0
        )
        == LINK
    )


async def test_switched_off_or_without_an_address_no_request_leaves():
    service = FakeService()
    for settings in (
        Settings(enabled=False, url=SERVICE, key=KEY),
        Settings(enabled=True, url=None, key=KEY),
    ):
        assert (
            await listen_link.resolve(
                settings, "Ada", "Chanson", transport=service.transport
            )
            is None
        )
    assert (
        await listen_link.resolve(on(), "", "Chanson", transport=service.transport)
        is None
    )
    assert service.requests == []


async def test_the_key_is_never_logged(caplog: pytest.LogCaptureFixture):
    service = FakeService(lambda _r: httpx.Response(500))
    with caplog.at_level(logging.DEBUG):
        await listen_link.resolve(
            on(KEY), "Ada", "Chanson", transport=service.transport
        )
    # httpx logs the address it calls, never a header: the key stays out of the log.
    assert KEY not in caplog.text


# -- the settings route ---------------------------------------------------------


async def _stored(dbsession: ormSession) -> dict:
    await dbsession.rollback()
    rows = await dbsession.scalars(
        select(Setting).where(
            Setting.key.in_(
                ("features.listen_link", "listen_link.url", "listen_link.key")
            )
        )
    )
    return {row.key: row.value for row in rows}


async def test_off_by_default_and_only_for_an_admin(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "ll-admin"
    )
    payload = await (await admin.get("/listen-link.json")).get_json()
    assert payload == {"enabled": False, "url": None, "key_set": False}

    programmer = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "ll-prog",
        {"live": True, "stream": True, "carts": True, "autodj": True},
    )
    for response in (
        await programmer.get("/listen-link.json"),
        await programmer.put("/listen-link.json", json={"enabled": True}),
    ):
        assert response.status_code == 403
    assert await _stored(dbsession) == {}


async def test_the_key_is_written_and_never_read_back(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "ll-key"
    )
    response = await admin.put(
        "/listen-link.json", json={"enabled": True, "url": f"{SERVICE}/", "key": KEY}
    )
    assert response.status_code == 200, await response.get_data(as_text=True)
    text = await response.get_data(as_text=True)
    assert KEY not in text
    assert json.loads(text) == {"enabled": True, "url": SERVICE, "key_set": True}
    assert KEY not in await (await admin.get("/listen-link.json")).get_data(
        as_text=True
    )
    assert (await _stored(dbsession))["listen_link.key"] == KEY

    # A PUT without the key keeps it; an empty key unsets it.
    kept = await (
        await admin.put("/listen-link.json", json={"enabled": False})
    ).get_json()
    assert kept == {"enabled": False, "url": SERVICE, "key_set": True}
    gone = await (await admin.put("/listen-link.json", json={"key": ""})).get_json()
    assert gone["key_set"] is False
    assert "listen_link.key" not in await _stored(dbsession)


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"url": "radio.example"}, "url"),
        ({"url": "ftp://liens.radio.example"}, "url"),
        ({"url": "https://user:pw@liens.radio.example"}, "url"),
        ({"url": 12}, "url"),
        ({"key": "deux mots"}, "key"),
        ({"key": "x" * 201}, "key"),
        ({"key": 5}, "key"),
        ({"enabled": "oui"}, "enabled"),
    ],
)
async def test_a_wrong_value_is_refused_and_writes_nothing(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    body: dict,
    field: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "ll-bad"
    )
    response = await admin.put("/listen-link.json", json={"enabled": True, **body})
    assert response.status_code == 400, await response.get_data(as_text=True)
    assert (await response.get_json())["field"] == field
    assert await _stored(dbsession) == {}


def test_domain_rules_unset_on_empty():
    from radiotomate.domain.listen_link import clean_key, clean_link, clean_url

    assert clean_url("  ") is None
    assert clean_key(None) is None
    assert (
        clean_link("https://liens.radio.example/l/1")
        == "https://liens.radio.example/l/1"
    )
    assert clean_link("javascript:alert(1)") is None
    with pytest.raises(DomainValidationError):
        clean_url("liens.radio.example")


# -- on air: the scheduler asks, the interface and nowplaying get the answer --------


async def _station_on(dbsession: ormSession, **extra: str) -> None:
    for key, value in {
        "features.listen_link": "1",
        "listen_link.url": SERVICE,
        "listen_link.key": KEY,
        **extra,
    }.items():
        await Setting.upsert(dbsession, key, value)
    await dbsession.commit()


async def _drain(app) -> None:
    for task in list(app.background_tasks):
        await asyncio.wait_for(task, 5)


def _fake_service(monkeypatch: pytest.MonkeyPatch, service: FakeService) -> None:
    """The scheduler builds its own client: it is given the fake transport."""
    real = listen_link.resolve

    async def resolve(settings, artist, title, **kwargs):
        return await real(
            settings, artist, title, transport=service.transport, **kwargs
        )

    monkeypatch.setattr(listen_link, "resolve", resolve)


async def test_a_track_on_air_gets_its_link_kept_and_sent_to_nowplaying(
    raw_app, dbsession: ormSession, auth: dict, monkeypatch: pytest.MonkeyPatch
):
    service = FakeService()
    _fake_service(monkeypatch, service)
    sent: list[dict] = []

    async def sidecar(payload: dict) -> None:
        sent.append(payload)

    monkeypatch.setattr("radiotomate.scheduler.live._post_sidecar", sidecar)
    await _station_on(dbsession)
    async with raw_app.test_app():
        client = raw_app.test_client()
        response = await client.post(
            "/metadata_log",
            json={
                "source": "autodj",
                "artist": "Ada",
                "title": "Chanson",
                "radiotomate_sound_id": "",
            },
            headers=auth,
        )
        assert response.status_code == 200
        await _drain(raw_app)

    assert len(service.requests) == 1
    assert sent == [
        {
            "listen_link": {
                "artist": "Ada",
                "title": "Chanson",
                "radiotomate_sound_id": "",
                "url": LINK,
            }
        }
    ]
    row = await Setting.from_key(dbsession, "listen_link.current")
    assert json.loads(row.value) == {"artist": "Ada", "title": "Chanson", "url": LINK}


@pytest.mark.parametrize("case", ["off", "no_address", "not_music"])
async def test_nothing_leaves_when_off_without_an_address_or_for_a_live(
    raw_app,
    dbsession: ormSession,
    auth: dict,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
):
    service = FakeService()
    _fake_service(monkeypatch, service)
    await _station_on(dbsession)
    if case == "off":
        await Setting.upsert(dbsession, "features.listen_link", "0")
    if case == "no_address":
        await dbsession.delete(await Setting.from_key(dbsession, "listen_link.url"))
    await dbsession.commit()
    source = "stream" if case == "not_music" else "autodj"
    async with raw_app.test_app():
        client = raw_app.test_client()
        response = await client.post(
            "/metadata_log",
            json={"source": source, "artist": "Ada", "title": "Chanson"},
            headers=auth,
        )
        assert response.status_code == 200
        await _drain(raw_app)
    assert service.requests == []
    assert await Setting.from_key(dbsession, "listen_link.current") is None


async def test_a_service_down_never_breaks_the_log_and_leaves_no_link(
    raw_app, dbsession: ormSession, auth: dict, monkeypatch: pytest.MonkeyPatch
):
    service = FakeService(lambda _r: httpx.Response(503))
    _fake_service(monkeypatch, service)
    sent: list[dict] = []

    async def sidecar(payload: dict) -> None:
        sent.append(payload)

    monkeypatch.setattr("radiotomate.scheduler.live._post_sidecar", sidecar)
    await _station_on(dbsession)
    async with raw_app.test_app():
        client = raw_app.test_client()
        response = await client.post(
            "/metadata_log",
            json={"source": "autodj", "artist": "Ada", "title": "Chanson"},
            headers=auth,
        )
        assert response.status_code == 200
        await _drain(raw_app)
    assert sent == []
    assert await Setting.from_key(dbsession, "listen_link.current") is None


async def test_the_answer_is_not_waited_for_by_the_log(
    raw_app, dbsession: ormSession, auth: dict, monkeypatch: pytest.MonkeyPatch
):
    """The playout's POST is answered while the service is still thinking."""
    release = asyncio.Event()
    started = asyncio.Event()

    async def slow(settings, artist, title, **kwargs):
        started.set()
        await release.wait()
        return LINK

    monkeypatch.setattr(listen_link, "resolve", slow)
    monkeypatch.setattr(
        "radiotomate.scheduler.live._post_sidecar", lambda payload: asyncio.sleep(0)
    )
    await _station_on(dbsession)
    async with raw_app.test_app():
        client = raw_app.test_client()
        response = await asyncio.wait_for(
            client.post(
                "/metadata_log",
                json={"source": "autodj", "artist": "Ada", "title": "Chanson"},
                headers=auth,
            ),
            2,
        )
        assert response.status_code == 200
        release.set()
        await _drain(raw_app)
    assert started.is_set()


async def test_live_json_carries_the_link_of_the_track_on_air_only_when_on(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "ll-live"
    )
    snapshot = {
        "status": "playing",
        "source": "autodj",
        "artist": "Ada",
        "title": "Chanson",
        "remaining": 8,
    }
    live_mod.set_live_snapshot(live_mod.normalize_live(snapshot))
    try:
        # Off, and nothing kept: no link.
        assert "listen_url" not in await (await admin.get("/live.json")).get_json()

        await _station_on(dbsession)
        await listen_link.keep_current(dbsession, "Ada", "Chanson", LINK)
        await dbsession.commit()
        assert (await (await admin.get("/live.json")).get_json())["listen_url"] == LINK

        # Another track on air: the link kept is not its own.
        live_mod.set_live_snapshot(
            live_mod.normalize_live({**snapshot, "title": "Autre"})
        )
        assert "listen_url" not in await (await admin.get("/live.json")).get_json()

        # A live: never.
        live_mod.set_live_snapshot(
            live_mod.normalize_live({**snapshot, "source": "stream"})
        )
        assert "listen_url" not in await (await admin.get("/live.json")).get_json()

        # Switched off again: the link kept is not shown.
        live_mod.set_live_snapshot(live_mod.normalize_live(snapshot))
        await Setting.upsert(dbsession, "features.listen_link", "0")
        await dbsession.commit()
        assert "listen_url" not in await (await admin.get("/live.json")).get_json()
    finally:
        live_mod.set_live_snapshot(None)
