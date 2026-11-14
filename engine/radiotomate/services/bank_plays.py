"""The plays of a title of the bank, read in the air log (FON-76). Sans Quart.

The air log (``metadata_log``) keeps 90 days of what went on air, with its source,
its cart and the file played (``source_url``, the request as the playout pushed it:
``annotate:…:/media/…``). The rundown keeps its lines 7 days only: where a line is
still there, it says that a sound of a cart came from the Agenda.

A title renamed by BUTTON (FON-68) keeps its plays by its former paths, which the
journal of gestures will give: ``title_plays`` takes them all.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from radiotomate.domain.emission import PARIS
from radiotomate.models import MetadataLog
from radiotomate.scheduler.retention import DEFAULT_METADATA_DAYS

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session as ormSession

PLAYS_DAYS = DEFAULT_METADATA_DAYS
RECENT = 10
AGENDA_ORIGIN = "agenda"
# Where a title came from, as the fiche says it.
ORIGINS = ("autodj", "bac", "agenda", "autre")


def _uri_matches(uri: str, paths: set[str]) -> bool:
    if uri in paths:
        return True
    # annotate:…:/media/x.mp3 : the path is what follows the last annotation.
    return any(uri.endswith(f":{path}") for path in paths)


def origin_of(log: MetadataLog) -> str:
    item = log.rundown_item
    if item is not None and item.origin == AGENDA_ORIGIN:
        return "agenda"
    if log.source == "autodj":
        return "autodj"
    if log.source in ("carts", "jingles") or log.cart_id is not None:
        return "bac"
    return "autre"


def _on_air(log: MetadataLog) -> str | None:
    """The air log keeps the container's wall clock (engine/AGENTS.md): to Paris."""
    if log.on_air is None:
        return None
    return log.on_air.astimezone(PARIS).isoformat(timespec="minutes")


async def title_plays(
    session: ormSession,
    paths: Iterable[str],
    *,
    now: datetime | None = None,
    recent: int = RECENT,
) -> dict:
    """How many times these files went on air in 90 days, the last ones, and from where.

    A title skipped before it played (``extra.skipped``) is not a play.
    """
    wanted = {path for path in paths if path}
    since = (now or datetime.now()) - timedelta(days=PLAYS_DAYS)
    plays: list[MetadataLog] = []
    if wanted:
        likes = [MetadataLog.source_url.like(f"%:{path}") for path in wanted]
        rows = await session.scalars(
            select(MetadataLog)
            .where(
                MetadataLog.on_air >= since,
                or_(MetadataLog.source_url.in_(wanted), *likes),
            )
            .options(
                selectinload(MetadataLog.rundown_item), selectinload(MetadataLog.cart)
            )
            .order_by(MetadataLog.on_air.desc(), MetadataLog.id.desc())
        )
        plays = [
            log
            for log in rows
            if _uri_matches(str(log.source_url or ""), wanted)
            and not (log.extra or {}).get("skipped")
        ]
    by_origin = dict.fromkeys(ORIGINS, 0)
    for log in plays:
        by_origin[origin_of(log)] += 1
    return {
        "days": PLAYS_DAYS,
        "count": len(plays),
        "by_origin": by_origin,
        "recent": [
            {
                "on_air": _on_air(log),
                "origin": origin_of(log),
                "cart": {"id": log.cart.id, "title": log.cart.title}
                if log.cart is not None
                else None,
            }
            for log in plays[:recent]
        ],
    }
