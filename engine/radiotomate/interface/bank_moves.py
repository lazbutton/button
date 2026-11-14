"""Move titles of the rotation and of the collections, keeping their identity (ARC-09).

The catalogue's ``/collection/move.json`` hands its moves here, with the
session of the browser: the engine holds Beets and the base, and rewrites the
paths they keep. The rules are in ``services/bank_moves.py``.
"""

from quart import Blueprint, g, jsonify
from werkzeug.exceptions import BadRequest

from radiotomate.auth import current_user, login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.interface.json_util import read_json_object
from radiotomate.services.bank_lock import BeetsPlace
from radiotomate.services.bank_moves import (
    MAX_MOVES,
    MovesOffError,
    move_titles,
    moves_on,
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
    if not await moves_on(g.dbsession):
        raise MovesOffError("Le moteur ne déplace pas encore les titres de la banque.")
    place = BeetsPlace.of(BeetsIntegration.get().lib)
    report = await move_titles(g.dbsession, place, moves, username=user.username)
    return jsonify(report.payload())
