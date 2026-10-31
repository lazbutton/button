"""
The station's settings, in the ``settings`` table under ``station.``: a station sets
its name and its addresses from the console, without rebuilding an image. The rules
are in ``domain/station.py``.

Settings with a lowercase key never reach the app's config (``from_mapping`` only
takes uppercase keys), and the YAML has no ``station`` section.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy import select

from radiotomate.domain.station import (
    KEYS,
    PUBLIC_KEYS,
    check_timezone,
    clean_settings,
)
from radiotomate.models import Setting

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

PREFIX = "station."


def station_timezone() -> str:
    """The containers' ``TZ`` (ADR 0005): the console shows it, and never sets it."""
    name = os.environ.get("TZ", "").strip().removeprefix(":")
    if name:
        return name
    # Without TZ, the C library reads /etc/localtime, and falls back to UTC.
    _, found, zone = os.path.realpath("/etc/localtime").partition("/zoneinfo/")
    return zone if found and zone else "UTC"


async def station_settings(session: ormSession) -> dict:
    """Every setting, None when unset."""
    rows = await session.scalars(
        select(Setting).where(Setting.key.in_([PREFIX + key for key in KEYS]))
    )
    stored = {row.key.removeprefix(PREFIX): row.value for row in rows}
    settings = {key: stored.get(key) or None for key in KEYS}
    port = settings["harbor_port"]
    settings["harbor_port"] = int(port) if port and port.isdigit() else None
    return settings


async def station_name(session: ormSession) -> str | None:
    row = await Setting.from_key(session, PREFIX + "name")
    return row.value if row and row.value else None


async def public_payload(session: ormSession) -> dict:
    """What a listener may see: ``GET /public/station.json``."""
    settings = await station_settings(session)
    return {key: settings[key] for key in PUBLIC_KEYS}


async def admin_payload(session: ormSession) -> dict:
    return {**await station_settings(session), "timezone": station_timezone()}


async def update_station(session: ormSession, data: dict) -> None:
    """
    Sets the keys present in ``data``, all or none. An empty value unsets its key: the
    console takes brand.json's again. A key absent from ``data`` keeps its value.
    """
    check_timezone(data.get("timezone"), station_timezone())
    for key, value in clean_settings(data).items():
        if value is not None:
            await Setting.upsert(session, PREFIX + key, value)
            continue
        row = await Setting.from_key(session, PREFIX + key)
        if row is not None:
            await session.delete(row)
