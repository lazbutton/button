from quart import Blueprint, g, jsonify, render_template, request, url_for
from werkzeug.exceptions import BadRequest

from radiotomate.auth import current_user, login_required
from radiotomate.interface.json_util import read_json_object

blueprint = Blueprint("account", __name__, template_folder="templates")


@blueprint.get("/account.json")
@login_required
async def account_json():
    user = current_user.user
    return jsonify(
        {
            "username": user.username,
            "permissions": user.permissions_payload(),
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
    return jsonify({"username": user.username, "permissions": user.permissions_payload()})


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
