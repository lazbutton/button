from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx
from quart.testing import QuartClient
from sqlalchemy.orm import Session as ormSession

from radiotomate.domain.agenda import utc_naive
from radiotomate.models import AgendaDiffusion
from radiotomate.scheduler import alerts, antenne
from radiotomate.scheduler.playout import PlayoutGateway, PlayoutResult

PARIS = ZoneInfo("Europe/Paris")

HEALTH = {
    "source": "autodj",
    "silence_s": "0.5",
    "rms_db": "-18.2",
    "on": "false",
    "icecast_targets": "icecast:8000/radio.mp3,radio.example:8000/radio.mp3",
    "icecast_connected": "icecast:8000/radio.mp3",
    "icecast_down": "radio.example:8000/radio.mp3",
}


def _status(listeners: int) -> dict:
    return {
        "icestats": {
            "source": {
                "listenurl": "http://localhost:8000/radio.mp3",
                "listeners": listeners,
                "listener_peak": listeners + 2,
                "title": "nowave - Dahlia",
            }
        }
    }


def test_playout_state_parses_health():
    state = antenne.playout_state(HEALTH)
    assert state["reachable"] is True
    assert state["silence_s"] == 0.5
    assert state["icecast_down"] == ["radio.example:8000/radio.mp3"]
    assert antenne.playout_state(None) == {"reachable": False}


def test_next_live_slot_picks_the_closest_window():
    slots = [
        alerts.LiveSlot("QG", day_of_week=2, start_minute=20 * 60, end_minute=22 * 60),
        alerts.LiveSlot(
            "Matinale", day_of_week=0, start_minute=8 * 60, end_minute=9 * 60
        ),
    ]
    monday_noon = datetime(2026, 9, 21, 12, 0, tzinfo=PARIS)
    nxt = antenne.next_live_slot(slots, monday_noon)
    assert nxt["title"] == "QG"
    assert nxt["starts_in_s"] == (2 * 24 + 8) * 3600
    active = antenne.next_live_slot(slots, datetime(2026, 9, 23, 20, 30, tzinfo=PARIS))
    assert active["active"] is True
    assert antenne.next_live_slot([], monday_noon) is None


async def test_state_json_aggregates(client: QuartClient, auth: dict, app):
    def status_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "icecast":
            return httpx.Response(200, json=_status(3))
        return httpx.Response(503)

    app.config["ANTENNE_HTTP_CLIENT"] = httpx.AsyncClient(
        transport=httpx.MockTransport(status_handler)
    )
    app.config["PLAYOUT_OUTPUTS"] = [
        {"driver": "icecast", "host": "icecast", "port": 8000, "mount": "radio.mp3"},
        {
            "driver": "icecast",
            "host": "radio.example",
            "port": 8000,
            "mount": "radio.mp3",
        },
        {"driver": "alsa", "device": "default"},
    ]
    monitor = alerts.AlertMonitor(alerts.AlertSettings(enabled=True))
    monitor.open["silence"] = alerts.Incident(
        "silence", "25 s de silence", opened_at=0.0
    )
    app.extensions["alert_monitor"] = monitor

    unauth = await client.get("/antenne/state.json")
    assert unauth.status_code == 401

    with patch.object(
        PlayoutGateway,
        "health",
        new=AsyncMock(
            return_value=PlayoutResult(ok=True, status_code=200, payload=HEALTH)
        ),
    ):
        response = await client.get("/antenne/state.json", headers=auth)
    assert response.status_code == 200, await response.get_data(as_text=True)
    body = await response.get_json()
    assert body["playout"]["source"] == "autodj"
    assert body["engine"]["db_ok"] is True
    assert body["incidents"][0]["kind"] == "silence"
    listeners = {row["target"]: row for row in body["listeners"]}
    local = listeners["icecast:8000/radio.mp3"]
    assert local["listeners"] == 3
    assert local["connected"] is True
    public = listeners["radio.example:8000/radio.mp3"]
    assert public["reachable"] is False
    assert public["connected"] is False
    assert isinstance(body["asrun"], list)
    assert body["next_live_slot"] is None


async def test_state_json_tells_the_next_live_from_the_instant(
    container_tz: str, client: QuartClient, auth: dict, dbsession: ormSession
):
    # A dated live of the Agenda starts in ten minutes, wherever the station is.
    start = datetime.now(UTC) + timedelta(minutes=10)
    dbsession.add(
        AgendaDiffusion(
            kind="live",
            title="Direct de test",
            starts_at=utc_naive(start),
            ends_at=utc_naive(start + timedelta(hours=1)),
        )
    )
    await dbsession.commit()
    with patch.object(
        PlayoutGateway,
        "health",
        new=AsyncMock(
            return_value=PlayoutResult(
                ok=True, status_code=200, payload={"source": "autodj"}
            )
        ),
    ):
        response = await client.get("/antenne/state.json", headers=auth)
    assert response.status_code == 200, await response.get_data(as_text=True)
    slot = (await response.get_json())["next_live_slot"]
    assert slot["title"] == "Direct de test"
    assert slot["active"] is False
    assert 9 * 60 <= slot["starts_in_s"] <= 10 * 60
