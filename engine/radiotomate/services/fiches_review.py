"""What the view « À relire » shows of the fiches (FON-26), in reading only.

- `review_page`: where the search stands, the counts by level, field, state and
  bank, the titles in error grouped by their cause, and a page of titles, each with
  its propositions. Without a level or a state asked, the titles that wait to be
  read: a proposition « proposée ».
- `review_detail`: one title, its fiche, its propositions, and its evidence, made
  readable by the rules: what was found, where, and its length.

Nothing is accepted here: FON-27 does it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from radiotomate.domain.agenda import iso_paris
from radiotomate.domain.errors import DomainNotFound, DomainValidationError
from radiotomate.fiches.evidence import from_json
from radiotomate.fiches.proposals import Track, build_row
from radiotomate.models import Fiche
from radiotomate.models.fiche import PROPOSED
from radiotomate.services.bank_titles import ROTATION, bank_rel, fold, title_of

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from sqlalchemy.orm import Session as ormSession

# The levels of a fiche, in the order the view ranks them: the surest first.
LEVELS = ("sûr", "à revoir", "rapproché", "introuvable", "écarté", "erreur")
FIELDS = ("title", "artist", "album", "year", "label", "isrc", "famille", "fmg")
STATES = (
    "proposée",
    "acceptée",
    "écrite",
    "refusée",
    "périmée",
    "revenue",
    "en erreur",
)
PAGE = 50
MAX_PAGE = 200
# The recent searches that tell the pace of the search.
PACE_OVER = 50
# The causes of the titles in error said in the head of the view.
FAILURES_SAID = 5


@dataclass(frozen=True)
class ReviewQuery:
    """What the view asks: a level, a field, a bank, a state, a text, and a page."""

    level: str = ""
    field: str = ""
    bank: str = ""
    state: str = ""
    q: str = ""
    offset: int = 0
    limit: int = PAGE

    @classmethod
    def from_args(cls, args: Mapping[str, str]) -> ReviewQuery:
        def one_of(name: str, values: tuple[str, ...]) -> str:
            value = str(args.get(name) or "").strip()
            if value and value not in values:
                raise DomainValidationError(
                    f"« {value} » n'est pas un choix.", field=name
                )
            return value

        def number(name: str, default: int, low: int, high: int) -> int:
            raw = args.get(name)
            if raw in (None, ""):
                return default
            try:
                value = int(raw)
            except (TypeError, ValueError) as exc:
                raise DomainValidationError(
                    "Un nombre entier est attendu.", field=name
                ) from exc
            return max(low, min(high, value))

        return cls(
            level=one_of("level", LEVELS),
            field=one_of("field", FIELDS),
            bank=str(args.get("bank") or "").strip(),
            state=one_of("state", STATES),
            q=" ".join(str(args.get("q") or "").split()),
            offset=number("offset", 0, 0, 10**9),
            limit=number("limit", PAGE, 1, MAX_PAGE),
        )


def _bank(title: dict) -> str:
    """Where a title is, as the filter names it: the rotation, or its collection."""
    return title["collection"] or ""


def _proposition(proposition: Any) -> dict:
    return {
        "id": proposition.id,
        "field": proposition.field,
        "before": proposition.before,
        "value": proposition.value,
        "level": proposition.level,
        "why": proposition.why,
        "source": proposition.source,
        "state": proposition.state,
    }


def _title(title: dict) -> dict:
    return {
        key: title[key]
        for key in (
            "id",
            "title",
            "artist",
            "album",
            "year",
            "duration",
            "zone",
            "collection",
            "path",
        )
    }


def _pace(fiches: list[Any]) -> float | None:
    """The seconds a title takes, read on the recent searches."""
    times = sorted(fiche.searched_at for fiche in fiches if fiche.searched_at)[
        -PACE_OVER:
    ]
    if len(times) < 2:
        return None
    span = (times[-1] - times[0]).total_seconds()
    return span / (len(times) - 1) if span > 0 else None


def _counted(counter: Counter, order: tuple[str, ...] = ()) -> list[dict]:
    known = [value for value in order if counter.get(value)]
    rest = sorted(value for value in counter if value not in order)
    return [{"value": value, "count": counter[value]} for value in [*known, *rest]]


async def review_page(
    session: ormSession, rows: list[tuple], query: ReviewQuery, *, enabled: bool
) -> dict:
    """The head of the view and one page of its titles."""
    titles = {entry["id"]: entry for entry in map(title_of, rows)}
    fiches = list(
        (
            await session.scalars(
                select(Fiche).options(selectinload(Fiche.propositions))
            )
        ).all()
    )
    fiches = [fiche for fiche in fiches if fiche.beets_id in titles]
    statuses = Counter(fiche.status for fiche in fiches)
    states = Counter(
        proposition.state for fiche in fiches for proposition in fiche.propositions
    )
    waiting = [
        fiche
        for fiche in fiches
        if any(one.state == PROPOSED for one in fiche.propositions)
    ]
    levels = Counter(fiche.level for fiche in waiting)
    fields = Counter(
        one.field
        for fiche in waiting
        for one in fiche.propositions
        if one.state == PROPOSED
    )
    banks = Counter(_bank(titles[fiche.beets_id]) for fiche in fiches)
    failures = Counter(
        fiche.error or "erreur" for fiche in fiches if fiche.status == "erreur"
    )
    pace = _pace(fiches)
    remaining = max(0, len(titles) - len(fiches))
    hours = round(remaining * pace / 3600, 1) if enabled and pace else None

    wanted = query.state or ("" if query.level else PROPOSED)
    words = fold(query.q)
    picked = []
    for fiche in fiches:
        title = titles[fiche.beets_id]
        if query.level and fiche.level != query.level:
            continue
        if query.bank and _bank(title) != query.bank:
            continue
        if words and words not in fold(
            " ".join((title["title"], title["artist"], title["album"]))
        ):
            continue
        shown = [
            one
            for one in fiche.propositions
            if (not wanted or one.state == wanted)
            and (not query.field or one.field == query.field)
        ]
        if (wanted or query.field) and not shown:
            continue
        picked.append((fiche, title, shown))
    rank = {level: index for index, level in enumerate(LEVELS)}
    picked.sort(
        key=lambda one: (
            rank.get(one[0].level, len(LEVELS)),
            fold(one[1]["artist"]),
            fold(one[1]["title"]),
            one[1]["id"],
        )
    )
    page = picked[query.offset : query.offset + query.limit]
    end = query.offset + len(page)
    return {
        "enabled": enabled,
        "progress": {
            "library": len(titles),
            "searched": len(fiches),
            "remaining_hours": hours,
        },
        "statuses": dict(statuses),
        "levels": _counted(levels, LEVELS),
        "fields": _counted(fields, FIELDS),
        "states": _counted(states, STATES),
        "banks": [
            {"value": value, "count": count}
            for value, count in sorted(
                banks.items(), key=lambda item: (item[0] != ROTATION, fold(item[0]))
            )
            if value
        ],
        "failures": [
            {"error": error, "count": count}
            for error, count in failures.most_common(FAILURES_SAID)
        ],
        "titles": [
            {
                **_title(title),
                "status": fiche.status,
                "level": fiche.level,
                "reasons": list(fiche.reasons or []),
                "source": fiche.source,
                "url": fiche.url,
                "propositions": [_proposition(one) for one in shown],
            }
            for fiche, title, shown in page
        ],
        "total": len(picked),
        "next": end if end < len(picked) else None,
    }


def _track(item: Any) -> Track:
    length = item.get("length")
    return Track(
        title=item.get("title") or "",
        artist=item.get("artist") or "",
        album=item.get("album") or "",
        year=int(item.get("year") or 0),
        label=item.get("label") or "",
        isrc=item.get("isrc") or "",
        length=float(length) if length else None,
        famille=item.get("famille") or "",
        fmg=item.get("fmg") or "",
    )


def _readable(fiche: Any, track: Track) -> dict | None:
    """What the sources said of a title, as the rules read it."""
    if not fiche.evidence:
        return None
    result, wikidata = from_json(fiche.evidence)
    row = build_row(track, result, wikidata)
    return {
        "found_at": row.found_at,
        "platform": row.platform,
        "url": row.url,
        "title": row.found_title,
        "artists": row.found_artists,
        "album": row.found_album,
        "duration": row.found_duration,
        "genres": row.genres,
        "year_source": row.year_source,
        "doubt": result.doubt,
    }


async def review_detail(session: ormSession, beets_id: int, item: Any) -> dict:
    """One title: its fiche, its propositions and its evidence."""
    fiche = await session.scalar(
        select(Fiche)
        .where(Fiche.beets_id == beets_id)
        .options(selectinload(Fiche.propositions))
    )
    if fiche is None or item is None:
        raise DomainNotFound("Ce titre n'a pas encore de fiche.")
    track = _track(item)
    path = bank_rel(item.get("path"))
    title = title_of(
        (
            beets_id,
            item.get("path"),
            track.title,
            track.artist,
            track.album,
            track.year,
            "",
            track.length,
            track.famille,
        )
    )
    return {
        "title": {
            **_title(title),
            "path": path,
            "label": track.label,
            "isrc": track.isrc,
        },
        "fiche": {
            "status": fiche.status,
            "level": fiche.level,
            "reasons": list(fiche.reasons or []),
            "source": fiche.source,
            "url": fiche.url,
            "error": fiche.error,
            "attempts": fiche.attempts,
            "searched_at": iso_paris(_utc(fiche.searched_at)),
            "next_at": iso_paris(_utc(fiche.next_at)),
        },
        "propositions": [_proposition(one) for one in fiche.propositions],
        "evidence": _readable(fiche, track),
        "listen": f"/autodj/beets/{beets_id}",
    }


def _utc(value: datetime | None) -> datetime | None:
    """A naive UTC time of the new tables, made aware for the API."""
    if value is None or value.year < 1971:
        return None
    return value.replace(tzinfo=UTC)
