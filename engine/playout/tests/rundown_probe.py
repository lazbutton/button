"""
The probe of the rundown bench: what the conducteur says, what airs, what the
playout beats.

It runs in the network of the playout, beside the scheduler and the interface,
and reads them as they are read on a station. It writes nothing:

- the conducteur, as a console left open on it reads it: six hours of it,
  every 3 s (`line`, `read`);
- the base of the engine: the lines handed to the playout (`item`), the
  journal of the antenna (`log`), the orders sent to the playout (`order`);
- the heartbeats of the playout, as the scheduler relays them (`beat`);
- what the playout hears on its own output (`health`), and what the cleaner of
  the queues and the flushes have removed from them (`removed`).

`GET /journal?since=N` gives rundown.py what the probe has noted from its N-th
event on. Every time is in seconds since the epoch, on the clock of the bench.
Standard library only.
"""

from __future__ import annotations

import http.cookiejar
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlsplit

import rundown_seed as seed

PORT = 6899
BASE = "/data/radiotomate.db"
INTERFACE = "http://127.0.0.1:6811"
SCHEDULER = "http://127.0.0.1:6822"
PLAYOUT = "http://127.0.0.1:6833"

# A console left open on the conducteur: its horizon, and how often it reads.
HORIZON_MINUTES = 360
READ_EVERY = 3.0
# The lines noted: those the conducteur plans within this long. A line it
# plans further is not about to air.
NOTED_SECONDS = 20 * 60
# The statuses of a line the playout holds or has held: the others, planned,
# are the forecast, which the console reads.
PLANNED = ("planned", "rescue")

_lock = threading.Lock()
_events: list[dict] = []


def note(event: str, **fields) -> None:
    with _lock:
        _events.append({"t": time.time(), "ev": event, **fields})


