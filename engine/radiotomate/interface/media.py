"""The bank's table (FON-64): the titles of the Beets library, sorted and filtered,
and the views each account keeps of it (FON-65).

Behind the general switch of « Ranger la banque », ``features.bank_tidy``: off,
the routes refuse, and the console keeps today's view.
"""

from quart import Blueprint, g, jsonify, request

from radiotomate.auth import current_user, login_required
from radiotomate.beets import BeetsIntegration
from radiotomate.interface.json_util import read_json_object
from radiotomate.services import bank_views
from radiotomate.services.bank_titles import TitleQuery, require_bank_tidy, titles_page

blueprint = Blueprint("media", __name__)


@blueprint.get("/media/titles.json")
@login_required
async def titles_json():
    await require_bank_tidy(g.dbsession)
    query = TitleQuery.from_args(request.args)
    rows = await BeetsIntegration.get().title_rows()
    return jsonify(titles_page(rows, query))


@blueprint.get("/media/views.json")
@login_required
async def views_json():
    await require_bank_tidy(g.dbsession)
    views = await bank_views.list_views(g.dbsession, current_user.user)
    return jsonify({"views": [bank_views.view_payload(view) for view in views]})


@blueprint.post("/media/views.json")
@login_required
async def create_view_json():
    await require_bank_tidy(g.dbsession)
    data = await read_json_object()
    view = await bank_views.create_view(
        g.dbsession, current_user.user, data.get("name"), data.get("state")
    )
    await g.dbsession.commit()
    return jsonify({"view": bank_views.view_payload(view)}), 201


@blueprint.put("/media/views/<int:view_id>.json")
@login_required
async def update_view_json(view_id: int):
    await require_bank_tidy(g.dbsession)
    data = await read_json_object()
    view = await bank_views.update_view(g.dbsession, current_user.user, view_id, data)
    await g.dbsession.commit()
    return jsonify({"view": bank_views.view_payload(view)})


@blueprint.delete("/media/views/<int:view_id>.json")
@login_required
async def delete_view_json(view_id: int):
    await require_bank_tidy(g.dbsession)
    await bank_views.delete_view(g.dbsession, current_user.user, view_id)
    await g.dbsession.commit()
    return jsonify({"ok": True})
