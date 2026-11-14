"""The listening link's settings, for an admin: Réglages → Station → « Fiches et
liens » in the console (FON-84). The partner key is written, never read back."""

from quart import Blueprint, g, jsonify

from radiotomate.auth import login_required
from radiotomate.interface.json_util import forbidden_unless, read_json_object
from radiotomate.services import listen_link

blueprint = Blueprint("listen_link", __name__)


@blueprint.get("/listen-link.json")
@login_required
async def listen_link_json():
    deny = forbidden_unless("admin")
    if deny:
        return deny
    return jsonify(await listen_link.admin_payload(g.dbsession))


@blueprint.put("/listen-link.json")
@login_required
async def update_listen_link_json():
    deny = forbidden_unless("admin")
    if deny:
        return deny
    data = await read_json_object()
    await listen_link.update_settings(g.dbsession, data)
    await g.dbsession.commit()
    return jsonify(await listen_link.admin_payload(g.dbsession))
