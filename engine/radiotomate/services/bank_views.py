"""The saved views of the bank's table (FON-65). Sans Quart.

Each account keeps its own, in the engine's base, to find them on another computer.
The browser only keeps the last view opened. A view holds what the table shows: its
ranking and group, its text, its order and its columns.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import select

from radiotomate.domain.agenda import iso_paris
from radiotomate.domain.errors import (
    DomainConflict,
    DomainNotFound,
    DomainValidationError,
)
from radiotomate.models import BankView
from radiotomate.services.bank_titles import FACETS, SORTS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.models import User

# The columns of the table, in their own order; the title always shows.
COLUMNS = ("title", "artist", "album", "famille", "genre", "year", "duration", "fiche")
NAME_MAX = 60
QUERY_MAX = 200
MAX_VIEWS = 100
STATE_MAX_BYTES = 4096


def clean_name(raw: object) -> str:
    name = " ".join(str(raw or "").split())
    if not name:
        raise DomainValidationError("Donne un nom à la vue.", field="name")
    if len(name) > NAME_MAX:
        raise DomainValidationError(
            f"Un nom de vue tient en {NAME_MAX} signes.", field="name"
        )
    return name


def clean_state(raw: object) -> dict:
    """What a view keeps, checked: a value the table does not know is refused."""
    if not isinstance(raw, dict):
        raise DomainValidationError("La vue est mal formée.", field="state")
    ranking = str(raw.get("ranking") or "collection")
    if ranking not in FACETS:
        raise DomainValidationError(f"Rangement inconnu : {ranking}.", field="state")
    group = raw.get("group")
    if group is not None and not isinstance(group, str):
        raise DomainValidationError("Le groupe est un texte.", field="state")
    q = str(raw.get("q") or "")
    if len(q) > QUERY_MAX:
        raise DomainValidationError("La recherche est trop longue.", field="state")
    sort = str(raw.get("sort") or "artist")
    if sort not in SORTS:
        raise DomainValidationError(f"Tri inconnu : {sort}.", field="state")
    order = str(raw.get("order") or "asc")
    if order not in ("asc", "desc"):
        raise DomainValidationError(f"Ordre inconnu : {order}.", field="state")
    columns = raw.get("columns", list(COLUMNS))
    if (
        not isinstance(columns, list)
        or not all(isinstance(column, str) for column in columns)
        or len(set(columns)) != len(columns)
        or not set(columns) <= set(COLUMNS)
        or "title" not in columns
    ):
        raise DomainValidationError(
            "Les colonnes de la vue sont inconnues, en double, ou sans le titre.",
            field="state",
        )
    state = {
        "ranking": ranking,
        "group": group,
        "q": q,
        "sort": sort,
        "order": order,
        "columns": columns,
    }
    if len(json.dumps(state, ensure_ascii=False).encode()) > STATE_MAX_BYTES:
        raise DomainValidationError("La vue est trop longue.", field="state")
    return state


def view_payload(view: BankView) -> dict:
    return {
        "id": view.id,
        "name": view.name,
        "state": dict(view.state),
        "modified": iso_paris(view.modified),
    }


async def list_views(session: ormSession, user: User) -> list[BankView]:
    rows = await session.scalars(
        select(BankView).where(BankView.user_id == user.id).order_by(BankView.name)
    )
    return list(rows)


async def _own(session: ormSession, user: User, view_id: int) -> BankView:
    view = await session.scalar(
        select(BankView).where(BankView.id == view_id, BankView.user_id == user.id)
    )
    if view is None:
        # Another account's view is not found either: its name is not told.
        raise DomainNotFound("Cette vue n'existe plus.")
    return view


async def _name_free(
    session: ormSession, user: User, name: str, but: int | None = None
) -> None:
    taken = await session.scalar(
        select(BankView.id).where(BankView.user_id == user.id, BankView.name == name)
    )
    if taken is not None and taken != but:
        raise DomainConflict(f"Tu as déjà une vue « {name} ».", field="name")


async def create_view(session: ormSession, user: User, name: object, state: object):
    clean = clean_name(name)
    kept = clean_state(state)
    await _name_free(session, user, clean)
    if len(await list_views(session, user)) >= MAX_VIEWS:
        raise DomainConflict(
            f"Tu gardes déjà {MAX_VIEWS} vues : supprime-en une d'abord."
        )
    view = BankView(user_id=user.id, name=clean, state=kept)
    session.add(view)
    await session.flush()
    return view


async def update_view(
    session: ormSession, user: User, view_id: int, data: dict
) -> BankView:
    view = await _own(session, user, view_id)
    if "name" in data:
        clean = clean_name(data["name"])
        await _name_free(session, user, clean, but=view.id)
        view.name = clean
    if "state" in data:
        view.state = clean_state(data["state"])
    await session.flush()
    return view


async def delete_view(session: ormSession, user: User, view_id: int) -> None:
    view = await _own(session, user, view_id)
    await session.delete(view)
    await session.flush()
