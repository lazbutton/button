"""Corriger la fiche d'un titre ou d'un lot (FON-66). Sans Quart.

Le seul service du moteur qui écrit la fiche d'un titre de la bibliothèque : la
correction d'une personne (FON-66), l'annulation d'un lot (« Revenir », FON-71) et
l'acceptation d'une proposition (FON-27) passent par lui.

- Le fichier d'abord, par Beets (`Item.write`, comme `beet modify`), puis la
  bibliothèque, qui note la nouvelle date du fichier : la boucle d'import ne le relit
  pas pour rien. Un fichier changé depuis sa dernière lecture est relu avant : Beets
  récrit tous les tags qu'il connaît, et ne doit pas écraser ce qu'un autre outil y a
  mis.
- La famille, et plus tard les étiquettes (FON-74), sont des champs flexibles de
  Beets : la bibliothèque seulement, jamais le fichier.
- Un lot prend 500 titres au plus.
- Un titre à l'antenne ou en file attend : une ligne du conducteur engagée porte son
  identifiant ou son chemin. Son écriture se fait quand il en est sorti
  (`apply_waiting`). La vérification et l'écriture du fichier se font sous le verrou
  d'écriture de la base : le scheduler n'envoie pas le titre entre les deux.
- Rien à moitié. Un titre qui ne peut pas s'écrire (disparu, illisible, que le
  moteur ne peut pas écrire, changé depuis ce que la personne a vu) refuse le lot
  entier, avant toute écriture. Un fichier qui échoue en route rend aux fichiers
  déjà écrits leurs tags d'avant. L'annulation et l'acceptation, elles, laissent un
  tel titre de côté et le disent : les autres s'écrivent.
- Chaque lot se note au journal, avec la valeur d'avant (`JournalEntry`).
- Le genre ne s'écrit jamais par une proposition ([ADR 0017]).
- Deux interrupteurs : celui du chantier, `features.bank_tidy` (FON-64), éteint
  tant que FON-85 ne l'a pas allumé, et celui de ce service, `features.title_edits`,
  allumé quand la clé manque.

[ADR 0017]: docs/decisions/0017-une-fiche-ne-s-ecrit-qu-acceptee.md
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from asyncio import get_running_loop
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from beets.dbcore.query import InvalidQueryArgumentValueError, ParsingError
from beets.library import FileOperationError, Item, parse_query_string
from sqlalchemy import or_, select, text

from radiotomate.domain.errors import (
    DomainConflict,
    DomainError,
    DomainNotFound,
    DomainValidationError,
)
from radiotomate.domain.execution import ENGAGED_STATUSES
from radiotomate.enums import CommandStatus, RundownStatus
from radiotomate.fiches.rules import FAMILIES
from radiotomate.models import (
    JournalChange,
    JournalEntry,
    MusicCategory,
    PlayoutCommand,
    RundownItem,
    Setting,
)
from radiotomate.services.bank_titles import bank_tidy_enabled
from radiotomate.services.beets_query import playable_query

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Mapping

    from beets.dbcore.query import Query
    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration

_log = logging.getLogger(__name__)

MAX_TITLES = 500

# Écrits dans le fichier, puis dans la bibliothèque.
TAG_FIELDS = ("title", "artist", "album", "year", "genre", "label", "isrc")
# Dans la bibliothèque seulement : des champs flexibles de Beets.
FLEX_FIELDS = ("famille",)
FIELDS = TAG_FIELDS + FLEX_FIELDS
# Ce qu'une personne corrige dans la console.
PERSON_FIELDS = ("title", "artist", "album", "year", "genre", "famille")

GESTURE_EDIT = "edit"
GESTURE_UNDO = "undo"
# FON-27 : une proposition acceptée.
GESTURE_ACCEPT = "accept"
GESTURES = (GESTURE_EDIT, GESTURE_UNDO, GESTURE_ACCEPT)
# Une proposition n'écrit jamais le genre (ADR 0017).
NEVER_ACCEPTED = frozenset({"genre"})

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_WAITING = "waiting"
STATUS_KEPT = "kept"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"

# L'interrupteur de ce service : allumé quand la clé manque. Celui du chantier,
# `features.bank_tidy`, est dans `bank_titles`.
SETTING_TITLE_EDITS = "features.title_edits"
_SETTING_OFF = {"0", "false", "off", "no", "non", ""}

# Une écriture que le moteur a laissée en route, par un arrêt : relue après ce délai.
PENDING_GRACE = timedelta(minutes=5)

MAX_TEXT = 1000
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ISRC = re.compile(r"[A-Z]{2}[A-Z0-9]{3}[0-9]{7}")
FAMILY_NAMES = frozenset(family.name for family in FAMILIES)

FIELD_LABELS = {
    "title": "le titre",
    "artist": "l'artiste",
    "album": "l'album",
    "year": "l'année",
    "genre": "le genre",
    "label": "le label",
    "isrc": "l'ISRC",
    "famille": "la famille",
}

# Pourquoi un titre ne s'écrit pas, ou pas encore.
ISSUE_UNKNOWN = "unknown"
ISSUE_MISSING = "missing"
ISSUE_READ_ONLY = "read_only"
ISSUE_UNREADABLE = "unreadable"
ISSUE_CHANGED = "changed"
ISSUE_ON_AIR = "on_air"
ISSUE_QUEUED = "queued"
ISSUE_FAILED = "failed"
ISSUE_MESSAGES = {
    ISSUE_UNKNOWN: "Ce titre n'est plus dans la bibliothèque.",
    ISSUE_MISSING: "Son fichier a disparu du disque.",
    ISSUE_READ_ONLY: "Le moteur n'a pas le droit d'écrire son fichier.",
    ISSUE_UNREADABLE: "Son fichier ne se lit pas : il est abîmé, ou d'un format "
    "que Beets ne connaît pas.",
    ISSUE_CHANGED: "Sa fiche a changé depuis : elle garde sa valeur.",
    ISSUE_ON_AIR: "Il est à l'antenne : sa fiche s'écrira quand il sera passé.",
    ISSUE_QUEUED: "Il est en file : sa fiche s'écrira quand il sera passé.",
    ISSUE_FAILED: "Son fichier n'a pas pu s'écrire.",
}


class TitleEditsOff(DomainError):  # noqa: N818
    status_code = 409
    code = "title_edits_off"


class TitlesRefused(DomainError):  # noqa: N818
    """Rien n'a été écrit : chaque titre en cause dit pourquoi."""

    status_code = 409
    code = "titles_refused"

    def __init__(self, message: str, titles: list[TitleIssue]):
        super().__init__(message)
        self.titles = titles


