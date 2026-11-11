"""
The version of each service of the station, as the station command recorded it.

The interface has no access to Docker, which alone knows the image of each
container and the version it carries. ``station install``, ``update`` and
``restore`` (``deploy/station``) write ``versions.json`` in the data folder once the
station runs, and ``GET /system/version.json`` reads it here. A station started by
hand, with ``docker compose up``, keeps the record of the last of them.
"""

from __future__ import annotations

import json
import logging
from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING

from radiotomate.domain.agenda import iso_paris

if TYPE_CHECKING:
    from pathlib import Path

FILE = "versions.json"

_log = logging.getLogger(__name__)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def read_versions(data_root: Path) -> dict:
    """``{version, recorded_at, services}``: the version of the station, when the
    station command recorded it, in Paris, and ``{service, image, version}`` for
    each container that ran then. Nothing recorded: nulls and no service."""
    path = data_root / FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = {}
    except (OSError, ValueError):
        _log.warning("versions: %s unreadable", path)
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    recorded = None
    with suppress(KeyError, ValueError):
        recorded = datetime.fromisoformat(str(raw["recorded_at"]))
    services = [
        {
            "service": item["service"],
            "image": _text(item.get("image")),
            "version": _text(item.get("version")),
        }
        for item in raw.get("services") or []
        if isinstance(item, dict) and _text(item.get("service"))
    ]
    return {
        "version": _text(raw.get("version")),
        "recorded_at": iso_paris(recorded) if recorded and recorded.tzinfo else None,
        "services": sorted(services, key=lambda item: item["service"]),
    }
