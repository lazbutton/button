"""JSON routes of the Agenda (Programmation → Agenda): dated broadcasts,
their guests and files, weekly shows cancelled for a day."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from quart import Blueprint, current_app, g, jsonify, request, send_file
from quart_auth import current_user

from radiotomate.auth import login_required
from radiotomate.domain.agenda import parse_day, utc
from radiotomate.domain.emission import PARIS
from radiotomate.domain.errors import DomainNotFound
from radiotomate.interface.json_util import forbidden_unless, read_json_object
from radiotomate.models import AgendaFile, AgendaGuest
from radiotomate.services import agenda
from radiotomate.services.media_bank import media_root

blueprint = Blueprint("agenda", __name__)

# A change inside this window rebuilds the forecast of the conducteur.
FORECAST_REACH = timedelta(hours=18)


def _username() -> str:
    user = getattr(current_user, "user", None)
    return str(getattr(user, "username", "") or "")


def _today() -> date:
    return datetime.now(PARIS).date()


async def _refresh_forecast(*starts: datetime) -> None:
    """A dated broadcast moved within reach: the rundown is drawn again."""
    from radiotomate.interface.autodj import invalidate_conducteur_cache
    from radiotomate.scheduler.agenda import _drop_planned_blocks

    now = datetime.now(timezone.utc)
    if any(utc(start) - now <= FORECAST_REACH for start in starts if start):
        await _drop_planned_blocks(g.dbsession)
    invalidate_conducteur_cache()


def _analyse_later(file_id: int) -> None:
    current_app.add_background_task(
        agenda.run_analysis, current_app.extensions["sqlalchemy"], file_id
    )


async def _diffusion(diffusion_id: int):
    return await agenda.get_diffusion(g.dbsession, diffusion_id)


@blueprint.get("/agenda.json")
@login_required
async def agenda_json():
    first = (
        parse_day(request.args.get("from"), field="from")
        if request.args.get("from")
        else _today() - timedelta(days=_today().weekday())
    )
    last = (
        parse_day(request.args.get("to"), field="to")
        if request.args.get("to")
        else first + timedelta(days=6)
    )
    payload = await agenda.agenda_payload(g.dbsession, first, last)
    await g.dbsession.commit()
    return jsonify(payload)


@blueprint.post("/agenda/diffusions/preview.json")
@login_required
async def preview_json():
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    data = await read_json_object()
    return jsonify(await agenda.preview(g.dbsession, data))


@blueprint.post("/agenda/diffusions.json")
@login_required
async def create_json():
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    data = await read_json_object()
    rows = await agenda.create(g.dbsession, data, username=_username())
    await _refresh_forecast(*(row.starts_at for row in rows))
    await g.dbsession.commit()
    return jsonify({"diffusions": [agenda.diffusion_payload(row) for row in rows]}), 201


@blueprint.get("/agenda/diffusions/<int:diffusion_id>.json")
@login_required
async def get_json(diffusion_id: int):
    row = await _diffusion(diffusion_id)
    return jsonify({"diffusion": agenda.diffusion_payload(row)})


@blueprint.put("/agenda/diffusions/<int:diffusion_id>.json")
@login_required
async def update_json(diffusion_id: int):
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    row = await _diffusion(diffusion_id)
    before = row.starts_at
    data = await read_json_object()
    row = await agenda.update(g.dbsession, row, data)
    await _refresh_forecast(before, row.starts_at)
    await g.dbsession.commit()
    return jsonify({"diffusion": agenda.diffusion_payload(row)})


@blueprint.delete("/agenda/diffusions/<int:diffusion_id>.json")
@login_required
async def delete_json(diffusion_id: int):
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    row = await _diffusion(diffusion_id)
    start = row.starts_at
    following = request.args.get("suivantes") in {"1", "true", "oui"}
    deleted = await agenda.delete(g.dbsession, row, following=following)
    await _refresh_forecast(start)
    await g.dbsession.commit()
    return jsonify({"deleted": deleted})


@blueprint.post("/agenda/diffusions/<int:diffusion_id>/stop.json")
@login_required
async def stop_json(diffusion_id: int):
    deny = forbidden_unless("live")
    if deny:
        return deny
    row = await _diffusion(diffusion_id)
    row = await agenda.request_stop(g.dbsession, row)
    await g.dbsession.commit()
    return jsonify({"diffusion": agenda.diffusion_payload(row)})


@blueprint.put("/agenda/diffusions/<int:diffusion_id>/file.json")
@login_required
async def attach_file_json(diffusion_id: int):
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    row = await _diffusion(diffusion_id)
    data = await read_json_object()
    item = await agenda.attach_bank_file(g.dbsession, row, data)
    await _refresh_forecast(row.starts_at)
    await g.dbsession.commit()
    _analyse_later(item.id)
    row = (await agenda.reload_diffusions(g.dbsession, [row.id]))[0]
    return jsonify({"diffusion": agenda.diffusion_payload(row)})


@blueprint.delete("/agenda/diffusions/<int:diffusion_id>/file.json")
@login_required
async def detach_file_json(diffusion_id: int):
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    row = await _diffusion(diffusion_id)
    await agenda.detach_file(g.dbsession, row)
    await _refresh_forecast(row.starts_at)
    await g.dbsession.commit()
    row = (await agenda.reload_diffusions(g.dbsession, [row.id]))[0]
    return jsonify({"diffusion": agenda.diffusion_payload(row)})


@blueprint.get("/agenda/files/<int:file_id>/audio")
@login_required
async def file_audio(file_id: int):
    row = await AgendaFile.from_id(g.dbsession, file_id)
    if row is None:
        return jsonify({"error": "not_found"}), 404
    path = (media_root() / row.path).resolve()
    if media_root() not in path.parents or not path.is_file():
        return jsonify({"error": "not_found"}), 404
    return await send_file(path, conditional=True)


@blueprint.post("/agenda/exceptions.json")
@login_required
async def add_exception_json():
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    data = await read_json_object()
    row = await agenda.add_exception(g.dbsession, data)
    await g.dbsession.commit()
    return jsonify({"emission_id": row.emission_id, "date": row.day.isoformat()}), 201


@blueprint.delete("/agenda/exceptions.json")
@login_required
async def remove_exception_json():
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    await agenda.remove_exception(
        g.dbsession,
        {
            "emission_id": request.args.get("emission_id"),
            "date": request.args.get("date"),
        },
    )
    await g.dbsession.commit()
    return jsonify({"ok": True})


@blueprint.get("/agenda/guests.json")
@login_required
async def guests_json():
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    rows = await AgendaGuest.all(g.dbsession)
    return jsonify({"guests": [agenda.guest_payload(row) for row in rows]})


@blueprint.post("/agenda/guests.json")
@login_required
async def create_guest_json():
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    data = await read_json_object()
    row = await agenda.create_guest(g.dbsession, data)
    await g.dbsession.commit()
    return jsonify({"guest": agenda.guest_payload(row)}), 201


async def _guest(guest_id: int) -> AgendaGuest:
    row = await AgendaGuest.from_id(g.dbsession, guest_id)
    if row is None:
        raise DomainNotFound("Invité introuvable.", field="id")
    return row


@blueprint.put("/agenda/guests/<int:guest_id>.json")
@login_required
async def update_guest_json(guest_id: int):
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    row = await _guest(guest_id)
    data = await read_json_object()
    row = await agenda.update_guest(g.dbsession, row, data)
    await g.dbsession.commit()
    return jsonify({"guest": agenda.guest_payload(row)})


@blueprint.post("/agenda/guests/<int:guest_id>/token.json")
@login_required
async def renew_guest_token_json(guest_id: int):
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    row = await agenda.renew_token(g.dbsession, await _guest(guest_id))
    await g.dbsession.commit()
    return jsonify({"guest": agenda.guest_payload(row)})


@blueprint.delete("/agenda/guests/<int:guest_id>.json")
@login_required
async def delete_guest_json(guest_id: int):
    deny = forbidden_unless("autodj")
    if deny:
        return deny
    await agenda.delete_guest(g.dbsession, await _guest(guest_id))
    await g.dbsession.commit()
    return jsonify({"ok": True})


@blueprint.put("/agenda/settings.json")
@login_required
async def settings_json():
    deny = forbidden_unless("admin")
    if deny:
        return deny
    data = await read_json_object()
    await agenda.set_agenda_enabled(g.dbsession, bool(data.get("enabled")))
    await g.dbsession.commit()
    return jsonify({"enabled": await agenda.agenda_enabled(g.dbsession)})


@blueprint.get("/agenda/deposit-auth")
async def deposit_auth():
    """nginx ``auth_request`` for ``/tus/``: a team session, or a guest's link."""
    token = request.headers.get("X-Invite-Token", "").strip()
    if token:
        if await agenda.guest_from_token(g.dbsession, token) is not None:
            return "", 204
        return "", 401
    user = getattr(current_user, "user", None)
    if user is not None and (user.can_admin() or user.can_carts() or user.can_autodj()):
        return "", 204
    return "", 401
