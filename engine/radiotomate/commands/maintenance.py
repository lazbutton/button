"""
Commands for running a station: ``radiotomate maintenance …``
=============================================================

``radiotomate update`` stays for the schema migrations: a command for running a
station goes in this group. The station command (``deploy/station``) runs them in
the interface's container, through ``docker compose exec``, and shows what they
print: in French, like the rest of its output.

* ``next-live``: the next live, as the Antenne page of the console shows it.
* ``window``: whether an update may start now, with no live, named slot or dated
  broadcast of the Agenda on air or starting within ``WINDOW_MINUTES``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import click

from . import radiotomate_cli

# How far ahead ``window`` looks: an update cuts the antenna while the engine
# restarts, and a slow one, images pulled, takes a few minutes before that.
WINDOW_MINUTES = 30
# The playout's API, which the interface reaches on its network, as the
# scheduler does (scheduler_app.py), and how long ``window`` waits for it.
PLAYOUT_URL = "http://127.0.0.1:6833"
PLAYOUT_WAIT_S = 3.0


@radiotomate_cli.group()
def maintenance():
    """
    Commands for running a station, used by the station command
    """


class _App:
    """What ``load_live_slots`` reads of the Quart app: its database."""

    def __init__(self, db):
        self.extensions = {"sqlalchemy": db}


def until(seconds: int) -> str:
    """How long until a start, as the console's Antenne page says it
    (``formatDuration``, console/src/api/antenneState.ts)."""
    s = max(0, round(seconds))
    if s < 60:
        return f"{s} s"
    minutes = s // 60
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {rest:02d}" if rest else f"{hours} h"
    return f"{hours // 24} j {hours % 24} h"


def describe_next_live(slot: dict | None, now: datetime) -> str:
    """The next live in one line, for ``station status``: ``slot`` is what
    ``next_live_slot`` returns for ``now``, an aware time in Paris."""
    from radiotomate.domain.agenda import MONTHS, WEEKDAYS

    if slot is None:
        return "aucun de prévu d'ici 7 jours"
    title = slot["title"] or "Direct"
    if slot["active"]:
        return f"{title}, en cours"
    start = now + timedelta(seconds=slot["starts_in_s"])
    day = f"{WEEKDAYS[start.weekday()]} {start.day} {MONTHS[start.month - 1]}"
    return f"{title}, {day} à {start:%H:%M}, dans {until(slot['starts_in_s'])}"


@maintenance.command("next-live")
@click.pass_obj
def next_live(config):
    """
    The next live: a weekly show, or a dated live of the Agenda
    """
    import asyncio

    from radiotomate.db import QuartAlchemy
    from radiotomate.domain.emission import now_paris
    from radiotomate.scheduler.alerts import load_live_slots
    from radiotomate.scheduler.antenne import next_live_slot

    db = QuartAlchemy()
    db.init_from_config(config["db"], {})
    # The container's clock, read as Paris, like the Antenne page
    # (antenne.build_state); to the second, since next_live_slot counts whole
    # seconds until the start.
    now = now_paris(datetime.now().replace(microsecond=0))

    async def find():
        try:
            return next_live_slot(await load_live_slots(_App(db)), now)
        finally:
            await db.after_serving()

    click.echo(describe_next_live(asyncio.run(find()), now))


def what_blocks(
    now: datetime,
    slot: dict | None,
    windows: list[dict],
    lives: list[tuple[str, datetime | None]],
    harbor: bool | None = None,
) -> str | None:
    """What keeps an update from starting at ``now``, in one line, or None.

    ``slot`` is what ``next_live_slot`` returns for ``now``: a weekly show or a
    dated live of the Agenda. ``windows`` is what ``agenda.forecast_windows``
    returns from ``now`` to ``WINDOW_MINUTES`` later: the dated lives and the
    sets that can play. ``lives`` are the lives named on the Antenne page, with
    their end if they have one. ``harbor`` is what the playout says: a live on
    the harbor now, named or not (True), none (False), or nothing said (None).
    A named live only counts while the playout does not say the harbor is off:
    its row stays until the next title. What is on air comes first, then what
    starts soonest; a dated live, in both, is told as the Agenda's. ``now`` is
    an aware time in Paris."""
    from radiotomate.domain.agenda import KIND_SET
    from radiotomate.domain.emission import now_paris

    events: list[tuple[datetime, datetime | None, str, str]] = []
    for title, end in lives if harbor is not False else []:
        if end is None or end > now:
            events.append((now, end, title or "Direct", "un direct"))
    for window in windows:
        nature = "un set" if window["kind"] == KIND_SET else "un direct"
        events.append(
            (window["start"], window["end"], window["title"], f"{nature} de l'Agenda")
        )
    if slot is not None:
        start = now + timedelta(seconds=0 if slot["active"] else slot["starts_in_s"])
        events.append((start, None, slot["title"] or "Direct", "un direct"))
    if harbor:
        # Last: a named live or a slot gives it a name first.
        events.append((now, None, "Direct", "un direct"))
    on_air = [
        event
        for event in events
        if event[0] <= now and (event[1] is None or now < event[1])
    ]
    if on_air:
        _, end, title, nature = on_air[0]
        until_end = f" jusqu'à {now_paris(end):%H:%M}" if end is not None else ""
        return f"{title}, {nature}, en cours{until_end}"
    horizon = now + timedelta(minutes=WINDOW_MINUTES)
    soon = sorted(
        (event for event in events if now < event[0] <= horizon),
        key=lambda event: event[0],
    )
    if not soon:
        return None
    start, _, title, nature = soon[0]
    seconds = (start - now).total_seconds()
    return (
        f"{title}, {nature}, commence à {now_paris(start):%H:%M}, dans {until(seconds)}"
    )


async def named_lives(session) -> list[tuple[str, datetime | None]]:
    """The lives named on the Antenne page, with their end in Paris, if they
    have one: stored in UTC, naive, as expire_idle_sessions reads it."""
    from radiotomate.domain.agenda import paris
    from radiotomate.models.emission import Emission

    return [
        (row.title, paris(row.ends_at) if row.ends_at else None)
        for row in await Emission.all_sessions(session)
    ]


@maintenance.command("window")
@click.pass_obj
def window(config):
    """
    Whether an update may start now: "libre", or "occupée" and why (exit 1)
    """
    import asyncio

    from httpx import AsyncClient

    from radiotomate.db import QuartAlchemy
    from radiotomate.domain.emission import is_harbor_source, now_paris
    from radiotomate.scheduler.alerts import load_live_slots
    from radiotomate.scheduler.antenne import next_live_slot
    from radiotomate.scheduler.playout import PlayoutGateway
    from radiotomate.services.agenda import forecast_windows

    db = QuartAlchemy()
    db.init_from_config(config["db"], {})
    # The instant, in Paris, whatever the container's TZ: the Agenda's times
    # are instants, and the harbor's gate reads the weekly shows in Paris.
    now = now_paris().replace(microsecond=0)
    token = str((config.get("playout_process_config") or {}).get("token") or "")

    async def on_harbor() -> bool | None:
        """Is a live on the harbor now, says the playout's /health. None when
        it does not answer: the playout stopped, or no station around."""
        async with AsyncClient(
            base_url=PLAYOUT_URL, headers={"X-Auth-Token": token}
        ) as client:
            result = await PlayoutGateway(
                client, timeout=PLAYOUT_WAIT_S, max_attempts=1
            ).health()
        if not result.ok or not isinstance(result.payload, dict):
            return None
        return is_harbor_source(result.payload.get("source"))

    async def find():
        try:
            slot = next_live_slot(await load_live_slots(_App(db)), now)
            async with db.session() as session:
                windows = await forecast_windows(
                    session, now, now + timedelta(minutes=WINDOW_MINUTES)
                )
                lives = await named_lives(session)
            return what_blocks(now, slot, windows, lives, await on_harbor())
        finally:
            await db.after_serving()

    blocker = asyncio.run(find())
    if blocker is None:
        click.echo(
            f"libre : ni direct ni diffusion de l'Agenda d'ici {WINDOW_MINUTES} min"
        )
        return
    click.echo(f"occupée : {blocker}")
    raise SystemExit(1)
