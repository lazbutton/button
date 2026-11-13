"""A stalled playout: the antenna still airs sound, but its queue no longer advances.

On 2026-11-12 a station aired the same 20 ms frame in a loop for tens of
minutes: the crossfade around the Auto-DJ queue had stopped pulling it. Nothing
was silent and nothing was logged, so no alert left. Two things gave it away,
read on the antenna bench (``playout/tests``) with Liquidsoap 2.4.6:

* in the heartbeat Liquidsoap posts to ``POST /live`` every second,
  ``remaining`` kept the same value above zero while ``elapsed`` went on;
* in ``GET /health``, ``rms``, the level of the antenna over its last 0.2 s,
  read the same to the last digit every time. On sound that plays it never
  does, not even on a steady tone sent by an encoder.

Neither is enough alone. With Liquidsoap 2.4.5 as with 2.4.6, the heartbeat
names its source ``autodj`` while a cart, a live or a relay cuts a title of the
Auto-DJ, and carries the remaining time of the title cut, which waits: there, a
remaining time that stays put is an antenna that is fine. And a level that
stands still says nothing of the queue.
:class:`StallWatch` reads the first sign in each heartbeat,
:func:`level_stands_still` the second in two readings of ``/health``, and
:mod:`radiotomate.scheduler.alerts` opens the ``playout_stalled`` incident when
both hold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from time import monotonic

from radiotomate.scheduler.timing import remaining_seconds, source_id

# A live and a relay have no end to count down.
UNWATCHED = {"stream", "relay"}
# Without a heartbeat for this long, nothing says the queue still stands.
DEFAULT_MAX_AGE = 10.0
# Two heartbeats further apart than this count for this much: a scheduler that
# was held up has two readings, not a minute of them.
MAX_BEAT_GAP = 5.0
# A queue that no heartbeat has read for this long is no longer told stalled:
# another one holds the antenna, and nothing says what became of it.
QUEUE_MAX_AGE = 300.0


@dataclass(frozen=True)
class Stall:
    """A queue whose remaining time has stopped moving while the antenna went
    on. ``seconds``: since it last moved. ``title``: empty when the title
    announced was not the one of this queue. ``still``: the seconds of antenna
    counted so far, which grow only while heartbeats say the antenna goes on."""

    source: str
    title: str
    remaining: float
    seconds: float
    still: float = field(default=0.0, compare=False)


@dataclass
class _Queue:
    """What the heartbeats last said of a queue: the remaining time it holds,
    since when, and for how many seconds of antenna."""

    remaining: float
    title: str
    since: float
    still: float = 0.0
    # The last heartbeat that read this queue.
    seen: float = 0.0


def _seconds(raw) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _title(live_data: dict, source: str) -> str:
    """The title a heartbeat announces, when it is the one of the queue it
    reads: a cart that cuts the Auto-DJ is announced while the heartbeat still
    reads the queue of the Auto-DJ."""
    pushed = str(live_data.get("radiotomate_queue") or "")
    if pushed and pushed != source:
        return ""
    return str(live_data.get("title") or "").strip()


class StallWatch:
    """Reads each heartbeat, and says which queue has stopped advancing.

    A queue keeps what was last read of it while another one is on air: a
    jingle that cuts a stalled Auto-DJ does not end its stall, and only a
    heartbeat of that queue with another remaining time does.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._queues: dict[str, _Queue] = {}
        # The last heartbeat: when, its source, its elapsed time.
        self._last: tuple[float, str, float] | None = None

    def beat(self, live_data: dict, now: float | None = None) -> None:
        now = monotonic() if now is None else now
        source = source_id(live_data)
        remaining = remaining_seconds(live_data)
        elapsed = _seconds(live_data.get("elapsed"))
        previous, self._last = self._last, (now, source, elapsed)
        if source in UNWATCHED:
            return
        if not remaining > 0 or not math.isfinite(remaining):
            # Nothing to count down: an empty queue, or a title without an end.
            self._queues.pop(source, None)
            return
        queue = self._queues.get(source)
        if queue is None or queue.remaining != remaining:
            title = _title(live_data, source)
            self._queues[source] = _Queue(remaining, title, now, seen=now)
            return
        queue.seen = now
        # The same remaining time as at the heartbeat before, of the same
        # queue: it counts while the antenna goes on.
        if previous is not None and previous[1] == source and elapsed != previous[2]:
            queue.still += min(now - previous[0], MAX_BEAT_GAP)

    def stalled(
        self,
        seconds: float,
        *,
        max_age: float = DEFAULT_MAX_AGE,
        now: float | None = None,
    ) -> Stall | None:
        """The queue whose remaining time has not moved for ``seconds`` of
        antenna, the oldest first. None once the heartbeats stop: the
        heartbeat's own incident tells of it."""
        now = monotonic() if now is None else now
        if self._last is None or now - self._last[0] > max_age:
            return None
        found: tuple[str, _Queue] | None = None
        for source, queue in self._queues.items():
            if queue.still < seconds or now - queue.seen > QUEUE_MAX_AGE:
                continue
            if found is None or queue.since < found[1].since:
                found = (source, queue)
        if found is None:
            return None
        source, queue = found
        return Stall(
            source, queue.title, queue.remaining, now - queue.since, queue.still
        )


def _level(health: dict | None) -> float | None:
    if not isinstance(health, dict):
        return None
    try:
        value = float(health.get("rms"))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def level_stands_still(first: dict | None, second: dict | None) -> bool | None:
    """Two readings of ``/health`` a moment apart: whether the level of the
    antenna is the same to the last digit, the same frame in a loop. A silence
    is not: its own incident tells of it. None when a reading is missing."""
    before, after = _level(first), _level(second)
    if before is None or after is None:
        return None
    return before > 0 and before == after


stall_watch = StallWatch()
