"""Agenda: dated broadcasts, their guests and files. No Quart.

Rows store naive UTC; payloads give Paris ISO strings with their offset.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
import secrets
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy import update as sql_update

from radiotomate.domain.agenda import (
    AIR_MISSED,
    AIR_ON_AIR,
    AIR_UPCOMING,
    CONTACT_MAX,
    KIND_LIVE,
    KIND_SET,
    LIVE_OPEN_BEFORE,
    NAME_MAX,
    ORIGIN_BANK,
    ORIGIN_DEPOT,
    OVERRUN_WARNING,
    PREP_WAITING,
    SET_TITLE_MAX,
    TITLE_MAX,
    TRACKLIST_MAX,
    UTC,
    FileFacts,
    TodoInput,
    clean_text,
    deadline_for,
    deposit_closes_at,
    deposit_late,
    deposit_open,
    iso_paris,
    loudness_gain,
    nth_of_month,
    occurrence_walls,
    overlaps,
    overrun_seconds,
    paris,
    parse_day,
    parse_instant,
    playable,
    prep_state,
    repeat_days,
    slug,
    todo_lines,
    utc,
    utc_naive,
    validate_kind,
    validate_window,
    wall_label,
    wall_to_utc,
)
from radiotomate.domain.autodj import require_expected_version
from radiotomate.domain.emission import PARIS
from radiotomate.domain.errors import (
    DomainConflict,
    DomainNotFound,
    DomainValidationError,
)
from radiotomate.models import (
    AgendaDiffusion,
    AgendaException,
    AgendaFile,
    AgendaGuest,
    Emission,
    Setting,
    User,
)
from radiotomate.services.media_bank import media_root, unique_trash_path

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

_log = logging.getLogger(__name__)

SETTING_ENABLED = "agenda_enabled"
DEPOSIT_SUFFIXES = {
    ".mp3",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".m4a",
    ".wav",
    ".wave",
    ".aiff",
    ".aif",
}
CONVERT_TO_FLAC = {".wav", ".wave", ".aiff", ".aif"}
MAX_DEPOSIT_BYTES = 4 * 1024**3
EMISSIONS_TOP = "40-emissions"
REFUSED_TOPS = {"00-inbox", "90-trash", "Carts"}
ANALYSIS_TIMEOUT = 15 * 60
_analysis_lock = asyncio.Lock()


def now_utc(now: datetime | None = None) -> datetime:
    return utc(now) if now is not None else datetime.now(UTC)


# -- switch --------------------------------------------------------------------


async def agenda_enabled(session: ormSession) -> bool:
    row = await Setting.from_key(session, SETTING_ENABLED)
    return row is None or str(row.value).strip() not in {"0", "false", "off", ""}


async def set_agenda_enabled(session: ormSession, enabled: bool) -> None:
    await Setting.upsert(session, SETTING_ENABLED, "1" if enabled else "0")


# -- payloads ------------------------------------------------------------------


def media_id(rel: str) -> str:
    """The catalog's document id for a bank path (services/catalog/app.py)."""
    import hashlib

    return hashlib.sha256(rel.encode()).hexdigest()[:20]


def file_facts(row: AgendaFile | None) -> FileFacts | None:
    if row is None:
        return None
    report = dict(row.report or {})
    return FileFacts(
        origin=row.origin,
        duration=float(row.duration or 0),
        status=str(report.get("status") or "pending"),
        error=str(report.get("error") or ""),
    )


def file_payload(row: AgendaFile) -> dict:
    report = dict(row.report or {})
    return {
        "id": row.id,
        "path": row.path,
        "media_id": media_id(row.path),
        "origin": row.origin,
        "original_name": row.original_name,
        "duration": float(row.duration or 0),
        "gain": row.gain,
        "late": bool(row.late),
        "created": iso_paris(row.created),
        "report": {
            "status": report.get("status") or "pending",
            "error": report.get("error") or "",
            "format": report.get("format") or "",
            "codec": report.get("codec") or "",
            "sample_rate": report.get("sample_rate"),
            "channels": report.get("channels"),
            "bit_rate": report.get("bit_rate"),
            "lufs": report.get("lufs"),
            "warnings": list(report.get("warnings") or []),
        },
    }


def guest_payload(row: AgendaGuest, *, with_token: bool = True) -> dict:
    payload = {
        "id": row.id,
        "version": row.version,
        "name": row.name,
        "contact": row.contact,
        "opened_at": iso_paris(row.opened_at),
        "created": iso_paris(row.created),
    }
    if with_token:
        payload["token"] = row.token
    return payload


def diffusion_state(row: AgendaDiffusion) -> tuple[str, str]:
    return prep_state(
        row.kind,
        file=file_facts(row.current_file),
        rights=row.rights_at is not None,
        host_username=row.host_username or "",
    )


