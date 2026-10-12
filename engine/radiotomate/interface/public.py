"""Routes without a console session.

* ``/public/guest/<token>…``: a guest's page (Agenda), reached by a private
  link. The token is the only key; it opens nothing but that guest's dates.
* ``/internal/agenda/…``: the catalog asks whether a guest may drop a file
  and declares the file it placed (``X-Auth-Token``, never the guest's token
  alone).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from quart import Blueprint, current_app, g, jsonify

from radiotomate.auth import token_required
from radiotomate.domain.errors import DomainNotFound
from radiotomate.interface.json_util import read_json_object
from radiotomate.services import agenda

blueprint = Blueprint("public", __name__)

TOKEN_IN_PATH = re.compile(r"(/public/guest/)[A-Za-z0-9_-]{20,100}")


class MaskTokens(logging.Filter):
    """Access logs never keep a guest's token."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "/public/guest/" in message:
            record.msg = TOKEN_IN_PATH.sub(r"\1…", message)
            record.args = ()
        return True


logging.getLogger("hypercorn.access").addFilter(MaskTokens())


@blueprint.after_request
async def private_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


async def _guest(token: str):
    guest = await agenda.guest_from_token(g.dbsession, token)
    if guest is None:
        raise DomainNotFound("Ce lien ne marche plus.", field="token")
    return guest


@blueprint.get("/public/guest/<token>.json")
async def guest_json(token: str):
    guest = await _guest(token)
    payload = await agenda.public_payload(g.dbsession, guest)
    await g.dbsession.commit()
    payload["station"] = current_app.config.get("INTERFACE_NAME") or "BUTTON"
    return jsonify(payload)


@blueprint.put("/public/guest/<token>/diffusions/<int:diffusion_id>.json")
async def guest_update_json(token: str, diffusion_id: int):
    guest = await _guest(token)
    data = await read_json_object()
    allowed = {
        key: data[key] for key in ("set_title", "tracklist", "rights") if key in data
    }
    row = await agenda.public_update(g.dbsession, guest, diffusion_id, allowed)
    await g.dbsession.commit()
    return jsonify(
        {"diffusion": agenda.public_diffusion(row, datetime.now(timezone.utc))}
    )


@blueprint.post("/internal/agenda/deposit-check.json")
@token_required
async def deposit_check_json():
    data = await read_json_object()
    return jsonify(await agenda.deposit_check(g.dbsession, data))


@blueprint.post("/internal/agenda/files.json")
@token_required
async def deposit_file_json():
    data = await read_json_object()
    item = await agenda.register_deposit(g.dbsession, data)
    await g.dbsession.commit()
    current_app.add_background_task(
        agenda.run_analysis, current_app.extensions["sqlalchemy"], item.id
    )
    return jsonify({"ok": True, "file_id": item.id}), 201
