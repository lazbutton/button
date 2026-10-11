"""Espace disque de la bibliothèque. Programmateur et admin seulement."""

import os
import shutil

from quart import Blueprint, jsonify

from radiotomate.auth import current_user, login_required

blueprint = Blueprint("system", __name__)


def library_path() -> str:
    raw = os.environ.get("MEDIA_ROOT", "/media").strip()
    return raw or "/media"


@blueprint.get("/system/disk.json")
@login_required
async def disk():
    user = current_user.user
    if not (user.can_carts() or user.can_autodj()):
        return jsonify({"error": "forbidden"}), 403
    path = library_path()
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return jsonify({"error": "disque illisible", "path": path}), 503
    return jsonify(
        {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "path": path,
        }
    )
