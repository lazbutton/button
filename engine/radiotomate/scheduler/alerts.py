"""Antenna alerts: silence, playout unreachable, heartbeat lost, live slot empty,
Icecast output (local or public relay) disconnected, disk almost full.

Runs inside the scheduler process, polls Liquidsoap ``/health`` and the runtime
metrics, and notifies once per incident (plus a recovery note) through:

* a generic JSON webhook (``alerts.webhook_url``),
* a Vikunja task (``alerts.vikunja``: url, project_id, label_id, token *or*
  username/password),
* ntfy, a notification on a phone (``alerts.ntfy``: the topic's url, and a
  token for a protected topic),
* an e-mail (``alerts.email``: recipients, sender, SMTP server and account),
  over TLS only: implicit on port 465, STARTTLS, required, on any other.

A target that fails never stops the others. On a station, ``station config``
sets ntfy and the e-mail in ``.env``, and ``radiotomate-init`` writes them
here: the loop reads this block again when the file changes, without a restart.

Configuration (``radiotomate.yaml``)::

    alerts:
      enabled: true
      interval_seconds: 15
      silence_seconds: 20
      heartbeat_max_age_seconds: 10
      cooldown_seconds: 900
      live_grace_seconds: 90
      disk_min_free_percent: 10
      disk_min_free_gb: 10
      disk_cooldown_seconds: 86400
      webhook_url: ""
      vikunja:
        url: "http://127.0.0.1:3456"
        project_id: 1
        label_id: 0
        username: "radio-bot"
        password: "…"
      station: "radio.example"
      ntfy:
        url: "https://ntfy.sh/button-0123456789abcdef01234567"
        token: ""
      email:
        to: ["technique@radio.example"]
        from: "alertes@radio.example"
        server: "smtp.radio.example:587"
        user: "alertes@radio.example"
        password: "…"

EF-01 (``live_absent``): a weekly live slot (``Emission`` scope ``weekly``) is
on, the harbor has not connected ``live_grace_seconds`` after the slot start,
and the antenna is held by the safety net — the daypart clock (or its
fallback cart). The incident names the slot and what is actually playing, and
resolves when the encoder connects or the slot ends. Nothing is pushed: the
net is the clock, by construction, never silence.

``disk``: the disk of the sound bank, or of the engine's data, has less than
``disk_min_free_percent`` of its size free, and less than
``disk_min_free_gb`` gigabytes, as ``/system/disk.json`` measures it. It
resolves once a tenth more is free again. A disk fills for days: it reminds
once a day (``disk_cooldown_seconds``), not every ``cooldown_seconds``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import smtplib
import socket
import ssl
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from time import time

import httpx

from radiotomate.domain.emission import (
    is_harbor_source,
    minute_of_day,
    now_paris,
    weekly_contains,
)
from radiotomate.quart import ShutdownError, or_shutdown
from radiotomate.scheduler.metrics import runtime_metrics
from radiotomate.scheduler.playout import gateway_for

_log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 15.0
MIN_INTERVAL = 5.0
DEFAULT_SILENCE_SECONDS = 20.0
DEFAULT_HEARTBEAT_MAX_AGE = 10.0
DEFAULT_COOLDOWN = 900.0
DEFAULT_LIVE_GRACE = 90.0
PLAYOUT_DOWN_AFTER = 3  # consecutive failed /health polls
# Disk almost full: less than this share of the disk free, and less than this
# many gigabytes. Both, so that neither a small VPS nor a big disk alerts too
# early. Once open, the incident waits for a tenth more room to resolve.
DEFAULT_DISK_FREE_PERCENT = 10.0
DEFAULT_DISK_FREE_GB = 10.0
DISK_RESOLVE_MARGIN = 1.1
# A disk almost full stays so for days: a reminder a day, not every quarter.
DEFAULT_DISK_COOLDOWN = 86400.0
GIB = 1024**3
# SMTP: implicit TLS on this port, STARTTLS (required) on any other.
SMTPS_PORT = 465
DEFAULT_SMTP_PORT = 587
SEND_TIMEOUT = 20.0

# What a phone or an inbox shows: the incident, then its end.
HEADLINES = {
    "silence": ("Silence à l'antenne", "Le son est revenu"),
    "playout_down": ("Le playout ne répond plus", "Le playout répond de nouveau"),
    "heartbeat": ("Battement de Liquidsoap perdu", "Battement de Liquidsoap retrouvé"),
    "icecast_down": (
        "Le flux ne part plus vers Icecast",
        "Le flux repart vers Icecast",
    ),
    "live_absent": ("Direct sans encodeur", "Fin de l'alerte : direct sans encodeur"),
    "agenda": (
        "Une diffusion de l'Agenda ne peut pas passer",
        "Fin de l'alerte de l'Agenda",
    ),
    "disk": ("Disque presque plein", "Le disque a de nouveau de la place"),
}


def headline(kind: str, resolved: bool, station: str = "") -> str:
    """The title of an incident on a phone, or of its e-mail."""
    opened, closed = HEADLINES.get(kind, (kind, f"Fin de l'alerte : {kind}"))
    text = closed if resolved else opened
    return f"{text} · {station}" if station else text


def duration_label(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    if total < 60:
        return f"{total} s"
    minutes, rest = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} min {rest:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def gib_label(size: float) -> str:
    """Bytes in gigabytes, the French way, like ``station status``: 1,8 Go."""
    value = size / GIB
    text = f"{value:.1f}" if value < 10 else f"{value:.0f}"
    return text.replace(".", ",") + " Go"


def _addresses(raw) -> list[str]:
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _smtp_server(raw) -> tuple[str, int] | None:
    """``HOST`` or ``HOST:PORT``, 587 by default."""
    text = str(raw or "").strip()
    if not text:
        return None
    host, colon, port = text.rpartition(":")
    if not colon or "]" in port:
        host, port = text, str(DEFAULT_SMTP_PORT)
    host = host.strip("[]")
    try:
        number = int(port)
    except ValueError:
        return None
    if not host or not 0 < number < 65536:
        return None
    return host, number


def _ntfy_topic(raw) -> tuple[str, str] | None:
    """The server and the topic of ``https://ntfy.sh/topic``."""
    url = str(raw or "").strip().rstrip("/")
    server, slash, topic = url.rpartition("/")
    if not slash or not topic or not server.partition("://")[2]:
        return None
    return server, topic


