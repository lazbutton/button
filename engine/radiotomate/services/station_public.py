"""What the station's own website reads, without an account and from another
domain: the coming week and the last music tracks. No Quart, no writes.

Only titles, times and kinds leave: never a guest, a host, a file, rights, a
tracklist, notes or a preparation state. Agenda rows hold naive UTC and
``metadata_log`` the container's local time (ADR 0008): each goes out through
its own domain function, at Paris time with its offset, to the second.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from radiotomate.domain.agenda import AIR_MISSED, KIND_LIVE, KIND_SET, paris, utc
from radiotomate.domain.emission import PARIS, now_paris
from radiotomate.domain.errors import DomainValidationError
from radiotomate.enums import PositionKind
from radiotomate.models import AgendaDiffusion, MetadataLog, RundownItem
from radiotomate.services import agenda

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

PROGRAMME_DAYS = 7
# ``kind`` of a programme item: a weekly show, or a dated broadcast (Agenda).
KIND_EMISSION = "emission"
PUBLIC_KINDS = {KIND_SET: "set", KIND_LIVE: "direct"}

HISTORY_LIMIT = 20
HISTORY_MAX = 50
# The queues the automation plays from. A live (``stream``) or a relay carries
# whatever its encoder or its source sends.
MUSIC_SOURCES = ("autodj", "carts")
# services/nowplaying's placeholder, before any metadata.
WAITING_TITLE = "En attente de métadonnées"


def _agenda_time(value: datetime) -> str:
    """An Agenda instant (naive UTC, or aware) at Paris time."""
    return paris(value).isoformat(timespec="seconds")


def _local_time(value: datetime) -> str:
    """A local wall time of the historical tables, with its Paris offset."""
    return now_paris(value).isoformat(timespec="seconds")


# -- the programme -------------------------------------------------------------


async def programme_payload(session: ormSession, now: datetime | None = None) -> dict:
    """Seven days from today: the weekly shows that do happen, the dated
    broadcasts. The Agenda switched off gives an empty week, not an error."""
    first = now_paris(now).date()
    last = first + timedelta(days=PROGRAMME_DAYS - 1)
    payload = {
        "timezone": PARIS.key,
        "from": first.isoformat(),
        "to": last.isoformat(),
        "items": [],
    }
    if not await agenda.agenda_enabled(session):
        return payload
    low, high = agenda._day_bounds(first, last)
    diffusions = await AgendaDiffusion.between(session, low, high)
    # The console's strings, read back: the rule that cancels a weekly day, or
    # gives it to a dated broadcast, stays in weekly_occurrences().
    entries = [
        (
            datetime.fromisoformat(row["starts_at"]),
            datetime.fromisoformat(row["ends_at"]),
            row["title"],
            KIND_EMISSION,
        )
        for row in await agenda.weekly_occurrences(session, first, last, diffusions)
        if not row["cancelled"] and row["replaced_by"] is None
    ]
    # A missed broadcast did not air, nor did the weekly show it covered.
    entries += [
        (row.starts_at, row.ends_at, row.title, PUBLIC_KINDS[row.kind])
        for row in diffusions
        if row.air_status != AIR_MISSED and row.kind in PUBLIC_KINDS
    ]
    entries.sort(key=lambda entry: (utc(entry[0]), utc(entry[1]), entry[2]))
    payload["items"] = [
        {
            "starts_at": _agenda_time(start),
            "ends_at": _agenda_time(end),
            "title": title,
            "kind": kind,
        }
        for start, end, title, kind in entries
    ]
    return payload


# -- the last tracks -----------------------------------------------------------


def history_limit(raw: object) -> int:
    """``?limit=``: 20 when absent, 50 at most."""
    text = str(raw or "").strip()
    if not text:
        return HISTORY_LIMIT
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise DomainValidationError(f"Entre 1 et {HISTORY_MAX} titres.", field="limit")
    return min(value, HISTORY_MAX)


async def history_payload(session: ormSession, limit: int = HISTORY_LIMIT) -> dict:
    """The last music tracks played, newest first."""
    title = func.trim(func.coalesce(MetadataLog.title, ""))
    first_plays = (
        select(func.min(MetadataLog.id).label("id"))
        # Music is what the rundown planned as music: a jingle, an ident, an
        # ad, a sound, a set or a live has another kind, or no rundown item.
        .join(RundownItem, RundownItem.id == MetadataLog.rundown_item_id)
        .where(
            RundownItem.kind == PositionKind.MUSIQUE.value,
            MetadataLog.source.in_(MUSIC_SOURCES),
            MetadataLog.on_air.is_not(None),
            # A title cut by a hard sync, logged afterwards (scheduler/clock.py).
            func.coalesce(func.json_extract(MetadataLog.extra, "$.skipped"), 0) == 0,
            title != "",
            title != WAITING_TITLE,
        )
        # The antenna coming back to a track after a cut logs it again.
        .group_by(MetadataLog.rundown_item_id)
        .subquery()
    )
    rows = await session.scalars(
        select(MetadataLog)
        .join(first_plays, first_plays.c.id == MetadataLog.id)
        .order_by(MetadataLog.on_air.desc(), MetadataLog.id.desc())
        .limit(limit)
    )
    return {
        "items": [
            {
                "played_at": _local_time(row.on_air),
                "title": (row.title or "").strip(),
                "artist": (row.artist or "").strip(),
                "album": (row.album or "").strip(),
            }
            for row in rows
        ]
    }
