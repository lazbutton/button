"""Les arrivées de la banque (FON-81) : les titres indexés depuis 30 jours. Sans Quart.

Pour chaque titre arrivé dans la rotation ou une collection : la fiche que la
recherche propose (FON-25), le nom que lui donnerait un modèle de FON-68 une fois
les propositions sûres acceptées, et ses doublons éventuels dans toute la banque
(FON-72). Un titre est prêt à ranger quand il n'attend aucune relecture : ses
propositions sont toutes sûres, et il a de quoi changer, une fiche ou un nom.

Rien ne s'écrit ici. « Ranger », dans la console, accepte les propositions sûres
(FON-27) puis renomme (FON-68) : chacun de ces gestes a son journal. Un fichier
nouveau passe déjà à l'antenne : la quarantaine n'a pas été retenue.

Derrière l'interrupteur général du chantier, `features.bank_tidy`, et le sien,
`features.bank_arrivals`, allumé quand il manque.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from radiotomate.domain.agenda import iso_paris
from radiotomate.domain.errors import DomainError
from radiotomate.models import Fiche, Setting
from radiotomate.models.fiche import PROPOSED
from radiotomate.services.bank_health import SETTING_OFF, duplicate_groups
from radiotomate.services.bank_names import renamed
from radiotomate.services.bank_titles import bank_tidy_enabled, title_of

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sqlalchemy.orm import Session as ormSession

SETTING_ARRIVALS = "features.bank_arrivals"
DAYS = 30
# Les arrivées listées, les plus récentes d'abord ; le compte prend tout.
MAX_ARRIVALS = 500
SURE = "sûr"
INDEXED_ZONES = ("rotation", "collections")
# Les champs d'une proposition qui changent le nom d'un fichier (FON-68).
NAME_FIELDS = ("artist", "album", "title")


class ArrivalsOff(DomainError):  # noqa: N818
    status_code = 409
    code = "bank_arrivals_off"


async def arrivals_on(session: ormSession) -> bool:
    """The general switch of the bank's tidying, and this view's own, on when absent."""
    if not await bank_tidy_enabled(session):
        return False
    row = await Setting.from_key(session, SETTING_ARRIVALS)
    return row is None or str(row.value).strip().lower() not in SETTING_OFF


async def require_arrivals(session: ormSession) -> None:
    if not await arrivals_on(session):
        raise ArrivalsOff("La vue Arrivées n'est pas ouverte sur cette station.")


def since(now: datetime | None = None, days: int = DAYS) -> float:
    """The Unix time from which a title is an arrival."""
    return ((now or datetime.now(UTC)) - timedelta(days=days)).timestamp()


def _proposition(proposition: Any) -> dict:
    return {
        "id": proposition.id,
        "field": proposition.field,
        "before": proposition.before,
        "value": proposition.value,
        "level": proposition.level,
        "why": proposition.why,
        "source": proposition.source,
        "state": proposition.state,
        "error": proposition.error,
    }


def _added(seconds: float) -> str | None:
    """Beets' `added`, in Unix seconds, at Paris time as the API says it."""
    moment = datetime.fromtimestamp(seconds, UTC).replace(tzinfo=None)
    return iso_paris(moment)


def _name_after(entry: dict, propositions: list[dict], model: str) -> str | None:
    """The file's name once its sure propositions are accepted, if it changes."""
    fields = {name: entry[name] for name in NAME_FIELDS}
    for proposition in propositions:
        if proposition["level"] == SURE and proposition["field"] in NAME_FIELDS:
            fields[proposition["field"]] = proposition["value"]
    target, _why = renamed(entry["path"], fields, model)
    if target is None:
        return None
    name = PurePosixPath(target).name
    return None if name == PurePosixPath(entry["path"]).name else name


def _brief(entry: dict) -> dict:
    return {
        key: entry[key]
        for key in ("id", "title", "artist", "duration", "zone", "collection", "path")
    }


def arrivals(
    rows: Iterable[tuple],
    added: Mapping[int, float],
    fiches: Mapping[int, Any],
    model: str,
    root: str | None = None,
) -> dict:
    """The arrivals, newest first, and their counts.

    `rows` are the whole bank's (`title_rows`), for the duplicates; `added` the
    titles indexed since the start of the view; `fiches` the fiches of these
    titles, by Beets id, with their propositions.
    """
    entries = [title_of(row, root) for row in rows]
    twins: dict[int, list[dict]] = {}
    for group in duplicate_groups(entries):
        for entry in group:
            twins[entry["id"]] = [
                _brief(other) for other in group if other["id"] != entry["id"]
            ]
    found = []
    for entry in entries:
        if entry["id"] not in added or entry["zone"] not in INDEXED_ZONES:
            continue
        fiche = fiches.get(entry["id"])
        propositions = [
            _proposition(one)
            for one in (fiche.propositions if fiche is not None else [])
            if one.state == PROPOSED
        ]
        review = any(one["level"] != SURE for one in propositions)
        sure = [one["id"] for one in propositions if one["level"] == SURE]
        to = _name_after(entry, propositions, model)
        found.append(
            {
                **entry,
                "added": _added(added[entry["id"]]),
                "searched": fiche is not None,
                "status": fiche.status if fiche is not None else "",
                "level": fiche.level if fiche is not None else "",
                "propositions": propositions,
                "sure": sure,
                "review": review,
                "to": to,
                "ready": not review and bool(sure or to),
                "duplicates": twins.get(entry["id"], []),
            }
        )
    found.sort(key=lambda arrival: (-added[arrival["id"]], arrival["path"]))
    return {
        "days": DAYS,
        "model": model,
        "total": len(found),
        "ready": sum(1 for arrival in found if arrival["ready"]),
        "review": sum(1 for arrival in found if arrival["review"]),
        "waiting": sum(1 for arrival in found if not arrival["searched"]),
        "duplicates": sum(1 for arrival in found if arrival["duplicates"]),
        "titles": found[:MAX_ARRIVALS],
    }


async def fiches_of(session: ormSession, ids: Iterable[int]) -> dict[int, Any]:
    """The fiches of these titles, with their propositions, by Beets id."""
    wanted = list(ids)
    found: dict[int, Any] = {}
    # By lots: SQLite takes a bounded number of values in a query.
    for start in range(0, len(wanted), 500):
        rows = await session.scalars(
            select(Fiche)
            .options(selectinload(Fiche.propositions))
            .where(Fiche.beets_id.in_(wanted[start : start + 500]))
        )
        found.update((fiche.beets_id, fiche) for fiche in rows)
    return found