def _float(raw, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


@dataclass
class AlertSettings:
    enabled: bool = False
    interval: float = DEFAULT_INTERVAL
    silence_seconds: float = DEFAULT_SILENCE_SECONDS
    heartbeat_max_age: float = DEFAULT_HEARTBEAT_MAX_AGE
    cooldown: float = DEFAULT_COOLDOWN
    live_grace: float = DEFAULT_LIVE_GRACE
    disk_free_percent: float = DEFAULT_DISK_FREE_PERCENT
    disk_free_gb: float = DEFAULT_DISK_FREE_GB
    disk_cooldown: float = DEFAULT_DISK_COOLDOWN
    webhook_url: str = ""
    vikunja: dict = field(default_factory=dict)
    # The station's name in the title of a notification or an e-mail: its
    # domain, on a station.
    station: str = ""
    ntfy: dict = field(default_factory=dict)
    email: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, raw) -> AlertSettings:
        raw = raw if isinstance(raw, dict) else {}

        def section(name: str) -> dict:
            value = raw.get(name)
            return dict(value) if isinstance(value, dict) else {}

        return cls(
            enabled=bool(raw.get("enabled", bool(raw))),
            interval=max(
                MIN_INTERVAL, _float(raw.get("interval_seconds"), DEFAULT_INTERVAL)
            ),
            silence_seconds=_float(raw.get("silence_seconds"), DEFAULT_SILENCE_SECONDS),
            heartbeat_max_age=_float(
                raw.get("heartbeat_max_age_seconds"), DEFAULT_HEARTBEAT_MAX_AGE
            ),
            cooldown=_float(raw.get("cooldown_seconds"), DEFAULT_COOLDOWN),
            live_grace=_float(raw.get("live_grace_seconds"), DEFAULT_LIVE_GRACE),
            disk_free_percent=_float(
                raw.get("disk_min_free_percent"), DEFAULT_DISK_FREE_PERCENT
            ),
            disk_free_gb=_float(raw.get("disk_min_free_gb"), DEFAULT_DISK_FREE_GB),
            disk_cooldown=_float(
                raw.get("disk_cooldown_seconds"), DEFAULT_DISK_COOLDOWN
            ),
            webhook_url=str(raw.get("webhook_url") or "").strip(),
            vikunja=section("vikunja"),
            station=str(raw.get("station") or "").strip(),
            ntfy=section("ntfy"),
            email=section("email"),
        )

    @property
    def ntfy_target(self) -> tuple[str, str] | None:
        """The ntfy server and topic, when set."""
        return _ntfy_topic(self.ntfy.get("url"))

    @property
    def email_target(self) -> dict | None:
        """The e-mail, when complete: recipients, sender and SMTP server."""
        recipients = _addresses(self.email.get("to"))
        server = _smtp_server(self.email.get("server"))
        sender = str(self.email.get("from") or "").strip()
        if not recipients or server is None or not sender:
            return None
        return {
            "to": recipients,
            "from": sender,
            "host": server[0],
            "port": server[1],
            "user": str(self.email.get("user") or ""),
            "password": str(self.email.get("password") or ""),
        }

    @property
    def targets(self) -> list[str]:
        names = []
        if self.webhook_url:
            names.append("webhook")
        if self.vikunja.get("url"):
            names.append("vikunja")
        if self.ntfy_target:
            names.append("ntfy")
        if self.email_target:
            names.append("e-mail")
        return names

    @property
    def has_target(self) -> bool:
        return bool(self.targets)


