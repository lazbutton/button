"""A stalled playout: the antenna airs the same sound in a loop, its queue no
longer advancing (``scheduler/stall.py``, and the ``playout_stalled`` incident
of ``scheduler/alerts.py``). The heartbeats and the levels of ``bench_beats.py``
were read on the antenna bench, with a real Liquidsoap."""

import asyncio
import itertools
import json
from pathlib import Path
from time import monotonic
from unittest.mock import patch

import httpx
import pytest
from ruamel.yaml import YAML

from radiotomate.commands.update import do_update
from radiotomate.models import Setting
from radiotomate.scheduler import alerts
from radiotomate.scheduler import live as sched_live
from radiotomate.scheduler.metrics import runtime_metrics
from radiotomate.scheduler.playout import PlayoutGateway, PlayoutResult
from radiotomate.scheduler.stall import (
    Stall,
    StallWatch,
    level_stands_still,
    stall_watch,
)
from radiotomate.scheduler_app import app_factory
from tests.scheduler.bench_beats import HEALTHY, STALLED, rows
from tests.scheduler.test_alerts import _settings, _Spy

# The level of the stall of the bench, the same at every reading.
STILL = "0.275994494957"
HEALTH = {"silence_s": "0.0", "source": "autodj", "rms": STILL}
STALL = Stall("autodj", "Dahlia", 33.115, 15.0)


def _beat(left: float, elapsed: float, **over) -> dict:
    """A heartbeat, as Liquidsoap posts it: ``left`` seconds remain."""
    md = {
        "source": "autodj",
        "radiotomate_queue": "autodj",
        "artist": "nowave",
        "title": "Dahlia",
        "remaining": str(left),
        "elapsed": str(elapsed),
    }
    md.update(over)
    return md


def _stuck(watch: StallWatch, start: int, stop: int, at: float = 0.0, **over) -> None:
    """A heartbeat a second from ``start`` to ``stop``, counted from ``at``:
    the remaining time put, the antenna going on."""
    for second in range(start, stop + 1):
        watch.beat(_beat(33.115, 3.5 + second, **over), now=at + second)


# --- the heartbeats ---


def test_a_title_that_plays_never_stalls():
    watch = StallWatch()
    for second in range(120):
        watch.beat(_beat(180.0 - second, float(second)), now=float(second))
        assert watch.stalled(15.0, now=float(second)) is None


def test_a_remaining_time_that_stays_put_while_the_antenna_goes_on_is_a_stall():
    watch = StallWatch()
    watch.beat(_beat(34.095, 2.5), now=-1.0)
    _stuck(watch, 0, 14)
    # Fourteen seconds: a title may hesitate, a stall does not end.
    assert watch.stalled(15.0, now=14.0) is None
    _stuck(watch, 15, 15)
    assert watch.stalled(15.0, now=15.0) == Stall("autodj", "Dahlia", 33.115, 15.0)
    # It counts from the heartbeat that first read this remaining time.
    _stuck(watch, 16, 60)
    assert watch.stalled(15.0, now=60.0).seconds == 60.0


def test_a_stall_ends_when_the_remaining_time_moves_again():
    watch = StallWatch()
    _stuck(watch, 0, 30)
    assert watch.stalled(15.0, now=30.0) is not None
    watch.beat(_beat(32.135, 34.5), now=31.0)
    assert watch.stalled(15.0, now=31.0) is None
    # Nor does it resume from where it was: the next stall counts from zero.
    for second in range(32, 46):
        watch.beat(_beat(32.135, 3.5 + second), now=float(second))
    assert watch.stalled(15.0, now=45.0) is None
    watch.beat(_beat(32.135, 49.5), now=46.0)
    assert watch.stalled(15.0, now=46.0).seconds == 15.0


def test_nothing_to_count_down_is_not_a_stall():
    """Nothing plays, or a title without an end: ``remaining`` is 0, or not a
    number."""
    for remaining in ("0", "0.0", "", None, "inf", "nan", "-1", "bientôt"):
        watch = StallWatch()
        for second in range(60):
            beat = _beat(0, float(second), remaining=remaining)
            watch.beat(beat, now=float(second))
        assert watch.stalled(15.0, now=59.0) is None, remaining
    # A queue that empties ends its stall.
    watch = StallWatch()
    _stuck(watch, 0, 30)
    watch.beat(_beat(0, 34.5), now=31.0)
    assert watch.stalled(15.0, now=31.0) is None


