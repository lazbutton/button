"""La santé de la banque (FON-72) : ce qui cloche, compté par nature. Sans Quart.

Le calcul lit les lignes du tableau (`BeetsIntegration.title_rows`, FON-64) et le
disque de la rotation et des collections, puis compte :

- les artistes écrits de plusieurs façons : le même nom une fois les accents, la
  casse, la ponctuation et les espaces retirés (`squash`, `fiches/normalize.py`) ;
- les doublons : le même artiste et le même titre normalisés, et une durée à 2 s
  près ;
- les fichiers mal nommés, d'après un modèle de FON-68 (`bank_names.py`) ;
- les fiches incomplètes, champ par champ (`FICHE_FIELDS`) ;
- le genre « Archive » que posait l'ancienne boucle d'import (FON-77) ;
- les fichiers audio de la banque que la bibliothèque n'a pas.

Il n'écrit rien. La console ouvre la correction de chaque ligne : la fiche d'un lot
(FON-66), le renommage (FON-68), ou le tableau rangé sur le champ vide.

Derrière l'interrupteur général du chantier, `features.bank_tidy`, et le sien,
`features.bank_health`, allumé quand il manque.
"""

from __future__ import annotations

import os
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from radiotomate.domain.errors import DomainError, DomainValidationError
from radiotomate.fiches.normalize import normalize_text, squash
from radiotomate.models import Setting
from radiotomate.services.bank_names import MODELS, renamed
from radiotomate.services.bank_titles import (
    FICHE_FIELDS,
    bank_tidy_enabled,
    facet_counts,
    fold,
    title_of,
)
from radiotomate.services.media_bank import (
    AUDIO_SUFFIXES,
    COLLECTIONS_TOP,
    ROTATION_TOP,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session as ormSession

SETTING_HEALTH = "features.bank_health"
SETTING_OFF = {"0", "false", "off", "no", "non"}
DEFAULT_MODEL = "artiste-titre"
# Deux titres dont les durées s'écartent de plus ne sont pas le même enregistrement.
DUPLICATE_SECONDS = 2.0
# Ce qu'un lot prend : la correction d'une fiche (FON-66), le renommage (FON-68).
MAX_TITLES = 500
# Les groupes et les fichiers listés ; les comptes, eux, prennent tout.
MAX_LISTED = 200
ARCHIVE = "archive"
INDEXED_ZONES = ("rotation", "collections")


class BankHealthOff(DomainError):  # noqa: N818
    status_code = 409
    code = "bank_health_off"


async def health_on(session: ormSession) -> bool:
    """The general switch of the bank's tidying, and this view's own, on when absent."""
    if not await bank_tidy_enabled(session):
        return False
    row = await Setting.from_key(session, SETTING_HEALTH)
    return row is None or str(row.value).strip().lower() not in SETTING_OFF


async def require_health(session: ormSession) -> None:
    if not await health_on(session):
        raise BankHealthOff(
            "La santé de la banque n'est pas ouverte sur cette station."
        )


def check_model(raw: object) -> str:
    model = str(raw or DEFAULT_MODEL)
    if model not in MODELS:
        raise DomainValidationError(f"Modèle inconnu : {model}.", field="model")
    return model


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _listed(entries: list[dict], limit: int = MAX_TITLES) -> list[dict]:
    return entries[:limit]


def _by_name(entry: dict) -> tuple:
    return fold(entry["artist"]), fold(entry["title"]), entry["path"]


def figures(entries: list[dict]) -> dict:
    """« La banque en chiffres » : the titles, the families, the complete fiches."""
    families = [row for row in facet_counts(entries, "famille") if row["value"]]
    families.sort(key=lambda row: (-row["count"], fold(row["label"])))
    return {
        "titles": len(entries),
        "complete": sum(1 for entry in entries if not entry["missing"]),
        "families": families,
        "without_family": sum(1 for entry in entries if not entry["famille"]),
    }


def spellings(entries: list[dict]) -> dict:
    """The artists written in several ways: one name, once squashed.

    The suggested spelling is the most frequent one; on a tie, the one with the
    most accents and capitals, which a hand rarely adds by mistake.
    """
    by_key: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        key = squash(entry["artist"]) if entry["artist"] else ""
        if key:
            by_key[key].append(entry)
    groups = []
    for key, members in by_key.items():
        counts = Counter(entry["artist"] for entry in members)
        if len(counts) < 2:
            continue
        ranked = sorted(
            counts.items(),
            key=lambda item: (-item[1], -_marks(item[0]), fold(item[0]), item[0]),
        )
        groups.append(
            {
                "key": key,
                "spellings": [{"value": value, "count": n} for value, n in ranked],
                "suggested": ranked[0][0],
                "count": len(members),
                "titles": _listed(sorted(members, key=_by_name)),
            }
        )
    groups.sort(key=lambda group: (-group["count"], group["key"]))
    return {
        "count": len(groups),
        "titles": sum(group["count"] for group in groups),
        "groups": groups[:MAX_LISTED],
    }


def _marks(text: str) -> int:
    """Accents and capitals: « Les Marées Hautes » outranks « les marees hautes »."""
    plain = unicodedata.normalize("NFD", text)
    return sum(1 for char in plain if unicodedata.combining(char) or char.isupper())


def duplicate_groups(entries: list[dict]) -> list[list[dict]]:
    """The same artist and title once normalized, lasting the same within 2 s.

    A title without a duration, or without an artist or a title, is no one's
    duplicate: nothing tells it apart from a different take.
    """
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in entries:
        artist, title = normalize_text(entry["artist"]), normalize_text(entry["title"])
        if artist and title and entry["duration"]:
            by_key[(artist, title)].append(entry)
    groups = []
    for members in by_key.values():
        members.sort(key=lambda entry: (entry["duration"], entry["path"]))
        cluster = [members[0]]
        for entry in members[1:]:
            if entry["duration"] - cluster[-1]["duration"] <= DUPLICATE_SECONDS:
                cluster.append(entry)
                continue
            if len(cluster) > 1:
                groups.append(cluster)
            cluster = [entry]
        if len(cluster) > 1:
            groups.append(cluster)
    return groups


def duplicates(entries: list[dict]) -> dict:
    """The duplicates of the bank, by group (`duplicate_groups`)."""
    groups = duplicate_groups(entries)
    payload = [
        {
            "label": f"{group[0]['artist']} - {group[0]['title']}",
            "titles": sorted(group, key=lambda entry: entry["path"]),
        }
        for group in groups
    ]
    payload.sort(key=lambda group: fold(group["label"]))
    return {
        "count": len(payload),
        "titles": sum(len(group["titles"]) for group in payload),
        "groups": payload[:MAX_LISTED],
    }


def misnamed(entries: list[dict], model: str) -> dict:
    """The files of the rotation and the collections not named after their fiche.

    In their own folder: the artist's folder is an option of the renaming, not
    a fault. A fiche the model cannot name is counted with the incomplete ones.
    """
    found = []
    for entry in entries:
        if entry["zone"] not in INDEXED_ZONES:
            continue
        target, _why = renamed(entry["path"], entry, model)
        if target is None:
            continue
        name = PurePosixPath(target).name
        if _nfc(name) != _nfc(PurePosixPath(entry["path"]).name):
            found.append({**entry, "to": name})
    found.sort(key=_by_name)
    return {"count": len(found), "titles": _listed(found)}


def incomplete(entries: list[dict]) -> dict:
    """The fiches with an empty field, counted field by field."""
    return {
        "count": sum(1 for entry in entries if entry["missing"]),
        "fields": [
            {
                "field": name,
                "count": sum(1 for entry in entries if name in entry["missing"]),
            }
            for name in FICHE_FIELDS
        ],
    }


def _genres(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def archive(entries: list[dict]) -> dict:
    """The titles whose genre says « Archive », written by the old loop (FON-77).

    Each one says the genre it keeps once « Archive » is taken out: the others
    stay, as a person would leave them.
    """
    found = []
    for entry in entries:
        genres = _genres(entry["genre"])
        if any(fold(genre) == ARCHIVE for genre in genres):
            kept = [genre for genre in genres if fold(genre) != ARCHIVE]
            found.append({**entry, "genre_without": ", ".join(kept)})
    found.sort(key=_by_name)
    return {"count": len(found), "titles": _listed(found)}


def bank_files(root: Path) -> Iterable[str]:
    """The audio files of the rotation and the collections, below the bank.

    Hidden files and folders are left out, as the import loop leaves them: a
    copy in progress (`.partial`), a system's file.
    """
    tops = [root / ROTATION_TOP]
    collections = root / COLLECTIONS_TOP
    if collections.is_dir():
        tops += [
            path
            for path in sorted(collections.iterdir())
            if path.is_dir() and not path.name.startswith(".")
        ]
    for top in tops:
        if not top.is_dir():
            continue
        for folder, dirs, files in os.walk(top):
            dirs[:] = sorted(name for name in dirs if not name.startswith("."))
            for name in sorted(files):
                if name.startswith("."):
                    continue
                if Path(name).suffix.lower() not in AUDIO_SUFFIXES:
                    continue
                yield Path(folder, name).relative_to(root).as_posix()


def unindexed(entries: list[dict], root: Path) -> dict:
    """The audio files of the bank that the library does not have.

    A file just dropped waits a minute for the import loop; one that stays here
    is one the loop cannot read, or skips.
    """
    known = {_nfc(entry["path"]) for entry in entries}
    found = [rel for rel in bank_files(root) if _nfc(rel) not in known]
    return {"count": len(found), "paths": found[:MAX_LISTED]}


def bank_health(rows: Iterable[tuple], root: Path, model: str = DEFAULT_MODEL) -> dict:
    """Everything the Santé view shows, from the library's rows and the disk."""
    entries = [title_of(row, str(root)) for row in rows]
    return {
        "model": model,
        "figures": figures(entries),
        "spellings": spellings(entries),
        "duplicates": duplicates(entries),
        "misnamed": misnamed(entries, model),
        "incomplete": incomplete(entries),
        "archive": archive(entries),
        "unindexed": unindexed(entries, root),
    }
