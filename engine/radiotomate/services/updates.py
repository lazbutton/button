"""
The updates of the station, asked from the console (MAJ-07).

The console never drives Docker (``docs/decisions/0004``): its button writes a
request here, in the data folder, and the station command, on the host, reads it
every minute through ``docker compose exec`` (``radiotomate maintenance updates``),
runs ``station update``, then writes the result the same way. The host also tells
what only it knows: ``HOLD``, its ``updates.log``, and whether it takes the requests
of the console at all.

What the page shows of the versions comes from GitHub: the release marked latest,
the one ``station update`` installs without options, and the notes of each version
between the installed one and it.

The files, in ``DATA_ROOT/updates``, written by the interface and by the command,
both as the engine's user, each by a rename, under a lock:

* ``request.json``: the request still open, ``pending`` or ``running``; absent
  otherwise. The host only looks at this path, every minute, before asking more.
* ``last.json``: the last closed request, with its result.
* ``host.json``: what the station command said last, and when.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from radiotomate.domain.agenda import iso_paris
from radiotomate.domain.errors import DomainConflict

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_log = logging.getLogger(__name__)

FOLDER = "updates"
REQUEST = "request.json"
LAST = "last.json"
HOST = "host.json"
LOCK = ".lock"

# The repository whose releases the station command installs, unless the host
# names another one: BUTTON_REPO, for a fork.
REPOSITORY = "lazbutton/button"
GITHUB_API = "https://api.github.com"
# The releases read again after this long; a failure sooner. The page may ask
# again, but not more than once a minute: unauthenticated, GitHub allows 60
# calls an hour.
FRESH_S = 30 * 60
FAILED_S = 5 * 60
FORCED_S = 60
# How long a read of the page waits for GitHub: under the console's 10 s.
WAIT_S = 4.0
HTTP_TIMEOUT_S = 8.0
# The versions whose notes the page shows, at most.
NOTES_MAX = 10
NOTES_CHARS = 20_000

# The host tells its state at least every hour, and within a minute of a
# change: past this, it has stopped answering.
HOST_SILENT = timedelta(hours=2)
# A pending request the host has not even looked at by then: its timer does
# not run.
UNSEEN = timedelta(minutes=3)

STATES = ("pending", "running")
# How a request ends: done, rolled back by the update itself, failed (before
# its files, nothing changed; after, the station is to repair), refused by the
# host (HOLD, a restore not finished, a major), nothing to do, withdrawn from
# the console, or interrupted (the host stopped during the update).
RESULTS = (
    "done",
    "rolled_back",
    "failed",
    "refused",
    "up_to_date",
    "withdrawn",
    "interrupted",
)

VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
REQUEST_ID = re.compile(r"[0-9a-f]{12}")
# The versions of updates.log and of BUTTON_VERSION: X.Y.Z, or main.
LOG_VERSION = re.compile(r"main|(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
REPO_NAME = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")
TEXT_CHARS = 2000
# updates.log, as the station command writes it: what each result says.
LOG_RESULTS = {
    "faite": "done",
    "arrêtée": "stopped",
    "annulée": "rolled_back",
    "échouée": "failed",
    "retour arrière": "rollback",
    "retour arrière échoué": "rollback_failed",
}


class UpdateBlocked(DomainConflict):
    """Why the button does not ask now: 409, with a code of its own."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _paris(value: object) -> str | None:
    instant = _instant(value)
    return iso_paris(instant) if instant else None


def _text(value: object, limit: int = TEXT_CHARS) -> str | None:
    """A text of the host or of the engine, without what a page would not show."""
    if not isinstance(value, str):
        return None
    cleaned = "".join(
        char for char in value if char in "\n\t" or (ord(char) >= 32 and char != "\x7f")
    ).strip()
    return cleaned[:limit] or None


def parse_version(value: object) -> tuple[int, int, int] | None:
    """X.Y.Z in numbers, or None: 0.10.0 comes after 0.9.0."""
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        return None
    major, minor, patch = (int(part) for part in value.split("."))
    return major, minor, patch


# --- The files ---


