#!/usr/bin/env python3
"""
The antenna bench: plays engine/playout/radiotomate.liq in the Liquidsoap of the
playout image, and listens to what comes out.

    python3 engine/playout/tests/antenna.py

`liquidsoap --check` only reads the script. This plays it: titles are pushed as
the scheduler pushes them, a jingle cuts in, and the bench records the WAV mount
of the console's headphones, the same sound as the public mount before its MP3
encoder. It fails when:

- a title pushed never airs, or airs out of order;
- the playout airs the same 20 ms frame again and again: the music queue has
  stalled, and the antenna buzzes;
- the remaining time of a title stays put while it plays;
- the antenna stays silent.

It needs Docker and Compose, and nothing else: standard library only. Its
messages are in French, as those of scripts/verifier.sh, which runs it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
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

TITLES = ["title-1", "title-2", "title-3", "title-4"]
JINGLE = "jingle"
# The start sound has aired, and the music queue has been empty for a while: a
# first title pushed then is what used to stall.
EMPTY_QUEUE_SECONDS = 5.0
LIMIT_SECONDS = 120.0


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

    def compose(self, *args: str, check: bool = True) -> str:
        command = ["docker", "compose", "-p", self.project]
        command += ["-f", str(HERE / "compose.yml"), *args]
        done = subprocess.run(
            command,
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
    """The playout of the bench, as the scheduler and a listener reach it."""

    def __init__(self, bench: Bench) -> None:
        self.api = bench.address("playout", 6833)
        self.journal_url = bench.address("playout", 6822) + "/journal"
        self.icecast = bench.address("icecast", 8000)

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

    def push(self, queue: str, name: str) -> None:
        payload = {
            "path": f"/sounds/{name}.mp3",
            "title": name,
            "artist": "Banc",
            "radiotomate_item_id": f"item-{name}",
        }
        status, body = call("POST", f"{self.api}/queue/{queue}", payload, timeout=30)
        if status != 200:
            raise RuntimeError(
                f"le playout a refusé {name} ({status}) : {body[:200]!r}"
            )


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


def scenario(playout: Playout) -> None:
    """Pushes the titles as the scheduler does, and a jingle on the second one."""
    pushed: list[str] = []
    jingle_at: float | None = None
    jingle_sent = False
    ending: float | None = None
    deadline = time.monotonic() + LIMIT_SECONDS
    while time.monotonic() < deadline:
        aired = playout.aired()
        # As the scheduler: two titles in the queue, behind the one on air.
        waiting = [name for name in pushed if name not in aired]
        if len(pushed) < len(TITLES) and len(waiting) < 2:
            pushed.append(TITLES[len(pushed)])
            playout.push("autodj", pushed[-1])
        # The jingle cuts the second title, two seconds in.
        if jingle_at is None and TITLES[1] in aired:
            jingle_at = time.monotonic() + 2
        elif (
            jingle_at is not None and not jingle_sent and time.monotonic() >= jingle_at
        ):
            jingle_sent = True
            playout.push("jingles", JINGLE)
        # The last title has started: leave it the time to end.
        if ending is None and TITLES[-1] in aired and JINGLE in aired:
            ending = time.monotonic() + sounds.SOUNDS[TITLES[-1]][0] + 2
        elif ending is not None and time.monotonic() >= ending:
            return
        time.sleep(0.5)


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


def verdict(pcm: bytes, aired: list[str], beats: list[dict]) -> list[str]:
    """What went wrong, in the words shown to whoever runs the bench."""
    seconds, stalls = listen(pcm)
    say(f"  à l'antenne : {', '.join(aired) or 'rien'}")
    say(f"  capture : {len(pcm) / BYTES_PER_SECOND:.1f} s, dont {seconds:.1f} s de son")

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
        f"« {name} » n'est jamais passé à l'antenne"
        for name in [*TITLES, JINGLE]
        if name not in aired
    ]
    order = [name for name in dict.fromkeys(aired) if name in TITLES]
    if order != [name for name in TITLES if name in order]:
        failures.append(f"les titres sont passés dans le désordre : {', '.join(order)}")
    expected = sum(sounds.SOUNDS[name][0] for name in [*TITLES, JINGLE])
    if seconds < 0.75 * expected:
        failures.append(
            f"{seconds:.1f} s de son seulement, sur {expected:.1f} s de sons poussés"
        )
    return failures


def play(bench: Bench) -> list[str]:
    playout = Playout(bench)
    playout.wait()
    time.sleep(EMPTY_QUEUE_SECONDS)
    capture = Capture(f"{playout.icecast}/studio.wav")
    capture.start()
    try:
        scenario(playout)
    finally:
        pcm = capture.stop()
    return verdict(pcm, playout.aired(), playout.journal()["live"])


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
        say("Bon : chaque titre passe à son tour, sans trame répétée ni reste figé.")
        return 0
    finally:
        bench.down()


if __name__ == "__main__":
    sys.exit(main())
