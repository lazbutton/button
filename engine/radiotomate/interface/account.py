from quart import Blueprint, g, jsonify, render_template, request, url_for
from werkzeug.exceptions import BadRequest

from radiotomate.auth import current_user, login_required
from radiotomate.interface.json_util import read_json_object
from radiotomate.services.bank_moves import moves_on
from radiotomate.services.bank_removals import removals_on
from radiotomate.services.bank_titles import bank_tidy_enabled
from radiotomate.services.title_edits import title_edits_enabled

blueprint = Blueprint("account", __name__, template_folder="templates")


@blueprint.get("/account.json")
@login_required
async def account_json():
    user = current_user.user
    return jsonify(
        {
            "username": user.username,
            "permissions": user.permissions_payload(),
            # What the console shows of the work in progress (ADR 0009).
            "features": {
                "bank_tidy": await bank_tidy_enabled(g.dbsession),
                "title_edits": await title_edits_enabled(g.dbsession),
                # ARC-09: a title moved keeps its identity.
                "bank_moves": await moves_on(g.dbsession),
                # FON-71: a title removed is noted, and comes back from the trash.
                "bank_removals": await removals_on(g.dbsession),
                # FON-74: the table gives the station's tags, and ranges by them.
                "station_tags": await bank_tidy_enabled(g.dbsession),
            },
        },
    )


@blueprint.get("/account")
@login_required
async def index():
    return await render_template("account/index.jinja")


@blueprint.put("/account.json")
@login_required
async def update_json():
    data = await read_json_object()
    password = str(data.get("password") or "")
    if not password.strip():
        raise BadRequest("Veuillez saisir un mot de passe")
    current_user.user.update_password(password)
    await g.dbsession.commit()
    user = current_user.user
    return jsonify(
        {"username": user.username, "permissions": user.permissions_payload()}
    )


@blueprint.put("/account")
@login_required
async def update():
    form = await request.form
    password = form.get("password") or ""
    if not password.strip():
        raise BadRequest("Veuillez saisir un mot de passe")
    current_user.user.update_password(password)
    await g.dbsession.commit()
    return (
        "",
        200,
        {
            "HX-Redirect": url_for("account.index"),
        },
    )
