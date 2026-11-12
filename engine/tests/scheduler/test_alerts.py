import json
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from time import time as time_now
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.orm import Session as ormSession

from radiotomate.domain.agenda import utc_naive
from radiotomate.domain.emission import now_paris
from radiotomate.models import AgendaDiffusion, Emission
from radiotomate.quart import CustomQuart
from radiotomate.scheduler import alerts, metrics
from radiotomate.services import agenda

PARIS = ZoneInfo("Europe/Paris")


class _Spy:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, **payload):
        self.sent.append(payload)


def _settings(**over) -> alerts.AlertSettings:
    raw = {
        "enabled": True,
        "silence_seconds": 20,
        "heartbeat_max_age_seconds": 10,
        # A target, that the spy stands for: without one, nothing goes out.
        "webhook_url": "http://hook.local/alert",
    }
    raw.update(over)
    return alerts.AlertSettings.from_config(raw)


async def test_silence_opens_once_then_resolves():
    spy = _Spy()
    monitor = alerts.AlertMonitor(_settings(cooldown_seconds=600), spy)
    quiet = {"silence_s": "25.0", "source": "autodj"}
    assert await monitor.step(quiet, heartbeat_age=1.0) == ["open:silence"]
    # still quiet, inside cooldown → no second notification
    assert await monitor.step(quiet, heartbeat_age=1.0) == []
    assert await monitor.step({"silence_s": "0.0", "source": "carts"}, 1.0) == [
        "resolved:silence"
    ]
    assert [s["resolved"] for s in spy.sent] == [False, True]
    assert spy.sent[0]["kind"] == "silence"
    assert "25 s" in spy.sent[0]["body"]


async def test_playout_down_needs_consecutive_failures_and_heartbeat_alert():
    spy = _Spy()
    monitor = alerts.AlertMonitor(_settings(), spy)
    emitted = []
    for _ in range(alerts.PLAYOUT_DOWN_AFTER):
        emitted += await monitor.step(None, heartbeat_age=None)
    assert emitted.count("open:heartbeat") == 1
    assert emitted.count("open:playout_down") == 1
    assert set(monitor.open) == {"heartbeat", "playout_down"}
    back = await monitor.step({"silence_s": "0", "source": "carts"}, heartbeat_age=0.5)
    assert sorted(back) == ["resolved:heartbeat", "resolved:playout_down"]
    assert monitor.open == {}


async def test_the_watch_is_on_without_a_block_and_enabled_false_stops_it():
    """SUR-04: without the block, or without a target, the monitor watches
    the antenna for the Antenne page. ``enabled: false`` switches it off."""
    for raw in (None, {}, {"silence_seconds": 30}, {"enabled": None}):
        conf = alerts.AlertSettings.from_config(raw)
        assert conf.enabled is True
        assert conf.has_target is False
    assert alerts.AlertSettings().enabled is True
    conf = alerts.AlertSettings.from_config({"webhook_url": "http://x/hook"})
    assert conf.enabled is True
    assert conf.has_target is True
    assert conf.interval == alerts.DEFAULT_INTERVAL
    # Off as YAML 1.2 reads it: a boolean, or a word it keeps as text, as the
    # switches of the settings read them.
    for off in (False, 0, "false", "off", "no", "non", " Off ", ""):
        assert alerts.AlertSettings.from_config({"enabled": off}).enabled is False
    for on in (True, "true", "on", "yes", "oui"):
        assert alerts.AlertSettings.from_config({"enabled": on}).enabled is True
    # A word in place of the block says it as well.
    for off in (False, "off", "no"):
        assert alerts.AlertSettings.from_config(off).enabled is False
    assert alerts.AlertSettings.from_config(True).enabled is True


async def test_a_word_neither_on_nor_off_keeps_the_watch_on_and_says_so(
    caplog, monkeypatch
):
    # tests.yaml, once a test has loaded it, stops the engine's records short
    # of the root logger, where caplog listens.
    monkeypatch.setattr(logging.getLogger("radiotomate"), "propagate", True)
    with caplog.at_level("WARNING", logger="radiotomate.scheduler.alerts"):
        assert alerts.AlertSettings.from_config({"enabled": "disabled"}).enabled
    assert "'disabled' is neither on nor off" in caplog.text