@dataclass(frozen=True)
class TitleEdit:
    """Les champs à écrire pour un titre de la bibliothèque.

    ``expected`` dit ce que l'appelant a vu : un champ qui vaut autre chose
    maintenant a changé depuis.
    """

    beets_id: int
    values: Mapping[str, object]
    expected: Mapping[str, object] | None = None


@dataclass(frozen=True)
class TitleIssue:
    beets_id: int
    label: str
    code: str

    @property
    def reason(self) -> str:
        return ISSUE_MESSAGES[self.code]

    def payload(self) -> dict:
        return {
            "id": self.beets_id,
            "label": self.label,
            "code": self.code,
            "reason": self.reason,
        }


@dataclass
class SelectionChange:
    """Une sélection de titres qui gagne ou perd des titres du lot."""

    id: int
    name: str
    gained: int = 0
    lost: int = 0

    def payload(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "gained": self.gained,
            "lost": self.lost,
        }


@dataclass
class EditOutcome:
    entry_id: int | None = None
    written: list[int] = field(default_factory=list)
    waiting: list[TitleIssue] = field(default_factory=list)
    kept: list[TitleIssue] = field(default_factory=list)
    refused: list[TitleIssue] = field(default_factory=list)
    unchanged: list[int] = field(default_factory=list)
    selections: list[SelectionChange] = field(default_factory=list)

    def payload(self) -> dict:
        return {
            "entry": self.entry_id,
            "written": len(self.written),
            "waiting": [issue.payload() for issue in self.waiting],
            "kept": [issue.payload() for issue in self.kept],
            "refused": [issue.payload() for issue in self.refused],
            "unchanged": len(self.unchanged),
            "selections": [change.payload() for change in self.selections],
        }


@dataclass
class _Plan:
    """Un titre à écrire : l'Item de Beets, et ce qui change."""

    item: Item
    label: str
    path: str
    before: dict[str, object]
    after: dict[str, object]
    # la valeur de chaque champ de Beets avant l'écriture, pour remettre le fichier
    snapshot: dict[str, object] = field(default_factory=dict)

    @property
    def beets_id(self) -> int:
        return int(self.item.id)

    @property
    def touches_file(self) -> bool:
        return any(name in TAG_FIELDS for name in self.after)


