"""The families and the verdict, for the programming (FON-28). Without Quart.

- `families_payload`: for each selection of titles, the families of its titles;
  for each family, its titles, those no selection takes, and a few of them. Read
  only: how the families meet the selections is read, never imposed.
- `verdict_counts`: the verdicts the library knows, by value.
- `verdict_summary`: what erasing the verdicts would touch: the titles, the
  verdicts still waiting, and the selections whose query reads `fmg`, which will
  empty.
- `erase_verdicts`: `fmg` and `fmg_source` taken out of the whole library, under
  the bank's lock, with the verdict propositions and decisions. An admin's
  gesture.
"""

from __future__ import annotations

import logging
import re
from asyncio import to_thread
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from beets.dbcore.query import InvalidQueryArgumentValueError, ParsingError
from sqlalchemy import delete, func, select

from radiotomate.fiches.rules import FAMILIES
from radiotomate.models import MusicCategory
from radiotomate.models.fiche import (
    ACCEPTED,
    PROPOSED,
    STALE,
    WRITE_FAILED,
    FicheDecision,
    FicheProposition,
)
from radiotomate.services.bank_lock import BeetsPlace, bank_lock
from radiotomate.services.bank_titles import FAMILY_LABELS, fold, title_of
from radiotomate.services.beets_query import playable_query
from radiotomate.services.fiches import read_settings
from radiotomate.services.title_edits import require_title_edits

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration

_log = logging.getLogger(__name__)

# The titles no selection takes, shown for each family.
SAMPLE = 20
# A query that reads the verdict: `fmg:oui`, `-fmg:non`, `^fmg_source:x`.
READS_VERDICT = re.compile(r"(?:^|[^\w])fmg(?:_source)?:")
# The verdicts not written yet: erasing takes them out too.
WAITING = (PROPOSED, ACCEPTED, STALE, WRITE_FAILED)


def reads_verdict(query: str) -> bool:
    return bool(READS_VERDICT.search(query or ""))


async def _matches(beets: BeetsIntegration, query: str) -> set[int] | None:
    """The titles a selection takes, as the auto-DJ reads it; None when Beets
    does not read its query."""
    try:
        items = await beets.search(playable_query(query))
    except (ParsingError, InvalidQueryArgumentValueError, ValueError):
        return None
    return {int(item.id) for item in items}


def _family_order(values: set[str]) -> list[str]:
    known = [family.name for family in FAMILIES if family.name in values]
    others = sorted(value for value in values if value and value not in known)
    return [*known, *others, *([""] if "" in values else [])]


async def families_payload(session: ormSession, beets: BeetsIntegration) -> dict:
    """The table of the families and the selections."""
    titles = {entry["id"]: entry for entry in map(title_of, await beets.title_rows())}
    taken: set[int] = set()
    selections = []
    in_selection: dict[str, Counter] = defaultdict(Counter)
    names: dict[int, str] = {}
    for category in await MusicCategory.all(session):
        names[category.id] = category.name
        matched = await _matches(beets, category.query)
        ids = (matched or set()) & titles.keys()
        taken |= ids
        families = Counter(titles[one]["famille"] for one in ids)
        for value, count in families.items():
            in_selection[value][category.id] += count
        selections.append(
            {
                "id": category.id,
                "name": category.name,
                "query": category.query,
                "count": None if matched is None else len(ids),
                "reads_verdict": reads_verdict(category.query)
                or reads_verdict(category.empty_query),
                "families": [
                    {
                        "value": value,
                        "label": FAMILY_LABELS.get(value, value),
                        "count": count,
                    }
                    for value, count in sorted(
                        families.items(), key=lambda one: (-one[1], fold(one[0]))
                    )
                ],
            }
        )
    counts = Counter(entry["famille"] for entry in titles.values())
    families = []
    for value in _family_order(set(counts)):
        left = sorted(
            (
                entry
                for entry in titles.values()
                if entry["famille"] == value and entry["id"] not in taken
            ),
            key=lambda entry: (
                fold(entry["artist"]),
                fold(entry["title"]),
                entry["id"],
            ),
        )
        families.append(
            {
                "value": value,
                "label": FAMILY_LABELS.get(value, value),
                "count": counts[value],
                "uncategorized": len(left),
                "selections": [
                    {"id": category_id, "name": names[category_id], "count": count}
                    for category_id, count in sorted(
                        in_selection[value].items(),
                        key=lambda one: (-one[1], fold(names[one[0]])),
                    )
                ],
                "sample": [
                    {
                        "id": entry["id"],
                        "title": entry["title"],
                        "artist": entry["artist"],
                    }
                    for entry in left[:SAMPLE]
                ],
            }
        )
    settings = await read_settings(session)
    return {
        "library": len(titles),
        "verdict": settings.verdict,
        "selections": selections,
        "families": families,
    }


