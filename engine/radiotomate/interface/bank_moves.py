"""Move titles of the rotation and of the collections, keeping their identity (ARC-09),
and rename them after their fiche (FON-68).

The catalogue's ``/collection/move.json`` hands its moves here, with the
session of the browser: the engine holds Beets and the base, and rewrites the
paths they keep. The rules are in ``services/bank_moves.py`` and
``services/title_renames.py``.
"""

from quart import Blueprint, g, jsonify
from werkzeug.exceptions import BadRequest

from radiotomate.auth import current_user, login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.interface.json_util import forbidden_unless, read_json_object
from radiotomate.services.bank_lock import BeetsPlace
from radiotomate.services.bank_moves import (
    MAX_MOVES,
    MovesOffError,
    move_titles,
    moves_on,
)
from radiotomate.services.bank_titles import require_bank_tidy
from radiotomate.services.title_renames import (
    RenamesOffError,
    parse_lot,
    plan_renames,
    rename_titles,
    renames_on,
)

blueprint = Blueprint("bank_moves", __name__)


def _moves(data: dict) -> list[tuple[str, str]]:
    raw = data.get("moves")
    if not isinstance(raw, list) or not raw:
        raise BadRequest("moves list required")
    if len(raw) > MAX_MOVES:
        raise BadRequest(f"{MAX_MOVES} moves at most")
    moves: list[tuple[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise BadRequest("each move is an object")
        source, target = entry.get("from"), entry.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            raise BadRequest("each move has a from and a to")
        moves.append((source, target))
    return moves


@blueprint.post("/media/move.json")
@login_required
async def move_json():
    # Who may deposit in the bank may move its titles, as in the catalogue.
    user = getattr(current_user, "user", None)
    if user is None or not (user.can_carts() or user.can_autodj()):
        return jsonify({"error": "forbidden"}), 403
    moves = _moves(await read_json_object())
    # Le rangement coupé, rien ne s'écrit : ni ici, ni par le catalogue (FON-85).
    await require_bank_tidy(g.dbsession)
    if not await moves_on(g.dbsession):
        raise MovesOffError("Le moteur ne déplace pas les titres de la banque.")
    place = BeetsPlace.of(BeetsIntegration.get().lib)
    report = await move_titles(g.dbsession, place, moves, username=user.username)
    return jsonify(report.payload())


@blueprint.post("/media/titles/rename.json")
@login_required
async def rename_json():
    """Rename files after their fiche, or try it (``dry_run``): the Programmateur."""
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    ids, model, by_artist, dry_run = parse_lot(await read_json_object())
    if not await renames_on(g.dbsession):
        raise RenamesOffError(
            "Le renommage des fichiers n'est pas ouvert sur cette station."
        )
    place = BeetsPlace.of(BeetsIntegration.get().lib)
    plans = await plan_renames(g.dbsession, place, ids, model, by_artist=by_artist)
    if dry_run:
        return jsonify(
            {
                "dry_run": True,
                "titles": [plan.payload() for plan in plans],
                "entry": None,
                "left": [],
            }
        )
    outcome = await rename_titles(
        g.dbsession, place, plans, username=current_user.user.username
    )
    return jsonify(
        {
            "dry_run": False,
            "titles": [plan.payload() for plan in outcome.titles],
            "entry": outcome.entry,
            "left": outcome.left,
        }
    )