class _WriteFailed(Exception):  # noqa: N818
    def __init__(self, plan: _Plan, cause: Exception):
        super().__init__(str(cause))
        self.plan = plan
        self.cause = cause


# -- interrupteurs -----------------------------------------------------------------


async def title_edits_enabled(session: ormSession) -> bool:
    """Le chantier ouvert, et ce service pas coupé."""
    if not await bank_tidy_enabled(session):
        return False
    row = await Setting.from_key(session, SETTING_TITLE_EDITS)
    return row is None or str(row.value).strip().lower() not in _SETTING_OFF


async def require_title_edits(session: ormSession) -> None:
    if not await title_edits_enabled(session):
        raise TitleEditsOff(
            "La correction des fiches n'est pas ouverte sur cette station."
        )


# -- les valeurs -------------------------------------------------------------------


def _genre_key() -> str:
    # Beets 2.14 garde les genres d'un titre dans une liste, `genres` (ARC-06).
    return "genres" if "genres" in Item._fields else "genre"


def clean_value(name: str, raw: object) -> object:
    """La valeur à écrire, vérifiée. Lève `DomainValidationError`."""
    if name == "year":
        return _clean_year(raw)
    if raw is None:
        raw = ""
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
        raise DomainValidationError(
            f"La valeur de {FIELD_LABELS[name]} doit être un texte.", field=name
        )
    value = unicodedata.normalize("NFC", str(raw)).strip()
    if _CONTROL.search(value):
        raise DomainValidationError(
            f"La valeur de {FIELD_LABELS[name]} a un saut de ligne ou un signe de "
            "contrôle : retire-le.",
            field=name,
        )
    if len(value) > MAX_TEXT:
        raise DomainValidationError(
            f"La valeur de {FIELD_LABELS[name]} dépasse {MAX_TEXT} signes.",
            field=name,
        )
    if name == "famille" and value and value not in FAMILY_NAMES:
        raise DomainValidationError(
            "Cette famille n'existe pas. Choisis-en une de la liste.", field=name
        )
    if name == "isrc" and value:
        value = value.replace("-", "").upper()
        if not _ISRC.fullmatch(value):
            raise DomainValidationError(
                "Un ISRC s'écrit en douze signes, comme FRZ039800212.", field=name
            )
    return value


def _clean_year(raw: object) -> int:
    if raw is None or raw == "":
        return 0
    if isinstance(raw, bool):
        raw = None
    elif isinstance(raw, str) and raw.strip().isdigit():
        raw = int(raw.strip())
    if not isinstance(raw, int) or not (raw == 0 or 1000 <= raw <= 9999):
        raise DomainValidationError(
            "L'année s'écrit en quatre chiffres, comme 2019.", field="year"
        )
    return raw


def current_value(item: Item, name: str) -> object:
    """Ce que la bibliothèque dit d'un champ, comme la console le montre."""
    if name == "year":
        return int(item.get("year") or 0)
    if name == "genre":
        key = _genre_key()
        value = item.get(key)
        if key == "genres":
            return ", ".join(str(part) for part in value or ())
        return str(value or "")
    if name in FLEX_FIELDS:
        return str(item.get(name, "") or "")
    return str(item.get(name) or "")


def _comparable(name: str, value: object) -> object:
    """Deux valeurs que la console montre de même sont égales : les espaces de
    trop ne comptent pas (`_text`, services/bank_titles.py)."""
    if name == "year":
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return value
    return " ".join(str(value or "").split())


def _set_value(item: Item, name: str, value: object) -> None:
    if name == "genre" and _genre_key() == "genres":
        item["genres"] = [part.strip() for part in str(value).split(",") if part]
    elif name in FLEX_FIELDS and value == "":
        if name in item:
            del item[name]
    else:
        item[name] = value


def title_label(item: Item) -> str:
    artist = str(item.get("artist") or "").strip()
    title = str(item.get("title") or "").strip()
    if artist and title:
        return f"{artist} \u2013 {title}"
    return title or artist or Path(os.fsdecode(item.path)).name


def _path(item: Item) -> str:
    return os.fsdecode(item.path)


# -- le plan : ce qui change, et ce qui empêche -------------------------------------