# -- the verdict -----------------------------------------------------------------


def _verdict_rows(beets: BeetsIntegration) -> tuple[dict[str, int], int]:
    with beets.lib.transaction() as tx:
        rows = tx.query(
            "SELECT value, COUNT(*) FROM item_attributes WHERE key = 'fmg' "
            "GROUP BY value"
        )
        marked = tx.query(
            "SELECT COUNT(DISTINCT entity_id) FROM item_attributes "
            "WHERE key IN ('fmg', 'fmg_source')"
        )
    return {str(value): int(count) for value, count in rows}, int(marked[0][0])


async def verdict_counts(beets: BeetsIntegration) -> dict[str, int]:
    """The verdicts the library knows: oui, mixte, non, by titles."""
    try:
        counts, _marked = await to_thread(_verdict_rows, beets)
    except AttributeError:
        # The demo's library has no table to read.
        return {}
    return {value: counts.get(value, 0) for value in ("oui", "mixte", "non")}


async def verdict_summary(session: ormSession, beets: BeetsIntegration) -> dict:
    """What erasing the verdicts would touch."""
    _counts, marked = await to_thread(_verdict_rows, beets)
    waiting = await session.scalar(
        select(func.count(FicheProposition.id)).where(
            FicheProposition.field == "fmg", FicheProposition.state.in_(WAITING)
        )
    )
    selections = []
    for category in await MusicCategory.all(session):
        if not (reads_verdict(category.query) or reads_verdict(category.empty_query)):
            continue
        matched = await _matches(beets, category.query)
        selections.append(
            {
                "id": category.id,
                "name": category.name,
                "query": category.query,
                "count": None if matched is None else len(matched),
            }
        )
    return {"titles": marked, "waiting": int(waiting or 0), "selections": selections}


def _erase(beets: BeetsIntegration) -> int:
    with beets.lib.transaction() as tx:
        marked = tx.query(
            "SELECT COUNT(DISTINCT entity_id) FROM item_attributes "
            "WHERE key IN ('fmg', 'fmg_source')"
        )
        tx.mutate("DELETE FROM item_attributes WHERE key IN ('fmg', 'fmg_source')")
    return int(marked[0][0])


async def erase_verdicts(
    session: ormSession, beets: BeetsIntegration, *, username: str
) -> dict:
    """`fmg` and `fmg_source` out of the whole library, and the verdicts waiting.
    A title searched again, verdict switched on, gets its proposition back."""
    await require_title_edits(session)
    summary = await verdict_summary(session, beets)
    async with bank_lock(BeetsPlace.of(beets.lib)):
        erased = await to_thread(_erase, beets)
    await session.execute(
        delete(FicheProposition).where(FicheProposition.field == "fmg")
    )
    # A decision kept by the key would write the verdict again on a file that
    # comes back.
    await session.execute(delete(FicheDecision).where(FicheDecision.field == "fmg"))
    await session.commit()
    _log.info("fiches : %s a effacé les verdicts de %s titre(s)", username, erased)
    return {
        "titles": erased,
        "waiting": summary["waiting"],
        "selections": summary["selections"],
    }