def test_an_antenna_that_does_not_go_on_does_not_count():
    """The sign is a remaining time put while ``elapsed`` goes on: before the
    outputs start, both stand."""
    watch = StallWatch()
    for second in range(60):
        watch.beat(_beat(33.115, 0.0), now=float(second))
    assert watch.stalled(15.0, now=59.0) is None
    # Seconds of antenna only: twenty that stand, then fifteen that go on.
    for second in range(60, 75):
        watch.beat(_beat(33.115, float(second)), now=float(second))
    assert watch.stalled(15.0, now=74.0).seconds == 74.0


def test_a_live_and_a_relay_are_not_watched_and_end_no_stall():
    for source in ("stream", "relay", "harbor"):
        watch = StallWatch()
        # A buffer that reads the same at every heartbeat.
        _stuck(watch, 0, 60, source=source, radiotomate_queue="")
        assert watch.stalled(15.0, now=60.0) is None, source
    # A queue stalled before a live still is under it: its heartbeats say
    # nothing of it.
    watch = StallWatch()
    _stuck(watch, 0, 30)
    _stuck(watch, 31, 90, source="stream", remaining="5.0")
    assert watch.stalled(15.0, now=90.0) == Stall("autodj", "Dahlia", 33.115, 90.0)


def test_a_jingle_that_cuts_a_stalled_queue_does_not_end_its_stall():
    """As on the bench: a jingle airs over the stalled Auto-DJ, its own
    remaining time moving, then the same frame airs again."""
    watch = StallWatch()
    _stuck(watch, 0, 30)
    for second, remaining in ((31, 1.735), (32, 0.775)):
        jingle = _beat(
            remaining, second - 30.3, source="jingles", radiotomate_queue="jingles"
        )
        watch.beat(jingle, now=float(second))
        assert watch.stalled(15.0, now=float(second)).source == "autodj"
    # Back to the queue of the Auto-DJ: the title announced is still the
    # jingle, the remaining time is the one of before.
    _stuck(watch, 33, 50, radiotomate_queue="jingles", title="jingle")
    assert watch.stalled(15.0, now=50.0) == Stall("autodj", "Dahlia", 33.115, 50.0)


def test_heartbeats_that_stop_say_nothing_of_the_queue():
    watch = StallWatch()
    assert watch.stalled(15.0, now=0.0) is None
    _stuck(watch, 0, 30)
    assert watch.stalled(15.0, now=40.0) is not None
    # Past the age the heartbeat's own incident opens at.
    assert watch.stalled(15.0, now=40.5) is None
    assert watch.stalled(15.0, max_age=5.0, now=36.0) is None
    # They come back, the remaining time as it was: still stalled, since then.
    _stuck(watch, 100, 101)
    assert watch.stalled(15.0, now=101.0).seconds == 101.0


def test_the_title_is_named_only_when_it_is_the_one_of_the_queue():
    """A cart that cuts the Auto-DJ is announced while the heartbeat still
    reads the queue of the Auto-DJ: its title is not the one that waits."""
    watch = StallWatch()
    _stuck(watch, 0, 20, radiotomate_queue="carts", title="Pub du marché")
    assert watch.stalled(15.0, now=20.0) == Stall("autodj", "", 33.115, 20.0)
    # The start sound has no queue, nor title.
    watch = StallWatch()
    _stuck(watch, 0, 20, radiotomate_queue=None, title=None)
    assert watch.stalled(15.0, now=20.0).title == ""


# --- the level ---


def test_the_level_stands_still_only_on_the_same_sound_and_never_on_a_silence():
    assert level_stands_still({"rms": STILL}, {"rms": STILL}) is True
    # A title that plays, then a steady tone sent by an encoder: read on the
    # bench, a second apart.
    for before, after in (
        ("0.276657883018", "0.276502731501"),
        ("0.0593611581746", "0.0593608638202"),
    ):
        assert level_stands_still({"rms": before}, {"rms": after}) is False
    # A silence is the same at every reading: its own incident tells of it.
    assert level_stands_still({"rms": "0.0"}, {"rms": "0.0"}) is False
    # A reading that misses, or a playout that does not give the level.
    for missing in (None, {}, {"rms": ""}, {"rms": "inf"}, {"rms": None}):
        assert level_stands_still({"rms": STILL}, missing) is None
        assert level_stands_still(missing, {"rms": STILL}) is None


# --- the incident ---


