"""
This module defines endpoints related to the harbor "stream" input.
"""

import logging

from quart import Blueprint, g, request
from werkzeug.exceptions import BadRequest, Unauthorized

from radiotomate.auth import token_required
from radiotomate.models import User
from radiotomate.services.emissions import harbor_allowed

_log = logging.getLogger(__name__)

blueprint = Blueprint("harbor", __name__)


@blueprint.post("/can_stream")
@token_required
async def can_stream():
    posted = await request.get_json()
    username = posted.get("user")
    password = posted.get("password")

    if not username:
        raise BadRequest("Please provide an username")
    if not password:
        raise BadRequest("Please provide a password")

    user = await User.check(g.dbsession, username, password)
    if not user:
        raise Unauthorized("Incorrect username or password")
    if not await harbor_allowed(g.dbsession, user):
        raise Unauthorized("User is not authorized to stream")

    return ""
