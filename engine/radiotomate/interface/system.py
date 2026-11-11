"""Le système de la station : l'espace disque de la bibliothèque, pour un
programmateur ou un admin, et la version de chaque service, pour un admin."""

import os
import shutil

from quart import Blueprint, current_app, jsonify

from radiotomate.auth import current_user, login_required
from radiotomate.interface.json_util import forbidden_unless
from radiotomate.services.versions import read_versions

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


@blueprint.get("/system/version.json")
@login_required
async def version():
    deny = forbidden_unless("admin")
    if deny:
        return deny
    return jsonify(read_versions(current_app.config["DATA_ROOT"]))
