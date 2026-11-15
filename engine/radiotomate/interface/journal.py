"""Le journal des gestes sur la banque et les bacs (FON-71), pour le Programmateur.

- `GET /media/journal.json` : les lots, du plus récent au plus ancien, filtrés par
  geste et par personne.
- `GET /media/journal/<id>.json` : un lot, ligne par ligne.
- `POST /media/journal/<id>/undo.json` : « Annuler », pendant 30 jours.

Derrière l'interrupteur du rangement de la banque, `features.bank_tidy` : coupé,
la page ne s'ouvre pas. Annuler une correction demande aussi
`features.title_edits`, comme l'écrire.
"""

from __future__ import annotations

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import current_user, login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainValidationError
from radiotomate.interface.json_util import forbidden_unless
from radiotomate.interface.title_edits import refused_response
from radiotomate.services import journal
from radiotomate.services.bank_titles import require_bank_tidy
from radiotomate.services.title_edits import TitlesRefused

blueprint = Blueprint("journal", __name__)


def _id_arg(name: str) -> int | None:
    raw = request.args.get(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise DomainValidationError(
            "Ce lot n'est pas un numéro du journal.", field=name
        ) from exc


@blueprint.get("/media/journal.json")
@login_required
async def journal_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    return jsonify(
        await journal.journal_page(
            g.dbsession,
            gesture=request.args.get("gesture") or None,
            username=request.args.get("username") or None,
            before=_id_arg("before"),
            limit=request.args.get("limit"),
        )
    )


@blueprint.get("/media/journal/<int:entry_id>.json")
@login_required
async def entry_json(entry_id: int):
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    return jsonify(await journal.entry_detail(g.dbsession, entry_id))


@blueprint.post("/media/journal/<int:entry_id>/undo.json")
@login_required
async def undo_json(entry_id: int):
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    try:
        outcome = await journal.undo(
            g.dbsession,
            BeetsIntegration.get(),
            entry_id,
            username=current_user.user.username,
        )
    except TitlesRefused as exc:
        return refused_response(exc)
    return jsonify({"dry_run": False, **outcome.payload()})
