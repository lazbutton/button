"""Les fiches de la bibliothèque, pour la console (FON-26), en lecture.

- `GET /fiches.json` : où en est la recherche, ses comptes, et une page de titres à
  relire, filtrée par niveau, champ, banque, état et texte. Droit `autodj`.
- `GET /fiches/<beets_id>.json` : un titre, sa fiche, ses propositions et ses
  preuves lisibles, avec le lien de sa pochette quand la station les montre
  (`features.fiches_covers`, FON-83). Droit `autodj`.
- `GET /fiches/reglages.json` : les interrupteurs de la recherche et de ses sources,
  et si une clé est posée, jamais sa valeur. Droit `autodj`.
- `PUT /fiches/reglages.json` : les mêmes, et les clés. Un admin.
- `POST /fiches/decisions.json` : accepter ou refuser des propositions (FON-27).
  Accepter écrit aussitôt, par le service de FON-66, au journal. Droit `autodj`.
- `POST /fiches/decisions/annuler.json` : le dernier geste de la relecture au
  clavier défait, ses propositions de nouveau à relire (FON-78). Droit `autodj`.
- `POST /fiches/propositions/<id>/revenir.json` : une valeur écrite revient à celle
  d'avant. Droit `autodj`.
- `POST /fiches/<beets_id>/rechercher.json` : chercher de nouveau. Droit `autodj`.
- `GET /fiches/familles.json` : pour chaque sélection de titres, les familles de ses
  titres ; pour chaque famille, ses titres et ceux qu'aucune sélection ne prend
  (FON-28). Droit `autodj`.
- `GET /fiches/verdicts.json` : ce qu'effacer les verdicts toucherait, avec les
  sélections qui lisent `fmg`. Droit `autodj`.
- `POST /fiches/verdicts/effacer.json` : retire `fmg` et `fmg_source` de toute la
  bibliothèque, et les verdicts en attente. Un admin.

Derrière l'interrupteur du rangement de la banque, `features.bank_tidy` : éteint,
les routes refusent. Écrire demande aussi `features.title_edits`, pas coupé.
"""

from __future__ import annotations

import logging
from asyncio import CancelledError, sleep
from typing import TYPE_CHECKING

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import current_user, login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.interface.json_util import forbidden_unless, read_json_object
from radiotomate.quart import ShutdownError, or_shutdown
from radiotomate.services import fiches_decisions, fiches_families, fiches_review
from radiotomate.services.bank_titles import bank_tidy_enabled, require_bank_tidy
from radiotomate.services.fiches import (
    read_settings,
    settings_payload,
    write_settings,
)

if TYPE_CHECKING:
    from radiotomate.db import QuartAlchemy

blueprint = Blueprint("fiches", __name__)
_log = logging.getLogger(__name__)

# Les propositions acceptées suivent le journal à ce rythme, comme les fiches qui
# attendent la fin d'un passage à l'antenne (interface/title_edits.py).
ACCEPTED_PERIOD = 15.0


@blueprint.get("/fiches.json")
@login_required
async def fiches_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    query = fiches_review.ReviewQuery.from_args(request.args)
    settings = await read_settings(g.dbsession)
    beets = BeetsIntegration.get()
    rows = await beets.title_rows()
    page = await fiches_review.review_page(
        g.dbsession, rows, query, enabled=settings.enabled
    )
    # La part des « oui » parmi les verdicts connus, en titres (FON-28).
    page["verdict"] = settings.verdict
    page["verdicts"] = await fiches_families.verdict_counts(beets)
    return jsonify(page)


@blueprint.get("/fiches/<int:beets_id>.json")
@login_required
async def fiche_json(beets_id: int):
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    item = await BeetsIntegration.get().get_item(beets_id)
    covers = (await read_settings(g.dbsession)).covers
    return jsonify(
        await fiches_review.review_detail(g.dbsession, beets_id, item, covers=covers)
    )


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


@blueprint.post("/fiches/decisions.json")
@login_required
async def decisions_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    accept, refuse = fiches_decisions.parse_decisions(await read_json_object())
    outcome = await fiches_decisions.decide(
        g.dbsession,
        BeetsIntegration.get(),
        accept,
        refuse,
        username=current_user.user.username,
    )
    return jsonify(outcome.payload())


@blueprint.post("/fiches/decisions/annuler.json")
@login_required
async def reopen_json():
    """« Z » de la relecture au clavier (FON-78) : le dernier geste défait."""
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    ids = fiches_decisions.parse_reopen(await read_json_object())
    outcome = await fiches_decisions.reopen(
        g.dbsession,
        BeetsIntegration.get(),
        ids,
        username=current_user.user.username,
    )
    return jsonify(outcome.payload())


@blueprint.post("/fiches/propositions/<int:proposition_id>/revenir.json")
@login_required
async def revert_json(proposition_id: int):
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    outcome = await fiches_decisions.revert(
        g.dbsession,
        BeetsIntegration.get(),
        proposition_id,
        username=current_user.user.username,
    )
    return jsonify(outcome.payload())


@blueprint.post("/fiches/<int:beets_id>/rechercher.json")
@login_required
async def search_again_json(beets_id: int):
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    await fiches_decisions.search_again(g.dbsession, beets_id)
    return jsonify({"queued": True})


@blueprint.get("/fiches/familles.json")
@login_required
async def families_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    return jsonify(
        await fiches_families.families_payload(g.dbsession, BeetsIntegration.get())
    )


@blueprint.get("/fiches/verdicts.json")
@login_required
async def verdicts_json():
    denied = forbidden_unless("autodj")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    return jsonify(
        await fiches_families.verdict_summary(g.dbsession, BeetsIntegration.get())
    )


@blueprint.post("/fiches/verdicts/effacer.json")
@login_required
async def erase_verdicts_json():
    denied = forbidden_unless("admin")
    if denied is not None:
        return denied
    await require_bank_tidy(g.dbsession)
    return jsonify(
        await fiches_families.erase_verdicts(
            g.dbsession,
            BeetsIntegration.get(),
            username=current_user.user.username,
        )
    )


async def accepted_writes_task(db: QuartAlchemy, beets: BeetsIntegration) -> None:
    """Les propositions acceptées suivent leur écriture au journal, et celles qui
    n'y sont jamais allées s'écrivent, comme sur un fichier revenu."""
    while True:
        try:
            await or_shutdown(sleep(ACCEPTED_PERIOD))
        except (ShutdownError, CancelledError):
            return
        try:
            async with db.session() as session:
                if await bank_tidy_enabled(session):
                    await fiches_decisions.write_accepted(session, beets)
        except (ShutdownError, CancelledError):
            return
        except Exception:
            _log.exception("while writing the accepted fiches")