async def test_a_target_hears_of_an_incident_once_and_of_its_end_only_after(
    tmp_path: Path,
):
    """SUR-04: an incident that went to the log only, with no target, goes to
    the first target set while it is open, on the next turn, even after a
    restart; then its end. A target that never heard of it never gets its end
    alone, even after a restart. Before SUR-04, incidents saved went to a
    target: they are not sent again."""
    posts: list[dict] = []

    def hook(request: httpx.Request) -> httpx.Response:
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={})

    alone = _settings(webhook_url="")
    told = _settings()
    state = tmp_path / "alerts.json"
    silent = {"silence_s": "30", "source": "autodj"}
    sound = {"silence_s": "0", "source": "autodj"}

    def monitor(settings) -> alerts.AlertMonitor:
        client = httpx.AsyncClient(transport=httpx.MockTransport(hook))
        notifier = alerts.Notifier(settings, client)
        watch = alerts.AlertMonitor(settings, notifier, state_path=state)
        watch.load_state()
        return watch

    def set_targets(watch: alerts.AlertMonitor, settings) -> None:
        # As the loop takes a new alerts: block.
        watch.settings = watch.notifier.settings = settings

    # No target: the silence goes to the log, and is saved.
    first = monitor(alone)
    assert await first.step(silent, 1.0) == ["open:silence"]
    assert json.loads(state.read_text())["open"]["silence"]["told"] is False
    # A target set on the turn the sound returns: nothing goes to it, and
    # the silence is gone from the file.
    set_targets(first, told)
    assert await first.step(sound, 1.0) == ["resolved:silence"]
    assert posts == []
    assert json.loads(state.read_text())["open"] == {}
    # A restart with the target: nothing to tell.
    assert await monitor(told).step(sound, 1.0) == []
    assert posts == []

    # No target, a silence saved; the scheduler restarts with a target set.
    assert await monitor(alone).step(silent, 1.0) == ["open:silence"]
    again = monitor(told)
    assert await again.step(silent, 1.0) == ["open:silence"]
    assert await again.step(silent, 1.0) == []
    assert await again.step(sound, 1.0) == ["resolved:silence"]
    assert [(post["kind"], post["resolved"]) for post in posts] == [
        ("silence", False),
        ("silence", True),
    ]

    # Saved before SUR-04, without "told": sent already, not again.
    posts.clear()
    stamp = time_now() - 60
    entry = {"detail": "30 s de silence", "opened_at": stamp, "notified_at": stamp}
    state.write_text(json.dumps({"open": {"silence": entry}}))
    old = monitor(told)
    assert await old.step(silent, 1.0) == []
    assert await old.step(sound, 1.0) == ["resolved:silence"]
    assert [(post["kind"], post["resolved"]) for post in posts] == [("silence", True)]


async def test_notifier_posts_webhook_and_vikunja_task():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"token": "jwt-1"})
        if request.url.path.endswith("/tasks") and request.method == "PUT":
            return httpx.Response(201, json={"id": 42})
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings(
        webhook_url="http://hook.local/alert",
        vikunja={
            "url": "http://vikunja.local",
            "project_id": 3,
            "label_id": 6,
            "username": "bot",
            "password": "pw",
        },
    )
    notifier = alerts.Notifier(settings, client)
    await notifier.send(
        kind="silence", resolved=False, title="[ALERTE] silence", body="25 s", host="h"
    )
    paths = [(c.method, c.url.host, c.url.path) for c in calls]
    assert paths == [
        ("POST", "hook.local", "/alert"),
        ("POST", "vikunja.local", "/api/v1/login"),
        ("PUT", "vikunja.local", "/api/v1/projects/3/tasks"),
        ("PUT", "vikunja.local", "/api/v1/tasks/42/labels"),
    ]
    task = json.loads(calls[2].content)
    assert task["title"] == "[ALERTE] silence"
    assert calls[2].headers["Authorization"] == "Bearer jwt-1"
    assert json.loads(calls[3].content) == {"label_id": 6}

    # Recovery closes the very task that was opened, no second task.
    calls.clear()
    await notifier.send(
        kind="silence", resolved=True, title="[RÉTABLI] silence", body="ok", host="h"
    )
    paths = [(c.method, c.url.host, c.url.path) for c in calls]
    assert paths == [
        ("POST", "hook.local", "/alert"),
        ("POST", "vikunja.local", "/api/v1/tasks/42"),
    ]
    assert json.loads(calls[1].content)["done"] is True


