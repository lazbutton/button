"""Poser et retirer des étiquettes de la station sur un lot de titres (FON-74).

Chaque titre garde ses autres étiquettes : le moteur lit les siennes, en ajoute
et en retire, puis passe le lot au service d'écriture de FON-66, qui ne touche
que la bibliothèque, note le lot au journal et sait le défaire. Sans Quart.
"""

from __future__ import annotations

from asyncio import to_thread
from typing import TYPE_CHECKING

from radiotomate.domain.errors import DomainValidationError
from radiotomate.services.station_tags import FIELD, clean_tag, with_tags
from radiotomate.services.title_edits import (
    MAX_TITLES,
    EditOutcome,
    TitleEdit,
    edit_titles,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration


def _ids(raw: object) -> list[int]:
    if not isinstance(raw, list) or not raw:
        raise DomainValidationError("Choisis au moins un titre.", field="ids")
    if any(not isinstance(item, int) or isinstance(item, bool) for item in raw):
        raise DomainValidationError(
            "Chaque titre du lot se nomme par son identifiant.", field="ids"
        )
    if len(set(raw)) != len(raw):
        raise DomainValidationError(
            "Un titre paraît deux fois dans le lot.", field="ids"
        )
    if len(raw) > MAX_TITLES:
        raise DomainValidationError(
            f"Un lot prend {MAX_TITLES} titres au plus : celui-ci en a {len(raw)}.",
            field="ids",
        )
    return raw


def _tags(raw: object, field: str) -> list[str]:
    if raw in (None, ""):
        return []
    if not isinstance(raw, list):
        raise DomainValidationError("Une liste d'étiquettes est attendue.", field=field)
    return sorted({clean_tag(tag, field=field) for tag in raw})


def _current(beets: BeetsIntegration, ids: list[int]) -> dict[int, str]:
    found: dict[int, str] = {}
    for beets_id in ids:
        item = beets.lib.get_item(beets_id)
        found[beets_id] = "" if item is None else str(item.get(FIELD, "") or "")
    return found


async def tag_titles(  # noqa: PLR0913
    session: ormSession,
    beets: BeetsIntegration,
    ids: object,
    add: object,
    remove: object,
    *,
    username: str,
    dry_run: bool = False,
) -> EditOutcome:
    """Pose les étiquettes `add` et retire les étiquettes `remove` sur chaque
    titre, ou dit ce qui changerait (`dry_run`), et les sélections touchées."""
    titles = _ids(ids)
    adds = _tags(add, "add")
    removes = _tags(remove, "remove")
    if not adds and not removes:
        raise DomainValidationError(
            "Choisis une étiquette à poser ou à retirer.", field="add"
        )
    if set(adds) & set(removes):
        raise DomainValidationError(
            "Une étiquette ne se pose et ne se retire pas d'un même geste.",
            field="remove",
        )
    current = await to_thread(_current, beets, titles)
    edits = [
        TitleEdit(
            beets_id,
            {FIELD: with_tags(current[beets_id], adds, removes)},
            {FIELD: current[beets_id]},
        )
        for beets_id in titles
    ]
    return await edit_titles(session, beets, edits, username=username, dry_run=dry_run)
