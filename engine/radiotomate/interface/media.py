"""The bank's table (FON-64): the titles of the Beets library, sorted and filtered,
and the plays of a title in its fiche (FON-76).

Behind the general switch of « Ranger la banque », ``features.bank_tidy``: off,
the route refuses, and the console keeps today's view.
"""

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainNotFound
from radiotomate.services.bank_plays import title_plays
from radiotomate.services.bank_titles import TitleQuery, require_bank_tidy, titles_page

blueprint = Blueprint("media", __name__)


@blueprint.get("/media/titles.json")
@login_required
async def titles_json():
    await require_bank_tidy(g.dbsession)
    query = TitleQuery.from_args(request.args)
    rows = await BeetsIntegration.get().title_rows()
    return jsonify(titles_page(rows, query))


@blueprint.get("/media/titles/<int:item_id>/plays.json")
@login_required
async def title_plays_json(item_id: int):
    await require_bank_tidy(g.dbsession)
    item = await BeetsIntegration.get().get_item(item_id)
    if item is None:
        raise DomainNotFound("Ce titre n'est plus dans la bibliothèque.")
    path = bytes(item.path).decode("utf-8", "surrogateescape")
    return jsonify(await title_plays(g.dbsession, [path]))