def test_headline_and_detail():
    assert alerts.headline("playout_stalled", False, "radio.example") == (
        "L'antenne est figée · radio.example"
    )
    assert alerts.headline("playout_stalled", True) == "L'antenne n'est plus figée"
    assert alerts.stall_detail(STALL, 15.0) == (
        "« Dahlia » n'avance plus depuis 15 s :"
        " le même son passe en boucle (source autodj)"
    )
    assert alerts.stall_detail(Stall("autodj", "", 33.115, 15.0), 125.0) == (
        "Le titre de la file n'avance plus depuis 2 min 05 s :"
        " le même son passe en boucle (source autodj)"
    )
    assert alerts.AlertSettings.from_config({}).stall_seconds == 15.0
    assert alerts.AlertSettings.from_config({"stall_seconds": 20}).stall_seconds == 20
    assert alerts.AlertSettings.from_config({"stall_seconds": 0}).stall_seconds == 15.0


async def test_a_stall_opens_only_once_the_level_stands_still_too_then_resolves(
    monkeypatch,
):
    clock = [1_000_000.0]
    monkeypatch.setattr(alerts, "time", lambda: clock[0])
    spy = _Spy()
    monitor = alerts.AlertMonitor(_settings(cooldown_seconds=600), spy)
    # The remaining time stands, the level was not read: nothing yet.
    assert await monitor.step(HEALTH, 1.0, stall=STALL) == []
    # The level moves: a cart or a live over a title that waits.
    assert await monitor.step(HEALTH, 1.0, stall=STALL, level_still=False) == []
    # The level alone says nothing of the queue.
    assert await monitor.step(HEALTH, 1.0, level_still=True) == []
    assert monitor.open == {}
    # Both: the same sound airs in a loop.
    assert await monitor.step(HEALTH, 1.0, stall=STALL, level_still=True) == [
        "open:playout_stalled"
    ]
    assert spy.sent[0]["kind"] == "playout_stalled"
    assert spy.sent[0]["body"] == (
        "« Dahlia » n'avance plus depuis 15 s :"
        " le même son passe en boucle (source autodj)"
    )
    assert monitor.open["playout_stalled"].opened_at == clock[0] - 15
    # Still stalled a minute later: once, and the detail follows.
    clock[0] += 60
    later = Stall("autodj", "Dahlia", 33.115, 75.0)
    assert await monitor.step(HEALTH, 1.0, stall=later, level_still=True) == []
    assert "depuis 1 min 15 s" in monitor.open["playout_stalled"].detail
    # The remaining time moves again.
    clock[0] += 15
    assert await monitor.step(HEALTH, 1.0) == ["resolved:playout_stalled"]
    assert spy.sent[1]["resolved"] is True
    assert spy.sent[1]["body"].startswith("Durée : 1 min 30 s\nDernier relevé : ")
    assert monitor.open == {}


async def test_an_open_stall_holds_through_what_cuts_it_then_ends_on_a_long_cut(
    monkeypatch,
):
    """A jingle or a cart over the stalled queue: the level moves, the
    remaining time still stands. Its end would be false good news. A long
    programme over it is an antenna that is fine: the stall ends, and returns
    with the same sound."""
    clock = [1_000_000.0]
    monkeypatch.setattr(alerts, "time", lambda: clock[0])
    spy = _Spy()
    monitor = alerts.AlertMonitor(_settings(cooldown_seconds=86400), spy)
    started = clock[0] - 15

    def stall() -> Stall:
        return Stall("autodj", "Dahlia", 33.115, clock[0] - started)

    assert await monitor.step(HEALTH, 1.0, stall=stall(), level_still=True) == [
        "open:playout_stalled"
    ]
    # Four minutes of advertising, a turn every fifteen seconds.
    for _ in range(16):
        clock[0] += 15
        assert await monitor.step(HEALTH, 1.0, stall=stall(), level_still=False) == []
    # A reading that misses in the middle changes nothing.
    assert await monitor.step(HEALTH, 1.0, stall=stall(), level_still=None) == []
    # The same frame again: still the same incident, counted from its start.
    clock[0] += 15
    assert await monitor.step(HEALTH, 1.0, stall=stall(), level_still=True) == []
    assert monitor.open["playout_stalled"].opened_at == started
    # An hour of a recorded show over it: five minutes in, the stall ends.
    quiet = []
    for _ in range(24):
        clock[0] += 15
        quiet += await monitor.step(HEALTH, 1.0, stall=stall(), level_still=False)
    assert quiet == ["resolved:playout_stalled"]
    assert monitor.open == {}
    # The show ends on the same frame: it opens again at once, counted from
    # the last level seen to move, not from an hour ago.
    clock[0] += 15
    assert await monitor.step(HEALTH, 1.0, stall=stall(), level_still=True) == [
        "open:playout_stalled"
    ]
    assert monitor.open["playout_stalled"].opened_at == clock[0] - 15
    assert "depuis 15 s" in spy.sent[-1]["body"]


