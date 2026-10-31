"""The station's settings, for an admin: Réglages → Station in the console. What a
listener may see is in ``public.py``, without a session."""

from quart import Blueprint, g, jsonify

from radiotomate.auth import login_required
from radiotomate.interface.json_util import forbidden_unless, read_json_object
from radiotomate.services import station

blueprint = Blueprint("station", __name__)


@blueprint.get("/station.json")
@login_required
async def station_json():
    deny = forbidden_unless("admin")
    if deny:
        return deny
    return jsonify(await station.admin_payload(g.dbsession))


@blueprint.put("/station.json")
@login_required
async def update_station_json():
    deny = forbidden_unless("admin")
    if deny:
        return deny
    data = await read_json_object()
    await station.update_station(g.dbsession, data)
    await g.dbsession.commit()
    return jsonify(await station.admin_payload(g.dbsession))