def _plan_titles(
    beets: BeetsIntegration, edits: Iterable[TitleEdit]
) -> tuple[list[_Plan], list[int], list[TitleIssue]]:
    """Ce qui change pour chaque titre, et les titres qui ne peuvent pas s'écrire.

    Synchrone : Beets lit sa base et les fichiers. Un fichier changé depuis sa
    dernière lecture est relu : la valeur d'avant est celle du fichier.
    """
    plans: list[_Plan] = []
    unchanged: list[int] = []
    issues: list[TitleIssue] = []
    for edit in edits:
        item = beets.lib.get_item(edit.beets_id)
        if item is None:
            issues.append(TitleIssue(edit.beets_id, "", ISSUE_UNKNOWN))
            continue
        label = title_label(item)
        if any(name in TAG_FIELDS for name in edit.values):
            problem = _file_problem(item)
            if problem is not None:
                issues.append(TitleIssue(edit.beets_id, label, problem))
                continue
        expected = edit.expected or {}
        if any(
            _comparable(name, current_value(item, name)) != _comparable(name, seen)
            for name, seen in expected.items()
        ):
            issues.append(TitleIssue(edit.beets_id, label, ISSUE_CHANGED))
            continue
        before: dict[str, object] = {}
        after: dict[str, object] = {}
        for name, value in edit.values.items():
            now = current_value(item, name)
            if now != value:
                before[name] = now
                after[name] = value
        if not after:
            unchanged.append(edit.beets_id)
            continue
        plans.append(_Plan(item, label, _path(item), before, after))
    return plans, unchanged, issues


def _file_problem(item: Item) -> str | None:
    """Ce qui empêche d'écrire le fichier d'un titre, s'il y a quelque chose."""
    path = item.path
    if not Path(os.fsdecode(path)).is_file():
        return ISSUE_MISSING
    if not os.access(path, os.R_OK | os.W_OK):
        return ISSUE_READ_ONLY
    try:
        if item.current_mtime() != int(item.get("mtime") or 0):
            # un autre outil a écrit le fichier depuis que Beets l'a lu
            item.read()
    except FileOperationError:
        return ISSUE_UNREADABLE
    except OSError:
        return ISSUE_MISSING
    return None


# -- l'antenne ---------------------------------------------------------------------

_SENDING = (CommandStatus.PENDING.value, CommandStatus.SENDING.value)


async def busy_status(session: ormSession, beets_id: int, path: str) -> str | None:
    """`ISSUE_ON_AIR` ou `ISSUE_QUEUED` quand une ligne du conducteur engagée joue
    ce titre, ou s'apprête à l'envoyer ; sinon `None`."""
    same_title = or_(RundownItem.beets_id == beets_id, RundownItem.path == path)
    statuses = list(
        await session.scalars(
            select(RundownItem.status).where(
                RundownItem.status.in_(ENGAGED_STATUSES), same_title
            )
        )
    )
    if RundownStatus.ON_AIR.value in statuses:
        return ISSUE_ON_AIR
    if statuses:
        return ISSUE_QUEUED
    # Une commande écrite, dont la ligne n'a pas encore changé d'état
    # (`enqueue_command`, scheduler/outbox.py).
    sending = await session.scalar(
        select(PlayoutCommand.id)
        .join(RundownItem, PlayoutCommand.rundown_item_id == RundownItem.id)
        .where(PlayoutCommand.status.in_(_SENDING), same_title)
        .limit(1)
    )
    return ISSUE_QUEUED if sending is not None else None


@asynccontextmanager
async def _write_lock(session: ormSession) -> AsyncIterator[None]:
    """Le verrou d'écriture de la base, comme `execution._write_lock` : le
    scheduler n'engage aucune ligne tant qu'il est pris. Le moins longtemps
    possible : l'écriture d'un seul fichier."""
    await session.flush()
    try:
        await session.execute(text("BEGIN IMMEDIATE"))
        yield
    except BaseException:
        await session.rollback()
        raise
    await session.commit()


# -- l'écriture --------------------------------------------------------------------


def _write_file(plan: _Plan) -> None:
    item = plan.item
    plan.snapshot = dict(item)
    for name, value in plan.after.items():
        _set_value(item, name, value)
    if plan.touches_file:
        item.write()


def _restore_file(plan: _Plan) -> None:
    item = plan.item
    for name, value in plan.snapshot.items():
        item[name] = value
    for name in plan.after:
        if name in FLEX_FIELDS and name not in plan.snapshot and name in item:
            del item[name]
    if plan.touches_file:
        item.write()


def _store(beets: BeetsIntegration, plans: list[_Plan]) -> None:
    """Toute la bibliothèque, ou rien : une transaction de Beets valide aussi ce
    qu'elle a écrit avant une erreur, d'où le retour en arrière."""
    with beets.lib.transaction():
        try:
            for plan in plans:
                plan.item.store()
        except BaseException:
            beets.lib._connection().rollback()
            raise


