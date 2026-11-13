#!/usr/bin/env python3
"""
The rundown bench: the real scheduler and the real interface hold the antenna
before the Liquidsoap of the playout image, and the bench compares what the
conducteur says to what airs.

    python3 engine/playout/tests/rundown.py [key=value ...]

The tests of the engine play the scheduler before a simulated heartbeat, and
the antenna bench (antenna.py) plays the playout before a fake scheduler: a
fault between the two shows in neither. This bench brings up a small station
(rundown.compose.yml): an Icecast, the playout, then the interface and the
scheduler in its network, as on a station, on a base seeded for the run
(rundown_seed.py). Its clock airs jingles and titles, and has three cuts on
the minute, a minute apart. A probe (rundown_probe.py) reads the conducteur as
a console does, the journal of the antenna and the heartbeats. The bench
launches a relay, as a console does, then sends a live to the harbor, as the
encoder of a studio does. It fails when:

- a sound starts more than a few seconds from the time the conducteur gave it
  a minute before. But for a known defect of the engine, told and not counted:
  the jingle that goes ahead of a title after the cut « Attend la fin »
  (FON-61);
- the cut « Coupe pile » does not go on its minute, or the title it cuts comes
  back after its sound;
- the cut « Attend la fin » cuts the title it waits for;
- a line sent to the playout never airs, or goes to a queue that already holds
  a line planned at the same time or later;
- the cleaner of the queues removes a sound: the sound of the first cut lasts
  longer than the cleaner lets a sound wait;
- the antenna goes silent;
- the relay does not take the antenna, or outlasts its maximal duration;
- the clock does not pause while the live is on air: it sends a sound to the
  playout, or plays the cut due meanwhile, then or after the live; a gesture
  of the console goes through; the title the live has cut comes back after
  it; the grid does not start again.

From the live on, the bench compares no time: the return of a live is not
clean yet (FON-55, FON-61), and it only judges the live itself.

`key=value` sets a key of the table `settings` before the engine starts: a
switch turned off shows the bench failing. `--journal FILE` keeps what the
probe has noted, and `--relire FILE` judges such a file again, without Docker.
The console of the probe opens before the antenna starts: the interface and
the scheduler then draw the forecast at the same time, and only one draw is
written (FON-60). With `features.forecast_drawn_once=0`, both are, and the
first sounds air twice, one start out of six or so.

It needs Docker and Compose, and nothing else: standard library only. The
image of the engine is built from engine/Containerfile, unless
RUNDOWN_ENGINE_IMAGE names one already built. Its messages are in French, as
those of scripts/verifier.sh, which runs it.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import antenna
import rundown_seed as seed
from antenna import say, wait_for

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent.parent

# What the bench does around the cut the live holds, in seconds from its
# minute. The relay goes first, once the flash of the cut before has aired, and
# the scheduler stops it before the studio connects.
RELAY_BEFORE = 32.0
# The harbor buffers a live for 5 s before it takes the antenna: the studio
# connects early enough for the live to be on air on the minute.
STUDIO_BEFORE = 13.0
# A gesture of the console, which the interface refuses during a live.
GESTURE_AFTER = 2.0
STUDIO_AFTER = 6.0
# The bench ends this long after the live, once the grid is back, and at
# END_AFTER after the minute of the cut it holds at the latest.
AFTER_LIVE = 25.0
END_AFTER = 90.0

# A minute before a sound starts, the conducteur says when: the time it gave
# then is compared to the start.
SAID_BEFORE = 60.0
# Seconds between the two. The conducteur itself keeps its times while the
# antenna is within 5 s of them (execution.REALIGN_TOLERANCE).
ON_TIME = 5.0
# A cut « Coupe pile » starts within this of its minute.
ON_THE_MINUTE = 5.0
# After a relay, a live or the start of the antenna, the conducteur follows
# the first line that starts. A console asks for it every 3 s, and the
# interface may take a few seconds to answer.
SETTLE = 8.0
# Heartbeats, one a second, that find a title playing again after the sound of
# a cut « Coupe pile »: it has come back. The scheduler has it skipped while
# that sound plays.
BACK_BEATS = 3
# The same after a live. The scheduler only has the title skipped once a
# heartbeat tells it the live is over: a second or so of it airs, more when the
# scheduler is busy (FON-55). Left alone, it plays to its end.
LIVE_BACK_BEATS = 8
# A tick that started before the live took the antenna may still push a sound.
LIVE_SLACK = 5.0
# Seconds of silence the playout counts on its own output.
SILENCE = 3.0
# A relay takes a few seconds to buffer, and to leave.
RELAY_SLACK = 6.0
# The statuses of a line the playout has been handed, not on air yet.
SENT = {"pending_push", "sent", "accepted", "in_queue"}
HELD_REASON = "retenue pendant le direct"
FLUSHED_REASON = "file vidée"
# What the journals of the engine and of the playout say each second.
NOISE = ("hypercorn.access", "lang.deprecated")


class Bench(antenna.Bench):
    """The Compose project of one run: its own name, free ports, and the image
    of the engine, built for the run unless one is given."""

    def __init__(self, settings: list[str]) -> None:
        super().__init__()
        self.project = f"conducteur-{os.getpid()}"
        self.given = os.environ.get("RUNDOWN_ENGINE_IMAGE", "")
        self.engine = self.given or f"{self.project}-moteur"
        self.env["ENGINE_IMAGE"] = self.engine
        self.env["RUNDOWN_SETTINGS"] = " ".join(settings)

    def command(self, *args: str) -> list[str]:
        command = ["docker", "compose", "-p", self.project]
        return [*command, "-f", str(HERE / "rundown.compose.yml"), *args]

    def build(self) -> None:
        """The image of the engine, from the repository: the code under test."""
        if self.given:
            return
        containerfile = str(ENGINE / "Containerfile")
        done = subprocess.run(
            ["docker", "build", "-q", "-t", self.engine, "-f", containerfile, ENGINE],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if done.returncode != 0:
            raise SystemExit(
                f"L'image du moteur ne se construit pas :\n{done.stdout[-3000:]}"
            )

    def up(self) -> None:
        try:
            super().up()
        except SystemExit:
            say("Le journal de la mise en place :\n" + self.log("init"), error=True)
            raise

    def down(self) -> None:
        super().down()
        if not self.given:
            subprocess.run(
                ["docker", "image", "rm", "-f", self.engine],
                check=False,
                capture_output=True,
            )

    def tail(self, service: str) -> str:
        """The end of the journal of a service, without what the bench makes it
        say each second: the reads of the probe, the heartbeats."""
        said = self.compose("logs", "--no-color", "--tail", "600", service, check=False)
        lines = [
            line
            for line in said.splitlines()
            if not any(noise in line for noise in NOISE)
        ]
        return "\n".join(lines[-60:])

    def read(self, service: str, path: Path) -> bytes:
        """A file of the bench, read where a service reads it."""
        done = subprocess.run(
            self.command("exec", "-T", service, "cat", str(path)),
            env=self.env,
            check=False,
            capture_output=True,
        )
        if done.returncode != 0 or not done.stdout:
            raise RuntimeError(f"{path} ne se lit pas : {done.stderr[:200]!r}")
        return done.stdout


class Console:
    """A session of the console, on the interface: its cookie, its CSRF token."""

    def __init__(self, interface: str) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )
        self.interface = interface
        self.csrf = ""

    def call(self, method: str, path: str, body: dict | None = None):
        """(status, body as a dict): 0 without an answer."""
        data = None if method == "GET" else json.dumps(body or {}).encode("utf-8")
        request = urllib.request.Request(self.interface + path, data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.csrf:
            request.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(request, timeout=15) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        except OSError:
            return 0, {}
        try:
            answer = json.loads(raw or b"{}")
        except ValueError:
            answer = {}
        return status, answer if isinstance(answer, dict) else {}

    def login(self, account: tuple[str, str]) -> bool:
        username, password = account
        body = {"username": username, "password": password}
        if self.call("POST", "/login.json", body)[0] != 200:
            return False
        self.csrf = str(self.call("GET", "/csrf.json")[1].get("csrf_token") or "")
        return bool(self.csrf)


class Journal:
    """What the probe has noted, fetched as the bench goes."""

    def __init__(self, probe: str) -> None:
        self.probe = probe
        self.events: list[dict] = []
        self.plan: dict = {}
        self.offset = 0.0
        self.skew = 0.0

    def fetch(self) -> bool:
        url = f"{self.probe}/journal?since={len(self.events)}"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                answer = json.loads(response.read())
        except (OSError, ValueError):
            return False
        self.events += answer["events"]
        self.plan = answer["plan"]
        self.offset = answer["offset"]
        self.skew = answer["now"] - time.time()
        return True

    def now(self) -> float:
        """The time of the bench: its clock dates every event of the probe."""
        return time.time() + self.skew


@dataclass(frozen=True)
class Span:
    """A stretch of heartbeats that name one source."""

    start: float
    end: float
    beats: int


@dataclass(frozen=True)
class Trouble:
    """A stretch the conducteur cannot foresee: until the antenna starts, then a
    relay and a live. It ends when a line starts again, which the conducteur
    follows: a time it gave before that says nothing."""

    start: float
    end: float


class Reading:
    """A journal of the probe, read: what aired, what the conducteur said of
    it, and what went wrong."""

    def __init__(self, plan: dict, offset: float, events: list[dict], marks: dict):
        self.plan = plan
        self.offset = offset
        self.zone = timezone(timedelta(seconds=offset))
        self.events = events
        self.marks = marks
        self.beats = [event for event in events if event["ev"] == "beat"]
        self.logs = [event for event in events if event["ev"] == "log"]
        self.orders = [event for event in events if event["ev"] == "order"]
        self.health = [event for event in events if event["ev"] == "health"]
        self.removed = [event for event in events if event["ev"] == "removed"]
        self.faults = [event for event in events if event["ev"] == "error"]
        self.reads = [event["t"] for event in events if event["ev"] == "read"]
        self.until = max([event["t"] for event in events], default=0.0)
        # The lines the playout was handed, and the lines the console read: the
        # states of each, in order.
        self.items: dict[str, list[dict]] = {}
        self.lines: dict[str, list[dict]] = {}
        for event in events:
            if event["ev"] == "item":
                self.items.setdefault(event["id"], []).append(event)
            elif event["ev"] == "line":
                self.lines.setdefault(event["id"], []).append(event)
        # A sound starts once: the journal of the antenna names again a title
        # that comes back after what cut it, and the clock writes there the
        # title a cut « Coupe pile » cuts.
        self.starts: list[dict] = []
        started: set[str] = set()
        for row in self.logs:
            if row["item"] and not row["skipped"] and row["item"] not in started:
                started.add(row["item"])
                self.starts.append(row)
        relayed = marks.get("relay")
        self.relay = self.span("relay", relayed) if relayed else None
        connected = marks.get("studio_in")
        self.live = self.span("stream", connected) if connected else None
        self.troubles = self.find_troubles()

    def hms(self, moment: float | None) -> str:
        if moment is None:
            return "--:--:--"
        return datetime.fromtimestamp(moment, self.zone).strftime("%H:%M:%S")

    def span(self, source: str, since: float) -> Span | None:
        """The heartbeats that name ``source`` after ``since``."""
        times = [
            b["t"] for b in self.beats if b["t"] >= since and b["source"] == source
        ]
        return Span(times[0], times[-1], len(times)) if times else None

    def next_start(self, after: float) -> dict | None:
        return next((row for row in self.starts if row["at"] > after), None)

    def find_troubles(self) -> list[Trouble]:
        """Until the antenna starts, and during a relay. And from the live on:
        the return of a live is not clean yet, the conducteur is compared up to
        it only (FON-55, FON-61)."""
        found = []
        if self.starts:
            found.append(Trouble(float("-inf"), self.starts[0]["at"]))
        relayed = self.marks.get("relay")
        if relayed is not None:
            first = self.next_start(self.relay.end if self.relay else relayed)
            found.append(Trouble(relayed, first["at"] if first else float("inf")))
        if self.marks.get("studio_in") is not None:
            found.append(Trouble(self.marks["studio_in"], float("inf")))
        return found

    def after_the_live(self, moment: float | None) -> bool:
        """Whether ``moment`` comes once the studio has connected: what the
        clock sends from then on is not judged but by the live itself."""
        begun = self.marks.get("studio_in")
        return begun is not None and moment is not None and moment >= begun

    def foreseen(self, start: float) -> bool:
        """Whether the conducteur could tell, a minute before, when a sound
        that started at ``start`` would go."""
        said = start - SAID_BEFORE
        if not self.reads or said < self.reads[0]:
            return False
        return not any(
            trouble.start <= start and said <= trouble.end + SETTLE
            for trouble in self.troubles
        )

    def said(self, item: str, moment: float) -> float | None:
        """The time the conducteur gave a line, as the console read it last
        before ``moment``: None when it did not show the line."""
        at = None
        for line in self.lines.get(item, []):
            if line["t"] > moment:
                break
            at = line["at"]
        return at

    def back(self, row: dict, since: float, seconds: float = 40.0) -> int:
        """The heartbeats that find the title of ``row`` playing again, in the
        ``seconds`` after ``since``. By its line: another line may air the same
        title. And with time left to play: once the title is skipped, the
        heartbeat keeps its name until the next sound."""
        return sum(
            1
            for beat in self.beats
            if since < beat["t"] <= since + seconds
            and beat["source"] == "autodj"
            and beat["item"] == row["item"]
            and beat["remaining"] > 0
        )

    def left(self, source: str, since: float) -> float | None:
        """When the heartbeats stop naming ``source``, after ``since``."""
        on_air = False
        for beat in self.beats:
            if beat["t"] < since:
                continue
            if beat["source"] == source:
                on_air = True
            elif on_air:
                return beat["t"]
        return None

    def of_cart(self, cart: str) -> list[dict]:
        """The sounds of a cart that started."""
        return [row for row in self.starts if row["cart"] == self.plan["carts"][cart]]

    def before(self, row: dict) -> dict | None:
        """The sound on air when ``row`` started."""
        at = self.starts.index(row)
        return self.starts[at - 1] if at else None

    def on_air_at(self, moment: float) -> dict | None:
        """The last sound that started before ``moment``."""
        started = [row for row in self.starts if row["at"] < moment]
        return started[-1] if started else None

    def spells(self) -> list[tuple[float, float]]:
        """The silences of the antenna, as (start, seconds): the playout counts
        the seconds its output has been silent, back to zero with the sound."""
        found = []
        longest, last = 0.0, 0.0
        for sample in self.health:
            if sample["silence"] < longest:
                found.append((last - longest, longest))
                longest = 0.0
            if sample["silence"] > 0:
                longest, last = sample["silence"], sample["t"]
        if longest:
            found.append((last - longest, longest))
        return found


def what(row: dict) -> str:
    return f"« {row['title']} »"


def jingle_ahead(reading: Reading, row: dict) -> dict | None:
    """A known defect of the engine, FON-61: the jingle of the motif that goes
    ahead of a title, right after the sound of the cut « Attend la fin ». The
    title the conducteur puts before the jingle is loaded behind that sound,
    and the heartbeat no longer counts it: the clock takes the queue of the
    Auto-DJ for empty. The title, when it is this one."""
    line = reading.items.get(row["item"], [{}])[-1]
    if row["source"] != "jingles" or line.get("when") != "sequential":
        return None
    before = reading.before(row)
    if before is None or before["cart"] != reading.plan["carts"][seed.FLASH]:
        return None
    title = reading.next_start(row["at"])
    if title is None or title["source"] != "autodj":
        return None
    moment = row["at"] - SAID_BEFORE
    said_title = reading.said(title["item"], moment)
    said_jingle = reading.said(row["item"], moment)
    if None in (said_title, said_jingle) or said_title >= said_jingle:
        return None
    return title


def on_time(reading: Reading) -> tuple[list[str], dict[int, float], list[str]]:
    """The sounds that started away from the time the conducteur gave them a
    minute before, the gap of each sound judged, by its row, and the sounds a
    known defect of the engine moved, which the bench does not count."""
    failures = []
    gaps: dict[int, float] = {}
    known = []
    for row in reading.starts:
        if not reading.foreseen(row["at"]):
            continue
        said = reading.said(row["item"], row["at"] - SAID_BEFORE)
        if said is None:
            failures.append(
                f"{what(row)} est passé à {reading.hms(row['at'])} : une minute avant,"
                " le conducteur ne l'annonçait pas"
            )
            continue
        gaps[row["id"]] = row["at"] - said
        if abs(gaps[row["id"]]) <= ON_TIME:
            continue
        title = jingle_ahead(reading, row) if gaps[row["id"]] < 0 else None
        if title is not None:
            known.append(
                f"FON-61 : {what(row)} est passé à {reading.hms(row['at'])}, devant"
                f" {what(title)}, que le conducteur annonçait avant lui"
            )
            continue
        failures.append(
            f"{what(row)} est passé à {reading.hms(row['at'])} : une minute avant,"
            f" le conducteur l'annonçait pour {reading.hms(said)}"
        )
    return failures, gaps, known


def hard_cut(reading: Reading) -> list[str]:
    """The cut « Coupe pile »: on its minute, and the title it cuts does not
    come back after its sound."""
    minute = reading.plan["hard"]
    shows = reading.of_cart(seed.SHOW)
    if not shows:
        return [
            f"la coupure « Coupe pile » de {reading.hms(minute)} n'est jamais passée"
        ]
    show = shows[0]
    failures = []
    if not 0 <= show["at"] - minute <= ON_THE_MINUTE:
        failures.append(
            f"la coupure « Coupe pile » de {reading.hms(minute)} est passée à"
            f" {reading.hms(show['at'])}"
        )
    cut = reading.before(show)
    ended = reading.left("carts", show["at"])
    if cut is not None and cut["source"] == "autodj" and ended is not None:
        back = reading.back(cut, ended - 1)
        if back >= BACK_BEATS:
            failures.append(
                f"{what(cut)}, coupé par la coupure « Coupe pile », est revenu à"
                f" l'antenne {back} s après {what(show)}"
            )
    return failures


def soft_cut(reading: Reading) -> list[str]:
    """The cut « Attend la fin »: after its minute, and without cutting the
    title it waits for."""
    minute = reading.plan["soft"]
    flashes = reading.of_cart(seed.FLASH)
    if not flashes:
        return [
            f"la coupure « Attend la fin » de {reading.hms(minute)} n'est jamais passée"
        ]
    flash = flashes[0]
    if flash["at"] < minute - 1:
        return [
            f"la coupure « Attend la fin » de {reading.hms(minute)} est passée avant"
            f" sa minute, à {reading.hms(flash['at'])}"
        ]
    waited = reading.before(flash)
    if waited is not None and any(
        row["item"] == waited["item"] and row["id"] > flash["id"]
        for row in reading.logs
    ):
        return [
            f"{what(flash)} a coupé {what(waited)}, dont la fin est revenue après"
            " lui : la coupure « Attend la fin » n'a pas attendu"
        ]
    return []


def never_aired(reading: Reading) -> list[str]:
    """The lines the playout was handed and that never aired, but those a
    flush took back and those whose turn has not come."""
    aired = {row["item"] for row in reading.logs if not row["skipped"]}
    failures = []
    for item, states in reading.items.items():
        sent = next((state for state in states if state["status"] in SENT), None)
        last = states[-1]
        if sent is None or item in aired or last["reason"] == FLUSHED_REASON:
            continue
        if reading.after_the_live(sent["t"]):
            continue
        if last["status"] in {"on_air", "played"}:
            continue
        waiting = last["status"] in SENT
        if waiting and (last["at"] or 0) > reading.until - ON_TIME:
            continue
        end = (
            "attend encore dans sa file"
            if waiting
            else f"s'est fermée « {last['status']} », {last['reason'] or 'sans raison'}"
        )
        failures.append(
            f"« {last['resource']} », envoyé au playout à {reading.hms(sent['t'])} et"
            f" prévu à {reading.hms(last['at'])}, n'est jamais passé : sa ligne {end}"
        )
    return failures


def queued_behind(reading: Reading) -> list[str]:
    """The lines sent to a queue of the playout that already held a line
    planned at the same time or later: the queue plays them one after the
    other, not at the times the conducteur gives. The forecast drawn twice at
    the start did that (FON-60)."""
    sent: dict[str, list[list[dict]]] = {}
    for states in reading.items.values():
        first, last = states[0], states[-1]
        if first["status"] in {*SENT, "on_air"} and last["reason"] != FLUSHED_REASON:
            sent.setdefault(first["queue"], []).append(states)
    failures = []
    for lines in sent.values():
        lines.sort(key=lambda states: (states[0]["t"], states[0]["at"] or 0.0))
        for before, after in zip(lines, lines[1:]):
            pushed = after[0]
            if reading.after_the_live(pushed["t"]):
                continue
            # Where the conducteur had the line before it, at that moment.
            then = [state for state in before if state["t"] <= pushed["t"] + 0.05][-1]
            # A line on air may be one a live or a relay has cut: the lines
            # after it are planned anew once the next sound starts.
            if then["status"] not in SENT or None in (then["at"], pushed["at"]):
                continue
            if pushed["at"] < then["at"] + (then["duration"] or 0) - 1:
                failures.append(
                    f"« {pushed['resource']} », envoyé au playout pour"
                    f" {reading.hms(pushed['at'])}, attend derrière"
                    f" « {then['resource']} », prévu à {reading.hms(then['at'])} dans"
                    " la même file : elle les jouera l'un après l'autre, pas à"
                    " l'heure du conducteur"
                )
    return failures


def cleaned(reading: Reading) -> list[str]:
    """What the cleaner of the queues removed. A flush removes too, when a live
    gives the antenna back: nothing else does."""
    back = reading.live.end if reading.live else None
    return [
        f"le nettoyeur des files a retiré {event['count']} son(s) de la file"
        f" « {event['queue']} » à {reading.hms(event['t'])} : rien n'y attend plus"
        f" de {seed.CLEAN_AGE} s, hors du titre que l'horloge garde prêt"
        for event in reading.removed
        if back is None or not back - 1 <= event["t"] <= back + 5
    ]


def silences(reading: Reading) -> tuple[list[str], float]:
    """The silences of the antenna, and the length of the one that followed
    the live. Before the first sound, the playout has nothing to play. When a
    live gives the antenna back, the scheduler empties the queues, then pushes
    a title: a known blank (FON-55), measured and told apart."""
    if not reading.starts:
        return [], 0.0
    first = reading.starts[0]["at"] + 1
    back = reading.live.end if reading.live else None
    failures = []
    after_live = 0.0
    for began, seconds in reading.spells():
        if back is not None and back - 2 <= began <= back + 10:
            after_live = max(after_live, seconds)
        elif seconds >= SILENCE and began > first:
            failures.append(
                f"l'antenne s'est tue {seconds:.0f} s, à partir de {reading.hms(began)}"
            )
    return failures, after_live


def relayed(reading: Reading) -> list[str]:
    """The relay the console launched: on air, then stopped by the scheduler
    when its maximal duration is over."""
    ordered = reading.marks.get("relay")
    if ordered is None:
        return ["le banc n'a pas lancé son relais"]
    status, answer = reading.marks.get("relay_answer") or (0, {})
    if status != 200:
        return [f"l'interface a refusé de lancer le relais ({status}) : {answer}"]
    if reading.relay is None or reading.relay.beats < BACK_BEATS:
        return ["le relais lancé par la console n'a jamais pris l'antenne"]
    held = reading.relay.end - ordered
    if held > seed.RELAY_SECONDS + RELAY_SLACK:
        return [
            f"le relais a tenu l'antenne {held:.0f} s : le scheduler devait l'arrêter"
            f" au bout de {seed.RELAY_SECONDS} s, sa durée maximale"
        ]
    return []


def live_held(reading: Reading) -> list[str]:
    """The live the studio sent: on air on the minute of the third cut, with
    the clock paused meanwhile, then the grid again."""
    marks = reading.marks
    if marks.get("studio_in") is None:
        return ["le banc n'a pas envoyé son direct"]
    if marks.get("studio_refused"):
        return [
            f"le harbor n'a pas pris le direct du studio : {marks['studio_refused']}"
        ]
    live = reading.live
    minute = reading.plan["held"]
    if live is None or live.beats < BACK_BEATS:
        return ["le direct du studio n'a jamais pris l'antenne"]
    if not live.start < minute < live.end:
        return [
            f"le direct a tenu l'antenne de {reading.hms(live.start)} à"
            f" {reading.hms(live.end)}, pas à {reading.hms(minute)} : le banc n'a pas"
            " pu voir ce que l'horloge fait de la coupure due pendant un direct"
        ]
    failures = []
    pushed = [
        order
        for order in reading.orders
        if order["created"] and live.start + LIVE_SLACK < order["created"] <= live.end
    ]
    if pushed:
        failures.append(
            f"pendant le direct, l'horloge a envoyé {len({o['id'] for o in pushed})}"
            f" son(s) au playout, dès {reading.hms(pushed[0]['created'])} : elle ne"
            " s'est pas mise en pause"
        )
    ads = reading.of_cart(seed.ADS)
    if ads:
        failures.append(
            f"la coupure de {reading.hms(minute)}, due pendant le direct, est passée"
            f" à {reading.hms(ads[0]['at'])} : l'horloge devait la laisser tomber"
        )
    closed = [
        states[-1]
        for states in reading.items.values()
        if states[-1]["cart"] == reading.plan["carts"][seed.ADS]
    ]
    if not any(
        line["status"] == "skipped" and line["reason"] == HELD_REASON for line in closed
    ):
        failures.append(
            f"la ligne de la coupure de {reading.hms(minute)}, due pendant le direct,"
            f" n'est pas fermée « {HELD_REASON} » au conducteur"
        )
    status, answer = marks.get("gesture") or (0, {})
    if status != 409 or answer.get("code") != "harbor_live":
        failures.append(
            "pendant le direct, l'interface n'a pas refusé « Diffuser maintenant »"
            f" ({status}) : {answer}"
        )
    cut = reading.on_air_at(live.start)
    if cut is not None and cut["source"] == "autodj":
        back = reading.back(cut, live.end)
        if back >= LIVE_BACK_BEATS:
            failures.append(
                f"{what(cut)}, coupé par le direct, est revenu à l'antenne {back} s"
                " après lui : le scheduler devait le sauter"
            )
    again = reading.next_start(live.end)
    if again is None or again["at"] > live.end + 15:
        failures.append("la grille n'a pas repris dans les 15 s qui suivent le direct")
    return failures


def unjudged(reading: Reading, gaps: dict[int, float]) -> list[str]:
    """The sounds the bench is there to compare to the conducteur, and could
    not: a bench that judged nothing proves nothing."""
    shows = reading.of_cart(seed.SHOW)
    ended = reading.left("carts", shows[0]["at"]) if shows else None
    wanted = {
        "celui qui suit la coupure « Coupe pile »": (
            reading.next_start(ended - 2) if ended else None
        ),
        "celui de la coupure « Attend la fin »": next(
            iter(reading.of_cart(seed.FLASH)), None
        ),
    }
    missing = [
        name for name, row in wanted.items() if row is None or row["id"] not in gaps
    ]
    if not missing:
        return []
    return [
        "le banc n'a pas pu comparer à l'heure du conducteur "
        + ", ni ".join(missing)
        + f" : {len(gaps)} son(s) comparé(s) en tout"
    ]


def table(reading: Reading, gaps: dict[int, float]) -> None:
    """What aired, as the journal of the antenna tells it, with the gap between
    the time the conducteur gave a minute before and the start."""
    say("  à l'antenne, et l'écart avec l'heure donnée une minute avant :")
    for row in reading.logs:
        name = f"{row['artist']} — {row['title']}" if row["artist"] else row["title"]
        if row["skipped"]:
            note = "coupé : noté par l'horloge"
        elif row["id"] in gaps:
            note = f"{round(gaps[row['id']]):+d} s"
        elif row not in reading.starts:
            note = "redit par le playout" if row["item"] else "sans ligne au conducteur"
        else:
            note = "pas jugé"
        say(
            f"    {reading.hms(row['at'])}  {row['source'] or '?':8}"
            f" {name or '(sans titre)':36} {note}"
        )


def verdict(reading: Reading) -> list[str]:
    """What went wrong, in the words shown to whoever runs the bench."""
    failures, gaps, known = on_time(reading)
    table(reading, gaps)
    for defect in known:
        say(f"  défaut connu, pas compté : {defect}")
    quiet, after_live = silences(reading)
    closed = sorted(
        {
            f"« {states[-1]['resource']} » ({states[-1]['reason']})"
            for states in reading.items.values()
            if states[-1]["status"] == "skipped"
        }
    )
    say(f"  lignes fermées sans passer : {', '.join(closed) or 'aucune'}")
    if reading.live:
        blank = f"un blanc d'au moins {after_live:.1f} s (FON-55)"
        say(
            f"  direct à l'antenne de {reading.hms(reading.live.start)} à"
            f" {reading.hms(reading.live.end)}, puis "
            + (blank if after_live else "la grille, sans blanc")
        )
    if reading.relay:
        say(
            f"  relais à l'antenne de {reading.hms(reading.relay.start)} à"
            f" {reading.hms(reading.relay.end)}"
        )
    # Before the antenna starts, the probe finds nobody to read.
    started = reading.starts[0]["at"] if reading.starts else float("inf")
    faults = {
        f"{fault['where']} ({fault['error']})"
        for fault in reading.faults
        if fault["t"] > started
    }
    if faults:
        say(f"  la sonde a manqué des lectures : {', '.join(sorted(faults))}")

    failures += hard_cut(reading)
    failures += soft_cut(reading)
    failures += never_aired(reading)
    failures += queued_behind(reading)
    failures += cleaned(reading)
    failures += quiet
    failures += relayed(reading)
    failures += live_held(reading)
    failures += unjudged(reading, gaps)
    return failures


def play(bench: Bench, journal: Journal, marks: dict) -> None:
    """Brings the antenna through its cuts: the relay, the live over the third
    one and a gesture meanwhile, then the grid again. ``marks``: what the bench
    did, and when, on the clock of the probe."""
    wait_for(journal.fetch, 120, "la sonde du banc ne répond pas")
    plan = journal.plan
    interface = bench.address("playout", 6811)
    console = Console(interface)
    wait_for(
        lambda: console.login(seed.CONSOLE), 120, "l'interface n'ouvre pas de session"
    )
    # The studio takes its token of encoder as an account does, in the console.
    studio_console = Console(interface)
    if not studio_console.login(seed.STUDIO):
        raise RuntimeError("le compte du studio n'ouvre pas de session")
    status, answer = studio_console.call("POST", "/users/me/stream-token.json")
    if status != 200 or not answer.get("token"):
        raise RuntimeError(f"le studio n'obtient pas son jeton d'encodeur ({status})")
    harbor = bench.address("playout", 6800)
    studio = antenna.Studio(harbor, bench.read("playout", seed.LIVE))
    studio.USER, studio.TOKEN = seed.STUDIO[0], str(answer["token"])

    hms = Reading(plan, journal.offset, [], {}).hms
    say(
        f"  coupures : « Coupe pile » à {hms(plan['hard'])}, « Attend la fin » à"
        f" {hms(plan['soft'])}, puis une « Coupe pile » à {hms(plan['held'])},"
        " pendant le direct"
    )
    held = plan["held"]
    carts = plan["carts"]
    try:
        while journal.now() < held + END_AFTER:
            now = journal.now()
            if "relay" not in marks and now >= held - RELAY_BEFORE:
                marks["relay"] = now
                marks["relay_answer"] = console.call(
                    "POST", f"/carts/{carts[seed.RELAY]}/now.json"
                )
                say(f"  {hms(now)}  la console lance le relais")
            if "studio_in" not in marks and now >= held - STUDIO_BEFORE:
                marks["studio_in"] = now
                studio.start()
                say(f"  {hms(now)}  le studio se connecte au harbor")
            if "gesture" not in marks and now >= held + GESTURE_AFTER:
                marks["gesture"] = console.call(
                    "POST", f"/carts/{carts[seed.ADS]}/now.json"
                )
            if "studio_out" not in marks and now >= held + STUDIO_AFTER:
                studio.stop()
                marks["studio_out"] = journal.now()
                marks["studio_refused"] = studio.refused
                say(f"  {hms(marks['studio_out'])}  le studio s'en va")
            journal.fetch()
            if "studio_out" in marks:
                # Over once the grid is back, and the title the live cut has had
                # the time to come back.
                reading = Reading(plan, journal.offset, journal.events, marks)
                if (
                    reading.live is not None
                    and reading.next_start(reading.live.end) is not None
                    and journal.now() >= reading.live.end + AFTER_LIVE
                ):
                    break
            time.sleep(1.0)
    finally:
        if "studio_in" in marks and "studio_out" not in marks:
            studio.stop()
    # The time for the last sound to reach the journal of the antenna.
    time.sleep(3.0)
    journal.fetch()


def keep(path: str, reading: Reading) -> None:
    """What the probe has noted and what the bench did, for --relire."""
    kept = {
        "plan": reading.plan,
        "offset": reading.offset,
        "marks": reading.marks,
        "events": reading.events,
    }
    Path(path).write_text(json.dumps(kept), encoding="utf-8")


def report(failures: list[str]) -> int:
    if failures:
        say("Échec :", error=True)
        for failure in failures:
            say(f"  - {failure}", error=True)
        return 1
    say(
        "Bon : chaque son comparé part à l'heure que le conducteur donnait une"
        " minute avant. La coupure « Coupe pile » part à sa minute, et le titre qu'elle"
        " tranche ne revient pas ; la coupure « Attend la fin » attend la fin du"
        " titre. Rien de ce qui est envoyé au playout ne se perd, et le nettoyeur"
        " des files ne retire rien. Le relais s'arrête à sa durée maximale. Pendant"
        " le direct, l'horloge se met en pause et laisse tomber la coupure due ;"
        " après lui, la grille reprend, sans le titre coupé."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Le banc du conducteur : le vrai scheduler devant le vrai playout."
    )
    parser.add_argument(
        "settings",
        nargs="*",
        metavar="clé=valeur",
        help="une clé de la table settings du banc, posée avant le démarrage",
    )
    parser.add_argument(
        "--journal", metavar="FICHIER", help="garde le relevé de la sonde"
    )
    parser.add_argument(
        "--relire", metavar="FICHIER", help="rejuge un relevé gardé, sans Docker"
    )
    args = parser.parse_args()
    if args.relire:
        kept = json.loads(Path(args.relire).read_text(encoding="utf-8"))
        reading = Reading(kept["plan"], kept["offset"], kept["events"], kept["marks"])
        return report(verdict(reading))
    for setting in args.settings:
        if "=" not in setting or " " in setting:
            parser.error(f"« {setting} » : une clé et sa valeur, comme clé=valeur")

    bench = Bench(args.settings)
    say(
        f"Conducteur : le scheduler et l'interface de {ENGINE.name}/, devant"
        f" {HERE.parent.name}/radiotomate.liq dans {bench.image}"
    )
    if args.settings:
        say(f"  réglages : {' '.join(args.settings)}")
    try:
        say(
            "  image du moteur : "
            + (
                bench.given
                or "construite depuis engine/Containerfile, deux à trois"
                " minutes la première fois"
            )
        )
        bench.build()
        if datetime.now().minute >= 55:
            say(
                "  l'heure tourne bientôt : le banc peut attendre la suivante, ses"
                " coupures tombent toutes dans l'heure où l'antenne démarre"
            )
        bench.up()
        journal = Journal(bench.address("playout", 6899))
        marks: dict = {}
        said = ["scheduler", "playout"]
        try:
            play(bench, journal, marks)
            failures = []
        except RuntimeError as exc:
            # The bench could not play its scenario: every service may tell why.
            failures = [str(exc)]
            said += ["interface", "probe"]
        reading = Reading(journal.plan, journal.offset, journal.events, marks)
        if args.journal:
            keep(args.journal, reading)
        status = report(failures or verdict(reading))
        if status:
            for service in said:
                tail = bench.tail(service)
                say(f"\nLa fin du journal de {service} :\n{tail}", error=True)
        return status
    finally:
        bench.down()


if __name__ == "__main__":
    sys.exit(main())
