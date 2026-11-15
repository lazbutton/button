"""Les arrivées de la banque (FON-81) : `GET /media/arrivals.json`.

Les titres indexés depuis 30 jours, avec leur fiche proposée, leur nom d'après un
modèle de FON-68 et leurs doublons, pour le Programmateur. Rien ne s'écrit ici :
« Ranger » passe par les routes des fiches (FON-27) et du renommage (FON-68).
"""

from __future__ import annotations

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.interface.json_util import forbidden_unless
from radiotomate.services.bank_arrivals import (
    arrivals,
    fiches_of,
    require_arrivals,
    since,
)
from radiotomate.services.bank_health import check_model
from radiotomate.services.bank_titles import require_bank_tidy

blueprint = Blueprint("bank_arrivals", __name__)


@blueprint.get("/media/arrivals.json")
@login_required
async def arrivals_json():
    await require_bank_tidy(g.dbsession)
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_arrivals(g.dbsession)
    model = check_model(request.args.get("model"))
    beets = BeetsIntegration.get()
    added = await beets.added_since(since())
    rows = await beets.title_rows()
    fiches = await fiches_of(g.dbsession, added)
    return jsonify(arrivals(rows, added, fiches, model))
