"""The settings of the fiches' search, and where it stands (FON-25).

- `features.fiches`, off by default, turns the search on: nothing is searched,
  nothing is written while it is off.
- `features.fiches_fmg`, off by default, turns the verdict on: no request about a
  person while it is off.
- `fiches.acoustid_key`, the AcoustID key of the station; BUTTON's otherwise
  (`BUTTON_ACOUSTID_KEY`, `fiches/sources.py`).
- The sources of FON-30, read by `SourceSettings.from_settings`.

Where the search stands is read with sqlite3 alone, from the engine's database:
`radiotomate maintenance fiches` says it, and so does `beet fiches`, from the
import loop, which has no event loop of its own.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select

from radiotomate.fiches.sources import BUTTON_ACOUSTID_KEY, SourceSettings
from radiotomate.models import Setting

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session as ormSession

SETTING_ENABLED = "features.fiches"
SETTING_FMG = "features.fiches_fmg"
SETTING_ACOUSTID_KEY = "fiches.acoustid_key"
_OFF = frozenset({"0", "false", "off", "non", ""})


def switched_on(value: object) -> bool:
    """An off-by-default switch: on only when set, and not to an « off »."""
    return value is not None and str(value).strip().lower() not in _OFF


@dataclass(frozen=True)
class FichesSettings:
    """What the search reads between two titles."""

    enabled: bool = False
    verdict: bool = False
    acoustid_key: str = field(default="", repr=False)
    sources: SourceSettings = field(default_factory=SourceSettings)

    @classmethod
    def from_settings(cls, values: dict[str, object]) -> FichesSettings:
        station_key = str(values.get(SETTING_ACOUSTID_KEY) or "").strip()
        return cls(
            enabled=switched_on(values.get(SETTING_ENABLED)),
            verdict=switched_on(values.get(SETTING_FMG)),
            acoustid_key=station_key or BUTTON_ACOUSTID_KEY,
            sources=SourceSettings.from_settings(values),
        )


async def read_settings(session: ormSession) -> FichesSettings:
    rows = await session.scalars(
        select(Setting).where(
            (Setting.key.like("features.fiches%")) | (Setting.key.like("fiches.%"))
        )
    )
    return FichesSettings.from_settings({row.key: row.value for row in rows})


async def set_enabled(session: ormSession, enabled: bool) -> None:
    await Setting.upsert(session, SETTING_ENABLED, "1" if enabled else "0")


@dataclass(frozen=True)
class Progress:
    """Where the search stands: the titles of the library, those searched, by
    status, and the propositions waiting to be read."""

    enabled: bool
    library: int | None
    statuses: dict[str, int]
    waiting: int

    @property
    def searched(self) -> int:
        return sum(self.statuses.values())


# The statuses of a fiche, in the order they are said.
STATUSES = ("trouvé", "rapproché", "introuvable", "écarté", "erreur")


def read_progress(database: Path, library: int | None = None) -> Progress:
    """Where the search stands, read in the engine's database. `library`: the number
    of titles of the library, when the caller can count them."""
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as con:
        tables = {
            name
            for (name,) in con.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }
        enabled = False
        if "settings" in tables:
            row = con.execute(
                "select value from settings where key = ?", (SETTING_ENABLED,)
            ).fetchone()
            enabled = switched_on(row[0] if row else None)
        if "fiches" not in tables:
            return Progress(enabled, library, {}, 0)
        statuses = Counter(
            dict(con.execute("select status, count(*) from fiches group by status"))
        )
        (waiting,) = con.execute(
            "select count(*) from fiche_propositions where state = 'proposée'"
        ).fetchone()
    return Progress(enabled, library, dict(statuses), waiting)


def _count(number: int) -> str:
    """A number as the console writes it: « 7 123 »."""
    return f"{number:,}".replace(",", "\u202f")


def describe(progress: Progress) -> str:
    """Where the search stands, in a few lines of French."""
    state = "allumée" if progress.enabled else "coupée"
    lines = [f"Recherche des fiches : {state}."]
    searched = progress.searched
    if progress.library is not None:
        lines.append(
            f"{_count(searched)} titre(s) cherché(s) sur {_count(progress.library)}."
        )
    else:
        lines.append(f"{_count(searched)} titre(s) cherché(s).")
    parts = [
        f"{_count(progress.statuses[status])} {status}"
        for status in STATUSES
        if progress.statuses.get(status)
    ]
    if parts:
        lines.append("Dont " + ", ".join(parts) + ".")
    lines.append(f"{_count(progress.waiting)} proposition(s) à relire.")
    if not progress.enabled:
        lines.append(
            "Pour l'allumer : station cli maintenance fiches --allumer. Ce qui part "
            "de la station : l'artiste, le titre, l'album et l'empreinte de ses "
            "fichiers, vers MusicBrainz, AcoustID, Deezer et Wikidata."
        )
    return "\n".join(lines)


def library_count(beets_library: Path) -> int | None:
    """The number of titles in the library of Beets, read with sqlite3."""
    if not beets_library.is_file():
        return None
    with closing(sqlite3.connect(f"file:{beets_library}?mode=ro", uri=True)) as con:
        if not con.execute(
            "select 1 from sqlite_master where name = 'items'"
        ).fetchone():
            return 0
        (count,) = con.execute("select count(*) from items").fetchone()
    return count