def diffusion_payload(row: AgendaDiffusion, now: datetime | None = None) -> dict:
    now = now_utc(now)
    prep, reason = diffusion_state(row)
    current = row.current_file
    start = utc(row.starts_at)
    end = utc(row.ends_at)
    payload = {
        "id": row.id,
        "version": row.version,
        "kind": row.kind,
        "title": row.title,
        "starts_at": iso_paris(start),
        "ends_at": iso_paris(end),
        "duration_min": int((end - start).total_seconds() // 60),
        "guest": guest_payload(row.guest) if row.guest is not None else None,
        "host_username": row.host_username or "",
        "set_title": row.set_title or "",
        "tracklist": row.tracklist or "",
        "rights": row.rights_at is not None,
        "rights_at": iso_paris(row.rights_at),
        "deadline_at": iso_paris(deadline_for(start, row.deadline_at)),
        "deposit_closes_at": iso_paris(deposit_closes_at(start)),
        "deposit_open": deposit_open(start, now) and row.air_status == AIR_UPCOMING,
        "series_id": row.series_id,
        "air_status": row.air_status,
        "air_reason": row.air_reason or "",
        "aired_start": iso_paris(row.aired_start),
        "aired_end": iso_paris(row.aired_end),
        "stop_requested": row.stop_requested_at is not None,
        "prep": prep,
        "prep_reason": reason,
        "file": file_payload(current) if current is not None else None,
        "overrun_seconds": None,
    }
    if current is not None and current.duration:
        over = overrun_seconds(start, end, float(current.duration))
        if over >= OVERRUN_WARNING.total_seconds():
            payload["overrun_seconds"] = round(over)
    return payload


# -- reading -------------------------------------------------------------------


def _day_bounds(first: date, last: date) -> tuple[datetime, datetime]:
    start = datetime.combine(first, time()).replace(tzinfo=PARIS)
    end = datetime.combine(last + timedelta(days=1), time()).replace(tzinfo=PARIS)
    return utc_naive(start), utc_naive(end)


def _lenient_wall(day: date, minute: int) -> datetime:
    wall = datetime.combine(day, time()) + timedelta(minutes=minute)
    return wall.replace(tzinfo=PARIS).astimezone(UTC)


def weekly_window(row: Emission, day: date) -> tuple[datetime, datetime] | None:
    if row.day_of_week is None or row.start_minute is None or row.end_minute is None:
        return None
    if day.weekday() != int(row.day_of_week):
        return None
    return (
        _lenient_wall(day, int(row.start_minute)),
        _lenient_wall(day, int(row.end_minute)),
    )


async def weekly_occurrences(
    session: ormSession,
    first: date,
    last: date,
    diffusions: list[AgendaDiffusion],
) -> list[dict]:
    weeklies = await Emission.all_weekly(session)
    cancelled = {
        (row.emission_id, row.day)
        for row in await AgendaException.between(session, first, last)
    }
    out: list[dict] = []
    day = first
    while day <= last:
        for row in weeklies:
            window = weekly_window(row, day)
            if window is None:
                continue
            start, end = window
            replaced_by = next(
                (
                    item.id
                    for item in diffusions
                    if overlaps(start, end, item.starts_at, item.ends_at)
                ),
                None,
            )
            out.append(
                {
                    "emission_id": row.id,
                    "date": day.isoformat(),
                    "title": row.title,
                    "artist": row.artist,
                    "host_username": row.host_username or "",
                    "starts_at": iso_paris(start),
                    "ends_at": iso_paris(end),
                    "cancelled": (row.id, day) in cancelled,
                    "replaced_by": replaced_by,
                }
            )
        day += timedelta(days=1)
    return out


async def upcoming_for_todo(
    session: ormSession, now: datetime
) -> list[AgendaDiffusion]:
    start = utc_naive(now)
    end = utc_naive(now + timedelta(days=7))
    rows = await AgendaDiffusion.between(session, start, end)
    return [row for row in rows if row.air_status == AIR_UPCOMING]


def todo_for(rows: list[AgendaDiffusion], now: datetime) -> list[dict]:
    inputs = []
    for row in rows:
        prep, reason = diffusion_state(row)
        inputs.append(
            TodoInput(
                diffusion_id=row.id,
                kind=row.kind,
                title=row.title,
                start=row.starts_at,
                air_status=row.air_status,
                prep=prep,
                prep_reason=reason,
                guest_name=row.guest.name if row.guest is not None else "",
                guest_opened=bool(row.guest is not None and row.guest.opened_at),
                has_file=row.current_file is not None,
            )
        )
    return todo_lines(inputs, now)


async def agenda_payload(
    session: ormSession, first: date, last: date, now: datetime | None = None
) -> dict:
    now = now_utc(now)
    if last < first:
        raise DomainValidationError("La fin est avant le début.", field="to")
    if (last - first).days > 62:
        raise DomainValidationError("Deux mois au plus.", field="to")
    start, end = _day_bounds(first, last)
    diffusions = await AgendaDiffusion.between(session, start, end)
    upcoming = await upcoming_for_todo(session, now)
    return {
        "enabled": await agenda_enabled(session),
        "now": iso_paris(now),
        "from": first.isoformat(),
        "to": last.isoformat(),
        "diffusions": [diffusion_payload(row, now) for row in diffusions],
        "weekly": await weekly_occurrences(session, first, last, diffusions),
        "todo": todo_for(upcoming, now),
    }


async def reload_diffusions(
    session: ormSession, ids: list[int]
) -> list[AgendaDiffusion]:
    if not ids:
        return []
    rows = await session.scalars(
        select(AgendaDiffusion)
        .where(AgendaDiffusion.id.in_(ids))
        .order_by(AgendaDiffusion.starts_at)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def get_diffusion(session: ormSession, diffusion_id: int) -> AgendaDiffusion:
    row = await AgendaDiffusion.from_id(session, diffusion_id)
    if row is None:
        raise DomainNotFound("Émission introuvable.", field="id")
    return row


# -- writing -------------------------------------------------------------------


async def _check_host(session: ormSession, raw: object) -> str:
    name = str(raw or "").strip()
    if not name:
        return ""
    user = await User.from_username(session, name)
    if user is None:
        raise DomainValidationError("Compte inconnu.", field="host_username")
    if not user.can_stream():
        raise DomainValidationError(
            "Ce compte ne peut pas passer en direct.", field="host_username"
        )
    return user.username


async def _guest_from_data(session: ormSession, data: dict) -> AgendaGuest | None:
    """``guest_id`` picks a guest, ``guest_name`` creates one, null removes it."""
    if "guest_id" in data and data.get("guest_id") not in (None, ""):
        try:
            guest_id = int(data["guest_id"])
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("Invité inconnu.", field="guest_id") from exc
        guest = await AgendaGuest.from_id(session, guest_id)
        if guest is None:
            raise DomainValidationError("Invité inconnu.", field="guest_id")
        return guest
    name = str(data.get("guest_name") or "").strip()
    if name:
        return await create_guest(session, {"name": name})
    return None


async def _conflicts(
    session: ormSession,
    windows: list[tuple[datetime, datetime]],
    *,
    ignore: set[int] | None = None,
) -> list[tuple[int, AgendaDiffusion]]:
    """(index of the window, diffusion in the way) for each clash."""
    if not windows:
        return []
    low = min(start for start, _ in windows)
    high = max(end for _, end in windows)
    existing = await AgendaDiffusion.between(session, utc_naive(low), utc_naive(high))
    clashes = []
    for index, (start, end) in enumerate(windows):
        for row in existing:
            if ignore and row.id in ignore:
                continue
            if overlaps(start, end, row.starts_at, row.ends_at):
                clashes.append((index, row))
                break
    return clashes


def _clash_text(row: AgendaDiffusion) -> str:
    return f"Ce créneau chevauche « {row.title} » ({wall_label(row.starts_at)})."


def _windows(data: dict, now: datetime) -> list[tuple[datetime, datetime]]:
    """The UTC windows asked for: one, or a repeated series."""
    start = parse_instant(data.get("start"), field="start")
    end = parse_instant(data.get("end"), field="end")
    validate_window(start, end)
    repeat = data.get("repeat")
    if not repeat:
        return [(start, end)]
    if not isinstance(repeat, dict):
        raise DomainValidationError("Répétition illisible.", field="repeat")
    start_wall = paris(start).replace(tzinfo=None)
    end_wall = paris(end).replace(tzinfo=None)
    count = repeat.get("count")
    until = repeat.get("until")
    try:
        count_value = int(count) if count not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("Nombre illisible.", field="repeat_count") from exc
    until_value = parse_day(until, field="repeat_until") if until else None
    nth = repeat.get("nth")
    try:
        nth_value = int(nth) if nth not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("Rang illisible.", field="repeat") from exc
    days = repeat_days(
        start_wall.date(),
        str(repeat.get("rule") or ""),
        count=count_value,
        until=until_value,
        nth=nth_value,
    )
    windows = []
    for wall_start, wall_end in occurrence_walls(start_wall, end_wall, days):
        windows.append(
            (
                wall_to_utc(wall_start, field="start"),
                wall_to_utc(wall_end, field="end"),
            )
        )
    return windows


async def preview(session: ormSession, data: dict, now: datetime | None = None) -> dict:
    """The dates a creation would make, each with its clash if any."""
    now = now_utc(now)
    windows = _windows(data, now)
    clashes = dict(await _conflicts(session, windows))
    rows = []
    seen: list[tuple[datetime, datetime]] = []
    for index, (start, end) in enumerate(windows):
        problem = ""
        if start < now - timedelta(minutes=1):
            problem = "Date passée."
        elif index in clashes:
            problem = _clash_text(clashes[index])
        elif any(overlaps(start, end, a, b) for a, b in seen):
            problem = "Chevauche une autre date de la série."
        seen.append((start, end))
        rows.append(
            {
                "start": iso_paris(start),
                "end": iso_paris(end),
                "label": wall_label(start),
                "problem": problem,
            }
        )
    first = paris(windows[0][0]).date()
    return {
        "occurrences": rows,
        "nth": nth_of_month(first),
    }


async def create(
    session: ormSession,
    data: dict,
    *,
    username: str = "",
    now: datetime | None = None,
) -> list[AgendaDiffusion]:
    now = now_utc(now)
    kind = validate_kind(data.get("kind"))
    title = clean_text(data.get("title"), field="title", limit=TITLE_MAX, required=True)
    windows = _windows(data, now)
    if isinstance(data.get("only"), list) and data.get("repeat"):
        keep = {str(item) for item in data["only"]}
        windows = [w for w in windows if iso_paris(w[0]) in keep]
        if not windows:
            raise DomainValidationError("Aucune date retenue.", field="repeat")
    for start, _end in windows:
        if start < now - timedelta(minutes=1):
            raise DomainValidationError(
                f"Le {wall_label(start)} est passé.", field="start"
            )
    for index, (start, end) in enumerate(windows):
        for other_start, other_end in windows[:index]:
            if overlaps(start, end, other_start, other_end):
                raise DomainValidationError(
                    "Deux dates de la série se chevauchent.", field="repeat"
                )
    clashes = await _conflicts(session, windows)
    if clashes:
        raise DomainConflict(_clash_text(clashes[0][1]), field="start")
    host = (
        await _check_host(session, data.get("host_username"))
        if kind == KIND_LIVE
        else ""
    )
    guest = await _guest_from_data(session, data) if kind == KIND_SET else None
    deadline = None
    if data.get("deadline"):
        deadline = parse_instant(data.get("deadline"), field="deadline")
    series_id = str(uuid4()) if len(windows) > 1 else None
    rows = []
    for start, end in windows:
        row = AgendaDiffusion(
            kind=kind,
            title=title,
            starts_at=utc_naive(start),
            ends_at=utc_naive(end),
            guest_id=guest.id if guest is not None else None,
            host_username=host,
            deadline_at=utc_naive(deadline) if deadline and len(windows) == 1 else None,
            series_id=series_id,
            created_by=username,
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return await reload_diffusions(session, [row.id for row in rows])


EDITABLE_AFTER_AIR = {"title", "set_title", "tracklist", "version"}


async def update(  # noqa: PLR0912
    session: ormSession,
    row: AgendaDiffusion,
    data: dict,
    *,
    now: datetime | None = None,
) -> AgendaDiffusion:
    now = now_utc(now)
    require_expected_version(row.version, data.get("version"))
    if row.air_status != AIR_UPCOMING:
        extra = set(data) - EDITABLE_AFTER_AIR
        if extra:
            raise DomainConflict(
                "Cette émission est déjà passée à l'antenne : seuls le titre et "
                "la tracklist se modifient.",
                field=sorted(extra)[0],
            )
    if "title" in data:
        row.title = clean_text(
            data["title"], field="title", limit=TITLE_MAX, required=True
        )
    if "set_title" in data:
        row.set_title = clean_text(
            data["set_title"], field="set_title", limit=SET_TITLE_MAX
        )
    if "tracklist" in data:
        row.tracklist = clean_text(
            data["tracklist"], field="tracklist", limit=TRACKLIST_MAX
        )
    if row.air_status != AIR_UPCOMING:
        await session.flush()
        return (await reload_diffusions(session, [row.id]))[0]
    if "kind" in data:
        kind = validate_kind(data["kind"])
        if kind != row.kind and kind == KIND_LIVE and row.current_file is not None:
            raise DomainConflict(
                "Ce set a un fichier : retire-le avant d'en faire un direct.",
                field="kind",
            )
        row.kind = kind
    if "start" in data or "end" in data:
        start = (
            parse_instant(data["start"], field="start")
            if "start" in data
            else utc(row.starts_at)
        )
        end = (
            parse_instant(data["end"], field="end")
            if "end" in data
            else utc(row.ends_at)
        )
        validate_window(start, end)
        if start < now - timedelta(minutes=1):
            raise DomainValidationError(
                f"Le {wall_label(start)} est passé.", field="start"
            )
        clashes = await _conflicts(session, [(start, end)], ignore={row.id})
        if clashes:
            raise DomainConflict(_clash_text(clashes[0][1]), field="start")
        row.starts_at = utc_naive(start)
        row.ends_at = utc_naive(end)
    if "deadline" in data:
        deadline = (
            parse_instant(data["deadline"], field="deadline")
            if data["deadline"]
            else None
        )
        row.deadline_at = utc_naive(deadline) if deadline else None
    if row.kind == KIND_LIVE:
        if "host_username" in data:
            row.host_username = await _check_host(session, data["host_username"])
        row.guest_id = None
    else:
        row.host_username = ""
        if "guest_id" in data or "guest_name" in data:
            guest = await _guest_from_data(session, data)
            row.guest_id = guest.id if guest is not None else None
    await session.flush()
    return (await reload_diffusions(session, [row.id]))[0]


async def delete(
    session: ormSession,
    row: AgendaDiffusion,
    *,
    following: bool = False,
) -> int:
    if row.air_status == AIR_ON_AIR:
        raise DomainConflict(
            "Elle est à l'antenne : arrête-la d'abord.", field="air_status"
        )
    doomed = [row]
    if following and row.series_id:
        siblings = await session.scalars(
            select(AgendaDiffusion).where(
                AgendaDiffusion.series_id == row.series_id,
                AgendaDiffusion.starts_at > row.starts_at,
                AgendaDiffusion.air_status == AIR_UPCOMING,
            )
        )
        doomed.extend(siblings)
    for item in doomed:
        await session.delete(item)
    await session.flush()
    return len(doomed)


async def request_stop(
    session: ormSession, row: AgendaDiffusion, now: datetime | None = None
) -> AgendaDiffusion:
    if row.air_status != AIR_ON_AIR:
        raise DomainConflict("Elle n'est pas à l'antenne.", field="air_status")
    if row.kind == KIND_LIVE:
        raise DomainConflict("Un direct s'arrête en coupant l'encodeur.", field="kind")
    row.stop_requested_at = utc_naive(now_utc(now))
    await session.flush()
    return row


# -- exceptions ----------------------------------------------------------------


async def add_exception(session: ormSession, data: dict) -> AgendaException:
    try:
        emission_id = int(data.get("emission_id"))
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("Émission inconnue.", field="emission_id") from exc
    emission = await Emission.from_id(session, emission_id)
    if emission is None or emission.scope != "weekly":
        raise DomainNotFound("Émission hebdo introuvable.", field="emission_id")
    day = parse_day(data.get("date"), field="date")
    if day.weekday() != emission.day_of_week:
        raise DomainValidationError(
            "Cette émission ne passe pas ce jour-là.", field="date"
        )
    existing = await AgendaException.find(session, emission_id, day)
    if existing is not None:
        return existing
    row = AgendaException(emission_id=emission_id, day=day)
    session.add(row)
    await session.flush()
    return row


async def remove_exception(session: ormSession, data: dict) -> None:
    try:
        emission_id = int(data.get("emission_id"))
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("Émission inconnue.", field="emission_id") from exc
    day = parse_day(data.get("date"), field="date")
    row = await AgendaException.find(session, emission_id, day)
    if row is None:
        raise DomainNotFound("Ce jour n'était pas annulé.", field="date")
    await session.delete(row)
    await session.flush()


async def blocked_weekly_ids(session: ormSession, now: datetime) -> set[int]:
    """Weekly emissions whose occurrence today is cancelled or covered by a date."""
    local = paris(now)
    day = local.date()
    blocked = {
        row.emission_id for row in await AgendaException.between(session, day, day)
    }
    weeklies = await Emission.all_weekly(session)
    windows = [(row, weekly_window(row, day)) for row in weeklies]
    windows = [(row, window) for row, window in windows if window is not None]
    if not windows:
        return blocked
    low = min(window[0] for _, window in windows)
    high = max(window[1] for _, window in windows)
    diffusions = await AgendaDiffusion.between(session, utc_naive(low), utc_naive(high))
    for row, (start, end) in windows:
        if any(
            overlaps(start, end, item.starts_at, item.ends_at) for item in diffusions
        ):
            blocked.add(row.id)
    return blocked


# -- guests --------------------------------------------------------------------


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def create_guest(session: ormSession, data: dict) -> AgendaGuest:
    name = clean_text(data.get("name"), field="name", limit=NAME_MAX, required=True)
    contact = clean_text(data.get("contact"), field="contact", limit=CONTACT_MAX)
    row = AgendaGuest(name=name, contact=contact, token=new_token())
    session.add(row)
    await session.flush()
    return row


async def update_guest(
    session: ormSession, row: AgendaGuest, data: dict
) -> AgendaGuest:
    require_expected_version(row.version, data.get("version"))
    if "name" in data:
        row.name = clean_text(data["name"], field="name", limit=NAME_MAX, required=True)
    if "contact" in data:
        row.contact = clean_text(data["contact"], field="contact", limit=CONTACT_MAX)
    await session.flush()
    return row


async def renew_token(session: ormSession, row: AgendaGuest) -> AgendaGuest:
    row.token = new_token()
    row.token_created = utc_naive(now_utc())
    row.opened_at = None
    await session.flush()
    return row


async def delete_guest(session: ormSession, row: AgendaGuest) -> None:
    for item in await AgendaDiffusion.of_guest(session, row.id):
        item.guest_id = None
    await session.delete(row)
    await session.flush()


async def guest_from_token(session: ormSession, token: str) -> AgendaGuest | None:
    token = str(token or "").strip()
    if len(token) < 20 or len(token) > 100:
        return None
    row = await AgendaGuest.from_token(session, token)
    if row is None or not hmac.compare_digest(row.token, token):
        return None
    return row


# -- the guest's page ----------------------------------------------------------


def public_diffusion(row: AgendaDiffusion, now: datetime) -> dict:
    full = diffusion_payload(row, now)
    current = row.current_file
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "starts_at": full["starts_at"],
        "ends_at": full["ends_at"],
        "duration_min": full["duration_min"],
        "deadline_at": full["deadline_at"],
        "deposit_closes_at": full["deposit_closes_at"],
        "deposit_open": full["deposit_open"],
        "air_status": row.air_status,
        "set_title": row.set_title or "",
        "tracklist": row.tracklist or "",
        "rights": row.rights_at is not None,
        "prep": full["prep"],
        "prep_reason": full["prep_reason"],
        "overrun_seconds": full["overrun_seconds"],
        "file": (
            {
                "original_name": current.original_name,
                "duration": float(current.duration or 0),
                "late": bool(current.late),
                "status": full["file"]["report"]["status"],
                "error": full["file"]["report"]["error"],
                "gain": current.gain,
            }
            if current is not None and current.origin == ORIGIN_DEPOT
            else None
        ),
    }


async def public_payload(
    session: ormSession, guest: AgendaGuest, now: datetime | None = None
) -> dict:
    now = now_utc(now)
    if guest.opened_at is None:
        # One statement, no version check: two tabs opening the link at once
        # must not fail on each other.
        await session.execute(
            sql_update(AgendaGuest)
            .where(AgendaGuest.id == guest.id, AgendaGuest.opened_at.is_(None))
            .values(opened_at=utc_naive(now))
            .execution_options(synchronize_session=False)
        )
    rows = await AgendaDiffusion.of_guest(session, guest.id)
    horizon = now - timedelta(days=2)
    visible = [
        row for row in rows if row.kind == KIND_SET and utc(row.ends_at) >= horizon
    ]
    return {
        "guest": {"name": guest.name},
        "now": iso_paris(now),
        "max_bytes": MAX_DEPOSIT_BYTES,
        "formats": sorted(suffix.lstrip(".") for suffix in DEPOSIT_SUFFIXES),
        "diffusions": [public_diffusion(row, now) for row in visible],
    }


async def guest_diffusion(
    session: ormSession, guest: AgendaGuest, diffusion_id: int
) -> AgendaDiffusion:
    row = await AgendaDiffusion.from_id(session, diffusion_id)
    if row is None or row.guest_id != guest.id or row.kind != KIND_SET:
        raise DomainNotFound("Émission introuvable.", field="id")
    return row


async def public_update(
    session: ormSession,
    guest: AgendaGuest,
    diffusion_id: int,
    data: dict,
    now: datetime | None = None,
) -> AgendaDiffusion:
    now = now_utc(now)
    row = await guest_diffusion(session, guest, diffusion_id)
    if row.air_status != AIR_UPCOMING:
        raise DomainConflict("Cette émission a déjà eu lieu.", field="air_status")
    if "set_title" in data:
        row.set_title = clean_text(
            data["set_title"], field="set_title", limit=SET_TITLE_MAX
        )
    if "tracklist" in data:
        row.tracklist = clean_text(
            data["tracklist"], field="tracklist", limit=TRACKLIST_MAX
        )
    if "rights" in data:
        row.rights_at = utc_naive(now) if bool(data["rights"]) else None
    await session.flush()
    return (await reload_diffusions(session, [row.id]))[0]


# -- deposits (catalog → engine) -----------------------------------------------


_UNSAFE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]+")


def deposit_name(row: AgendaDiffusion, guest: AgendaGuest, suffix: str) -> str:
    local = paris(row.starts_at)
    stem = f"{local:%Y-%m-%d} {guest.name} - {row.title}"
    stem = _UNSAFE.sub(" ", stem).strip(" .")[:150] or f"{local:%Y-%m-%d} set"
    return f"{stem}{suffix.lower()}"


def deposit_folder(row: AgendaDiffusion) -> str:
    return f"{EMISSIONS_TOP}/{slug(row.title)}/entiere"


async def deposit_check(  # noqa: PLR0911
    session: ormSession,
    data: dict,
    now: datetime | None = None,
) -> dict:
    """May this guest send this file now? Asked by the catalog before tus starts."""
    now = now_utc(now)
    guest = await guest_from_token(session, str(data.get("token") or ""))
    if guest is None:
        return {"ok": False, "reason": "lien invalide"}
    try:
        diffusion_id = int(data.get("diffusion_id"))
    except (TypeError, ValueError):
        return {"ok": False, "reason": "émission inconnue"}
    row = await AgendaDiffusion.from_id(session, diffusion_id)
    if row is None or row.guest_id != guest.id or row.kind != KIND_SET:
        return {"ok": False, "reason": "émission inconnue"}
    if row.air_status != AIR_UPCOMING or not deposit_open(row.starts_at, now):
        return {"ok": False, "reason": "dépôt fermé"}
    name = str(data.get("filename") or "").strip()
    suffix = Path(name).suffix.lower()
    if suffix not in DEPOSIT_SUFFIXES:
        return {"ok": False, "reason": "format inconnu"}
    size = data.get("size")
    try:
        nbytes = int(size) if size is not None else None
    except (TypeError, ValueError):
        nbytes = None
    if nbytes is not None and nbytes <= 0:
        return {"ok": False, "reason": "fichier vide"}
    if nbytes is not None and nbytes > MAX_DEPOSIT_BYTES:
        return {"ok": False, "reason": "fichier trop gros (4 Go au plus)"}
    return {
        "ok": True,
        "folder": deposit_folder(row),
        "filename": deposit_name(row, guest, suffix),
    }


def _media_file(raw: str) -> tuple[Path, str]:
    root = media_root()
    text = str(raw or "").strip().replace("\\", "/")
    if text.startswith("media:"):
        text = text[len("media:") :]
    candidate = Path(text)
    path = candidate if candidate.is_absolute() else root / candidate
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        raise DomainValidationError(
            "Ce fichier n'est pas dans la banque.", field="path"
        ) from exc
    if rel.split("/", 1)[0] in REFUSED_TOPS:
        raise DomainValidationError("Ce dossier ne sert pas à l'antenne.", field="path")
    if resolved.suffix.lower() not in DEPOSIT_SUFFIXES or not resolved.is_file():
        raise DomainValidationError("Fichier audio introuvable.", field="path")
    return resolved, rel


def _retire(row: AgendaFile, now: datetime) -> None:
    """Mark a file replaced; a guest's file goes to 90-trash, a bank file stays."""
    row.replaced_at = utc_naive(now)
    if row.origin != ORIGIN_DEPOT:
        return
    source = media_root() / row.path
    if not source.is_file():
        return
    dest = unique_trash_path(source.name)
    try:
        shutil.move(str(source), str(dest))
    except OSError:
        _log.warning("agenda: cannot move %s to the trash", source)


async def register_deposit(
    session: ormSession,
    data: dict,
    now: datetime | None = None,
) -> AgendaFile:
    """The catalog placed a guest's file: attach it, analysis follows."""
    now = now_utc(now)
    guest = await guest_from_token(session, str(data.get("token") or ""))
    if guest is None:
        raise DomainNotFound("Lien invalide.", field="token")
    try:
        diffusion_id = int(data.get("diffusion_id"))
    except (TypeError, ValueError) as exc:
        raise DomainNotFound("Émission inconnue.", field="diffusion_id") from exc
    row = await guest_diffusion(session, guest, diffusion_id)
    if row.air_status != AIR_UPCOMING or now >= utc(row.starts_at):
        raise DomainConflict("Trop tard : l'émission a commencé.", field="diffusion_id")
    _resolved, rel = _media_file(str(data.get("path") or ""))
    for old in row.files:
        if old.replaced_at is None:
            _retire(old, now)
    item = AgendaFile(
        diffusion_id=row.id,
        path=rel,
        origin=ORIGIN_DEPOT,
        original_name=clean_text(
            data.get("original_name"), field="original_name", limit=255
        ),
        report={"status": "pending"},
        late=1 if deposit_late(row.starts_at, row.deadline_at, now) else 0,
    )
    session.add(item)
    await session.flush()
    return item


async def attach_bank_file(
    session: ormSession,
    row: AgendaDiffusion,
    data: dict,
    now: datetime | None = None,
) -> AgendaFile:
    now = now_utc(now)
    if row.kind != KIND_SET:
        raise DomainConflict("Un direct n'a pas de fichier.", field="kind")
    if row.air_status != AIR_UPCOMING:
        raise DomainConflict("Cette émission a déjà eu lieu.", field="air_status")
    _resolved, rel = _media_file(str(data.get("path") or ""))
    try:
        duration = max(0.0, float(data.get("duration") or 0))
    except (TypeError, ValueError):
        duration = 0.0
    for old in row.files:
        if old.replaced_at is None:
            _retire(old, now)
    item = AgendaFile(
        diffusion_id=row.id,
        path=rel,
        origin=ORIGIN_BANK,
        original_name=Path(rel).name,
        duration=duration,
        report={"status": "pending"},
    )
    session.add(item)
    await session.flush()
    return item


async def detach_file(
    session: ormSession, row: AgendaDiffusion, now: datetime | None = None
) -> None:
    if row.air_status != AIR_UPCOMING:
        raise DomainConflict("Cette émission a déjà eu lieu.", field="air_status")
    current = row.current_file
    if current is None:
        raise DomainNotFound("Pas de fichier.", field="file")
    _retire(current, now_utc(now))
    await session.flush()


# -- analysis ------------------------------------------------------------------


async def _run(*args: str, timeout: float) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return -1, "", "timeout"
    return (
        process.returncode or 0,
        out.decode("utf-8", "replace"),
        err.decode("utf-8", "replace"),
    )


_LUFS = re.compile(r"I:\s+(-?\d+(?:\.\d+)?)\s+LUFS")


async def probe_audio(path: Path) -> dict:
    """ffprobe for the format, then a full decode through ebur128 for loudness."""
    code, out, err = await _run(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "format=duration,format_name,bit_rate:stream=codec_name,sample_rate,channels",
        "-of",
        "json",
        str(path),
        timeout=60,
    )
    if code != 0:
        return {"status": "error", "error": "Fichier illisible", "detail": err[-400:]}
    try:
        info = json.loads(out or "{}")
    except ValueError:
        return {"status": "error", "error": "Fichier illisible"}
    streams = info.get("streams") or []
    fmt = info.get("format") or {}
    if not streams:
        return {"status": "error", "error": "Pas de piste audio"}
    stream = streams[0]
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        return {"status": "error", "error": "Durée illisible"}
    code, _out, err = await _run(
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-filter:a",
        "ebur128=framelog=quiet",
        "-f",
        "null",
        "-",
        timeout=ANALYSIS_TIMEOUT,
    )
    if code != 0:
        return {
            "status": "error",
            "error": "Fichier illisible" if code > 0 else "Analyse trop longue",
            "detail": err[-400:],
        }
    found = _LUFS.findall(err)
    lufs = float(found[-1]) if found else None
    decode_errors = sum(
        1 for line in err.splitlines() if "error" in line.lower() and "LUFS" not in line
    )
    warnings = []
    if decode_errors:
        warnings.append(f"{decode_errors} erreur(s) de décodage")
    if lufs is not None and lufs < -36:
        warnings.append("Niveau très faible")
    try:
        bit_rate = int(fmt.get("bit_rate")) if fmt.get("bit_rate") else None
    except (TypeError, ValueError):
        bit_rate = None
    try:
        sample_rate = (
            int(stream.get("sample_rate")) if stream.get("sample_rate") else None
        )
    except (TypeError, ValueError):
        sample_rate = None
    return {
        "status": "ok",
        "error": "",
        "format": str(fmt.get("format_name") or ""),
        "codec": str(stream.get("codec_name") or ""),
        "sample_rate": sample_rate,
        "channels": stream.get("channels"),
        "bit_rate": bit_rate,
        "duration": round(duration, 3),
        "lufs": lufs,
        "gain": loudness_gain(lufs),
        "warnings": warnings,
    }


async def convert_to_flac(path: Path) -> Path | None:
    target = path.with_suffix(".flac")
    index = 2
    while target.exists():
        target = path.with_name(f"{path.stem}-{index}.flac")
        index += 1
    code, _out, err = await _run(
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-c:a",
        "flac",
        str(target),
        timeout=ANALYSIS_TIMEOUT,
    )
    if code != 0 or not target.is_file():
        _log.warning("agenda: flac conversion of %s failed: %s", path, err[-300:])
        target.unlink(missing_ok=True)
        return None
    path.unlink(missing_ok=True)
    return target


async def analyse(session: ormSession, file_id: int) -> AgendaFile | None:
    """Convert a guest's wav/aiff, then measure; the report lands on the row."""
    row = await AgendaFile.from_id(session, file_id)
    if row is None or row.replaced_at is not None:
        return row
    path = media_root() / row.path
    if not path.is_file():
        row.report = {"status": "error", "error": "Fichier introuvable"}
        await session.flush()
        return row
    if row.origin == ORIGIN_DEPOT and path.suffix.lower() in CONVERT_TO_FLAC:
        converted = await convert_to_flac(path)
        if converted is not None:
            path = converted
            row.path = converted.relative_to(media_root()).as_posix()
    report = await probe_audio(path)
    if report.get("status") == "ok":
        row.duration = float(report.get("duration") or row.duration or 0)
        row.gain = report.get("gain")
    report.pop("detail", None)
    report["analysed_at"] = iso_paris(now_utc())
    row.report = report
    await session.flush()
    return row


async def run_analysis(db, file_id: int) -> None:
    """Background task: one analysis at a time, never raises."""
    async with _analysis_lock:
        try:
            async with db.session() as session:
                await analyse(session, file_id)
                await session.commit()
        except Exception:
            _log.exception("agenda: analysis of file %s failed", file_id)


async def pending_analyses(session: ormSession) -> list[int]:
    return [row.id for row in await AgendaFile.pending(session)]


# -- for the harbor and the antenna -------------------------------------------


async def host_has_live_window(
    session: ormSession, username: str, now: datetime
) -> bool:
    name = username.strip().lower()
    if not name:
        return False
    now = utc(now)
    rows = await AgendaDiffusion.between(
        session,
        utc_naive(now - timedelta(hours=24)),
        utc_naive(now + LIVE_OPEN_BEFORE + timedelta(minutes=1)),
    )
    for row in rows:
        if row.kind != KIND_LIVE or row.air_status not in (AIR_UPCOMING, AIR_ON_AIR):
            continue
        if (row.host_username or "").strip().lower() != name:
            continue
        if utc(row.starts_at) - LIVE_OPEN_BEFORE <= now < utc(row.ends_at):
            return True
    return False


async def any_named_live(session: ormSession, now: datetime) -> bool:
    """A dated live with a host closes the harbor to others, as a weekly host does."""
    rows = await session.scalars(
        select(AgendaDiffusion.id)
        .where(
            AgendaDiffusion.kind == KIND_LIVE,
            AgendaDiffusion.host_username != "",
            AgendaDiffusion.ends_at > utc_naive(utc(now) - timedelta(days=1)),
        )
        .limit(1)
    )
    return rows.first() is not None


async def current_dated(
    session: ormSession, now: datetime, source: object
) -> dict | None:
    """The dated broadcast that names the antenna now, in emissions' shape."""
    from radiotomate.domain.emission import (
        STATE_ON_AIR,
        STATE_WAITING,
        is_harbor_source,
    )

    now = utc(now)
    rows = await AgendaDiffusion.between(
        session,
        utc_naive(now - timedelta(hours=24)),
        utc_naive(now + timedelta(minutes=1)),
    )
    on_air = [row for row in rows if row.air_status == AIR_ON_AIR]
    candidates = on_air or [
        row
        for row in rows
        if row.kind == KIND_LIVE
        and row.air_status == AIR_UPCOMING
        and utc(row.starts_at) <= now < utc(row.ends_at)
    ]
    if not candidates:
        return None
    row = candidates[0]
    if row.kind == KIND_LIVE:
        state = STATE_ON_AIR if is_harbor_source(source) else STATE_WAITING
        artist = row.host_username or ""
    else:
        # Only while the set is what plays: the track after it keeps its own name.
        in_carts = str(source or "").strip().lower() == "carts"
        state = (
            STATE_ON_AIR if row.air_status == AIR_ON_AIR and in_carts else STATE_WAITING
        )
        artist = row.guest.name if row.guest is not None else ""
    return {
        "id": row.id,
        "title": row.title,
        "artist": artist or row.title,
        "state": state,
        "scope": "dated",
        "kind": row.kind,
        "until": iso_paris(row.ends_at),
    }


async def agenda_issues(session: ormSession, now: datetime) -> list[str]:
    """For the alerts: sets due within two hours that cannot play, recent misses."""
    now = utc(now)
    rows = await AgendaDiffusion.between(
        session,
        utc_naive(now - timedelta(minutes=30)),
        utc_naive(now + timedelta(hours=2)),
    )
    issues = []
    for row in rows:
        start = utc(row.starts_at)
        guest = f" ({row.guest.name})" if row.guest is not None else ""
        if row.air_status == AIR_MISSED and now - start <= timedelta(minutes=30):
            issues.append(
                f"Émission manquée à {paris(start):%H:%M} : {row.title}{guest} — "
                f"{row.air_reason or 'pas passée'}"
            )
            continue
        if row.air_status != AIR_UPCOMING or row.kind != KIND_SET or start <= now:
            continue
        prep, reason = diffusion_state(row)
        if prep in (PREP_WAITING,) or not playable(
            row.kind,
            file=file_facts(row.current_file),
            rights=row.rights_at is not None,
        ):
            what = reason or "Set attendu"
            issues.append(f"{what} pour {paris(start):%H:%M} : {row.title}{guest}")
    return issues


async def dated_live_windows(
    session: ormSession, now: datetime, *, days: int = 0
) -> list[AgendaDiffusion]:
    """Dated lives around now (and up to ``days`` ahead), not yet over."""
    now = utc(now)
    rows = await AgendaDiffusion.between(
        session,
        utc_naive(now - timedelta(hours=1)),
        utc_naive(now + timedelta(hours=1, days=days)),
    )
    return [
        row
        for row in rows
        if row.kind == KIND_LIVE and row.air_status in (AIR_UPCOMING, AIR_ON_AIR)
    ]


async def forecast_windows(
    session: ormSession, start: datetime, end: datetime
) -> list[dict]:
    """Where the rundown must leave room: playable sets and dated lives.

    A set that cannot play is no window: the grid fills its slot.
    """
    if not await agenda_enabled(session):
        return []
    start = utc(start)
    end = utc(end)
    rows = await AgendaDiffusion.between(
        session, utc_naive(start - timedelta(hours=24)), utc_naive(end)
    )
    windows = []
    for row in rows:
        if row.air_status not in (AIR_UPCOMING, AIR_ON_AIR):
            continue
        slot = utc(row.ends_at) - utc(row.starts_at)
        if row.kind == KIND_LIVE:
            begin = utc(row.starts_at)
            finish = utc(row.ends_at)
            artist = row.host_username or row.title
        else:
            current = row.current_file
            if row.air_status == AIR_UPCOMING and not playable(
                row.kind, file=file_facts(current), rights=row.rights_at is not None
            ):
                continue
            begin = (
                utc(row.aired_start)
                if row.air_status == AIR_ON_AIR and row.aired_start
                else utc(row.starts_at)
            )
            length = (
                timedelta(seconds=float(current.duration))
                if current is not None and current.duration
                else slot
            )
            finish = begin + length
            artist = row.guest.name if row.guest is not None else row.title
        if finish <= start or begin >= end:
            continue
        windows.append(
            {
                "id": row.id,
                "kind": row.kind,
                "title": row.title,
                "artist": artist,
                "start": begin,
                "end": finish,
            }
        )
    windows.sort(key=lambda item: item["start"])
    return windows
