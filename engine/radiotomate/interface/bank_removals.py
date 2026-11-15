"""Retirer des titres de la rotation et des collections, et le noter (FON-71).

Le `/collection/remove.json` du catalogue passe ses retraits ici, avec la
session du navigateur, comme ses déplacements (ARC-09). Les règles sont dans
`services/bank_removals.py`.
"""

from quart import Blueprint, g, jsonify
from werkzeug.exceptions import BadRequest

from radiotomate.auth import current_user, login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.interface.json_util import read_json_object
from radiotomate.services.bank_lock import BeetsPlace
from radiotomate.services.bank_removals import (
    MAX_REMOVALS,
    RemovalsOffError,
    removals_on,
    remove_titles,
)
from radiotomate.services.bank_titles import require_bank_tidy

blueprint = Blueprint("bank_removals", __name__)


def _paths(data: dict) -> list[str]:
    raw = data.get("paths")
    if not isinstance(raw, list) or not raw:
        raise BadRequest("paths list required")
    if len(raw) > MAX_REMOVALS:
        raise BadRequest(f"{MAX_REMOVALS} paths at most")
    if not all(isinstance(path, str) for path in raw):
        raise BadRequest("each path is a string")
    return raw


@blueprint.post("/media/remove.json")
@login_required
async def remove_json():
    # Qui peut déposer dans la banque peut en retirer, comme dans le catalogue.
    user = getattr(current_user, "user", None)
    if user is None or not (user.can_carts() or user.can_autodj()):
        return jsonify({"error": "forbidden"}), 403
    paths = _paths(await read_json_object())
    # Le rangement coupé, rien ne s'écrit : ni ici, ni par le catalogue (FON-85).
    await require_bank_tidy(g.dbsession)
    if not await removals_on(g.dbsession):
        raise RemovalsOffError("Le moteur ne retire pas les titres de la banque.")
    place = BeetsPlace.of(BeetsIntegration.get().lib)
    report = await remove_titles(g.dbsession, place, paths, username=user.username)
    return jsonify(report.payload())
