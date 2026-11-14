"""Corriger la fiche d'un titre ou d'un lot (FON-66), pour le Programmateur.

`POST /media/titles/edit.json` écrit un lot, ou l'essaie (`dry_run`) : ce qui
s'écrirait, ce qui attendrait, et les sélections de titres touchées.
`POST /media/titles/tags.json` pose et retire des étiquettes de la station sur un
lot (FON-74), par le même service. « Revenir » passe par le journal
(`radiotomate.interface.journal`).

Les règles sont dans `radiotomate.services.title_edits`.
"""

from __future__ import annotations

import logging
from asyncio import CancelledError, sleep
from typing import TYPE_CHECKING

from quart import Blueprint, g, jsonify

from radiotomate.auth import current_user, login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.interface.json_util import forbidden_unless, read_json_object
from radiotomate.quart import ShutdownError, or_shutdown
from radiotomate.services.title_edits import (
    TitlesRefused,
    apply_waiting,
    edit_titles,
    has_waiting,
    parse_person_edits,
)
from radiotomate.services.title_tags import tag_titles

if TYPE_CHECKING:
    from radiotomate.db import QuartAlchemy

_log = logging.getLogger(__name__)

blueprint = Blueprint("title_edits", __name__)

# Un titre qui attend la fin de son passage à l'antenne est repris à ce rythme.
WAITING_PERIOD = 15.0


def refused_response(exc: TitlesRefused):
    """Le refus d'un lot, avec chaque titre en cause et sa raison."""
    return jsonify(
        {
            "error": exc.message,
            "code": exc.code,
            "message": exc.message,
            "titles": [issue.payload() for issue in exc.titles],
        }
    ), exc.status_code


@blueprint.post("/media/titles/edit.json")
@login_required
async def edit_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    data = await read_json_object()
    edits = parse_person_edits(data)
    dry_run = data.get("dry_run") is True
    try:
        outcome = await edit_titles(
            g.dbsession,
            BeetsIntegration.get(),
            edits,
            username=current_user.user.username,
            dry_run=dry_run,
        )
    except TitlesRefused as exc:
        return refused_response(exc)
    return jsonify({"dry_run": dry_run, **outcome.payload()})


@blueprint.post("/media/titles/tags.json")
@login_required
async def tags_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    data = await read_json_object()
    dry_run = data.get("dry_run") is True
    try:
        outcome = await tag_titles(
            g.dbsession,
            BeetsIntegration.get(),
            data.get("ids"),
            data.get("add"),
            data.get("remove"),
            username=current_user.user.username,
            dry_run=dry_run,
        )
    except TitlesRefused as exc:
        return refused_response(exc)
    return jsonify({"dry_run": dry_run, **outcome.payload()})


async def waiting_writes_task(db: QuartAlchemy, beets: BeetsIntegration) -> None:
    """Écrit les fiches qui attendaient la fin d'un passage à l'antenne."""
    while True:
        try:
            await or_shutdown(sleep(WAITING_PERIOD))
        except (ShutdownError, CancelledError):
            return
        try:
            async with db.session() as session:
                if await has_waiting(session):
                    await apply_waiting(session, beets)
        except (ShutdownError, CancelledError):
            return
        except Exception:
            _log.exception("while writing the waiting title edits")
