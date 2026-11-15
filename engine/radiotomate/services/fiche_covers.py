"""The cover of the title on air, for the console (FON-83).

Settled on 15 November 2026 with the user: the cover shows in the console only,
behind `features.fiches_covers`, off by default, and by its link only. It is never
copied, never written in the file, and `now.json` says nothing of it: this module
adds ``cover_url`` to the snapshot of `GET /live.json` alone.

The title on air is found by its file: the path that ``initial_uri`` names, then its
id in Beets, then its fiche. Only a title found (« trouvé ») shows its cover: a title
only approached could be another record.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import TYPE_CHECKING

from sqlalchemy import select

from radiotomate.fiches.covers import cover_of
from radiotomate.fiches.evidence import from_json
from radiotomate.models.fiche import Fiche
from radiotomate.services.fiches import covers_on
from radiotomate.services.listen_link import is_music

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.orm import Session as ormSession

# The ids of the last files on air, by path: the console reads /live.json every few
# seconds, and a query of Beets for each read would be wasted. A file Beets does not
# know is asked again after a minute: the import loop may index it in between.
_IDS: OrderedDict[str, tuple[int | None, float]] = OrderedDict()
_IDS_SIZE = 64
_UNKNOWN_FOR_S = 60.0


def path_of(uri: object) -> str:
    """The file of a request as the playout pushed it: ``annotate:…:/media/x.mp3``
    names it after its last annotation."""
    text = str(uri or "").strip()
    if text.startswith("annotate:"):
        at = text.rfind(":/")
        text = text[at + 1 :] if at >= 0 else ""
    return text if text.startswith("/") else ""


def forget_ids() -> None:
    """For the tests: the ids already looked for are forgotten."""
    _IDS.clear()


async def _id_at(
    path: str,
    find: Callable[[str], Awaitable[int | None]],
    now: Callable[[], float] = time.monotonic,
) -> int | None:
    kept = _IDS.get(path)
    if kept is not None and (kept[0] is not None or now() - kept[1] < _UNKNOWN_FOR_S):
        _IDS.move_to_end(path)
        return kept[0]
    found = await find(path)
    _IDS[path] = (found, now())
    _IDS.move_to_end(path)
    while len(_IDS) > _IDS_SIZE:
        _IDS.popitem(last=False)
    return found


async def cover_for(session: ormSession, beets_id: int) -> str | None:
    """The link of the cover of a title found, from its evidence."""
    row = (
        await session.execute(
            select(Fiche.status, Fiche.evidence)
            .where(Fiche.beets_id == beets_id)
            .limit(1)
        )
    ).first()
    if row is None or row.status != "trouvé" or not row.evidence:
        return None
    result, _ = from_json(row.evidence)
    return cover_of(result)


async def attach_cover(
    session: ormSession,
    snapshot: dict,
    find: Callable[[str], Awaitable[int | None]],
) -> None:
    """Adds ``cover_url`` to the live snapshot: the cover of the music on air, when
    the switch is on and its title was found. `find`: the id of a file in Beets."""
    if not is_music(snapshot.get("source")):
        return
    path = path_of(snapshot.get("initial_uri"))
    if not path or not await covers_on(session):
        return
    beets_id = await _id_at(path, find)
    if beets_id is None:
        return
    cover = await cover_for(session, beets_id)
    if cover:
        snapshot["cover_url"] = cover