def folder(data_root: Path) -> Path:
    return data_root / FOLDER


@contextlib.contextmanager
def locked(data_root: Path) -> Iterator[Path]:
    """The folder, for one writer at a time: the interface or the command."""
    path = folder(data_root)
    path.mkdir(mode=0o755, exist_ok=True)
    with (path / LOCK).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield path
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _read(path: Path) -> dict | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        _log.warning("updates: %s unreadable", path)
        return None
    return raw if isinstance(raw, dict) else None


def _write(path: Path, value: dict | None) -> None:
    """Replaced at once, or removed: never half written."""
    if value is None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        return
    part = path.with_name(f".{path.name}.{os.getpid()}")
    part.write_text(
        json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    part.chmod(0o644)
    part.replace(path)


def read_request(data_root: Path) -> dict | None:
    """The open request, checked: anything else counts as none."""
    raw = _read(folder(data_root) / REQUEST)
    if (
        raw is None
        or not isinstance(raw.get("id"), str)
        or not REQUEST_ID.fullmatch(raw["id"])
        or raw.get("state") not in STATES
        or _instant(raw.get("requested_at")) is None
    ):
        return None
    return raw


def read_last(data_root: Path) -> dict | None:
    raw = _read(folder(data_root) / LAST)
    if raw is None or raw.get("result") not in RESULTS:
        return None
    return raw


def read_host(data_root: Path) -> dict | None:
    raw = _read(folder(data_root) / HOST)
    if raw is None or _instant(raw.get("seen_at")) is None:
        return None
    return raw


# --- What the host says ---


def parse_log_line(line: str) -> dict | None:
    """A line of updates.log: the time of its start, in seconds since 1970, the
    version of before, the new one, the result, the backup, and the rest."""
    fields = line.rstrip("\n").split("\t")
    if len(fields) < 4 or not fields[0].isdigit():
        return None
    started = datetime.fromtimestamp(int(fields[0]), UTC)
    before, after, result = fields[1], fields[2], fields[3]
    if not LOG_VERSION.fullmatch(before) or not LOG_VERSION.fullmatch(after):
        return None
    return {
        "started_at": iso_paris(started),
        "from": before,
        "to": after,
        "result": LOG_RESULTS.get(result, "other"),
        "label": _text(result, 80),
        "detail": _text(fields[5] if len(fields) > 5 else "", 500),
    }


def host_state(raw: dict, now: datetime | None = None) -> dict:
    """What the station command sends, as the engine keeps it: checked, each
    text cleaned, the lines of updates.log read, the newest first."""
    lines = raw.get("updates")
    history = [
        entry
        for entry in (
            parse_log_line(line)
            for line in (lines if isinstance(lines, list) else [])
            if isinstance(line, str)
        )
        if entry is not None
    ]
    history.reverse()
    version = raw.get("version")
    command = raw.get("command")
    repo = raw.get("repo")
    nightly = raw.get("nightly")
    time_of_day = raw.get("time")
    zone = raw.get("zone")
    return {
        "seen_at": _iso(now or _now()),
        "requests": raw.get("requests") != "no",
        "version": version
        if isinstance(version, str) and LOG_VERSION.fullmatch(version)
        else None,
        "command": command
        if isinstance(command, str) and LOG_VERSION.fullmatch(command)
        else None,
        "repo": repo
        if isinstance(repo, str) and REPO_NAME.fullmatch(repo)
        else REPOSITORY,
        "hold": _text(raw.get("hold")),
        "history": history[:10],
        "nightly": nightly if nightly in ("auto", "manual") else None,
        "time": time_of_day
        if isinstance(time_of_day, str)
        and re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", time_of_day)
        else None,
        "zone": zone
        if isinstance(zone, str) and re.fullmatch(r"[A-Za-z0-9_+/-]{1,64}", zone)
        else None,
    }


# --- The request ---


def _close(
    path: Path, request: dict, result: str, detail: str | None, **extra: Any
) -> dict:
    closed = {
        **request,
        "result": result,
        "detail": _text(detail),
        "finished_at": _iso(_now()),
        **extra,
    }
    closed.pop("state", None)
    _write(path / LAST, closed)
    _write(path / REQUEST, None)
    return closed


def ask(
    data_root: Path, username: str, target: str | None, installed: str | None
) -> dict:
    """A new request, pending: nothing open before it."""
    with locked(data_root) as path:
        if read_request(data_root) is not None:
            raise UpdateBlocked(
                "open", "Une mise à jour est déjà demandée : la page suit celle-là."
            )
        request = {
            "id": secrets.token_hex(6),
            "state": "pending",
            "requested_at": _iso(_now()),
            "requested_by": username,
            "from": installed,
            "target": target,
            "waiting": None,
            "seen_at": None,
            "started_at": None,
        }
        _write(path / REQUEST, request)
        return request


def withdraw(data_root: Path, username: str) -> dict:
    """A pending request withdrawn from the console. Once running, too late."""
    with locked(data_root) as path:
        request = read_request(data_root)
        if request is None:
            raise UpdateBlocked("none", "Aucune mise à jour n'est demandée.")
        if request["state"] == "running":
            raise UpdateBlocked(
                "running",
                "La mise à jour a commencé sur la machine : elle ne s'arrête plus"
                " d'ici.",
            )
        return _close(path, request, "withdrawn", f"Retirée par {username}.")


def record_host(data_root: Path, raw: dict) -> dict | None:
    """What the host says, kept; a pending request closed if the host no longer
    takes the requests of the console. The open request, after."""
    with locked(data_root) as path:
        state = host_state(raw)
        _write(path / HOST, state)
        request = read_request(data_root)
        if request is None:
            return None
        request["seen_at"] = state["seen_at"]
        if not state["requests"] and request["state"] == "pending":
            _close(
                path,
                request,
                "refused",
                "Les demandes de la console sont coupées sur la machine.",
            )
            return None
        _write(path / REQUEST, request)
        return request


def _open(data_root: Path, request_id: str) -> dict | None:
    request = read_request(data_root)
    if request is None or request["id"] != request_id:
        return None
    return request


def wait(data_root: Path, request_id: str, reason: str) -> bool:
    """The request waits, and why: the antenna, another command of the host.
    One that had started goes back to pending."""
    with locked(data_root) as path:
        request = _open(data_root, request_id)
        if request is None:
            return False
        request.update(
            state="pending",
            started_at=None,
            waiting=_text(reason, 500),
            seen_at=_iso(_now()),
        )
        _write(path / REQUEST, request)
        return True


def start(data_root: Path, request_id: str) -> bool:
    """The host starts the update: only a request still pending."""
    with locked(data_root) as path:
        request = _open(data_root, request_id)
        if request is None or request["state"] != "pending":
            return False
        now = _iso(_now())
        request.update(state="running", started_at=now, seen_at=now, waiting=None)
        _write(path / REQUEST, request)
        return True


def finish(
    data_root: Path,
    request_id: str,
    result: str,
    detail: str,
    versions: tuple[str | None, str | None] = (None, None),
) -> bool:
    """The host closes the request, with its result, and the versions the
    station went from and to, when it updated."""
    if result not in RESULTS:
        raise ValueError(result)
    before, after = (
        value if value and LOG_VERSION.fullmatch(value) else None for value in versions
    )
    with locked(data_root) as path:
        request = _open(data_root, request_id)
        if request is None:
            return False
        _close(path, request, result, detail, went_from=before, went_to=after)
        return True


# --- The releases, from GitHub ---


@dataclass
class Releases:
    """What GitHub said last, for one repository."""

    latest: dict | None = None
    others: list[dict] = field(default_factory=list)
    error: str | None = None
    checked_at: datetime | None = None
    fetched: float = 0.0
    task: asyncio.Task | None = None


_releases: dict[str, Releases] = {}


def forget_releases() -> None:
    """For the tests: GitHub is asked again."""
    _releases.clear()


def _release(raw: object) -> dict | None:
    if not isinstance(raw, dict) or raw.get("draft") or raw.get("prerelease"):
        return None
    tag = raw.get("tag_name")
    version = tag[1:] if isinstance(tag, str) and tag.startswith("v") else None
    if parse_version(version) is None:
        return None
    url = raw.get("html_url")
    return {
        "version": version,
        "published_at": _paris(raw.get("published_at")),
        "url": url if isinstance(url, str) and url.startswith("https://") else None,
        "notes": _text(raw.get("body"), NOTES_CHARS),
    }


async def _fetch(
    repo: str, transport: httpx.AsyncBaseTransport | None
) -> tuple[dict, list[dict]]:
    from radiotomate.version import get_version

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"BUTTON/{get_version()} ( https://github.com/{REPOSITORY} )",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(
        base_url=GITHUB_API,
        headers=headers,
        timeout=HTTP_TIMEOUT_S,
        transport=transport,
    ) as client:
        answer = await client.get(f"/repos/{repo}/releases/latest")
        if answer.status_code == 404:
            raise LookupError("aucune version publiée")
        answer.raise_for_status()
        latest = _release(answer.json())
        if latest is None:
            raise ValueError("la dernière version publiée ne se lit pas")
        others: list[dict] = []
        # The notes of the versions in between: without them, the latest's only.
        with contextlib.suppress(httpx.HTTPError, ValueError):
            listed = await client.get(
                f"/repos/{repo}/releases", params={"per_page": 30}
            )
            listed.raise_for_status()
            items = listed.json()
            others = [
                release
                for release in (
                    _release(item)
                    for item in (items if isinstance(items, list) else [])
                )
                if release is not None
            ]
        return latest, others


def _error(caught: BaseException) -> str:
    if isinstance(caught, LookupError):
        return "GitHub n'a aucune version publiée de BUTTON"
    if isinstance(caught, httpx.HTTPStatusError):
        status = caught.response.status_code
        if status in (403, 429):
            return (
                "GitHub limite les demandes de cette machine : réessaie dans une heure"
            )
        return f"GitHub répond {status}"
    if isinstance(caught, httpx.TimeoutException):
        return "GitHub ne répond pas à temps"
    if isinstance(caught, httpx.HTTPError):
        return "GitHub ne répond pas : la machine n'y a peut-être pas accès"
    return "la réponse de GitHub ne se lit pas"


async def releases(
    repo: str,
    *,
    refresh: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Releases:
    """What GitHub says of the releases, asked again when it is old, or on
    ``refresh``, once a minute at most. The answer waits a few seconds: past
    that, the page reads it on its next poll."""
    entry = _releases.setdefault(repo, Releases())
    age = time.monotonic() - entry.fetched
    stale = entry.checked_at is None or age > (FAILED_S if entry.error else FRESH_S)
    if (stale or (refresh and age > FORCED_S)) and (
        entry.task is None or entry.task.done()
    ):

        async def ask_github() -> None:
            try:
                latest, others = await _fetch(repo, transport)
            # Whatever goes wrong, the page says it, and the task ends.
            except Exception as caught:
                _log.warning("updates: GitHub, %s", caught)
                entry.error = _error(caught)
            else:
                entry.latest, entry.others, entry.error = latest, others, None
            entry.checked_at = _now()
            entry.fetched = time.monotonic()

        entry.task = asyncio.ensure_future(ask_github())
    if entry.task is not None and not entry.task.done():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(entry.task), WAIT_S)
    return entry


# --- What the page shows ---


def major_action(notes: str | None) -> str | None:
    """The paragraph « Mise en service » of a version's notes, as the station
    command cites it before a major (major_action, in deploy/station)."""
    if not notes:
        return None
    lines: list[str] = []
    fenced = found = False
    for line in notes.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        if fenced:
            continue
        if not found and line.startswith("**Mise en service.**"):
            found = True
            lines.append(line.removeprefix("**Mise en service.**").strip())
        elif found and not line.strip():
            break
        elif found:
            lines.append(line)
    return _text("\n".join(lines)) if found else None


def between(
    installed: str | None, latest: dict | None, others: list[dict]
) -> list[dict]:
    """The versions the update brings, the newest first: above the installed
    one, up to the latest. Without a version to compare, the latest alone."""
    if latest is None:
        return []
    top = parse_version(latest["version"])
    low = parse_version(installed)
    found = {latest["version"]: latest}
    if low is not None:
        for release in others:
            number = parse_version(release["version"])
            if number is not None and low < number <= top:
                found.setdefault(release["version"], release)
    chosen = sorted(
        found.values(),
        key=lambda release: parse_version(release["version"]),
        reverse=True,
    )
    if low is not None:
        chosen = [
            release for release in chosen if parse_version(release["version"]) > low
        ]
    result = []
    for release in chosen[:NOTES_MAX]:
        number = parse_version(release["version"])
        major = low is not None and number[0] > low[0] and number[1:] == (0, 0)
        result.append(
            {
                **release,
                "major": major,
                "action": major_action(release.get("notes")) if major else None,
            }
        )
    return result


# Why the button cannot ask now, by code: what the page says, and does.
BLOCKED = {
    "open": "Une mise à jour est déjà demandée : la page la suit.",
    "no_host": (
        "La machine ne prend pas encore les demandes de la console : la station"
        " n'a pas été installée par la commande station, ou sa commande date"
        " d'avant ce bouton. Sur la machine : sudo station update, une fois."
    ),
    "requests_off": (
        "Les demandes de la console sont coupées sur la machine. Pour les"
        " rallumer : sudo station config --console-requests yes."
    ),
    "host_silent": (
        "La machine ne donne plus de nouvelles depuis le {seen} : son minuteur ne"
        " tourne peut-être plus. Sur la machine : sudo station status."
    ),
    "hold": (
        "Les mises à jour sont bloquées sur la machine (HOLD). Pour les"
        " débloquer, une fois la cause réglée : sudo station unhold."
    ),
    "main": (
        "La station suit main, pour un essai : elle se met à jour à la main, sur"
        " la machine."
    ),
    "unknown_version": (
        "La version de la station ne se lit pas : sudo station status, sur la"
        " machine."
    ),
    "latest_pending": (
        "La dernière version se lit encore sur GitHub : réessaie dans un instant."
    ),
    "latest_unknown": "La dernière version ne se lit pas : {error}.",
    "up_to_date": "La station est à jour : {installed}, la plus haute version publiée.",
    "major": (
        "La mise à jour passe la {major}, une version majeure : elle demande une"
        " action à la station avant de la prendre, et ne part pas d'ici. Une"
        " fois l'action faite, sur la machine : sudo station update --major."
    ),
}


def _blocker_code(  # noqa: PLR0913
    request: dict | None,
    host: dict | None,
    installed: str | None,
    latest: dict | None,
    error: str | None,
    now: datetime,
) -> str | None:
    seen = _instant(host.get("seen_at")) if host else None
    current = parse_version(installed)
    checks = (
        ("open", request is not None),
        ("no_host", host is None),
        ("requests_off", host is not None and not host.get("requests", True)),
        ("host_silent", seen is None or now - seen > HOST_SILENT),
        ("hold", bool(host and host.get("hold"))),
        ("main", installed == "main"),
        ("unknown_version", current is None),
        ("latest_pending", latest is None and error is None),
        ("latest_unknown", latest is None),
    )
    for code, applies in checks:
        if applies:
            return code
    newest = parse_version(latest["version"])
    if newest <= current:
        return "up_to_date"
    return "major" if newest[0] > current[0] else None


def blocker(  # noqa: PLR0913
    *,
    request: dict | None,
    host: dict | None,
    installed: str | None,
    latest: dict | None,
    error: str | None,
    now: datetime | None = None,
) -> tuple[str, str] | None:
    """Why the button cannot ask now, as a code and a sentence, or None."""
    code = _blocker_code(request, host, installed, latest, error, now or _now())
    if code is None:
        return None
    seen = _instant(host.get("seen_at")) if host else None
    message = BLOCKED[code].format(
        seen=_wall(seen),
        error=error,
        installed=installed,
        major=first_major(installed, latest),
    )
    return ("latest_unknown" if code == "latest_pending" else code), message


def first_major(installed: str | None, latest: dict | None) -> str | None:
    """The first major the update to the latest goes through, as the station
    command counts them (update_major): X.0.0, above the installed one."""
    current = parse_version(installed)
    newest = parse_version(latest["version"]) if latest else None
    if current is None or newest is None or newest[0] <= current[0]:
        return None
    return f"{current[0] + 1}.0.0"


def _wall(value: datetime | None) -> str:
    if value is None:
        return "?"
    return datetime.fromisoformat(iso_paris(value)).strftime("%d/%m/%Y à %H:%M")


def installed_version(host: dict | None, recorded: dict) -> str | None:
    """BUTTON_VERSION, as the host said it last, or as versions.json has it."""
    if host and host.get("version"):
        return host["version"]
    version = recorded.get("version")
    return (
        version if isinstance(version, str) and LOG_VERSION.fullmatch(version) else None
    )


def request_view(request: dict | None, now: datetime | None = None) -> dict | None:
    if request is None:
        return None
    now = now or _now()
    requested = _instant(request.get("requested_at"))
    seen = _instant(request.get("seen_at"))
    # The host looks at a pending request every minute: untouched for minutes,
    # its timer does not run.
    touched = (
        max(value for value in (requested, seen) if value is not None)
        if requested
        else None
    )
    unseen = (
        request["state"] == "pending" and touched is not None and now - touched > UNSEEN
    )
    return {
        "id": request["id"],
        "state": request["state"],
        "requested_at": _paris(request.get("requested_at")),
        "requested_by": _text(request.get("requested_by"), 64),
        "from": request.get("from"),
        "target": request.get("target"),
        "waiting": _text(request.get("waiting"), 500),
        "started_at": _paris(request.get("started_at")),
        "seen_at": _paris(request.get("seen_at")),
        "unseen": unseen,
    }


def last_view(last: dict | None) -> dict | None:
    if last is None:
        return None
    return {
        "id": last.get("id"),
        "result": last["result"],
        "detail": _text(last.get("detail")),
        "requested_at": _paris(last.get("requested_at")),
        "requested_by": _text(last.get("requested_by"), 64),
        "finished_at": _paris(last.get("finished_at")),
        "from": last.get("went_from") or last.get("from"),
        "to": last.get("went_to") or last.get("target"),
    }


def host_view(host: dict | None) -> dict | None:
    if host is None:
        return None
    return {
        "seen_at": _paris(host.get("seen_at")),
        "requests": bool(host.get("requests", True)),
        "command": host.get("command"),
        "hold": host.get("hold"),
        "nightly": host.get("nightly"),
        "time": host.get("time"),
        "zone": host.get("zone"),
    }


def view(  # noqa: PLR0913
    *,
    host: dict | None,
    recorded: dict,
    found: Releases,
    request: dict | None,
    last: dict | None,
    now: datetime | None = None,
) -> dict:
    """GET /system/updates.json: the versions, the request, what the host says,
    and why the button cannot ask, when it cannot."""
    installed = installed_version(host, recorded)
    blocked = blocker(
        request=request,
        host=host,
        installed=installed,
        latest=found.latest,
        error=found.error,
        now=now,
    )
    brought = between(installed, found.latest, found.others)
    major = first_major(installed, found.latest)
    major_release = next((item for item in brought if item["version"] == major), None)
    repo = host["repo"] if host and host.get("repo") else REPOSITORY
    return {
        "installed": installed,
        "recorded_at": recorded.get("recorded_at"),
        "services": recorded.get("services", []),
        "latest": found.latest["version"] if found.latest else None,
        "check": {
            "at": iso_paris(found.checked_at) if found.checked_at else None,
            "error": found.error,
            "pending": found.task is not None and not found.task.done(),
        },
        "releases": brought,
        "major": {
            "version": major,
            "action": major_release["action"] if major_release else None,
            "url": f"https://github.com/{repo}/releases/tag/v{major}",
        }
        if major
        else None,
        "host": host_view(host),
        "history": host.get("history", []) if host else [],
        "request": request_view(request, now),
        "last": last_view(last),
        "blocked": {"code": blocked[0], "message": blocked[1]} if blocked else None,
    }
