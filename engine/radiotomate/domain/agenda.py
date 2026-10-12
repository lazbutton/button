"""Pure rules for dated broadcasts (Agenda): time, repeats, overlaps, states.

Instants are compared in UTC; walls (what the console shows) are Paris time.
A naive datetime handed to :func:`wall_to_utc` is a Paris wall clock reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from radiotomate.domain.emission import PARIS
from radiotomate.domain.errors import DomainValidationError

UTC = timezone.utc

KIND_SET = "set"
KIND_LIVE = "live"
KINDS = (KIND_SET, KIND_LIVE)

AIR_UPCOMING = "upcoming"
AIR_ON_AIR = "on_air"
AIR_AIRED = "aired"
AIR_MISSED = "missed"

PREP_WAITING = "attendu"
PREP_ANALYSING = "analyse"
PREP_REVIEW = "a_revoir"
PREP_READY = "pret"

ORIGIN_DEPOT = "depot"
ORIGIN_BANK = "banque"

REPEAT_WEEKLY = "weekly"
REPEAT_BIWEEKLY = "biweekly"
REPEAT_MONTHLY = "monthly"
REPEAT_RULES = (REPEAT_WEEKLY, REPEAT_BIWEEKLY, REPEAT_MONTHLY)
MAX_REPEAT = 52

MIN_DURATION = timedelta(minutes=1)
MAX_DURATION = timedelta(hours=24)
DEFAULT_DEADLINE_BEFORE = timedelta(hours=24)
DEPOSIT_CLOSE_BEFORE = timedelta(minutes=30)
LIVE_OPEN_BEFORE = timedelta(minutes=15)
# A set may run past its slot; past this, a diffusion still "upcoming" is gone.
OVERRUN_WARNING = timedelta(minutes=1)
TODO_HORIZON = timedelta(days=7)
TODO_SET_WAITING = timedelta(hours=48)
TODO_LINK_UNOPENED = timedelta(hours=72)

TITLE_MAX = 120
NAME_MAX = 80
CONTACT_MAX = 200
SET_TITLE_MAX = 200
TRACKLIST_MAX = 20000

MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def utc(value: datetime) -> datetime:
    """An aware UTC instant. Naive values are UTC (that is how rows store them)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def utc_naive(value: datetime) -> datetime:
    """What a row stores: UTC, without tzinfo."""
    return utc(value).replace(tzinfo=None)


def paris(value: datetime) -> datetime:
    return utc(value).astimezone(PARIS)


def iso_paris(value: datetime | None) -> str | None:
    if value is None:
        return None
    return paris(value).isoformat(timespec="minutes")


def wall_label(value: datetime) -> str:
    """« samedi 24 octobre, 22:00 » (Paris)."""
    local = paris(value)
    return (
        f"{WEEKDAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]}, "
        f"{local:%H:%M}"
    )


def wall_to_utc(wall: datetime, *, field: str = "start") -> datetime:
    """Paris wall time → UTC instant. Refuses the hour skipped in March.

    An hour that happens twice (October) is the first one, summer time.
    """
    wall = wall.replace(tzinfo=None, second=0, microsecond=0)
    instant = wall.replace(tzinfo=PARIS, fold=0).astimezone(UTC)
    if instant.astimezone(PARIS).replace(tzinfo=None) != wall:
        raise DomainValidationError(
            f"Le {wall:%d/%m/%Y} à {wall:%H:%M} n'existe pas : "
            "on passe à l'heure d'été.",
            field=field,
        )
    return instant


