"""The bank's table (FON-64): the titles of the Beets library, sorted and filtered,
the views each account keeps of it (FON-65), and the plays of a title in its
fiche (FON-76), and a selection composed by filters (FON-73).

They answer whatever the general switch of « Ranger la banque »,
``features.bank_tidy``: off, the table stays readable (FON-85). A view kept is a
way to read it, written in the engine's base, never in a file.
"""

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import current_user, login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.domain.errors import DomainNotFound
from radiotomate.interface.json_util import read_json_object
from radiotomate.services import bank_views
from radiotomate.services.bank_plays import title_plays
from radiotomate.services.bank_titles import (
    TitleQuery,
    carts_by_title,
    titles_page,
)
from radiotomate.services.beets_query import validate_selection_query
from radiotomate.services.fiches import verdict_on
from radiotomate.services.selection_filters import SelectionFilters, selection_query

blueprint = Blueprint("media", __name__)


@blueprint.get("/media/titles.json")
@login_required
async def titles_json():
    # FON-80 : le verdict, colonne, filtre et rangement, seulement allumé.
    verdict = await verdict_on(g.dbsession)
    query = TitleQuery.from_args(request.args, verdict=verdict)
    rows = await BeetsIntegration.get().title_rows()
    carts = await carts_by_title(g.dbsession)
    return jsonify(titles_page(rows, query, carts=carts, verdict=verdict))


@blueprint.get("/media/views.json")
@login_required
async def views_json():
    views = await bank_views.list_views(g.dbsession, current_user.user)
    return jsonify({"views": [bank_views.view_payload(view) for view in views]})


@blueprint.post("/media/views.json")
@login_required
async def create_view_json():
    data = await read_json_object()
    view = await bank_views.create_view(
        g.dbsession, current_user.user, data.get("name"), data.get("state")
    )
    await g.dbsession.commit()
    return jsonify({"view": bank_views.view_payload(view)}), 201


@blueprint.put("/media/views/<int:view_id>.json")
@login_required
async def update_view_json(view_id: int):
    data = await read_json_object()
    view = await bank_views.update_view(g.dbsession, current_user.user, view_id, data)
    await g.dbsession.commit()
    return jsonify({"view": bank_views.view_payload(view)})


@blueprint.delete("/media/views/<int:view_id>.json")
@login_required
async def delete_view_json(view_id: int):
    await bank_views.delete_view(g.dbsession, current_user.user, view_id)
    await g.dbsession.commit()
    return jsonify({"ok": True})


@blueprint.get("/media/titles/<int:item_id>/plays.json")
@login_required
async def title_plays_json(item_id: int):
    item = await BeetsIntegration.get().get_item(item_id)
    if item is None:
        raise DomainNotFound("Ce titre n'est plus dans la bibliothèque.")
    path = bytes(item.path).decode("utf-8", "surrogateescape")
    return jsonify(await title_plays(g.dbsession, [path]))


@blueprint.get("/media/selection.json")
@login_required
async def selection_json():
    """A selection composed by filters (FON-73): its query, its count, ten titles."""
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