@dataclass
class Incident:
    kind: str
    detail: str
    opened_at: float
    notified_at: float | None = None


@dataclass(frozen=True)
class LiveSlot:
    """A weekly live window, as stored on ``Emission`` (scope ``weekly``).

    ``skip_dates``: Paris days it does not happen (cancelled in the Agenda,
    or covered by a dated broadcast).
    """

    title: str
    day_of_week: int
    start_minute: int
    end_minute: int
    skip_dates: frozenset = frozenset()

    def active(self, now: datetime) -> bool:
        if now_paris(now).date() in self.skip_dates:
            return False
        return weekly_contains(
            now, self.day_of_week, self.start_minute, self.end_minute
        )

    def elapsed_seconds(self, now: datetime) -> float:
        """Seconds since the slot started (only meaningful when active)."""
        local = now_paris(now)
        return (minute_of_day(local) - self.start_minute) * 60 + local.second

    @property
    def label(self) -> str:
        return (
            f"{self.title or 'créneau live'} "
            f"{self.start_minute // 60:02d}:{self.start_minute % 60:02d}"
            f"-{self.end_minute // 60:02d}:{self.end_minute % 60:02d}"
        )


@dataclass(frozen=True)
class DatedLiveSlot:
    """A dated live of the Agenda (aware start and end)."""

    title: str
    start: datetime
    end: datetime

    def active(self, now: datetime) -> bool:
        moment = now_paris(now)
        return self.start <= moment < self.end

    def elapsed_seconds(self, now: datetime) -> float:
        return (now_paris(now) - self.start).total_seconds()

    @property
    def label(self) -> str:
        start = now_paris(self.start)
        end = now_paris(self.end)
        return f"{self.title or 'direct'} {start:%d/%m %H:%M}-{end:%H:%M}"