async def _write_plans(
    session: ormSession, beets: BeetsIntegration, plans: list[_Plan]
) -> tuple[list[_Plan], list[tuple[_Plan, str]]]:
    """Écrit chaque titre qui n'est ni à l'antenne ni en file, puis la bibliothèque.

    Rend les titres écrits, et ceux qui attendent avec leur raison. Un fichier
    qui échoue lève `_WriteFailed` ; une autre erreur, comme une base occupée,
    passe telle quelle. Dans les deux cas, les fichiers déjà écrits, et celui
    qui a échoué, reprennent d'abord leurs tags d'avant.
    """
    loop = get_running_loop()
    written: list[_Plan] = []
    waiting: list[tuple[_Plan, str]] = []
    current: _Plan | None = None
    try:
        for plan in plans:
            current = plan
            if not plan.touches_file:
                await loop.run_in_executor(None, _write_file, plan)
                written.append(plan)
                continue
            async with _write_lock(session):
                busy = await busy_status(session, plan.beets_id, plan.path)
                if busy is None:
                    try:
                        await loop.run_in_executor(None, _write_file, plan)
                    except (FileOperationError, OSError) as exc:
                        raise _WriteFailed(plan, exc) from exc
            if busy is None:
                written.append(plan)
            else:
                waiting.append((plan, busy))
        current = None
        if written:
            try:
                await loop.run_in_executor(None, _store, beets, written)
            except Exception as exc:
                raise _WriteFailed(written[-1], exc) from exc
    except Exception:
        # le fichier qui a échoué a pu être écrit en partie
        failed = [] if current is None or current in written else [current]
        await _restore([*written, *failed])
        raise
    return written, waiting


async def _restore(written: list[_Plan]) -> None:
    """Rend leurs tags d'avant aux fichiers écrits. Sans le verrou de la base :
    elle peut être la cause de l'échec, et ces titres n'étaient pas engagés."""
    loop = get_running_loop()
    for plan in written:
        if not plan.snapshot:
            continue
        try:
            await loop.run_in_executor(None, _restore_file, plan)
        except Exception:
            _log.exception("could not restore the tags of %s", plan.path)


def _changes(plan: _Plan, status: str, reason: str | None = None) -> list:
    now = _utcnow() if status == STATUS_DONE else None
    return [
        JournalChange(
            beets_id=plan.beets_id,
            path=plan.path,
            label=plan.label,
            field=name,
            old_value=plan.before[name],
            new_value=value,
            status=status,
            reason=reason,
            applied_at=now,
        )
        for name, value in plan.after.items()
    ]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# -- l'essai : les sélections touchées ---------------------------------------------


def _selection_query(query: str) -> Query | None:
    playable = playable_query(query)
    if not isinstance(playable, str):
        return playable
    try:
        return parse_query_string(playable, Item)[0]
    except (ParsingError, InvalidQueryArgumentValueError, ValueError):
        return None


def _selection_changes(
    categories: list[tuple[int, str, str]], plans: list[_Plan]
) -> list[SelectionChange]:
    """Les sélections que le lot fait gagner ou perdre, en jouant leurs requêtes sur
    chaque titre, avant et après, comme `/autodj/testquery.json`."""
    changes = []
    for category_id, name, query_text in categories:
        query = _selection_query(query_text)
        if query is None:
            continue
        change = SelectionChange(category_id, name)
        for plan in plans:
            after = plan.item.copy()
            for field_name, value in plan.after.items():
                _set_value(after, field_name, value)
            was, will = query.match(plan.item), query.match(after)
            if will and not was:
                change.gained += 1
            elif was and not will:
                change.lost += 1
        if change.gained or change.lost:
            changes.append(change)
    return changes


# -- les gestes --------------------------------------------------------------------


def _check_edits(edits: list[TitleEdit], gesture: str) -> list[TitleEdit]:
    """Le lot vérifié, et ses valeurs nettoyées par `clean_value`. Une annulation
    remet les valeurs d'avant telles quelles, même celles qu'une personne ne
    pourrait pas écrire."""
    if gesture not in GESTURES:
        raise ValueError(gesture)
    if not edits:
        raise DomainValidationError("Choisis au moins un titre.", field="titles")
    ids = [edit.beets_id for edit in edits]
    if len(set(ids)) != len(ids):
        raise DomainValidationError(
            "Un titre paraît deux fois dans le lot.", field="titles"
        )
    if len(ids) > MAX_TITLES:
        raise DomainValidationError(
            f"Un lot prend {MAX_TITLES} titres au plus : celui-ci en a {len(ids)}.",
            field="titles",
        )
    for edit in edits:
        for name in edit.values:
            if name not in FIELDS:
                raise DomainValidationError(
                    f"Le champ {name} ne se corrige pas ici.", field=name
                )
            if gesture == GESTURE_ACCEPT and name in NEVER_ACCEPTED:
                raise DomainValidationError(
                    "Une proposition n'écrit jamais le genre.", field=name
                )
    if gesture == GESTURE_UNDO:
        return edits
    return [
        TitleEdit(
            edit.beets_id,
            {name: clean_value(name, value) for name, value in edit.values.items()},
            edit.expected,
        )
        for edit in edits
    ]