async def test_a_stall_that_follows_a_cart_counts_from_the_cart_not_before(
    monkeypatch,
):
    """The heartbeat reads the remaining time of the title a cart has cut: it
    stood for the three minutes of the cart, on an antenna that was fine."""
    clock = [1_000_000.0]
    monkeypatch.setattr(alerts, "time", lambda: clock[0])
    monitor = alerts.AlertMonitor(_settings(), _Spy())
    cut = clock[0]
    for _ in range(12):
        clock[0] += 15
        waiting = Stall("autodj", "", 33.115, clock[0] - cut)
        assert await monitor.step(HEALTH, 1.0, stall=waiting, level_still=False) == []
    clock[0] += 15
    stalled = Stall("autodj", "", 33.115, clock[0] - cut)
    assert await monitor.step(HEALTH, 1.0, stall=stalled, level_still=True) == [
        "open:playout_stalled"
    ]
    assert monitor.open["playout_stalled"].opened_at == clock[0] - 15


async def test_an_incident_forgotten_leaves_without_a_word(tmp_path: Path):
    """ADR 0009, the switch off: no recovery goes out for the incident it
    closes, and nothing of it stays for a restart."""
    posts: list[dict] = []

    def hook(request: httpx.Request) -> httpx.Response:
        posts.append(json.loads(request.content))
        return httpx.Response(200, json={})

    settings = _settings()
    client = httpx.AsyncClient(transport=httpx.MockTransport(hook))
    state = tmp_path / "alerts.json"
    monitor = alerts.AlertMonitor(
        settings, alerts.Notifier(settings, client), state_path=state
    )
    await monitor.step(HEALTH, 1.0, stall=STALL, level_still=True)
    assert "playout_stalled" in json.loads(state.read_text())["open"]
    monitor.forget("playout_stalled")
    monitor.forget("playout_stalled")
    assert json.loads(state.read_text())["open"] == {}
    assert await monitor.step(HEALTH, 1.0) == []
    assert [(post["kind"], post["resolved"]) for post in posts] == [
        ("playout_stalled", False)
    ]


# --- the bench, replayed ---


async def _replay(trace: str, monkeypatch) -> tuple[alerts.AlertMonitor, list, list]:
    """A trace of the bench through the watch and the monitor, as the loop of
    the alerts reads them: a turn every five rows, its shortest interval, and
    the level read again a row later when the remaining time stands. Returns
    the monitor, what each turn emitted, and the turns the remaining time
    stood at."""
    clock = [0.0]
    monkeypatch.setattr(alerts, "time", lambda: 1_000_000.0 + clock[0])
    watch = StallWatch()
    monitor = alerts.AlertMonitor(_settings(), _Spy())
    beats = rows(trace)
    emitted, standing = [], []
    for index, (seconds, remaining, elapsed, rms) in enumerate(beats[:-1]):
        clock[0] = seconds
        watch.beat(_beat(remaining, elapsed), now=seconds)
        if index % 5:
            continue
        stall = watch.stalled(monitor.settings.stall_seconds, now=seconds)
        level = None
        if stall is not None:
            standing.append(seconds)
            level = level_stands_still({"rms": rms}, {"rms": beats[index + 1][3]})
        turn = await monitor.step(HEALTH, 0.5, stall=stall, level_still=level)
        if turn:
            emitted.append((seconds, turn))
    return monitor, emitted, standing