def live_slot_without_encoder(
    slots: list[LiveSlot], health: dict | None, now: datetime, grace: float
) -> str | None:
    """EF-01: return the incident detail when a live slot runs without harbor."""
    if health is None:
        return None  # playout_down covers this
    source = str(health.get("source") or "")
    if is_harbor_source(source):
        return None
    for slot in slots:
        if not slot.active(now):
            continue
        if slot.elapsed_seconds(now) < grace:
            continue
        net = source or "?"
        return (
            f"EF-01 {slot.label} : encodeur absent, filet horloge à l'antenne ({net})"
        )
    return None


def disk_paths(data_root: Path | str) -> list[tuple[str, str]]:
    """The disks to watch: the sound bank, as ``/system/disk.json`` reads it,
    and the engine's data."""
    media = os.environ.get("MEDIA_ROOT", "/media").strip() or "/media"
    return [("la banque de sons", media), ("les données du moteur", str(data_root))]


def disk_almost_full(
    paths: list[tuple[str, str]],
    free_percent: float,
    free_gb: float,
    already_open: bool = False,
) -> str | None:
    """The incident detail when one of these disks is almost full: less than
    ``free_percent`` of it free, and less than ``free_gb`` gigabytes. An open
    incident waits for a tenth more room. A disk is read once, and a path that
    does not read is skipped."""
    margin = DISK_RESOLVE_MARGIN if already_open else 1.0
    seen: set[int] = set()
    for label, path in paths:
        try:
            device = Path(path).stat().st_dev
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        if device in seen or usage.total <= 0:
            continue
        seen.add(device)
        if (
            usage.free < usage.total * free_percent / 100 * margin
            and usage.free < free_gb * GIB * margin
        ):
            return (
                f"{gib_label(usage.free)} libres sur {gib_label(usage.total)},"
                f" sur le disque de {label} ({path})"
            )
    return None