def parse_person_edits(data: Mapping[str, object]) -> list[TitleEdit]:
    """Le lot d'une personne, tel que la console l'envoie :

        {"titles": [{"id": 12, "values": {"album": "Ciel"},
                     "expected": {"album": "Estuaire"}}, …]}

    Seuls les champs qu'une personne corrige (`PERSON_FIELDS`) passent.
    """
    titles = data.get("titles")
    if not isinstance(titles, list):
        raise DomainValidationError("Choisis au moins un titre.", field="titles")
    if len(titles) > MAX_TITLES:
        raise DomainValidationError(
            f"Un lot prend {MAX_TITLES} titres au plus : celui-ci en a {len(titles)}.",
            field="titles",
        )
    edits = []
    for raw in titles:
        beets_id = raw.get("id") if isinstance(raw, dict) else None
        values = raw.get("values") if isinstance(raw, dict) else None
        expected = raw.get("expected") if isinstance(raw, dict) else None
        if (
            not isinstance(beets_id, int)
            or isinstance(beets_id, bool)
            or not isinstance(values, dict)
            or not values
            or not isinstance(expected, (dict, type(None)))
        ):
            raise DomainValidationError(
                "Chaque titre du lot dit son identifiant et ses champs.",
                field="titles",
            )
        for name in (*values, *(expected or {})):
            if name not in PERSON_FIELDS:
                raise DomainValidationError(
                    f"Le champ {name} ne se corrige pas ici.", field=str(name)
                )
        edits.append(TitleEdit(beets_id, values, expected))
    return edits


async def edit_titles(  # noqa: PLR0913
    session: ormSession,
    beets: BeetsIntegration,
    edits: list[TitleEdit],
    *,
    username: str,
    gesture: str = GESTURE_EDIT,
    undo_of: int | None = None,
    dry_run: bool = False,
) -> EditOutcome:
    """Écrit un lot de fiches, ou dit ce qu'il ferait (``dry_run``).

    Une correction
    (`GESTURE_EDIT`) refuse tout le lot quand un titre ne peut pas s'écrire ;
    l'annulation et l'acceptation laissent ce titre de côté (`kept`), et écrivent
    les autres.
    """
    await require_title_edits(session)
    edits = _check_edits(edits, gesture)
    loop = get_running_loop()
    plans, unchanged, issues = await loop.run_in_executor(
        None, _plan_titles, beets, edits
    )
    outcome = EditOutcome(unchanged=unchanged)
    strict = gesture == GESTURE_EDIT
    if strict:
        outcome.refused = issues
    else:
        outcome.kept = issues

    if dry_run:
        return await _try(session, plans, outcome)

    if strict and issues:
        count = len(issues)
        raise TitlesRefused(
            "Rien n'a été écrit : "
            + (
                "un titre ne peut pas l'être."
                if count == 1
                else f"{count} titres ne peuvent pas l'être."
            ),
            issues,
        )
    if not plans and not outcome.kept:
        return outcome

    entry = JournalEntry(
        gesture=gesture,
        username=username,
        titles=len(plans),
        undo_of=undo_of,
        details={"fields": sorted({name for plan in plans for name in plan.after})},
    )
    for plan in plans:
        entry.changes.extend(_changes(plan, STATUS_PENDING))
    for issue in outcome.kept:
        entry.changes.extend(_kept_changes(edits, issue))
    session.add(entry)
    await session.commit()

    try:
        written, waiting = await _write_plans(session, beets, plans)
    except _WriteFailed as failure:
        await _forget(session, entry)
        issue = TitleIssue(failure.plan.beets_id, failure.plan.label, ISSUE_FAILED)
        _log.warning("title edit failed on %s: %s", failure.plan.path, failure.cause)
        raise TitlesRefused(
            f"Rien n'a été écrit : le fichier de « {issue.label} » n'a pas pu "
            "l'être. Les fichiers déjà écrits ont repris leurs tags d'avant.",
            [issue],
        ) from failure
    except Exception:
        await _forget(session, entry)
        raise

    done = {plan.beets_id for plan in written}
    busy = {plan.beets_id: reason for plan, reason in waiting}
    _settle(entry, done, busy)
    await session.commit()

    outcome.entry_id = entry.id
    outcome.written = sorted(done)
    outcome.waiting = [
        TitleIssue(plan.beets_id, plan.label, reason) for plan, reason in waiting
    ]
    return outcome