async def test_the_stall_of_the_bench_opens_the_incident_and_keeps_it(monkeypatch):
    """The queue of the Auto-DJ stalls 15.1 s in. A live, then a cart, cut it:
    the incident stays, and the same frame airs again after each."""
    monitor, emitted, standing = await _replay(STALLED, monkeypatch)
    # Fifteen seconds of a remaining time put, then the next turn.
    assert emitted == [(30.3, ["open:playout_stalled"])]
    incident = monitor.open["playout_stalled"]
    assert incident.opened_at == pytest.approx(1_000_000.0 + 15.1)
    assert incident.detail.startswith("« Dahlia » n'avance plus depuis ")
    # The remaining time never moved again, not under the live nor the cart:
    # it stood at every turn since, to the last one.
    turns = [seconds for seconds, *_ in rows(STALLED)[:-1]][::5]
    assert standing == [seconds for seconds in turns if seconds >= 30.3]
    assert len(standing) == 12


async def test_a_healthy_playout_never_opens_it_though_its_remaining_time_stands(
    monkeypatch,
):
    """A live, then a relay, over a title of the Auto-DJ: the heartbeats say
    ``autodj`` and a remaining time put, for as long as each lasts. Only the
    level tells them from a stall."""
    monitor, emitted, standing = await _replay(HEALTHY, monkeypatch)
    assert emitted == []
    assert monitor.open == {}
    # Under the live, then under the relay.
    assert standing == [50.3, 55.4, 100.7]


# --- the loop, and its switch ---


class _App:
    """What the loop needs of the scheduler: a playout that answers /health,
    and counts its readings."""

    def __init__(self, health: dict | None):
        self.health = health
        self.readings = 0

        def playout(request: httpx.Request) -> httpx.Response:
            self.readings += 1
            if self.health is None:
                return httpx.Response(503)
            return httpx.Response(200, json=self.health)

        self.config = {
            "PLAYOUT_CLIENT": httpx.AsyncClient(
                transport=httpx.MockTransport(playout), base_url="http://playout"
            )
        }
        self.extensions: dict = {}


async def test_the_level_is_read_again_only_when_the_remaining_time_stands(
    monkeypatch,
):
    monkeypatch.setattr(alerts, "LEVEL_GAP_SECONDS", 0.01)
    settings = _settings()
    app = _App(HEALTH)
    # A title that plays: the turn's reading is enough.
    stall_watch.beat(_beat(34.095, 2.5), now=monotonic() - 21)
    assert await alerts.read_stall(app, settings, HEALTH) == (None, None)
    assert app.readings == 0
    # The remaining time has stood for twenty seconds, to this one, and the
    # playout airs the same sound.
    _stuck(stall_watch, 0, 20, at=monotonic() - 20)
    stall, level_still = await alerts.read_stall(app, settings, HEALTH)
    assert (stall.source, stall.title, level_still) == ("autodj", "Dahlia", True)
    assert app.readings == 1
    # Another sound: the level has moved since the turn's reading.
    app.health = dict(HEALTH, rms="0.276502731501")
    assert (await alerts.read_stall(app, settings, HEALTH))[1] is False
    assert app.readings == 2
    # A playout that stops answering: not read, which is not "it moves".
    app.health = None
    assert (await alerts.read_stall(app, settings, HEALTH))[1] is None
    # Nor read again when the turn's own reading has failed.
    asked = app.readings
    assert (await alerts.read_stall(app, settings, None))[1] is None
    assert app.readings == asked
    # A missing extension, as in these fakes, keeps the alert on.
    assert await alerts.stall_alert_on(app) is True


class _Station:
    """A scheduler and its playout, which beats on. ``stuck``: the remaining
    time of its heartbeats is put, as over a title that waits under a cart, or
    stalled. ``playing``: the level of its antenna moves."""

    def __init__(self, app, client, auth: dict):
        self.app = app
        self.client = client
        self.auth = auth
        self.stuck = True
        self.playing = True
        self.levels = itertools.count(1)

    async def health(self) -> PlayoutResult:
        """In place of ``PlayoutGateway.health``."""
        runtime_metrics.heartbeat()  # Liquidsoap beats from the start
        # A sound that plays reads another level each time; a stall, the same.
        rms = f"0.27{next(self.levels):010d}" if self.playing else STILL
        payload = {"source": "autodj", "silence_s": "0.0", "rms": rms}
        return PlayoutResult(ok=True, status_code=200, payload=payload)

    async def beat_on(self) -> None:
        for beat in itertools.count(1):
            remaining = 33.115 if self.stuck else 600 - beat * 0.05
            md = _beat(remaining, beat * 0.05)
            await self.client.post("/live", headers=self.auth, json=md)
            await asyncio.sleep(0.05)

    async def incidents(self) -> list[dict]:
        """The incidents of the Antenne page."""
        response = await self.client.get("/antenne/state.json", headers=self.auth)
        assert response.status_code == 200
        return (await response.get_json())["incidents"]

    async def until(self, kinds: list[str]) -> list[dict]:
        """The incidents of the Antenne page, once they are of these kinds."""
        deadline = monotonic() + 10
        while True:
            incidents = await self.incidents()
            if [row["kind"] for row in incidents] == kinds:
                return incidents
            assert monotonic() < deadline, f"{incidents}, attendus : {kinds}"
            await asyncio.sleep(0.05)

    async def switch(self, value: str | None) -> None:
        """Sets ``features.stalled_playout_alert``, or removes the key."""
        async with self.app.extensions["sqlalchemy"].session() as session:
            if value is None:
                row = await Setting.from_key(session, alerts.SETTING_STALL_ALERT)
                await session.delete(row)
            else:
                await Setting.upsert(session, alerts.SETTING_STALL_ALERT, value)
            await session.commit()


