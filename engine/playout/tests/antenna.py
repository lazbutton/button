#!/usr/bin/env python3
"""
The antenna bench: plays engine/playout/radiotomate.liq in the Liquidsoap of the
playout image, and listens to what comes out.

    python3 engine/playout/tests/antenna.py

`liquidsoap --check` only reads the script. This plays it: titles are pushed as
the scheduler pushes them, a sound of a cart and a jingle cut in, two more wait
for the end of a title, then a relay and a live, sent to the harbor as a studio
sends it, cut the last title. The bench records the WAV mount of the console's
headphones, the same sound as the public mount before its MP3 encoder. It fails
when:

- a title pushed never airs, or airs out of order;
- the playout airs the same 20 ms frame again and again: the music queue has
  stalled, and the antenna buzzes;
- the remaining time of a title stays put while it plays;
- the length a title is announced with, what it has played plus what is left,
  is not its own: the scheduler cuts it in the middle, or waits for its end
  long after it;
- the heartbeat names another source than the one on air: a sound of a cart
  told as the Auto-DJ, with the remaining time of the title it has cut, a
  relay or a live told as anything else, or the title that comes back after
  them;
- a sound told to wait for the end of a title cuts it: the end of the title
  comes back after the sound;
- a relay comes back once the live that took the antenna from it is over;
- the cleaner of the queues takes out the next title of the Auto-DJ, which the
  scheduler keeps ready behind what plays, or leaves the one after it;
- the antenna stays silent.

It needs Docker and Compose, and nothing else: standard library only. Its
messages are in French, as those of scripts/verifier.sh, which runs it.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import sounds

HERE = Path(__file__).resolve().parent
CONTAINERFILE = HERE.parent / "Containerfile"

RATE = 44100
BYTES_PER_SECOND = RATE * 4  # 16 bits, stereo
FRAME = 882 * 4  # the frame of Liquidsoap: 20 ms
WINDOW = BYTES_PER_SECOND // 10
# A frame aired again for this long is a stall. A real sound never repeats to
# the sample, and the sounds of the bench are sweeps.
STALL_SECONDS = 0.3
# Heartbeats in a row, one a second, with the same remaining time.
STUCK_BEATS = 5
# Seconds between the length a title is announced with and its own.
LENGTH_SLACK = 1.5

TITLES = [f"title-{number}" for number in range(1, 8)]
JINGLE = "jingle"
CART = "cart"
# What waits for the end of a title, pushed in its last seconds as the scheduler
# does: the title, and the sound. A jingle of the motif, then the sound of a cut
# on the minute that waits for the end.
WAITS = [(TITLES[2], "jingle-fin"), (TITLES[3], "cart-fin")]
LAST_SECONDS = 3.0
# The queue each sound is pushed to: the source the heartbeat names meanwhile.
QUEUES = {
    **dict.fromkeys(TITLES, "autodj"),
    JINGLE: "jingles",
    CART: "carts",
    WAITS[0][1]: "jingles",
    WAITS[1][1]: "carts",
}
# What cuts in: the title cut, the seconds into it, and the sound. A sound of a
# cart, as a cut on the minute pushes, then a jingle.
CUTS = [(TITLES[0], 6.0, CART), (TITLES[1], 2.0, JINGLE)]
# The last title: a relay, then a live over it, cut it, and it comes back.
CUT_BY_LIVE = TITLES[-1]
# What the studio sends to the harbor: the bench never pushes it to a queue.
LIVE = "live"
# The sounds whose announced length is compared to their own.
MEASURED = [
    name
    for name in [*TITLES, CART]
    if name not in {CUT_BY_LIVE, *(cut[0] for cut in CUTS)}
]
# What follows each sound that waited: its title before it, the next one after.
FOLLOWS = {sound: (title, TITLES[TITLES.index(title) + 1]) for title, sound in WAITS}
# The cleaner of the queues, which the scheduler runs every minute: the second
# title is the next one of the Auto-DJ and stays, the third one leaves once it
# has waited this long, the least the playout takes. The first title, 40 s and
# the sound of a cart that cuts it, is still on air then.
SPARED, CLEANED = TITLES[1], TITLES[2]
CLEAN_SECONDS = 30.0
# The start sound has aired, and the music queue has been empty for a while: a
# first title pushed then is what used to stall.
EMPTY_QUEUE_SECONDS = 5.0
LIMIT_SECONDS = 180.0

# The relay takes the public mount of the bench itself, as the playout reaches it.
RELAY_URL = f"http://icecast:8000/{sounds.PUBLIC_MOUNT}"
# The seconds a relay has to take the antenna: the last title still plays.
RELAY_WAIT = 10
# The relay holds the antenna this long before the studio connects, the studio
# sends its live this long, and the last title has this long to come back.
RELAY_SECONDS = 5.0
LIVE_SECONDS = sounds.HARBOR_BUFFER + 8
BACK_SECONDS = sounds.HARBOR_BUFFER + 7
# Seconds left to the harbor: to put a live on air once the studio connects, and
# to air what it has buffered once the studio has left.
HARBOR_SECONDS = sounds.HARBOR_BUFFER + 3


def say(text: str, *, error: bool = False) -> None:
    out = sys.stderr if error else sys.stdout
    out.write(text + "\n")
    out.flush()


def liquidsoap_image() -> str:
    """The image the playout is built from: the bench plays the same Liquidsoap."""
    for line in CONTAINERFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("FROM "):
            return line.split()[1]
    raise SystemExit(f"Pas de ligne FROM dans {CONTAINERFILE}.")


def call(method: str, url: str, body: dict | None = None, timeout: float = 10.0):
    """An HTTP call with the token of the bench: (status, body), 0 without answer."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("X-Auth-Token", sounds.TOKEN)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except OSError:
        return 0, b""