def stamp(value: object) -> float | None:
    """A time of the engine, naive in the zone of the bench, or one of the
    API, as seconds since the epoch."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


class Quiet:
    """Notes a fault once per place and message: a service that is not up yet
    fails at every try."""

    def __init__(self) -> None:
        self.said: set[tuple[str, str]] = set()

    def __call__(self, where: str, exc: Exception) -> None:
        key = (where, repr(exc))
        if key not in self.said:
            self.said.add(key)
            note("error", where=where, error=repr(exc))


fault = Quiet()


def watch_base() -> None:
    """The lines handed to the playout, the journal of the antenna, the orders."""
    items: dict[str, tuple] = {}
    orders: dict[str, tuple] = {}
    last_log = 0
    while True:
        try:
            base = sqlite3.connect(BASE, timeout=5)
            base.row_factory = sqlite3.Row
            try:
                for row in base.execute(
                    "SELECT id, planned_at, duration, kind, when_mode, queue, resource,"
                    " status, reason, origin, cart_id FROM rundown_items"
                    " WHERE status NOT IN (?, ?)",
                    PLANNED,
                ):
                    state = (row["planned_at"], row["status"], row["reason"])
                    if items.get(row["id"]) != state:
                        items[row["id"]] = state
                        note(
                            "item",
                            id=row["id"],
                            at=stamp(row["planned_at"]),
                            duration=row["duration"],
                            kind=row["kind"],
                            when=row["when_mode"],
                            queue=row["queue"],
                            resource=row["resource"],
                            status=row["status"],
                            reason=row["reason"],
                            origin=row["origin"],
                            cart=row["cart_id"],
                        )
                for row in base.execute(
                    "SELECT id, on_air, source, artist, title, rundown_item_id,"
                    " cart_id, extra FROM metadata_log WHERE id > ? ORDER BY id",
                    (last_log,),
                ):
                    last_log = row["id"]
                    try:
                        extra = json.loads(row["extra"] or "{}")
                    except ValueError:
                        extra = {}
                    note(
                        "log",
                        id=row["id"],
                        at=stamp(row["on_air"]),
                        source=row["source"] or "",
                        artist=row["artist"] or "",
                        title=row["title"] or "",
                        item=row["rundown_item_id"],
                        cart=row["cart_id"],
                        # Written by the clock, not by the playout: the title a
                        # cut on the minute has just cut.
                        skipped=bool(extra.get("skipped")),
                    )
                for row in base.execute(
                    "SELECT id, rundown_item_id, action, queue, status, attempts,"
                    " last_error, created FROM playout_commands"
                ):
                    state = (row["status"], row["attempts"])
                    if orders.get(row["id"]) != state:
                        orders[row["id"]] = state
                        note(
                            "order",
                            id=row["id"],
                            item=row["rundown_item_id"],
                            action=row["action"],
                            queue=row["queue"],
                            status=row["status"],
                            attempts=row["attempts"],
                            error=row["last_error"],
                            created=stamp(row["created"]),
                        )
            finally:
                base.close()
        except sqlite3.Error as exc:
            fault("base", exc)
        time.sleep(0.5)


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def watch_beats(token: str) -> None:
    """Every heartbeat of the playout, as the scheduler relays it to whoever
    listens to its `GET /live`: the interface does."""
    while True:
        try:
            request = urllib.request.Request(
                f"{SCHEDULER}/live", headers={"X-Auth-Token": token}
            )
            with urllib.request.urlopen(request, timeout=30) as stream:
                # The heartbeat is a JSON over several lines, up to an empty one.
                parts: list[str] = []
                for raw in stream:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line.startswith("data: "):
                        parts = [line[6:]]
                    elif line:
                        parts.append(line)
                    elif parts:
                        try:
                            beat = json.loads("\n".join(parts))
                        except ValueError:
                            beat = None
                        parts = []
                        if isinstance(beat, dict):
                            note(
                                "beat",
                                source=str(beat.get("source") or ""),
                                title=str(beat.get("title") or ""),
                                artist=str(beat.get("artist") or ""),
                                item=beat.get("radiotomate_item_id"),
                                remaining=_number(beat.get("remaining")),
                                elapsed=_number(beat.get("elapsed")),
                                autodj=int(_number(beat.get("autodj_queued"))),
                                jingles=int(_number(beat.get("jingles_queued"))),
                                carts=int(_number(beat.get("carts_queued"))),
                            )
        except OSError as exc:
            fault("beats", exc)
            time.sleep(1.0)


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read())


def watch_health() -> None:
    """Each second: the seconds of silence the playout counts on its output,
    and what the scheduler has had removed from the queues, by its cleaner or
    by a flush."""
    removed: dict[str, int] = {}
    while True:
        try:
            health = fetch(f"{PLAYOUT}/health")
            note(
                "health",
                silence=_number(health.get("silence_s")),
                source=str(health.get("source") or ""),
            )
        except (OSError, ValueError) as exc:
            fault("health", exc)
        try:
            totals = fetch(f"{SCHEDULER}/metrics.json")["queue_clean_removed_total"]
            for queue, total in totals.items():
                if total > removed.get(queue, 0):
                    note("removed", queue=queue, count=total - removed.get(queue, 0))
                removed[queue] = total
        except (OSError, ValueError, KeyError) as exc:
            fault("metrics", exc)
        time.sleep(1.0)


def watch_conducteur() -> None:
    """As a console left open on the conducteur: logs in, then reads six hours
    of it every 3 s. Notes each line when its time or its status changes, dated
    when the console asked: the interface may take seconds to answer, and what
    it answers is no older than the question.

    The console opens at once, before the antenna starts: the interface draws
    the forecast while the scheduler draws its own, at its first tick, and only
    one of the two draws is written (FON-60)."""
    jar = http.cookiejar.CookieJar()
    console = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    logged = False
    shown: dict[str, tuple] = {}
    while True:
        started = time.time()
        try:
            if not logged:
                username, password = seed.CONSOLE
                account = {"username": username, "password": password}
                login = urllib.request.Request(
                    f"{INTERFACE}/login.json",
                    data=json.dumps(account).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with console.open(login, timeout=10):
                    logged = True
            url = f"{INTERFACE}/autodj/conducteur.json?horizon={HORIZON_MINUTES}"
            with console.open(url, timeout=30) as response:
                lines = json.loads(response.read()).get("items") or []
        except urllib.error.HTTPError as exc:
            logged = logged and exc.code != 401
            fault("conducteur", exc)
        except (OSError, ValueError) as exc:
            fault("conducteur", exc)
        else:
            now = time.time()
            read: dict[str, tuple] = {}
            for line in lines:
                at = stamp(line.get("at"))
                if at is None or at > now + NOTED_SECONDS:
                    continue
                read[str(line.get("id"))] = (at, line.get("status_code"))
                if shown.get(str(line.get("id"))) != (at, line.get("status_code")):
                    note(
                        "line",
                        t=started,
                        id=str(line.get("id")),
                        at=at,
                        status=line.get("status_code"),
                        reason=line.get("reason"),
                        resource=line.get("resource"),
                        kind=line.get("kind"),
                        queue=line.get("queue"),
                        duration=line.get("duration"),
                    )
            for gone in shown.keys() - read.keys():
                note("line", t=started, id=gone, at=None)
            shown = read
            note("read", t=started, lines=len(lines), took=round(now - started, 3))
        time.sleep(max(0.5, READ_EVERY - (time.time() - started)))


class Handler(BaseHTTPRequestHandler):
    # What the seed chose, without the token of the playout.
    plan: ClassVar[dict] = {}

    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        if url.path != "/journal":
            self.send_error(404)
            return
        try:
            since = int(parse_qs(url.query).get("since", ["0"])[0])
        except ValueError:
            since = 0
        with _lock:
            events = _events[since:]
            total = len(_events)
        now = datetime.now().astimezone()
        body = json.dumps(
            {
                "now": now.timestamp(),
                # The zone of the bench, to tell its times as the engine does.
                "offset": now.utcoffset().total_seconds(),
                "plan": self.plan,
                "events": events,
                "next": total,
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    Handler.plan = json.loads(seed.PLAN.read_text(encoding="utf-8"))
    token = Handler.plan.pop("token")
    for watch, args in (
        (watch_base, ()),
        (watch_beats, (token,)),
        (watch_health, ()),
        (watch_conducteur, ()),
    ):
        threading.Thread(target=watch, args=args, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