@pytest.fixture
async def station(app_configration: dict, beets_integration, auth: dict, monkeypatch):
    """The real scheduler, its loop of the alerts turning every 50 ms, and a
    playout that stalls after 0.3 s of a remaining time put."""
    monkeypatch.setattr(alerts, "MIN_INTERVAL", 0.05)
    monkeypatch.setattr(alerts, "DEFAULT_INTERVAL", 0.05)
    monkeypatch.setattr(alerts, "LEVEL_GAP_SECONDS", 0.01)
    # Not the disks of this machine: one could be almost full.
    monkeypatch.setattr(alerts, "disk_paths", lambda data_root: [])
    monkeypatch.delenv("RTCONFIG", raising=False)
    # The clock is not what is tested: no tick on these heartbeats.
    monkeypatch.setattr(sched_live, "should_run_tick", lambda live_data: False)
    # tests.yaml keeps the watch off for the other tests.
    config = dict(app_configration)
    config["alerts"] = {"stall_seconds": 0.3}
    path = Path(config["data"]["root"]) / "radiotomate.yaml"
    yaml = YAML()
    data = yaml.load(path)
    data["alerts"] = {"stall_seconds": 0.3}
    yaml.dump(data, path)
    app = app_factory(config, beets_integration)
    await do_update(app.extensions["sqlalchemy"].engine)
    async with app.test_app() as test_app:
        station = _Station(app, test_app.test_client(), auth)
        with patch.object(PlayoutGateway, "health", new=station.health):
            beating = asyncio.create_task(station.beat_on())
            try:
                # The heartbeats are counted: the remaining time stands.
                deadline = monotonic() + 10
                while stall_watch.stalled(0.3) is None:
                    assert monotonic() < deadline, "aucun battement compté"
                    await asyncio.sleep(0.05)
                yield station
            finally:
                beating.cancel()
                await asyncio.gather(beating, return_exceptions=True)


async def test_a_stalled_playout_shows_on_the_antenne_page(station: _Station):
    """From the heartbeats posted to /live to the Antenne page, through the
    loop of the alerts."""
    # A cart over a title that waits: the remaining time stands, the level
    # moves. No incident, turn after turn.
    await asyncio.sleep(0.5)
    assert await station.incidents() == []
    # The same sound in a loop.
    station.playing = False
    [incident] = await station.until(["playout_stalled"])
    assert incident["detail"].startswith("« Dahlia » n'avance plus depuis ")
    assert incident["detail"].endswith(" : le même son passe en boucle (source autodj)")
    # No target on this station: to the log only.
    assert incident["notified"] is False
    # The queue advances again: the incident closes.
    station.stuck = False
    station.playing = True
    await station.until([])


async def test_the_switch_closes_the_incident_and_opens_it_again(station: _Station):
    """ADR 0009: ``features.stalled_playout_alert`` set to false, a stalled
    playout opens no incident, and the open one leaves. True, or the key gone,
    it opens again."""
    station.playing = False
    await station.until(["playout_stalled"])
    await station.switch("false")
    await station.until([])
    await asyncio.sleep(0.5)
    assert await station.incidents() == []
    # No recovery was written for it: the file of the open incidents is empty.
    state = Path(station.app.config["DATA_ROOT"]) / "alerts.json"
    assert json.loads(state.read_text())["open"] == {}
    await station.switch("true")
    await station.until(["playout_stalled"])
    await station.switch("0")
    await station.until([])
    await station.switch(None)
    await station.until(["playout_stalled"])
