"""La santé de la banque (FON-72) : `GET /media/health.json`.

Le calcul tourne à part, dans un fil, pendant que la route rend le dernier fait.
Il se refait après un geste noté au journal (FON-71), au bout de dix minutes,
pour les fichiers que la boucle d'import a pris depuis, ou à la demande
(`?refresh=1`). La console redemande tant qu'il tourne.

Un compte par modèle de nom (FON-68) : le reste est le même, mais les fichiers mal
nommés dépendent du modèle que la console a choisi.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import TYPE_CHECKING

from quart import Blueprint, g, jsonify, request
from sqlalchemy import func, select

from radiotomate.auth import login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.domain.agenda import iso_paris
from radiotomate.models import JournalEntry
from radiotomate.services.bank_health import bank_health, check_model, require_health
from radiotomate.services.bank_titles import require_bank_tidy
from radiotomate.services.fiches import verdict_on
from radiotomate.services.media_bank import media_root

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session as ormSession

_log = logging.getLogger(__name__)

blueprint = Blueprint("bank_health", __name__)

STALE_AFTER = timedelta(minutes=10)
FAILED = "Le compte n'a pas abouti. Réessaie dans un moment."


@dataclass
class _Count:
    result: dict | None = None
    # UTC, naive, as the journal keeps its times.
    computed_at: datetime | None = None
    # The last gesture of the journal the count has seen.
    mark: int = 0
    error: str | None = None
    task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()


# One count per model of names, and per state of the verdict (FON-80): switched
# off, the answer has no trace of it, even counted before.
_counts: dict[tuple[str, bool], _Count] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _journal_mark(session: ormSession) -> int:
    return (await session.scalar(select(func.max(JournalEntry.id)))) or 0


async def _count(  # noqa: PLR0913
    count: _Count,
    beets: BeetsIntegration,
    root: Path,
    model: str,
    mark: int,
    verdict: bool,
) -> None:
    try:
        rows = await beets.title_rows()
        result = await asyncio.to_thread(
            partial(bank_health, verdict=verdict), rows, root, model
        )
    except Exception:
        _log.exception("The bank's health could not be counted")
        count.error = FAILED
        return
    count.result, count.computed_at, count.mark, count.error = (
        result,
        _utcnow(),
        mark,
        None,
    )


def _stale(count: _Count, mark: int, now: datetime) -> bool:
    if count.result is None or count.computed_at is None:
        return count.error is None
    return count.mark != mark or now - count.computed_at > STALE_AFTER


async def settle() -> None:
    """Wait for the counts in progress: for the tests."""
    tasks = [count.task for count in _counts.values() if count.running]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def forget() -> None:
    """Forget every count: for the tests, each with its own library."""
    _counts.clear()


@blueprint.get("/media/health.json")
@login_required
async def health_json():
    await require_bank_tidy(g.dbsession)
    await require_health(g.dbsession)
    model = check_model(request.args.get("model"))
    verdict = await verdict_on(g.dbsession)
    count = _counts.setdefault((model, verdict), _Count())
    mark = await _journal_mark(g.dbsession)
    asked = request.args.get("refresh") == "1"
    if not count.running and (asked or _stale(count, mark, _utcnow())):
        count.error = None
        count.task = asyncio.create_task(
            _count(count, BeetsIntegration.get(), media_root(), model, mark, verdict)
        )
    return jsonify(
        {
            "computing": count.running,
            "computed_at": iso_paris(count.computed_at),
            "error": count.error,
            "health": count.result,
        }
    )
