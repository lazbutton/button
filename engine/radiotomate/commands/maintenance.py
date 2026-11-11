"""
Commands for running a station: ``radiotomate maintenance …``
=============================================================

``radiotomate update`` stays for the schema migrations: a command for running a
station goes in this group. The station command (``deploy/station``) runs them in
the interface's container, through ``docker compose exec``, and shows what they
print: in French, like the rest of its output.

* ``next-live``: the next live, as the Antenne page of the console shows it.

The update command (MAJ-04) adds ``window`` here: whether an update may start now,
with no live, named slot or dated broadcast starting soon.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import click

from . import radiotomate_cli


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
