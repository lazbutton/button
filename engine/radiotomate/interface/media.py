"""The bank's table (FON-64): the titles of the Beets library, sorted and filtered.

Behind the general switch of « Ranger la banque », ``features.bank_tidy``: off,
the route refuses, and the console keeps today's view.
"""

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.services.bank_titles import TitleQuery, require_bank_tidy, titles_page
from radiotomate.services.beets_query import validate_selection_query
from radiotomate.services.selection_filters import SelectionFilters, selection_query

blueprint = Blueprint("media", __name__)


@blueprint.get("/media/titles.json")
@login_required
async def titles_json():
    await require_bank_tidy(g.dbsession)
    query = TitleQuery.from_args(request.args)
    rows = await BeetsIntegration.get().title_rows()
    return jsonify(titles_page(rows, query))


@blueprint.get("/media/selection.json")
@login_required
async def selection_json():
    """A selection composed by filters (FON-73): its query, its count, ten titles."""
    await require_bank_tidy(g.dbsession)
    beets = BeetsIntegration.get()
    filters = SelectionFilters.from_args(request.args)
    query = selection_query(filters, genre_field=await beets.genre_field())
    validate_selection_query(query)
    items = await beets.search(query)
    sample = [
        {"artist": str(item.get("artist") or ""), "title": str(item.get("title") or "")}
        for item in items[:10]
    ]
    return jsonify({"query": query, "count": len(items), "sample": sample})