class AlertMonitor:
    """Evaluate the antenna state and keep one open incident per kind."""

    def __init__(
        self,
        settings: AlertSettings,
        notifier: Notifier | None = None,
        state_path: Path | None = None,
    ):
        self.settings = settings
        self.notifier = notifier
        self.open: dict[str, Incident] = {}
        self.playout_failures = 0
        self.host = socket.gethostname()
        self.live_slots: list[LiveSlot | DatedLiveSlot] = []
        # Agenda: sets due soon that cannot play, recent misses.
        self.agenda_issues: list[str] = []
        # The disks to watch, with their label: none, unless the loop sets them.
        self.disk_paths: list[tuple[str, str]] = []
        # Open incidents (and their Vikunja tasks) survive a scheduler restart
        # so the recovery closes the right task instead of leaving it open.
        self.state_path = state_path

    def load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            _log.warning("alerts: unreadable state %s", self.state_path)
            return
        for kind, raw in (data.get("open") or {}).items():
            try:
                self.open[kind] = Incident(
                    kind=kind,
                    detail=str(raw.get("detail") or ""),
                    opened_at=float(raw.get("opened_at") or time()),
                    notified_at=(
                        float(raw["notified_at"])
                        if raw.get("notified_at") is not None
                        else None
                    ),
                )
            except (TypeError, ValueError, AttributeError):
                continue
        if self.notifier is not None:
            for kind, task_id in (data.get("vikunja_open") or {}).items():
                try:
                    self.notifier._vikunja_open[kind] = int(task_id)
                except (TypeError, ValueError):
                    continue
        if self.open:
            _log.info("alerts: %d incident(s) restored from disk", len(self.open))

    def save_state(self) -> None:
        if self.state_path is None:
            return
        payload = {
            "open": {
                kind: {
                    "detail": inc.detail,
                    "opened_at": inc.opened_at,
                    "notified_at": inc.notified_at,
                }
                for kind, inc in self.open.items()
            },
            "vikunja_open": dict(self.notifier._vikunja_open) if self.notifier else {},
        }
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload))
            tmp.replace(self.state_path)
        except OSError:
            _log.warning("alerts: cannot write state %s", self.state_path)

    # -- evaluation ------------------------------------------------------------

    def evaluate(
        self,
        health: dict | None,
        heartbeat_age: float | None,
        now: datetime | None = None,
    ) -> dict[str, str]:
        """Return the conditions currently true, keyed by kind."""
        active: dict[str, str] = {}
        # The instant, whatever the container's TZ, as the harbor's gate reads
        # the lives: the alert follows what the encoder may do.
        live_absent = live_slot_without_encoder(
            self.live_slots, health, now or now_paris(), self.settings.live_grace
        )
        if live_absent:
            active["live_absent"] = live_absent
        if self.agenda_issues:
            active["agenda"] = " · ".join(self.agenda_issues[:3])
        if health is None:
            self.playout_failures += 1
            if self.playout_failures >= PLAYOUT_DOWN_AFTER:
                active["playout_down"] = (
                    f"Liquidsoap /health injoignable ({self.playout_failures} essais)"
                )
        else:
            self.playout_failures = 0
            silence = _float(health.get("silence_s"), 0.0)
            source = str(health.get("source") or "?")
            if silence >= self.settings.silence_seconds:
                active["silence"] = f"{silence:.0f} s de silence (source {source})"
            down = [t for t in str(health.get("icecast_down") or "").split(",") if t]
            if down:
                active["icecast_down"] = "Sortie Icecast déconnectée : " + ", ".join(
                    sorted(down)
                )
        if heartbeat_age is None or heartbeat_age > self.settings.heartbeat_max_age:
            age = "jamais" if heartbeat_age is None else f"{heartbeat_age:.0f} s"
            active["heartbeat"] = f"Dernier battement Liquidsoap : {age}"
        disk = disk_almost_full(
            self.disk_paths,
            self.settings.disk_free_percent,
            self.settings.disk_free_gb,
            already_open="disk" in self.open,
        )
        if disk:
            active["disk"] = disk
        return active

    async def step(
        self,
        health: dict | None,
        heartbeat_age: float | None,
        now: datetime | None = None,
    ) -> list[str]:
        """Update incidents; returns the notifications emitted (for tests/logs)."""
        active = self.evaluate(health, heartbeat_age, now)
        now = time()
        emitted: list[str] = []
        for kind, detail in active.items():
            incident = self.open.get(kind)
            if incident is None:
                incident = Incident(kind=kind, detail=detail, opened_at=now)
                self.open[kind] = incident
            incident.detail = detail
            cooldown = (
                self.settings.disk_cooldown
                if kind == "disk"
                else self.settings.cooldown
            )
            due = incident.notified_at is None or now - incident.notified_at >= cooldown
            if due:
                incident.notified_at = now
                runtime_metrics.record_alert(kind)
                await self._notify(incident, resolved=False)
                emitted.append(f"open:{kind}")
        for kind in list(self.open):
            if kind in active:
                continue
            incident = self.open.pop(kind)
            if incident.notified_at is not None:
                await self._notify(incident, resolved=True)
                emitted.append(f"resolved:{kind}")
        if emitted:
            self.save_state()
        return emitted

    async def _notify(self, incident: Incident, *, resolved: bool) -> None:
        state = "RÉTABLI" if resolved else "ALERTE"
        title = f"[{state}] antenne {incident.kind} — {self.host}"
        lasted = time() - incident.opened_at
        body = (
            incident.detail
            if not resolved
            else (f"{incident.detail}\nDurée : {duration_label(lasted)}")
        )
        _log.warning("%s: %s", title, body.replace("\n", " | "))
        if self.notifier is None:
            return
        try:
            await self.notifier.send(
                kind=incident.kind,
                resolved=resolved,
                title=title,
                body=body,
                host=self.host,
            )
        except Exception:
            _log.exception("alert notification failed for %s", incident.kind)


