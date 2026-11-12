"""Le système de la station : l'espace disque de la bibliothèque, pour un
programmateur ou un admin ; la version de chaque service, et les mises à jour
demandées depuis la console (MAJ-07), pour un admin."""

import os
import shutil

from quart import Blueprint, current_app, jsonify, request

from radiotomate.auth import current_user, login_required
from radiotomate.interface.json_util import forbidden_unless
from radiotomate.services import updates
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


async def _updates_view(refresh: bool = False) -> dict:
    """Ce que montre la page Mises à jour : les versions, la demande, ce que dit
    la machine, et pourquoi le bouton ne demande pas, s'il ne le peut pas."""
    root = current_app.config["DATA_ROOT"]
    host = updates.read_host(root)
    found = await updates.releases(
        host["repo"] if host else updates.REPOSITORY,
        refresh=refresh,
        transport=current_app.config.get("UPDATES_TRANSPORT"),
    )
    return updates.view(
        host=host,
        recorded=read_versions(root),
        found=found,
        request=updates.read_request(root),
        last=updates.read_last(root),
    )


@blueprint.get("/system/updates.json")
@login_required
async def updates_state():
    deny = forbidden_unless("admin")
    if deny:
        return deny
    return jsonify(await _updates_view(refresh=request.args.get("refresh") == "1"))


@blueprint.post("/system/updates/request.json")
@login_required
async def updates_request():
    """« Mettre à jour maintenant » : une demande, que la machine prend dans la
    minute. Refusée, 409, quand le bouton ne peut pas demander, avec pourquoi."""
    deny = forbidden_unless("admin")
    if deny:
        return deny
    view = await _updates_view()
    if view["blocked"]:
        raise updates.UpdateBlocked(view["blocked"]["code"], view["blocked"]["message"])
    updates.ask(
        current_app.config["DATA_ROOT"],
        current_user.user.username,
        view["latest"],
        view["installed"],
    )
    return jsonify(await _updates_view()), 202


@blueprint.delete("/system/updates/request.json")
@login_required
async def updates_withdraw():
    """La demande retirée, tant que la machine ne l'a pas commencée."""
    deny = forbidden_unless("admin")
    if deny:
        return deny
    updates.withdraw(current_app.config["DATA_ROOT"], current_user.user.username)
    return jsonify(await _updates_view())