async def _forget(session: ormSession, entry: JournalEntry) -> None:
    """Un lot qui n'a rien écrit ne reste pas au journal."""
    try:
        await session.rollback()
        await session.delete(entry)
        await session.commit()
    except Exception:
        _log.exception("could not drop the journal entry %s", entry.id)


async def _try(
    session: ormSession, plans: list[_Plan], outcome: EditOutcome
) -> EditOutcome:
    """L'essai : ce que le lot écrirait, ce qui attendrait, et les sélections qu'il
    toucherait. Rien ne s'écrit."""
    for plan in plans:
        busy = await busy_status(session, plan.beets_id, plan.path)
        if busy is not None and plan.touches_file:
            outcome.waiting.append(TitleIssue(plan.beets_id, plan.label, busy))
    categories = [
        (category.id, category.name, category.query)
        for category in await MusicCategory.all(session)
    ]
    loop = get_running_loop()
    outcome.selections = await loop.run_in_executor(
        None, _selection_changes, categories, plans
    )
    outcome.written = [plan.beets_id for plan in plans]
    return outcome


def _settle(entry: JournalEntry, done: set[int], busy: dict[int, str]) -> None:
    now = _utcnow()
    for change in entry.changes:
        if change.status != STATUS_PENDING:
            continue
        if change.beets_id in done:
            change.status = STATUS_DONE
            change.applied_at = now
        else:
            change.status = STATUS_WAITING
            change.reason = ISSUE_MESSAGES[busy[change.beets_id]]


def _kept_changes(edits: list[TitleEdit], issue: TitleIssue) -> list[JournalChange]:
    """Ce qu'un titre laissé de côté n'a pas reçu, pour que le journal le dise."""
    edit = next(edit for edit in edits if edit.beets_id == issue.beets_id)
    expected = edit.expected or {}
    return [
        JournalChange(
            beets_id=issue.beets_id,
            label=issue.label,
            field=name,
            old_value=expected.get(name),
            new_value=value,
            status=STATUS_KEPT,
            reason=issue.reason,
        )
        for name, value in edit.values.items()
    ]


async def undo_entry(
    session: ormSession,
    beets: BeetsIntegration,
    entry_id: int,
    *,
    username: str,
) -> EditOutcome:
    """« Revenir » : remet la valeur d'avant de chaque champ écrit par un lot, tant
    que personne ne l'a changée depuis. Un titre changé depuis garde sa valeur, et
    l'annulation le dit. Ce qui attendait encore ne s'écrira pas."""
    await require_title_edits(session)
    entry = await JournalEntry.from_id(session, entry_id)
    if entry is None:
        raise DomainNotFound("Ce geste n'est pas au journal.")
    if entry.gesture not in GESTURES:
        raise DomainValidationError("Ce geste ne s'annule pas encore.")
    undone = await session.scalar(
        select(JournalEntry.id).where(JournalEntry.undo_of == entry.id).limit(1)
    )
    if undone is not None:
        raise DomainConflict("Ce lot a déjà été défait.")
    changes = list(
        await session.scalars(
            select(JournalChange)
            .where(JournalChange.entry_id == entry.id)
            .order_by(JournalChange.id)
        )
    )
    values: dict[int, dict[str, object]] = defaultdict(dict)
    expected: dict[int, dict[str, object]] = defaultdict(dict)
    cancelled = 0
    for change in changes:
        if change.status == STATUS_WAITING:
            change.status = STATUS_CANCELLED
            change.reason = "Défaite avant d'avoir été écrite."
            cancelled += 1
        elif change.status == STATUS_DONE and change.beets_id is not None:
            values[change.beets_id][change.field] = change.old_value
            expected[change.beets_id][change.field] = change.new_value
    await session.commit()
    edits = [
        TitleEdit(beets_id, values[beets_id], expected[beets_id]) for beets_id in values
    ]
    if not edits:
        # Rien n'avait été écrit : le lot attendait encore.
        entry_undo = JournalEntry(
            gesture=GESTURE_UNDO,
            username=username,
            titles=0,
            undo_of=entry.id,
            details={"fields": [], "cancelled": cancelled},
        )
        session.add(entry_undo)
        await session.commit()
        return EditOutcome(entry_id=entry_undo.id)
    return await edit_titles(
        session,
        beets,
        edits,
        username=username,
        gesture=GESTURE_UNDO,
        undo_of=entry.id,
    )