def parse_instant(raw: object, *, field: str) -> datetime:
    """ISO with an offset is an instant; without one, a Paris wall time."""
    text = str(raw or "").strip()
    if not text:
        raise DomainValidationError("Date et heure requises.", field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainValidationError("Date ou heure illisible.", field=field) from exc
    if parsed.tzinfo is None:
        return wall_to_utc(parsed, field=field)
    return utc(parsed).replace(second=0, microsecond=0)


def parse_day(raw: object, *, field: str) -> date:
    text = str(raw or "").strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise DomainValidationError("Date illisible.", field=field) from exc


def validate_window(start: datetime, end: datetime) -> None:
    if end <= start:
        raise DomainValidationError("La fin doit être après le début.", field="end")
    if end - start < MIN_DURATION:
        raise DomainValidationError(
            "Une émission dure au moins une minute.", field="end"
        )
    if end - start > MAX_DURATION:
        raise DomainValidationError("Une émission dure 24 h au plus.", field="end")


def overlaps(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> bool:
    return utc(start_a) < utc(end_b) and utc(start_b) < utc(end_a)


def clean_text(raw: object, *, field: str, limit: int, required: bool = False) -> str:
    text = str(raw or "").strip()
    if required and not text:
        labels = {
            "title": "Le titre est requis.",
            "name": "Le nom est requis.",
        }
        raise DomainValidationError(labels.get(field, "Champ requis."), field=field)
    if len(text) > limit:
        raise DomainValidationError(
            f"{limit} caractères au plus.",
            field=field,
        )
    return text


def validate_kind(raw: object) -> str:
    kind = str(raw or KIND_SET).strip()
    if kind not in KINDS:
        raise DomainValidationError("Type inconnu : set ou direct.", field="kind")
    return kind


# -- repeats -------------------------------------------------------------------


def nth_of_month(day: date) -> int:
    """1 to 4, or -1 when ``day`` is the last such weekday of its month."""
    if (day + timedelta(days=7)).month != day.month:
        return -1
    return min(4, (day.day - 1) // 7 + 1)


def _weekday_in_month(year: int, month: int, weekday: int, nth: int) -> date:
    if nth == -1:
        if month == 12:
            last = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(year, month + 1, 1) - timedelta(days=1)
        return last - timedelta(days=(last.weekday() - weekday) % 7)
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (nth - 1))


def repeat_days(
    first: date,
    rule: str,
    *,
    count: int | None = None,
    until: date | None = None,
    nth: int | None = None,
) -> list[date]:
    """The dates of a series, ``first`` included, at most :data:`MAX_REPEAT`."""
    if rule not in REPEAT_RULES:
        raise DomainValidationError("Répétition inconnue.", field="repeat")
    if count is None and until is None:
        raise DomainValidationError(
            "Dis combien de fois, ou jusqu'à quand.", field="repeat"
        )
    if count is not None and not 1 <= count <= MAX_REPEAT:
        raise DomainValidationError(
            f"Entre 1 et {MAX_REPEAT} dates.", field="repeat_count"
        )
    if until is not None and until < first:
        raise DomainValidationError(
            "La fin de la répétition est avant la première date.",
            field="repeat_until",
        )
    limit = min(count or MAX_REPEAT, MAX_REPEAT)
    days: list[date] = []
    if rule in (REPEAT_WEEKLY, REPEAT_BIWEEKLY):
        step = timedelta(days=7 if rule == REPEAT_WEEKLY else 14)
        current = first
        while len(days) < limit and (until is None or current <= until):
            days.append(current)
            current += step
        return days
    rank = nth if nth in (1, 2, 3, 4, -1) else nth_of_month(first)
    year, month = first.year, first.month
    while len(days) < limit:
        current = _weekday_in_month(year, month, first.weekday(), rank)
        if until is not None and current > until:
            break
        if current >= first:
            days.append(current)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return days


def occurrence_walls(
    start_wall: datetime, end_wall: datetime, days: list[date]
) -> list[tuple[datetime, datetime]]:
    """Same Paris wall hours on each day, so a series keeps 22:00 all year."""
    span = end_wall - start_wall
    walls = []
    for day in days:
        start = datetime.combine(day, start_wall.time())
        walls.append((start, start + span))
    return walls


# -- states --------------------------------------------------------------------


@dataclass(frozen=True)
class FileFacts:
    """What the scheduler and the console need to know about a set file."""

    origin: str
    duration: float
    status: str  # "pending" | "ok" | "error"
    error: str = ""


def prep_state(  # noqa: PLR0911
    kind: str,
    *,
    file: FileFacts | None,
    rights: bool,
    host_username: str,
) -> tuple[str, str]:
    """(state, reason) of a diffusion before air: attendu, analyse, à revoir, prêt."""
    if kind == KIND_LIVE:
        if host_username.strip():
            return PREP_READY, ""
        return PREP_WAITING, "Personne pour ce direct"
    if file is None:
        return PREP_WAITING, "Set attendu"
    if file.status == "error":
        return PREP_REVIEW, file.error or "Fichier illisible"
    if file.origin == ORIGIN_DEPOT and not rights:
        return PREP_REVIEW, "Droits non cochés"
    if file.status == "pending":
        return PREP_ANALYSING, "Analyse en cours"
    return PREP_READY, ""


def playable(kind: str, *, file: FileFacts | None, rights: bool) -> bool:
    """A set goes on air with a readable file and, for a guest's file, rights."""
    if kind != KIND_SET or file is None or file.status == "error":
        return False
    return file.origin != ORIGIN_DEPOT or rights


def overrun_seconds(start: datetime, end: datetime, duration: float) -> float:
    return float(duration) - (utc(end) - utc(start)).total_seconds()


def deadline_for(start: datetime, deadline: datetime | None) -> datetime:
    return (
        utc(deadline) if deadline is not None else utc(start) - DEFAULT_DEADLINE_BEFORE
    )


def deposit_closes_at(start: datetime) -> datetime:
    return utc(start) - DEPOSIT_CLOSE_BEFORE


def deposit_open(start: datetime, now: datetime) -> bool:
    return utc(now) < deposit_closes_at(start)


def deposit_late(start: datetime, deadline: datetime | None, now: datetime) -> bool:
    return utc(now) > deadline_for(start, deadline)


@dataclass(frozen=True)
class TodoInput:
    diffusion_id: int
    kind: str
    title: str
    start: datetime
    air_status: str
    prep: str
    prep_reason: str
    guest_name: str
    guest_opened: bool
    has_file: bool


def todo_lines(rows: list[TodoInput], now: datetime) -> list[dict]:
    """« À préparer »: what still needs a gesture in the next seven days."""
    now = utc(now)
    lines: list[dict] = []
    for row in sorted(rows, key=lambda item: utc(item.start)):
        start = utc(row.start)
        if row.air_status != AIR_UPCOMING or start < now or start - now > TODO_HORIZON:
            continue
        when = wall_label(start)
        base = {"diffusion_id": row.diffusion_id, "at": iso_paris(start)}
        if row.kind == KIND_LIVE:
            if row.prep == PREP_WAITING:
                lines.append(
                    {
                        **base,
                        "rule": "live_host",
                        "text": f"Personne pour le direct du {when}",
                    }
                )
            continue
        if row.prep == PREP_REVIEW:
            lines.append(
                {
                    **base,
                    "rule": "review",
                    "text": f"{row.prep_reason} : {row.title}, {when}",
                }
            )
            continue
        if row.prep != PREP_WAITING:
            continue
        if start - now <= TODO_SET_WAITING:
            lines.append(
                {
                    **base,
                    "rule": "set_waiting",
                    "text": f"Set attendu : {row.title}, {when}",
                }
            )
            continue
        if (
            row.guest_name
            and not row.guest_opened
            and not row.has_file
            and start - now <= TODO_LINK_UNOPENED
        ):
            lines.append(
                {
                    **base,
                    "rule": "link_unopened",
                    "text": f"{row.guest_name} n'a pas ouvert son lien ({when})",
                }
            )
    return lines


def loudness_gain(integrated_lufs: float | None) -> float | None:
    """ReplayGain 2.0 reference: -18 LUFS. Clamped so a near-silent file stays sane."""
    if integrated_lufs is None:
        return None
    return round(max(-24.0, min(24.0, -18.0 - float(integrated_lufs))), 2)


def slug(text: str, *, fallback: str = "agenda") -> str:
    import unicodedata

    plain = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    out = []
    last_dash = False
    for char in plain.lower():
        if char.isalnum():
            out.append(char)
            last_dash = False
        elif not last_dash and out:
            out.append("-")
            last_dash = True
    cleaned = "".join(out).strip("-")
    return cleaned[:60] or fallback