async def test_metrics_snapshot_roundtrip(tmp_path: Path):
    reg = metrics.runtime_metrics
    reg.reset()
    reg.record_push("carts", "ok")
    reg.record_push("carts", "ok")
    reg.record_alert("silence")
    reg.tick_run_total = 7
    saved = await metrics.save_snapshot(tmp_path, history=True)
    assert saved["playout_push_total"] == {"carts:ok": 2}
    assert (tmp_path / metrics.SNAPSHOT_FILE).exists()
    history = (tmp_path / metrics.HISTORY_FILE).read_text().splitlines()
    assert len(history) == 1

    reg.reset()
    assert reg.playout_push_total == {}
    metrics.load_snapshot(tmp_path)
    assert reg.playout_push_total["carts:ok"] == 2
    assert reg.alerts_total["silence"] == 1
    assert reg.tick_run_total == 7
    assert reg.restored_from == saved["saved_at"]
    reg.reset()


def _paris(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    # 2026-09-21 is a Monday (weekday 0)
    return datetime(2026, 9, 21 + day, hour, minute, second, tzinfo=PARIS)


async def test_ef01_live_slot_without_encoder_opens_after_grace_and_resolves():
    spy = _Spy()
    monitor = alerts.AlertMonitor(_settings(live_grace_seconds=90), spy)
    monitor.live_slots = [
        alerts.LiveSlot(
            title="QG St Aignan",
            day_of_week=2,
            start_minute=20 * 60,
            end_minute=22 * 60,
        )
    ]
    clock = {"silence_s": "0.0", "source": "carts"}

    # Tuesday, nothing scheduled: quiet.
    assert await monitor.step(clock, 1.0, now=_paris(1, 20, 1)) == []
    # Wednesday 20:00:30, inside the grace period: still quiet.
    assert await monitor.step(clock, 1.0, now=_paris(2, 20, 0, 30)) == []
    # 20:02 with the clock on air → EF-01 incident, naming the safety net.
    assert await monitor.step(clock, 1.0, now=_paris(2, 20, 2)) == ["open:live_absent"]
    body = spy.sent[0]["body"]
    assert "QG St Aignan 20:00-22:00" in body
    assert "carts" in body
    # Encoder finally connects → resolved.
    live = {"silence_s": "0.0", "source": "stream"}
    assert await monitor.step(live, 1.0, now=_paris(2, 20, 5)) == [
        "resolved:live_absent"
    ]
    # Slot over without encoder: no incident either.
    assert await monitor.step(clock, 1.0, now=_paris(2, 22, 30)) == []


async def test_ef01_reads_the_instant_whatever_the_container_tz(container_tz: str):
    monitor = alerts.AlertMonitor(_settings(live_grace_seconds=90), _Spy())
    # A dated live of the Agenda, on for five minutes, the encoder still absent.
    start = datetime.now(PARIS) - timedelta(minutes=5)
    monitor.live_slots = [
        alerts.DatedLiveSlot("Direct de test", start, start + timedelta(hours=1))
    ]
    clock = {"silence_s": "0.0", "source": "carts"}
    # No time given: the scheduler's loop lets the monitor read the clock.
    assert await monitor.step(clock, 1.0) == ["open:live_absent"]


def test_ef01_playout_down_does_not_double_report():
    slot = alerts.LiveSlot("x", 2, 20 * 60, 21 * 60)
    assert (
        alerts.live_slot_without_encoder([slot], None, _paris(2, 20, 10), 90.0) is None
    )


async def test_live_slots_skip_what_the_agenda_cancels_or_replaces(
    container_tz: str, raw_app: CustomQuart, dbsession: ormSession
):
    today = now_paris().date()
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=7)
    qg = Emission(
        scope="weekly",
        title="QG",
        artist="avec l'équipe",
        day_of_week=today.weekday(),
        start_minute=20 * 60,
        end_minute=22 * 60,
    )
    matinale = Emission(
        scope="weekly",
        title="Matinale",
        artist="avec l'équipe",
        day_of_week=tomorrow.weekday(),
        start_minute=8 * 60,
        end_minute=9 * 60,
    )
    dbsession.add_all([qg, matinale])
    await dbsession.flush()
    # Tonight, a dated set of the Agenda takes the place of QG; next week, a
    # dated live.
    for day, kind, title in (
        (today, "set", "Set invité"),
        (next_week, "live", "Direct spécial"),
    ):
        start = datetime.combine(day, time(20, 30), tzinfo=PARIS)
        dbsession.add(
            AgendaDiffusion(
                kind=kind,
                title=title,
                starts_at=utc_naive(start),
                ends_at=utc_naive(start + timedelta(hours=1)),
            )
        )
    # Tomorrow's Matinale is cancelled.
    cancel = {"emission_id": matinale.id, "date": tomorrow.isoformat()}
    await agenda.add_exception(dbsession, cancel)
    await dbsession.commit()
    slots = {slot.title: slot for slot in await alerts.load_live_slots(raw_app)}
    assert slots["QG"].skip_dates == {today, next_week}
    assert slots["Matinale"].skip_dates == {tomorrow}
    # The live that replaces QG next week is read, whatever the hour.
    assert isinstance(slots["Direct spécial"], alerts.DatedLiveSlot)
    assert set(slots) == {"QG", "Matinale", "Direct spécial"}