# -- ce qui attend -----------------------------------------------------------------


async def apply_waiting(session: ormSession, beets: BeetsIntegration) -> int:
    """Écrit les fiches qui attendaient la fin d'un passage à l'antenne. Rend le
    nombre de titres écrits.

    Un titre dont la fiche a changé depuis la demande garde sa valeur : sa
    demande passe `kept`. Les deux interrupteurs coupés, rien ne s'écrit.
    """
    if not await title_edits_enabled(session):
        return 0
    await _settle_pending(session, beets)
    rows = list(
        await session.scalars(
            select(JournalChange)
            .where(JournalChange.status == STATUS_WAITING)
            .order_by(JournalChange.id)
        )
    )
    groups: dict[tuple[int, int], list[JournalChange]] = defaultdict(list)
    for row in rows:
        if row.beets_id is not None:
            groups[(row.entry_id, row.beets_id)].append(row)
    count = 0
    for (_entry_id, beets_id), group in groups.items():
        if await _apply_group(session, beets, beets_id, group):
            count += 1
    return count


def _close(group: list[JournalChange], status: str, reason: str | None) -> None:
    now = _utcnow() if status == STATUS_DONE else None
    for row in group:
        row.status = status
        row.reason = reason
        row.applied_at = now


async def _apply_group(
    session: ormSession,
    beets: BeetsIntegration,
    beets_id: int,
    group: list[JournalChange],
) -> bool:
    """Les champs d'un titre qui attendaient, écrits ensemble. Vrai s'il l'a été."""
    edit = TitleEdit(
        beets_id,
        {row.field: row.new_value for row in group},
        {row.field: row.old_value for row in group},
    )
    loop = get_running_loop()
    plans, unchanged, issues = await loop.run_in_executor(
        None, _plan_titles, beets, [edit]
    )
    if issues or unchanged:
        if issues:
            _close(group, STATUS_KEPT, issues[0].reason)
        else:
            _close(group, STATUS_DONE, None)
        await session.commit()
        return False
    # « Revenir » a pu l'annuler pendant qu'on la préparait
    statuses = await session.scalars(
        select(JournalChange.status).where(
            JournalChange.id.in_([row.id for row in group])
        )
    )
    if any(status != STATUS_WAITING for status in statuses):
        return False
    try:
        written, _waiting = await _write_plans(session, beets, plans)
    except _WriteFailed as failure:
        _log.warning(
            "waiting title edit failed on %s: %s", failure.plan.path, failure.cause
        )
        _close(group, STATUS_FAILED, ISSUE_MESSAGES[ISSUE_FAILED])
        await session.commit()
        return False
    if not written:
        return False
    _close(group, STATUS_DONE, None)
    await session.commit()
    return True


async def _settle_pending(session: ormSession, beets: BeetsIntegration) -> None:
    """Une écriture qu'un arrêt du moteur a laissée en route : faite si la
    bibliothèque porte la nouvelle valeur, ratée sinon."""
    limit = _utcnow() - PENDING_GRACE
    rows = list(
        await session.scalars(
            select(JournalChange)
            .join(JournalEntry, JournalChange.entry_id == JournalEntry.id)
            .where(JournalChange.status == STATUS_PENDING, JournalEntry.created < limit)
        )
    )
    if not rows:
        return
    loop = get_running_loop()
    for row in rows:
        item = (
            await loop.run_in_executor(None, beets.lib.get_item, row.beets_id)
            if row.beets_id is not None
            else None
        )
        if item is not None and current_value(item, row.field) == row.new_value:
            row.status = STATUS_DONE
        else:
            row.status = STATUS_FAILED
            row.reason = "Écriture interrompue par un arrêt du moteur."
    await session.commit()


async def has_waiting(session: ormSession) -> bool:
    """Une fiche attend-elle, ou une écriture est-elle restée en route ?"""
    row = await session.scalar(
        select(JournalChange.id)
        .where(JournalChange.status.in_((STATUS_WAITING, STATUS_PENDING)))
        .limit(1)
    )
    return row is not None