def wait_for(ready, seconds: float, failure: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if ready():
            return
        time.sleep(0.5)
    raise RuntimeError(failure)


class Bench:
    """The Compose project of one run: its own name, free ports."""

    def __init__(self) -> None:
        self.project = f"antenne-{os.getpid()}"
        self.image = liquidsoap_image()
        self.env = {**os.environ, "LIQUIDSOAP_IMAGE": self.image}

    def command(self, *args: str) -> list[str]:
        command = ["docker", "compose", "-p", self.project]
        return [*command, "-f", str(HERE / "compose.yml"), *args]

    def compose(self, *args: str, check: bool = True) -> str:
        done = subprocess.run(
            self.command(*args),
            env=self.env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if check and done.returncode != 0:
            raise SystemExit(
                f"docker compose {' '.join(args)} a échoué :\n{done.stdout}"
            )
        return done.stdout

    def sound(self, name: str) -> bytes:
        """A sound of the bench, read where the playout reads it."""
        done = subprocess.run(
            self.command("exec", "-T", "playout", "cat", f"/sounds/{name}.mp3"),
            env=self.env,
            check=False,
            capture_output=True,
        )
        if done.returncode != 0 or not done.stdout:
            raise RuntimeError(
                f"le son « {name} » du banc ne se lit pas : {done.stderr[:200]!r}"
            )
        return done.stdout

    def address(self, service: str, port: int) -> str:
        # The last line: Compose may warn before it.
        lines = self.compose("port", service, str(port)).strip().splitlines()
        return "http://" + lines[-1].strip()

    def up(self) -> None:
        self.compose("up", "-d", "--build", "--quiet-pull")

    def down(self) -> None:
        # With the volume of the sounds, and the two images built under the name
        # of this run: nothing of it stays on the machine.
        self.compose("down", "-v", "--rmi", "local", "--remove-orphans", check=False)

    def log(self, service: str) -> str:
        return self.compose("logs", "--no-color", "--tail", "60", service, check=False)


class Playout:
    """The playout of the bench, as the scheduler, a studio and a listener reach it."""

    def __init__(self, bench: Bench) -> None:
        self.api = bench.address("playout", 6833)
        self.journal_url = bench.address("playout", 6822) + "/journal"
        self.harbor = bench.address("playout", 6800)
        self.icecast = bench.address("icecast", 8000)
        # What the cleaner of the queues answered, once the scenario has run it.
        self.cleaned: dict | None = None

    def wait(self) -> None:
        wait_for(
            lambda: call("GET", f"{self.api}/version")[0] == 200,
            180,
            "le playout ne répond pas",
        )
        wait_for(
            lambda: b"studio.wav" in call("GET", f"{self.icecast}/status-json.xsl")[1],
            60,
            "le playout n'a pas monté le mount studio.wav d'Icecast",
        )

    def journal(self) -> dict:
        """What the playout told the fake scheduler: heartbeats, titles aired."""
        status, body = call("GET", self.journal_url)
        return json.loads(body) if status == 200 else {"live": [], "metadata": []}

    def aired(self) -> list[str]:
        # The start sound has no title.
        return [row["title"] for row in self.journal()["metadata"] if row["title"]]

    def last_beat(self) -> dict | None:
        beats = self.journal()["live"]
        return beats[-1] if beats else None

    def now(self) -> float:
        """The time of the journal: when its last heartbeat came. Its clock dates
        every heartbeat and every title, whatever the pace of the heartbeats."""
        for _ in range(3):
            beat = self.last_beat()
            if beat is not None:
                return beat["at"]
            time.sleep(0.5)
        raise RuntimeError("le faux scheduler ne rend plus son journal")

    def push(self, queue: str, name: str, *, wait: bool = False) -> None:
        payload: dict = {
            "path": f"/sounds/{name}.mp3",
            "title": name,
            "artist": "Banc",
            "radiotomate_item_id": f"item-{name}",
        }
        if wait:
            # As the scheduler: the sound goes at the end of the title on air.
            payload["wait"] = True
        status, body = call("POST", f"{self.api}/queue/{queue}", payload, timeout=30)
        if status != 200:
            raise RuntimeError(
                f"le playout a refusé {name} ({status}) : {body[:200]!r}"
            )

    def clean(self, seconds: float) -> dict:
        """Takes out of the queues what has waited there that long, as the
        scheduler does every minute: what the playout says it removed and kept."""
        status, body = call(
            "POST", f"{self.api}/queue/clean", {"max_age_seconds": seconds}
        )
        if status != 200:
            raise RuntimeError(
                f"le playout a refusé de nettoyer ses files ({status}) : {body[:200]!r}"
            )
        return json.loads(body)

    def relay(self, url: str) -> None:
        status, body = call("POST", f"{self.api}/relay?url={url}")
        if status != 200:
            raise RuntimeError(
                f"le playout a refusé le relais ({status}) : {body[:200]!r}"
            )


class Studio(threading.Thread):
    """Sends a live to the harbor until told to stop, as the encoder of a studio
    does: an MP3 in a loop, at the speed it plays."""

    USER = "studio"
    TOKEN = "jeton-du-studio"

    def __init__(self, harbor: str, mp3: bytes) -> None:
        super().__init__(daemon=True)
        host, port = harbor.removeprefix("http://").rsplit(":", 1)
        self.address = (host, int(port))
        self.mp3 = mp3
        self.stopped = threading.Event()
        # Why the harbor did not take the live, or dropped it.
        self.refused = ""

    def run(self) -> None:
        login = base64.b64encode(f"{self.USER}:{self.TOKEN}".encode()).decode("ascii")
        head = (
            f"PUT /{sounds.HARBOR_MOUNT} HTTP/1.1\r\n"
            f"Host: {self.address[0]}:{self.address[1]}\r\n"
            f"Authorization: Basic {login}\r\n"
            "Content-Type: audio/mpeg\r\n"
            "Expect: 100-continue\r\n\r\n"
        )
        try:
            with socket.create_connection(self.address, timeout=10) as harbor:
                harbor.sendall(head.encode("ascii"))
                answer = harbor.recv(1024).split(b"\r\n")[0].decode("ascii", "replace")
                if answer.split(" ")[1:2] not in (["100"], ["200"]):
                    self.refused = answer or "aucune réponse"
                    return
                self.send(harbor)
        except OSError as exc:
            self.refused = str(exc)

    def send(self, harbor: socket.socket) -> None:
        rate = sounds.MP3_KBPS * 1000 // 8
        started = time.monotonic()
        sent = 0
        while not self.stopped.is_set():
            due = int((time.monotonic() - started) * rate)
            while sent < due:
                at = sent % len(self.mp3)
                sent += harbor.send(self.mp3[at : at + min(4096, due - sent)])
            self.stopped.wait(0.05)

    def stop(self) -> None:
        self.stopped.set()
        self.join(timeout=15)


class Capture(threading.Thread):
    """Records a mount of Icecast until told to stop."""

    def __init__(self, url: str) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.pcm = bytearray()
        self.stopped = threading.Event()

    def run(self) -> None:
        try:
            with urllib.request.urlopen(self.url, timeout=10) as stream:
                while not self.stopped.is_set():
                    chunk = stream.read(8192)
                    if not chunk:
                        break
                    self.pcm += chunk
        except OSError:
            pass

    def stop(self) -> bytes:
        self.stopped.set()
        self.join(timeout=15)
        return bytes(self.pcm)


@dataclass(frozen=True)
class Cuts:
    """When the last title was cut, in the time of the journal."""

    # The relay had taken the antenna.
    relay: float
    # The studio connected to the harbor, then left it.
    live: float
    left: float


def foreign(rows: list[dict], since: float) -> list[str]:
    """The titles announced since then that the bench never pushed: those of a
    relay."""
    return [
        row["title"]
        for row in rows
        if row["at"] > since and row["title"] not in {"", *QUEUES}
    ]


def cut(playout: Playout, mp3: bytes) -> Cuts:
    """Cuts the last title with a relay, then with a live over the relay, and
    leaves the title the time to come back."""
    time.sleep(2)
    ordered = playout.now()
    playout.relay(RELAY_URL)
    # A relay on air announces the title of its stream: one the bench never pushed.
    wait_for(
        lambda: foreign(playout.journal()["metadata"], ordered),
        RELAY_WAIT,
        "le relais n'a jamais pris l'antenne",
    )
    relay = playout.now()
    time.sleep(RELAY_SECONDS)
    live = playout.now()
    studio = Studio(playout.harbor, mp3)
    studio.start()
    # A studio the harbor refuses is told at once.
    leaving = time.monotonic() + LIVE_SECONDS
    while time.monotonic() < leaving and not studio.refused:
        time.sleep(0.5)
    studio.stop()
    left = playout.now()
    if studio.refused:
        raise RuntimeError(
            f"le harbor n'a pas pris le direct du studio : {studio.refused}"
        )
    time.sleep(BACK_SECONDS)
    return Cuts(relay, live, left)


def scenario(playout: Playout, mp3: bytes) -> Cuts | None:
    """Pushes the titles as the scheduler does, a sound of a cart on the first
    one, a jingle on the second, then two sounds that wait for the end of the
    third and of the fourth, and cuts the last one with a relay and a live. While
    the first title plays, it runs the cleaner of the queues. None when the last
    title never came."""
    pushed: list[str] = []
    pushed_at: dict[str, float] = {}
    due: dict[str, float] = {}
    sent: set[str] = set()
    deadline = time.monotonic() + LIMIT_SECONDS
    while time.monotonic() < deadline:
        aired = playout.aired()
        # As the scheduler: two titles in the queue, behind the one on air.
        waiting = [name for name in pushed if name not in aired]
        if len(pushed) < len(TITLES) and len(waiting) < 2:
            pushed.append(TITLES[len(pushed)])
            playout.push("autodj", pushed[-1])
            pushed_at[pushed[-1]] = time.monotonic()
        if (
            playout.cleaned is None
            and CLEANED in pushed_at
            and SPARED not in aired
            and time.monotonic() >= pushed_at[CLEANED] + CLEAN_SECONDS + 1
        ):
            playout.cleaned = playout.clean(CLEAN_SECONDS)
            removed = playout.cleaned.get("autodj", {}).get("removed", 0)
            # The scheduler pushes again what it no longer finds in the queue:
            # the rest of the bench goes on with every title.
            for name in [SPARED, CLEANED][2 - min(2, removed) :]:
                playout.push("autodj", name)
        for title, seconds, sound in CUTS:
            if title in aired and sound not in due:
                due[sound] = time.monotonic() + seconds
            elif sound in due and sound not in sent and time.monotonic() >= due[sound]:
                sent.add(sound)
                playout.push(QUEUES[sound], sound)
        beat = playout.last_beat()
        for title, sound in WAITS:
            if sound in sent or beat is None or beat["title"] != title:
                continue
            if 0 < beat["remaining"] <= LAST_SECONDS:
                sent.add(sound)
                playout.push(QUEUES[sound], sound, wait=True)
        # The last title has started: a relay and a live cut it.
        if CUT_BY_LIVE in aired and JINGLE in aired:
            return cut(playout, mp3)
        time.sleep(0.5)
    return None


def ranges(starts: list[int]) -> list[tuple[float, float]]:
    """Windows that follow each other, as (start, length) in seconds."""
    found: list[list[int]] = []
    for start in starts:
        if found and start - found[-1][1] <= WINDOW:
            found[-1][1] = start + WINDOW
        else:
            found.append([start, start + WINDOW])
    return [(a / BYTES_PER_SECOND, (b - a) / BYTES_PER_SECOND) for a, b in found]


def listen(pcm: bytes) -> tuple[float, list[tuple[float, float]]]:
    """The seconds of sound in a capture, and where the same frame airs again."""
    view = memoryview(pcm)
    silence = bytes(WINDOW)
    sound = 0
    stalled = []
    for start in range(0, len(pcm) - WINDOW - FRAME, WINDOW):
        window = view[start : start + WINDOW]
        if window == silence:
            continue
        sound += 1
        if window == view[start + FRAME : start + FRAME + WINDOW]:
            stalled.append(start)
    stalls = [(at, length) for at, length in ranges(stalled) if length >= STALL_SECONDS]
    return sound * WINDOW / BYTES_PER_SECOND, stalls


def stuck(beats: list[dict]) -> list[tuple[str, int]]:
    """Titles whose remaining time stayed put: (title, seconds)."""
    found: dict[str, int] = {}
    run = 0
    for before, beat in zip(beats, beats[1:]):
        same = (
            beat["remaining"] > 0
            and beat["remaining"] == before["remaining"]
            and beat["title"] == before["title"]
            and beat["source"] == before["source"]
        )
        run = run + 1 if same else 0
        if run >= STUCK_BEATS:
            found[beat["title"]] = max(found.get(beat["title"], 0), run)
    return sorted(found.items())


def announced(beats: list[dict]) -> dict[str, float]:
    """The length each sound is announced with: what it has played plus what is
    left, the median of its heartbeats. Not a title that a sound cuts: what it
    has played starts again after that sound. Nor the jingle: too few heartbeats."""
    found: dict[str, float] = {}
    for name in MEASURED:
        lengths = sorted(
            beat["elapsed"] + beat["remaining"]
            for beat in beats
            if beat["title"] == name and beat["remaining"] > 0
        )
        if lengths:
            found[name] = lengths[len(lengths) // 2]
    return found


def misnamed(beats: list[dict]) -> dict[str, str]:
    """The sounds whose heartbeats mostly name another source than their queue,
    and that source. A heartbeat at the turn of two sounds may mix them."""
    found: dict[str, str] = {}
    for name, queue in QUEUES.items():
        named = [beat["source"] for beat in beats if beat["title"] == name]
        if named.count(queue) * 2 < len(named):
            found[name] = max(set(named), key=named.count)
    return found


def returned(aired: list[str]) -> list[tuple[str, str]]:
    """The titles that came back on air after another sound, with that sound: it
    cut them before their end. Not the titles the bench cuts on purpose."""
    cut = {CUT_BY_LIVE, *(title for title, *_ in CUTS)}
    found = []
    for index, name in enumerate(aired):
        before = aired[:index]
        back = name in before and before[-1] != name
        if name in TITLES and name not in cut and back:
            found.append((name, before[-1]))
    return found


def misplaced(aired: list[str]) -> list[str]:
    """The sounds that waited and did not air between their title and the next."""
    order = list(dict.fromkeys(aired))
    found = []
    for sound, (title, after) in FOLLOWS.items():
        if sound not in order:
            continue
        at = order.index(sound)
        if order[at - 1 : at] != [title] or order[at + 1 : at + 2] != [after]:
            found.append(sound)
    return found


def told(beats: list[dict], source: str) -> str:
    """The other sources these heartbeats name, as a failure says them."""
    others = sorted({beat["source"] for beat in beats if beat["source"] != source})
    return ", ".join(f"« {name} »" for name in others)


def relayed(beats: list[dict], rows: list[dict], cuts: Cuts) -> list[str]:
    """What went wrong while a relay, then a live, held the antenna, and once
    the live was over."""
    failures: list[str] = []

    def between(start: float, end: float) -> list[dict]:
        return [beat for beat in beats if start < beat["at"] < end]

    # The relay holds the antenna until the harbor has buffered the live, which
    # holds it until the studio leaves.
    on_relay = between(cuts.relay + 1, cuts.live + 3)
    on_live = between(cuts.live + HARBOR_SECONDS, cuts.left)
    held = {"le relais": ("relay", on_relay), "le direct": ("stream", on_live)}
    # The harbor then airs what it has buffered, and the title comes back.
    after = between(cuts.left + HARBOR_SECONDS, float("inf"))
    back = [beat for beat in after if beat["title"] == CUT_BY_LIVE]
    if foreign(rows, cuts.left):
        failures.append(
            "le relais est revenu à l'antenne après le direct, qui ne l'a pas arrêté"
        )
    elif not back:
        failures.append(
            f"« {CUT_BY_LIVE} » n'est pas revenu à l'antenne après le direct"
        )
    else:
        held[f"« {CUT_BY_LIVE} », revenu après le direct"] = (
            QUEUES[CUT_BY_LIVE],
            back,
        )
    for what, (source, span) in held.items():
        if not span:
            failures.append(f"aucun battement pendant {what}")
        elif told(span, source):
            failures.append(
                f"pendant {what}, le playout dit la source {told(span, source)},"
                f" pas « {source} » : le scheduler ne sait pas ce qui est à l'antenne"
            )
    return failures


def swept(cleaned: dict | None) -> list[str]:
    """What went wrong when the cleaner of the queues ran, behind the first title."""
    if cleaned is None:
        return [
            f"le nettoyage des files n'a pas tourné : « {SPARED} » était déjà"
            f" passé {CLEAN_SECONDS:.0f} s après l'envoi de « {CLEANED} »"
        ]
    removed = cleaned.get("autodj", {}).get("removed")
    if removed == 1:
        return []
    return [
        f"le nettoyage des files a retiré {removed} titre(s) de la file de l'auto-DJ,"
        f" en attente depuis {CLEAN_SECONDS:.0f} s : il laisse le prochain, que le"
        " scheduler garde prêt derrière ce qui passe, et retire celui d'après"
    ]


def verdict(
    pcm: bytes, journal: dict, cuts: Cuts | None, cleaned: dict | None
) -> list[str]:
    """What went wrong, in the words shown to whoever runs the bench."""
    beats = journal["live"]
    aired = [row["title"] for row in journal["metadata"] if row["title"]]
    seconds, stalls = listen(pcm)
    say(f"  à l'antenne : {', '.join(aired) or 'rien'}")
    say(f"  capture : {len(pcm) / BYTES_PER_SECOND:.1f} s, dont {seconds:.1f} s de son")
    lengths = announced(beats)
    say(
        "  durées annoncées : "
        + ", ".join(f"{name} {length:.1f} s" for name, length in lengths.items())
    )

    failures = [
        f"la même trame de 20 ms passe en boucle pendant {length:.1f} s, à partir"
        f" de {at:.1f} s : la file s'est figée, et l'antenne bourdonne"
        for at, length in stalls
    ]
    failures += [
        f"le temps restant de « {title} » n'a pas bougé pendant {still} s"
        for title, still in stuck(beats)
    ]
    failures += [
        f"« {name} » est annoncé pour {length:.1f} s, il en dure"
        f" {sounds.SOUNDS[name][0]:.1f} : le scheduler le couperait, ou"
        " attendrait sa fin bien après elle"
        for name, length in lengths.items()
        if abs(length - sounds.SOUNDS[name][0]) > LENGTH_SLACK
    ]
    failures += [
        f"« {name} » est passé à l'antenne sans temps restant"
        for name in MEASURED
        if name in aired and name not in lengths
    ]
    failures += [
        f"pendant « {name} », le playout dit la source « {source} », pas"
        f" « {QUEUES[name]} » : le scheduler ne sait pas ce qui est à l'antenne"
        for name, source in misnamed(beats).items()
    ]
    failures += [
        f"« {name} » est revenu à l'antenne après « {sound} » : ce son l'a coupé"
        " avant sa fin, au lieu de l'attendre"
        for name, sound in returned(aired)
    ]
    failures += [
        f"« {sound} », qui attendait la fin de « {FOLLOWS[sound][0]} », n'est pas"
        f" passé entre ce titre et « {FOLLOWS[sound][1]} »"
        for sound in misplaced(aired)
    ]
    failures += [
        f"« {name} » n'est jamais passé à l'antenne"
        for name in QUEUES
        if name not in aired
    ]
    order = [name for name in dict.fromkeys(aired) if name in TITLES]
    if order != [name for name in TITLES if name in order]:
        failures.append(f"les titres sont passés dans le désordre : {', '.join(order)}")
    if cuts is not None:
        failures += relayed(beats, journal["metadata"], cuts)
    failures += swept(cleaned)
    expected = sum(sounds.audible(name) for name in QUEUES)
    if seconds < 0.75 * expected:
        failures.append(
            f"{seconds:.1f} s de son seulement, sur {expected:.1f} s de sons poussés"
        )
    return failures


def play(bench: Bench) -> list[str]:
    playout = Playout(bench)
    playout.wait()
    mp3 = bench.sound(LIVE)
    time.sleep(EMPTY_QUEUE_SECONDS)
    capture = Capture(f"{playout.icecast}/studio.wav")
    capture.start()
    try:
        cuts = scenario(playout, mp3)
    finally:
        pcm = capture.stop()
    return verdict(pcm, playout.journal(), cuts, playout.cleaned)


def main() -> int:
    bench = Bench()
    say(f"Antenne : {HERE.parent.name}/radiotomate.liq dans {bench.image}")
    try:
        bench.up()
        try:
            failures = play(bench)
        except RuntimeError as exc:
            failures = [str(exc)]
        if failures:
            say("Échec :", error=True)
            for failure in failures:
                say(f"  - {failure}", error=True)
            say("\nLa fin du journal du playout :\n" + bench.log("playout"), error=True)
            return 1
        say(
            "Bon : chaque titre passe à son tour, annoncé pour sa durée et sous sa"
            " source, sans trame répétée ni reste figé. Le nettoyage des files"
            " laisse le prochain titre. Un relais, puis un direct, prennent"
            " l'antenne sous leur nom, et la rendent."
        )
        return 0
    finally:
        bench.down()


if __name__ == "__main__":
    sys.exit(main())
