"""The station's settings, for an admin: Réglages → Station in the console. What a
listener may see is in ``public.py``, without a session. What an encoder needs, the
harbor's address, is for every account."""

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


@blueprint.get("/station/harbor.json")
@login_required
async def harbor_json():
    # « Passer en direct » is open to every account: the harbor's host, port and
    # mount, and none of the other settings.
    return jsonify(await station.harbor_payload(g.dbsession))


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
