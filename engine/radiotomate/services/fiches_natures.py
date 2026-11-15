"""The sure propositions, grouped by what they change (FON-79), in reading only.

A group is accepted at once, after ten examples, by the routes of FON-27: the
console sends its propositions 500 at a time. Only a proposition « sûr » and
« proposée » enters a group: a group never mixes two levels, and a proposition
« à revoir » or « rapprochée » is read alone, title by title.

- `graphie`: the title, artist, album or label written otherwise, the same text
  once normalized (`normalize_text`): case, accents, punctuation, spaces.
- `album`, `annee`: an album or a year where there was none.
- `label_isrc`: a label or an ISRC, other than a mere spelling.
- `famille`: a family.

What fits none of them, like a title that says something else, an album or a
year replaced, or the verdict, stays to be read title by title.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from radiotomate.fiches.normalize import normalize_text
from radiotomate.models import Fiche
from radiotomate.models.fiche import PROPOSED
from radiotomate.services.bank_titles import fold, title_of

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

SURE = "sûr"
NATURES = ("graphie", "album", "annee", "label_isrc", "famille")
NATURE_LABELS = {
    "graphie": "La graphie : casse, accents, ponctuation",
    "album": "Un album ajouté",
    "annee": "Une année ajoutée",
    "label_isrc": "Un label ou un ISRC",
    "famille": "Une famille",
}
# Written text whose spelling a proposition may correct.
SPELLED = ("title", "artist", "album", "label")
EXAMPLES = 10


def nature_of(field: str, before: str, value: str) -> str:
    """What a proposition changes, or "" when it is none of the natures."""
    before = before or ""
    value = value or ""
    if (
        field in SPELLED
        and before.strip()
        and before != value
        and normalize_text(before) == normalize_text(value)
    ):
        return "graphie"
    if field == "album" and not before.strip():
        return "album"
    if field == "year" and before.strip() in ("", "0"):
        return "annee"
    if field in ("label", "isrc"):
        return "label_isrc"
    if field == "famille":
        return "famille"
    return ""


def in_group(proposition: Any) -> str:
    """The group of a proposition: sure and still to read, or none."""
    if proposition.state != PROPOSED or proposition.level != SURE:
        return ""
    return nature_of(proposition.field, proposition.before, proposition.value)


async def nature_groups(
    session: ormSession, rows: list[tuple], *, rng: random.Random | None = None
) -> list[dict]:
    """The groups of the whole bank, in their order, each with its number of
    propositions and of titles, its propositions, and ten examples at random."""
    titles = {entry["id"]: entry for entry in map(title_of, rows)}
    fiches = (
        await session.scalars(select(Fiche).options(selectinload(Fiche.propositions)))
    ).all()
    found: dict[str, list[tuple[dict, Any]]] = {nature: [] for nature in NATURES}
    for fiche in fiches:
        title = titles.get(fiche.beets_id)
        if title is None:
            continue
        for proposition in fiche.propositions:
            nature = in_group(proposition)
            if nature:
                found[nature].append((title, proposition))
    pick = rng or random.Random()
    groups = []
    for nature in NATURES:
        members = sorted(
            found[nature],
            key=lambda one: (fold(one[0]["artist"]), fold(one[0]["title"]), one[1].id),
        )
        if not members:
            continue
        shown = pick.sample(members, min(EXAMPLES, len(members)))
        groups.append(
            {
                "nature": nature,
                "label": NATURE_LABELS[nature],
                "count": len(members),
                "titles": len({title["id"] for title, _one in members}),
                "ids": [proposition.id for _title, proposition in members],
                "examples": [
                    {
                        "id": proposition.id,
                        "beets_id": title["id"],
                        "title": title["title"],
                        "artist": title["artist"],
                        "field": proposition.field,
                        "before": proposition.before,
                        "value": proposition.value,
                    }
                    for title, proposition in shown
                ],
            }
        )
    return groups
