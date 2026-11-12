"""The station's website reads these without a session, from its own domain:
the coming week and the last music tracks. Read only.

Apart from ``interface/public.py`` on purpose: a guest's page is never cached,
these answers are public and keep a little while. ``features.public_site_routes``
at false closes both (``services/station_public.py``).
"""

from __future__ import annotations

from quart import Blueprint, g, jsonify, request

from radiotomate.services import station_public

blueprint = Blueprint("station_public", __name__)


@blueprint.before_request
async def closed_by_the_station():
    # Before the routes: a closed route answers 404 whatever its query says.
    await station_public.ensure_open(g.dbsession)


@blueprint.after_request
async def site_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    # nginx leaves Referrer-Policy to the engine under /public/.
    response.headers["Referrer-Policy"] = "no-referrer"
    # For the station's website to show, not for a search engine.
    response.headers["X-Robots-Tag"] = "noindex"
    if response.status_code != 200:
        response.headers["Cache-Control"] = "no-store"
    return response


@blueprint.get("/public/programme.json")
async def programme_json():
    payload = await station_public.programme_payload(g.dbsession)
    return jsonify(payload), 200, {"Cache-Control": "public, max-age=60"}


@blueprint.get("/public/historique.json")
async def historique_json():
    limit = station_public.history_limit(request.args.get("limit"))
    payload = await station_public.history_payload(g.dbsession, limit)
    return jsonify(payload), 200, {"Cache-Control": "public, max-age=15"}
