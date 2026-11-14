"""The bank's table (FON-64): the titles of the Beets library, sorted and filtered.

Behind the general switch of « Ranger la banque », ``features.bank_tidy``: off,
the route refuses, and the console keeps today's view.
"""

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.services.bank_titles import TitleQuery, require_bank_tidy, titles_page

blueprint = Blueprint("media", __name__)


@blueprint.get("/media/titles.json")
@login_required
async def titles_json():
    await require_bank_tidy(g.dbsession)
    query = TitleQuery.from_args(request.args)
    rows = await BeetsIntegration.get().title_rows()
    return jsonify(titles_page(rows, query))