async def test_icecast_output_down_opens_and_resolves():
    spy = _Spy()
    monitor = alerts.AlertMonitor(_settings(), spy)
    ok = {
        "silence_s": "0.0",
        "source": "autodj",
        "icecast_targets": "icecast:8000/radio.mp3,radio.example:8000/radio.mp3",
        "icecast_connected": "icecast:8000/radio.mp3,radio.example:8000/radio.mp3",
        "icecast_down": "",
    }
    assert await monitor.step(ok, 1.0) == []
    lost = dict(
        ok,
        icecast_connected="icecast:8000/radio.mp3",
        icecast_down="radio.example:8000/radio.mp3",
    )
    assert await monitor.step(lost, 1.0) == ["open:icecast_down"]
    assert "radio.example:8000/radio.mp3" in spy.sent[0]["body"]
    assert await monitor.step(ok, 1.0) == ["resolved:icecast_down"]


async def test_incidents_survive_restart(tmp_path: Path):
    """An incident opened before a restart is resolved (and its task closed) after."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"token": "jwt"})
        if request.url.path.endswith("/tasks") and request.method == "PUT":
            return httpx.Response(201, json={"id": 77})
        return httpx.Response(200, json={})

    settings = _settings(
        vikunja={
            "url": "http://vikunja.local",
            "project_id": 3,
            "username": "b",
            "password": "p",
        }
    )
    state = tmp_path / "alerts.json"
    first = alerts.AlertMonitor(
        settings,
        alerts.Notifier(
            settings, httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ),
        state_path=state,
    )
    assert await first.step({"silence_s": "30", "source": "autodj"}, 1.0) == [
        "open:silence"
    ]
    assert state.exists()

    # "restart": a fresh monitor + notifier reload the disk state
    second = alerts.AlertMonitor(
        settings,
        alerts.Notifier(
            settings, httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ),
        state_path=state,
    )
    second.load_state()
    assert "silence" in second.open
    calls.clear()
    assert await second.step({"silence_s": "0", "source": "autodj"}, 1.0) == [
        "resolved:silence"
    ]
    closing = [
        c for c in calls if c.method == "POST" and c.url.path == "/api/v1/tasks/77"
    ]
    assert len(closing) == 1
    assert json.loads(closing[0].content)["done"] is True
    assert json.loads(state.read_text())["open"] == {}
