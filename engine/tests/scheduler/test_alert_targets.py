"""SUR-01: the alerts on a phone, by ntfy, and by e-mail, through a fake ntfy
and a fake SMTP server on this machine (``fake_targets.py``); the disk almost
full; and the ``alerts:`` block read again when radiotomate.yaml changes."""

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import NamedTuple

import httpx
import pytest

from radiotomate.scheduler import alerts, antenne
from radiotomate.scheduler.metrics import runtime_metrics
from tests.scheduler.fake_targets import (
    FakeNtfy,
    FakeSMTP,
    client_context,
    make_certificate,
)

GB = alerts.GIB
USER = "alertes@radio.example"
PASSWORD = "mot-de-passe-de-test"
HOOK = "http://hook.radio.example/alerte"


@pytest.fixture(scope="module")
def certificate(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    if shutil.which("openssl") is None:
        pytest.skip("openssl manque : il fait le certificat du faux serveur SMTP")
    return make_certificate(tmp_path_factory.mktemp("certificat"))


def _settings(**over) -> alerts.AlertSettings:
    raw = {"enabled": True, "station": "radio.example"}
    raw.update(over)
    return alerts.AlertSettings.from_config(raw)


def _email(port: int, **over) -> dict:
    conf = {
        "to": "technique@radio.example, direction@radio.example",
        "from": USER,
        "server": f"localhost:{port}",
        "user": USER,
        "password": PASSWORD,
    }
    conf.update(over)
    return conf


async def _send(notifier: alerts.Notifier, *, resolved: bool = False) -> list[str]:
    return await notifier.send(
        kind="silence",
        resolved=resolved,
        title="[ALERTE] antenne silence — h",
        body="25 s de silence (source autodj)" + ("\nDurée : 2 min 05 s" * resolved),
        host="h",
    )


# --- settings ---


def test_settings_read_ntfy_and_the_email():
    conf = _settings(
        ntfy={"url": "https://ntfy.sh/button-abc/", "token": "tk_x"},
        email=_email(587, server="smtp.radio.example"),
    )
    assert conf.ntfy_target == ("https://ntfy.sh", "button-abc")
    target = conf.email_target
    assert target is not None
    assert target["to"] == ["technique@radio.example", "direction@radio.example"]
    assert (target["host"], target["port"]) == ("smtp.radio.example", 587)
    assert conf.targets == ["ntfy", "e-mail"]
    assert conf.has_target

    # A server without its topic, an e-mail without its server: no target.
    lacking = _settings(ntfy={"url": "https://ntfy.sh"}, email=_email(0, server=""))
    assert lacking.ntfy_target is None
    assert lacking.email_target is None
    assert lacking.targets == []
    assert alerts._smtp_server("smtps.radio.example:465") == (
        "smtps.radio.example",
        465,
    )
    assert alerts._smtp_server("[::1]:2525") == ("::1", 2525)
    assert alerts._smtp_server("smtp.radio.example:port") is None


def test_headlines_and_durations():
    assert alerts.headline("silence", False, "radio.example") == (
        "Silence à l'antenne · radio.example"
    )
    assert alerts.headline("silence", True, "radio.example") == (
        "Le son est revenu · radio.example"
    )
    assert alerts.headline("disk", False) == "Disque presque plein"
    assert alerts.headline("autre", True) == "Fin de l'alerte : autre"
    assert alerts.duration_label(42) == "42 s"
    assert alerts.duration_label(125) == "2 min 05 s"
    assert alerts.duration_label(3 * 3600 + 7 * 60) == "3 h 07 min"
    assert alerts.gib_label(1.84 * GB) == "1,8 Go"
    assert alerts.gib_label(40 * GB) == "40 Go"


# --- ntfy ---


async def test_ntfy_gets_the_french_title_the_priority_and_the_token():
    with FakeNtfy(token="tk_jeton-de-test") as ntfy:
        settings = _settings(
            ntfy={"url": f"{ntfy.url}/button-sujet", "token": "tk_jeton-de-test"}
        )
        notifier = alerts.Notifier(settings)
        assert await _send(notifier) == []
        assert await _send(notifier, resolved=True) == []
    opened, closed = ntfy.messages
    assert opened["topic"] == "button-sujet"
    assert opened["title"] == "Silence à l'antenne · radio.example"
    assert opened["message"] == "25 s de silence (source autodj)"
    assert (opened["priority"], opened["tags"]) == (4, ["warning"])
    assert opened["authorization"] == "Bearer tk_jeton-de-test"
    assert closed["title"] == "Le son est revenu · radio.example"
    assert "Durée : 2 min 05 s" in closed["message"]
    assert (closed["priority"], closed["tags"]) == (3, ["white_check_mark"])


async def test_a_protected_topic_refuses_a_missing_token():
    with FakeNtfy(token="tk_jeton-de-test") as ntfy:
        notifier = alerts.Notifier(_settings(ntfy={"url": f"{ntfy.url}/button-sujet"}))
        assert await _send(notifier) == ["ntfy"]
    assert ntfy.messages == []


# --- e-mail ---


async def test_the_email_goes_over_starttls_with_the_account(certificate):
    with FakeSMTP("starttls", certificate) as smtp:
        notifier = alerts.Notifier(
            _settings(email=_email(smtp.port)),
            ssl_context=client_context(certificate[0]),
        )
        assert await _send(notifier) == []
        assert await _send(notifier, resolved=True) == []
    opened, closed = smtp.mails
    assert opened.tls
    assert opened.user == USER
    assert opened.sender == USER
    assert opened.recipients == ["technique@radio.example", "direction@radio.example"]
    message = opened.message
    assert message["Subject"] == "Silence à l'antenne · radio.example"
    assert message["To"] == "technique@radio.example, direction@radio.example"
    body = message.get_content()
    assert "25 s de silence (source autodj)" in body
    assert 'station config --alert-email ""' in body
    assert closed.message["Subject"] == "Le son est revenu · radio.example"
    # STARTTLS before AUTH: the password never went in clear.
    assert smtp.commands.index("STARTTLS") < smtp.commands.index("AUTH")


async def test_the_email_goes_over_tls_on_port_465(certificate, monkeypatch):
    with FakeSMTP("smtps", certificate) as smtp:
        # The fake cannot listen on 465: its port plays it.
        monkeypatch.setattr(alerts, "SMTPS_PORT", smtp.port)
        notifier = alerts.Notifier(
            _settings(email=_email(smtp.port)),
            ssl_context=client_context(certificate[0]),
        )
        assert await _send(notifier) == []
    assert smtp.mails[0].tls
    assert "STARTTLS" not in smtp.commands


async def test_a_server_without_tls_never_gets_the_password(certificate):
    with FakeSMTP("plain") as smtp:
        notifier = alerts.Notifier(
            _settings(email=_email(smtp.port)),
            ssl_context=client_context(certificate[0]),
        )
        assert await _send(notifier) == ["e-mail"]
    assert smtp.logins == []
    assert smtp.mails == []


async def test_a_wrong_password_fails_and_a_target_down_stops_nothing(certificate):
    with FakeSMTP("starttls", certificate) as smtp, FakeNtfy() as ntfy:
        ntfy.failing = True
        notifier = alerts.Notifier(
            _settings(
                ntfy={"url": f"{ntfy.url}/button-sujet"},
                email=_email(smtp.port, password="faux"),
            ),
            ssl_context=client_context(certificate[0]),
        )
        assert await _send(notifier) == ["ntfy", "e-mail"]
        # ntfy down, the e-mail goes all the same.
        notifier.settings = _settings(
            ntfy={"url": f"{ntfy.url}/button-sujet"}, email=_email(smtp.port)
        )
        assert await _send(notifier) == ["ntfy"]
    assert len(smtp.mails) == 1


# --- disk ---


class Usage(NamedTuple):
    total: int
    used: int
    free: int


async def test_a_disk_almost_full_opens_then_resolves_with_a_margin(
    tmp_path: Path, monkeypatch
):
    sizes = {"total": 50 * GB, "free": 30 * GB}

    def usage(path):
        return Usage(sizes["total"], sizes["total"] - sizes["free"], sizes["free"])

    monkeypatch.setattr(alerts.shutil, "disk_usage", usage)
    (tmp_path / "media").mkdir()
    (tmp_path / "data").mkdir()
    spy = []

    class Spy:
        async def send(self, **payload):
            spy.append(payload)

    # A target, that the spy stands for: without one, nothing goes out.
    monitor = alerts.AlertMonitor(_settings(webhook_url=HOOK), Spy())
    monitor.disk_paths = [
        ("la banque de sons", str(tmp_path / "media")),
        ("les données du moteur", str(tmp_path / "data")),
    ]
    health = {"silence_s": "0", "source": "autodj"}
    assert await monitor.step(health, 1.0) == []
    # 4 Go free: under 10 % and under 10 Go.
    sizes["free"] = 4 * GB
    assert await monitor.step(health, 1.0) == ["open:disk"]
    assert spy[0]["body"] == (
        "4,0 Go libres sur 50 Go, sur le disque de la banque de sons"
        f" ({tmp_path}/media)"
    )
    # 5,2 Go: over 10 %, but under the margin: still open, nothing sent.
    sizes["free"] = int(5.2 * GB)
    assert await monitor.step(health, 1.0) == []
    sizes["free"] = 6 * GB
    assert await monitor.step(health, 1.0) == ["resolved:disk"]


async def test_a_disk_almost_full_reminds_once_a_day_not_every_quarter(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        alerts.shutil, "disk_usage", lambda path: Usage(50 * GB, 46 * GB, 4 * GB)
    )
    spy = []

    class Spy:
        async def send(self, **payload):
            spy.append(payload["kind"])

    # A reminder at every turn for the other incidents, as a test.
    monitor = alerts.AlertMonitor(
        _settings(cooldown_seconds=0.001, webhook_url=HOOK), Spy()
    )
    monitor.disk_paths = [("la banque de sons", str(tmp_path))]
    silence = {"silence_s": "30", "source": "autodj"}
    assert sorted(await monitor.step(silence, 1.0)) == ["open:disk", "open:silence"]
    time.sleep(0.01)
    # The silence reminds; the disk, full for days, waits a day.
    assert await monitor.step(silence, 1.0) == ["open:silence"]
    assert alerts.AlertSettings.from_config({}).disk_cooldown == 86400
    monitor.open["disk"].notified_at -= 86400
    time.sleep(0.01)
    assert await monitor.step(silence, 1.0) == ["open:silence", "open:disk"]


def test_a_big_disk_with_room_does_not_alert(tmp_path: Path, monkeypatch):
    # 2 To, 150 Go free: under 10 %, but far over 10 Go.
    monkeypatch.setattr(
        alerts.shutil, "disk_usage", lambda path: Usage(2000 * GB, 1850 * GB, 150 * GB)
    )
    paths = [("la banque de sons", str(tmp_path))]
    assert alerts.disk_almost_full(paths, 10, 10) is None
    # A small disk: 1 Go free of 20.
    monkeypatch.setattr(
        alerts.shutil, "disk_usage", lambda path: Usage(20 * GB, 19 * GB, 1 * GB)
    )
    assert alerts.disk_almost_full(paths, 10, 10).startswith("1,0 Go libres sur 20 Go")
    # A path that does not read is skipped.
    assert alerts.disk_almost_full([("rien", str(tmp_path / "absent"))], 10, 10) is None


def test_the_disks_are_the_bank_and_the_data(monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", "/banque")
    assert alerts.disk_paths(Path("/data")) == [
        ("la banque de sons", "/banque"),
        ("les données du moteur", "/data"),
    ]


# --- radiotomate.yaml read again ---


def _write(path: Path, text: str) -> None:
    path.write_text(text)
    # A new modification time, whatever the file system's resolution.
    stamp = time.time_ns() + 10_000_000
    os.utime(path, ns=(stamp, stamp))


def test_a_change_is_read_once_the_file_settles(tmp_path: Path):
    config = tmp_path / "radiotomate.yaml"
    _write(config, "data:\n  root: /data\n")
    watch = alerts.ConfigWatch(config)
    assert watch.changed() is None
    _write(config, "alerts:\n  ntfy:\n    url: https://ntfy.sh/button-abc\n")
    # Seen moving: read on the next turn, if it has not moved again.
    assert watch.changed() is None
    assert watch.changed() == {"ntfy": {"url": "https://ntfy.sh/button-abc"}}
    assert watch.changed() is None
    # Half written: kept as it was, and said.
    _write(config, "alerts: [\n")
    assert watch.changed() is None
    assert watch.changed() is None
    # The block gone: no alerts.
    _write(config, "data:\n  root: /data\n")
    watch.changed()
    assert watch.changed() == {}
    # A word in place of the block (SUR-04): off, as the block would say.
    _write(config, "alerts: off\n")
    watch.changed()
    assert alerts.AlertSettings.from_config(watch.changed()).enabled is False
    # No file: nothing to read.
    assert alerts.ConfigWatch(tmp_path / "absent.yaml").changed() is None


# --- the loop, as on a bench ---


class _App:
    """What the alerts' loop reads of the scheduler: its config, its playout."""

    def __init__(self, data_root: Path, raw_alerts: dict, health: dict):
        self.health = health

        def playout(request: httpx.Request) -> httpx.Response:
            # Liquidsoap answers, and its heartbeat goes on.
            runtime_metrics.heartbeat()
            return httpx.Response(200, json=self.health)

        self.config = {
            "ALERTS": raw_alerts,
            "DATA_ROOT": data_root,
            "PLAYOUT_CLIENT": httpx.AsyncClient(
                transport=httpx.MockTransport(playout), base_url="http://playout"
            ),
        }
        self.extensions: dict = {}


async def _until(check, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < deadline, "rien n'est arrivé à temps"
        await asyncio.sleep(0.02)


@pytest.fixture
def quick_loop(monkeypatch, tmp_path: Path):
    """The loop turns every 50 ms, its disks are none of this machine's, and
    it stops with the test."""

    async def plain(coro):
        return await coro

    monkeypatch.setattr(alerts, "MIN_INTERVAL", 0.05)
    monkeypatch.setattr(alerts, "DEFAULT_INTERVAL", 0.05)
    monkeypatch.setattr(alerts, "or_shutdown", plain)
    monkeypatch.setattr(alerts, "disk_paths", lambda data_root: [])
    monkeypatch.setenv("RTCONFIG", str(tmp_path / "radiotomate.yaml"))


async def test_a_silence_sends_ntfy_and_an_email_then_a_note_when_the_sound_returns(
    certificate, quick_loop, tmp_path: Path, monkeypatch
):
    """The bench of the fiche: a silence sends an alert by ntfy and an e-mail,
    then a note when the sound returns."""
    silence = {"silence_s": "30.0", "source": "autodj"}
    with FakeSMTP("starttls", certificate) as smtp, FakeNtfy() as ntfy:
        raw = {
            "interval_seconds": 0.05,
            "station": "radio.example",
            "ntfy": {"url": f"{ntfy.url}/button-sujet"},
            "email": _email(smtp.port),
        }
        app = _App(tmp_path, raw, silence)
        original = alerts.Notifier.__init__

        def trusting(self, settings, client=None, ssl_context=None):
            original(self, settings, client, client_context(certificate[0]))

        monkeypatch.setattr(alerts.Notifier, "__init__", trusting)
        task = asyncio.create_task(alerts.loop(app))
        try:
            await _until(lambda: ntfy.messages and smtp.mails)
            assert ntfy.messages[0]["title"] == "Silence à l'antenne · radio.example"
            assert smtp.mails[0].message["Subject"] == (
                "Silence à l'antenne · radio.example"
            )
            assert "silence" in app.extensions["alert_monitor"].open
            app.health = {"silence_s": "0.0", "source": "autodj"}
            await _until(lambda: len(ntfy.messages) == 2 and len(smtp.mails) == 2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert ntfy.messages[1]["title"] == "Le son est revenu · radio.example"
    assert smtp.mails[1].message["Subject"] == "Le son est revenu · radio.example"
    assert "Durée : " in smtp.mails[1].message.get_content()
    # Once each: the cooldown holds the rest.
    assert len(ntfy.messages) == 2
    assert len(smtp.mails) == 2


def _on_the_page(app) -> list[str]:
    """The incidents /antenne/state.json gives the Antenne page."""
    return [row["kind"] for row in antenne.incidents_state(app)]


async def test_the_loop_takes_new_targets_without_a_restart(quick_loop, tmp_path: Path):
    """SUR-04: no alerts: block, as radiotomate install leaves it. The silence
    shows on the Antenne page, and goes nowhere else. station config sets ntfy,
    radiotomate-init writes it: the silence still open goes out on the next
    turn, without a restart. ntfy gone, the end of the silence goes nowhere."""
    config = tmp_path / "radiotomate.yaml"
    _write(config, "data:\n  root: /data\n")
    with FakeNtfy() as ntfy:
        app = _App(tmp_path, {}, {"silence_s": "30.0", "source": "autodj"})
        task = asyncio.create_task(alerts.loop(app))
        try:
            await _until(lambda: _on_the_page(app) == ["silence"])
            await asyncio.sleep(0.3)
            assert ntfy.messages == []
            enabled = (
                "data:\n  root: /data\nalerts:\n  interval_seconds: 0.05\n"
                f"  ntfy:\n    url: {ntfy.url}/button-sujet\n"
            )
            _write(config, enabled)
            await _until(lambda: ntfy.messages)
            assert ntfy.messages[0]["title"] == "Silence à l'antenne"
            # ntfy gone: the monitor stays, and the end of the silence, seen
            # on the page, goes nowhere.
            monitor = app.extensions["alert_monitor"]
            _write(config, "data:\n  root: /data\n")
            await _until(lambda: not monitor.settings.has_target)
            app.health = {"silence_s": "0.0", "source": "autodj"}
            await _until(lambda: _on_the_page(app) == [])
            assert app.extensions["alert_monitor"] is monitor
            await asyncio.sleep(0.3)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert len(ntfy.messages) == 1


async def test_enabled_false_switches_the_watch_off_and_on_without_a_restart(
    quick_loop, tmp_path: Path
):
    """ADR 0009: ``alerts.enabled: false`` switches the monitor off, the
    incidents of the Antenne page with it, and none comes back with a restart;
    the line gone, it watches again, without a restart."""
    config = tmp_path / "radiotomate.yaml"
    off = "data:\n  root: /data\nalerts:\n  enabled: false\n"
    _write(config, off)
    app = _App(tmp_path, {"enabled": False}, {"silence_s": "30.0", "source": "autodj"})
    task = asyncio.create_task(alerts.loop(app))
    try:
        await asyncio.sleep(0.3)
        assert "alert_monitor" not in app.extensions
        assert _on_the_page(app) == []
        _write(config, "data:\n  root: /data\n")
        await _until(lambda: _on_the_page(app) == ["silence"])
        _write(config, off)
        await _until(lambda: "alert_monitor" not in app.extensions)
        assert _on_the_page(app) == []
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    state = json.loads((tmp_path / "alerts.json").read_text())
    assert state["open"] == {}