class Notifier:
    """Fan-out to the webhook, Vikunja, ntfy and the e-mail. Its settings may
    change between two alerts: the loop reloads them."""

    def __init__(
        self,
        settings: AlertSettings,
        client: httpx.AsyncClient | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=10.0)
        # The certificates the SMTP server is checked against: the system's.
        self.ssl_context = ssl_context
        self._vikunja_jwt: str | None = None
        # kind -> open Vikunja task id, so the recovery closes it instead of
        # piling a second "[RÉTABLI]" task next to the alert.
        self._vikunja_open: dict[str, int] = {}

    async def send(
        self, *, kind: str, resolved: bool, title: str, body: str, host: str
    ) -> list[str]:
        """Sends to every target, each on its own: one that fails, logged,
        never stops the others. Returns the targets that failed."""
        payload = {
            "kind": kind,
            "resolved": resolved,
            "title": title,
            "body": body,
            "host": host,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        senders = {
            "webhook": self._webhook,
            "vikunja": self._vikunja,
            "ntfy": self._ntfy,
            "e-mail": self._email,
        }
        failed = []
        for name in self.settings.targets:
            try:
                await senders[name](payload)
            except Exception as error:
                failed.append(name)
                _log.warning(
                    "alerts: %s not sent through %s: %s",
                    kind,
                    name,
                    str(error) or type(error).__name__,
                )
        return failed

    def _headline(self, payload: dict) -> str:
        return headline(payload["kind"], payload["resolved"], self.settings.station)

    async def _webhook(self, payload: dict) -> None:
        response = await self.client.post(self.settings.webhook_url, json=payload)
        response.raise_for_status()

    async def _ntfy(self, payload: dict) -> None:
        """A notification on a phone: ntfy's JSON, posted to the server's root,
        carries the French title whole, where a header would not."""
        server, topic = self.settings.ntfy_target or ("", "")
        token = str(self.settings.ntfy.get("token") or "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        message = {
            "topic": topic,
            "title": self._headline(payload),
            "message": payload["body"],
            "priority": 3 if payload["resolved"] else 4,
            "tags": ["white_check_mark" if payload["resolved"] else "warning"],
        }
        response = await self.client.post(
            f"{server}/", json=message, headers=headers, timeout=SEND_TIMEOUT
        )
        response.raise_for_status()

    async def _email(self, payload: dict) -> None:
        target = self.settings.email_target
        if target is None:
            return
        station = self.settings.station
        message = EmailMessage()
        message["Subject"] = self._headline(payload)
        message["From"] = target["from"]
        message["To"] = ", ".join(target["to"])
        message["Date"] = formatdate(localtime=True)
        # Never the machine's name: getfqdn() would ask the DNS, in the loop.
        message["Message-ID"] = make_msgid(domain=station or "button.invalid")
        message.set_content(
            f"{payload['body']}\n\n"
            f"Une alerte de la station{' ' + station if station else ''}, envoyée"
            " par BUTTON. Pour ne plus la recevoir, sur la machine de la station :"
            ' station config --alert-email ""\n'
        )
        await asyncio.to_thread(self._smtp_send, target, message)

    def _smtp_send(self, target: dict, message: EmailMessage) -> None:
        context = self.ssl_context or ssl.create_default_context()
        host, port = target["host"], target["port"]
        if port == SMTPS_PORT:
            client = smtplib.SMTP_SSL(host, port, timeout=SEND_TIMEOUT, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=SEND_TIMEOUT)
        with client:
            if port != SMTPS_PORT:
                # Required: a server without it fails, nothing goes in clear.
                client.starttls(context=context)
            if target["user"]:
                client.login(target["user"], target["password"])
            client.send_message(
                message, from_addr=target["from"], to_addrs=target["to"]
            )

    async def _vikunja_headers(self, *, force_login: bool = False) -> dict:
        conf = self.settings.vikunja
        token = str(conf.get("token") or "").strip()
        if token:
            return {"Authorization": f"Bearer {token}"}
        if self._vikunja_jwt is None or force_login:
            base = str(conf["url"]).rstrip("/")
            response = await self.client.post(
                f"{base}/api/v1/login",
                json={
                    "username": conf.get("username", ""),
                    "password": conf.get("password", ""),
                    "long_token": True,
                },
            )
            response.raise_for_status()
            self._vikunja_jwt = response.json()["token"]
        return {"Authorization": f"Bearer {self._vikunja_jwt}"}

    async def _vikunja(self, payload: dict) -> None:
        conf = self.settings.vikunja
        base = str(conf["url"]).rstrip("/")
        try:
            project_id = int(conf.get("project_id") or 0)
        except (TypeError, ValueError):
            project_id = 0
        if project_id <= 0:
            return
        kind = str(payload["kind"])
        headers = await self._vikunja_headers()
        if payload["resolved"] and kind in self._vikunja_open:
            task_id = self._vikunja_open.pop(kind)
            response = await self.client.post(
                f"{base}/api/v1/tasks/{task_id}",
                json={
                    "done": True,
                    "description": payload["body"].replace("\n", "<br>"),
                },
                headers=headers,
            )
            if response.status_code < 400:
                return
            _log.warning(
                "vikunja: cannot close task %s (%s), creating a recovery task",
                task_id,
                response.status_code,
            )
        task = {
            "title": payload["title"],
            "description": payload["body"].replace("\n", "<br>"),
            "done": bool(payload["resolved"]),
        }
        response = await self.client.put(
            f"{base}/api/v1/projects/{project_id}/tasks", json=task, headers=headers
        )
        if response.status_code == 401 and not conf.get("token"):
            headers = await self._vikunja_headers(force_login=True)
            response = await self.client.put(
                f"{base}/api/v1/projects/{project_id}/tasks",
                json=task,
                headers=headers,
            )
        response.raise_for_status()
        if not payload["resolved"]:
            created_id = response.json().get("id")
            if created_id:
                self._vikunja_open[kind] = int(created_id)
        try:
            label_id = int(conf.get("label_id") or 0)
        except (TypeError, ValueError):
            label_id = 0
        if label_id > 0:
            task_id = response.json().get("id")
            if task_id:
                await self.client.put(
                    f"{base}/api/v1/tasks/{task_id}/labels",
                    json={"label_id": label_id},
                    headers=headers,
                )


async def _poll_health(app) -> dict | None:
    gateway = gateway_for(app.config["PLAYOUT_CLIENT"])
    result = await gateway.health()
    if not result.ok or not isinstance(result.payload, dict):
        return None
    return result.payload


async def load_live_slots(app) -> list[LiveSlot | DatedLiveSlot]:
    """Weekly live windows and the Agenda's dated lives (a handful of rows)."""
    from radiotomate.models.emission import Emission
    from radiotomate.services import agenda

    db = app.extensions.get("sqlalchemy")
    if db is None:
        return []
    now = now_paris()
    today = now.date()
    async with db.session() as session:
        rows = await Emission.all_weekly(session)
        blocked: set[tuple[int, date]] = set()
        dated = []
        if await agenda.agenda_enabled(session):
            # The days next_live_slot reads, today and the seven after, and one
            # more on each side: its caller reads the clock a moment before or
            # after this. The dated lives as far: a weekly show that one of them
            # replaces is skipped, and that live is the one to tell.
            blocked = await agenda.blocked_weekly_days(
                session, today - timedelta(days=1), today + timedelta(days=8)
            )
            dated = await agenda.dated_live_windows(session, now, days=8)
    slots: list[LiveSlot | DatedLiveSlot] = []
    for row in rows:
        if (
            row.day_of_week is None
            or row.start_minute is None
            or row.end_minute is None
        ):
            continue
        slots.append(
            LiveSlot(
                title=row.title,
                day_of_week=int(row.day_of_week),
                start_minute=int(row.start_minute),
                end_minute=int(row.end_minute),
                skip_dates=frozenset(
                    day for emission_id, day in blocked if emission_id == row.id
                ),
            )
        )
    for row in dated:
        slots.append(
            DatedLiveSlot(
                title=row.title,
                start=agenda.paris(row.starts_at),
                end=agenda.paris(row.ends_at),
            )
        )
    return slots


async def load_agenda_issues(app) -> list[str]:
    from radiotomate.services import agenda

    db = app.extensions.get("sqlalchemy")
    if db is None:
        return []
    async with db.session() as session:
        if not await agenda.agenda_enabled(session):
            return []
        return await agenda.agenda_issues(session, now_paris())


class ConfigWatch:
    """The ``alerts:`` block of ``radiotomate.yaml``, read again when the file
    changes: ``station config`` sets ntfy and the e-mail through
    ``radiotomate-init``, without restarting the scheduler.

    radiotomate-init writes the file in place, since nowplaying and the
    catalogue mount it alone: a write could be read half done. A change is
    read once the file has stayed the same for a whole turn of the loop."""

    def __init__(self, path: Path | None):
        self.path = path
        self.seen = self._stamp()
        self.pending: int | None = None

    def _stamp(self) -> int | None:
        if self.path is None:
            return None
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return None

    def changed(self) -> dict | None:
        """The new ``alerts:`` block, ``{}`` without one, or ``None`` when the
        file has not changed, or not settled yet."""
        stamp = self._stamp()
        if stamp is None or stamp == self.seen:
            self.pending = None
            return None
        if stamp != self.pending:
            self.pending = stamp
            return None
        self.seen = stamp
        self.pending = None
        from ruamel.yaml import YAML

        try:
            data = YAML(typ="safe").load(self.path.read_text())
        except Exception:
            _log.warning("alerts: %s does not read, settings kept", self.path)
            return None
        if not isinstance(data, dict):
            _log.warning("alerts: %s does not read, settings kept", self.path)
            return None
        raw = data.get("alerts")
        return dict(raw) if isinstance(raw, dict) else {}


def config_path(app) -> Path:
    """The engine's configuration: ``RTCONFIG``, or the one of its data."""
    raw = os.environ.get("RTCONFIG", "").strip()
    return Path(raw) if raw else Path(app.config["DATA_ROOT"]) / "radiotomate.yaml"


def _announce(settings: AlertSettings, *, reloaded: bool = False) -> None:
    if not settings.enabled:
        _log.info("alerts off%s", " (reloaded)" if reloaded else "")
        return
    _log.info(
        "alerts on%s: silence>=%.0fs heartbeat>%.0fs targets=%s",
        " (reloaded)" if reloaded else "",
        settings.silence_seconds,
        settings.heartbeat_max_age,
        ",".join(settings.targets) or "log",
    )


async def loop(app) -> None:
    settings = AlertSettings.from_config(app.config.get("ALERTS"))
    notifier = Notifier(settings)
    state_path = Path(app.config["DATA_ROOT"]) / "alerts.json"
    monitor = AlertMonitor(settings, notifier, state_path=state_path)
    monitor.disk_paths = disk_paths(app.config["DATA_ROOT"])
    if settings.enabled:
        monitor.load_state()
    watch = ConfigWatch(config_path(app))
    _announce(settings)
    while True:
        try:
            await or_shutdown(asyncio.sleep(settings.interval))
            raw = watch.changed()
            if raw is not None:
                fresh = AlertSettings.from_config(raw)
                if fresh != settings:
                    if fresh.enabled != settings.enabled:
                        # Switched on or off: nothing open survives, and a
                        # recovery never goes out for an incident of before.
                        monitor.open.clear()
                        monitor.playout_failures = 0
                        monitor.save_state()
                    settings = monitor.settings = notifier.settings = fresh
                    _announce(settings, reloaded=True)
            if not settings.enabled:
                app.extensions.pop("alert_monitor", None)
                continue
            app.extensions["alert_monitor"] = monitor
            try:
                monitor.live_slots = await load_live_slots(app)
            except Exception:
                _log.exception("alerts: cannot load live slots")
            try:
                monitor.agenda_issues = await load_agenda_issues(app)
            except Exception:
                _log.exception("alerts: cannot load agenda issues")
            health = await _poll_health(app)
            await monitor.step(health, runtime_metrics.heartbeat_age())
        except (ShutdownError, asyncio.CancelledError):
            break
        except Exception:
            _log.exception("alerts loop crashed")
