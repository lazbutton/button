"""Les fiches de la bibliothèque, pour la console (FON-26), en lecture.

- `GET /fiches.json` : où en est la recherche, ses comptes, et une page de titres à
  relire, filtrée par niveau, champ, banque, état et texte. Droit `autodj`.
- `GET /fiches/<beets_id>.json` : un titre, sa fiche, ses propositions et ses
  preuves lisibles. Droit `autodj`.
- `GET /fiches/reglages.json` : les interrupteurs de la recherche et de ses sources,
  et si une clé est posée, jamais sa valeur. Droit `autodj`.
- `PUT /fiches/reglages.json` : les mêmes, et les clés. Un admin.

Derrière l'interrupteur du rangement de la banque, `features.bank_tidy` : éteint,
les routes refusent. Rien ne s'y accepte encore : FON-27.
"""

from __future__ import annotations

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.interface.json_util import forbidden_unless, read_json_object
from radiotomate.services import fiches_review
from radiotomate.services.bank_titles import require_bank_tidy
from radiotomate.services.fiches import (
    read_settings,
    settings_payload,
    write_settings,
)

blueprint = Blueprint("fiches", __name__)


@blueprint.get("/fiches.json")
@login_required
async def fiches_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    query = fiches_review.ReviewQuery.from_args(request.args)
    settings = await read_settings(g.dbsession)
    rows = await BeetsIntegration.get().title_rows()
    return jsonify(
        await fiches_review.review_page(
            g.dbsession, rows, query, enabled=settings.enabled
        )
    )


@blueprint.get("/fiches/<int:beets_id>.json")
@login_required
async def fiche_json(beets_id: int):
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    item = await BeetsIntegration.get().get_item(beets_id)
    return jsonify(await fiches_review.review_detail(g.dbsession, beets_id, item))


@blueprint.get("/fiches/reglages.json")
@login_required
async def reglages_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    return jsonify(await settings_payload(g.dbsession))


@blueprint.put("/fiches/reglages.json")
@login_required
async def put_reglages_json():
    denied = forbidden_unless("admin")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    await write_settings(g.dbsession, await read_json_object())
    await g.dbsession.commit()
    return jsonify(await settings_payload(g.dbsession))
