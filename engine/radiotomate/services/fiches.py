"""The settings of the fiches' search, and where it stands (FON-25).

- `features.fiches`, off by default, turns the search on: nothing is searched,
  nothing is written while it is off.
- `features.fiches_fmg`, off by default, turns the verdict on: no request about a
  person while it is off.
- `fiches.acoustid_key`, the AcoustID key of the station; BUTTON's otherwise
  (`BUTTON_ACOUSTID_KEY`, `fiches/sources.py`).
- The sources of FON-30, read by `SourceSettings.from_settings`.
- `features.fiches_covers`, off by default, shows the cover of a title found in the
  console, by its link only (FON-83): in its fiche and in the title on air.

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

from sqlalchemy import delete, select

from radiotomate.domain.errors import DomainValidationError
from radiotomate.fiches.sources import (
    BUTTON_ACOUSTID_KEY,
    SETTING_APPLE,
    SETTING_BANDCAMP,
    SETTING_TIDAL,
    SETTING_TIDAL_CLIENT_ID,
    SETTING_TIDAL_CLIENT_SECRET,
    SourceSettings,
)
from radiotomate.models import Setting
from radiotomate.services.bank_titles import bank_tidy_enabled

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session as ormSession

SETTING_ENABLED = "features.fiches"
SETTING_FMG = "features.fiches_fmg"
SETTING_ACOUSTID_KEY = "fiches.acoustid_key"
SETTING_COVERS = "features.fiches_covers"
_OFF = frozenset({"0", "false", "off", "non", ""})


def switched_on(value: object) -> bool:
    """An off-by-default switch: on only when set, and not to an « off »."""
    return value is not None and str(value).strip().lower() not in _OFF


@dataclass(frozen=True)
class FichesSettings:
    """What the search reads between two titles."""

    enabled: bool = False
    verdict: bool = False
    covers: bool = False
    acoustid_key: str = field(default="", repr=False)
    sources: SourceSettings = field(default_factory=SourceSettings)

    @classmethod
    def from_settings(cls, values: dict[str, object]) -> FichesSettings:
        station_key = str(values.get(SETTING_ACOUSTID_KEY) or "").strip()
        return cls(
            enabled=switched_on(values.get(SETTING_ENABLED)),
            verdict=switched_on(values.get(SETTING_FMG)),
            covers=switched_on(values.get(SETTING_COVERS)),
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


async def verdict_on(session: ormSession) -> bool:
    """The verdict « femme ou minorité de genre » shown (FON-80): `features.fiches_fmg`
    on. Off, no route says a word of it. The general switch of the bank's tidying
    off, the table still reads, its verdict with it (FON-85)."""
    return (await read_settings(session)).verdict


async def covers_on(session: ormSession) -> bool:
    """Whether the console shows the covers of the titles found (FON-83): behind the
    general switch of the bank's tidying, as the fiches are, and their own."""
    row = await Setting.from_key(session, SETTING_COVERS)
    return switched_on(row.value if row else None) and await bank_tidy_enabled(session)


async def set_enabled(session: ormSession, enabled: bool) -> None:
    await Setting.upsert(session, SETTING_ENABLED, "1" if enabled else "0")


# What part of the station the search sends, as Réglages says it.
SENT = (
    "l'artiste, le titre, l'album et l'empreinte de ses fichiers, vers MusicBrainz, "
    "AcoustID, Deezer et Wikidata ; l'artiste et le titre vers Tidal, Apple Music et "
    "Bandcamp, s'ils sont allumés. Rien des auditeurs. Rien de l'équipe, sauf, "
    "pochettes allumées, l'adresse du navigateur de la console, qui demande chaque "
    "pochette à Deezer, Apple Music ou Bandcamp."
)

# The switches that `PUT /fiches/reglages.json` writes, by the name of its field.
SWITCHES = {
    "enabled": SETTING_ENABLED,
    "verdict": SETTING_FMG,
    "covers": SETTING_COVERS,
    "tidal": SETTING_TIDAL,
    "apple_music": SETTING_APPLE,
    "bandcamp": SETTING_BANDCAMP,
}
# The keys, written and never read back: a route says only whether one is set.
KEYS = {
    "acoustid_key": SETTING_ACOUSTID_KEY,
    "tidal_client_id": SETTING_TIDAL_CLIENT_ID,
    "tidal_client_secret": SETTING_TIDAL_CLIENT_SECRET,
}
KEY_MAX = 200


async def settings_payload(session: ormSession) -> dict:
    """The settings of the search, without the value of a key."""
    rows = await session.scalars(
        select(Setting).where(
            (Setting.key.like("features.fiches%")) | (Setting.key.like("fiches.%"))
        )
    )
    values = {row.key: row.value for row in rows}
    settings = FichesSettings.from_settings(values)
    sources = settings.sources
    return {
        "enabled": settings.enabled,
        "verdict": settings.verdict,
        "covers": settings.covers,
        "acoustid_key_set": bool(str(values.get(SETTING_ACOUSTID_KEY) or "").strip()),
        "sources": {
            "tidal": sources.tidal,
            "apple_music": sources.apple,
            "bandcamp": sources.bandcamp,
            "tidal_key_set": sources.tidal_key,
        },
        "sent": SENT,
    }


async def write_settings(session: ormSession, data: dict) -> None:
    """The settings that `data` names, all checked before any is written. A key
    given empty is removed: BUTTON's AcoustID key comes back."""
    switches, keys = {}, {}
    for name, value in data.items():
        if name in SWITCHES:
            if not isinstance(value, bool):
                raise DomainValidationError(
                    "Coche ou décoche, sans autre valeur.", field=name
                )
            switches[SWITCHES[name]] = value
        elif name in KEYS:
            if not isinstance(value, str) or len(value.strip()) > KEY_MAX:
                raise DomainValidationError(
                    f"Une clé tient en {KEY_MAX} signes au plus.", field=name
                )
            if any(char.isspace() for char in value.strip()):
                raise DomainValidationError(
                    "Une clé tient sur une ligne, sans espace.", field=name
                )
            keys[KEYS[name]] = value.strip()
    for key, on in switches.items():
        await Setting.upsert(session, key, "1" if on else "0")
    for key, value in keys.items():
        if value:
            await Setting.upsert(session, key, value)
        else:
            await session.execute(delete(Setting).where(Setting.key == key))


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
