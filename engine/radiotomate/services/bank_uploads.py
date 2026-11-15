"""Ce que la banque sait d'un fichier envoyé (FON-82). Sans Quart.

Tranché avec l'utilisateur le 15 novembre 2026 : un doublon envoyé se range comme
les autres fichiers, et se signale, dans la file d'envoi de la vue Ajouter et dans
Arrivées (FON-81). Un fichier ne se perd jamais : rien ici n'écrit, ne déplace ni
ne refuse.

La console nomme chaque fichier par sa destination, la rotation ou une collection,
et le nom qu'il avait en partant. `promote-inbox.sh` le range sous le même nom, à
l'extension près : un wav devient un flac, et une station qui diffuse en mp3 ou en
opus convertit tout. Il se retrouve donc par son dossier et le nom sans extension.

Pour chacun :

- s'il est dans la bibliothèque, une fois promu et indexé par la boucle d'import ;
- ses doublons, lus comme la santé de la banque les lit (`duplicate_groups`, FON-72) :
  le même artiste et le même titre normalisés, et une durée à 2 s près ;
- ce que la recherche des fiches en a reconnu (FON-25), qui cherche un titre nouveau
  avant le reste : l'artiste et le titre trouvés, et le niveau.
"""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from radiotomate.domain.errors import DomainValidationError
from radiotomate.fiches.evidence import from_json
from radiotomate.fiches.proposals import Track, build_row
from radiotomate.models.fiche import Fiche
from radiotomate.services.bank_health import duplicate_groups, duplicate_key
from radiotomate.services.bank_titles import ROTATION
from radiotomate.services.media_bank import COLLECTIONS_TOP, ROTATION_TOP

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session as ormSession

# Les fichiers d'une demande : ceux d'un envoi, que la console suit à la fois.
MAX_FILES = 100
# Ce que la recherche a trouvé, et qui se dit « reconnu ».
RECOGNIZED = ("trouvé", "rapproché")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _plain(name: object, what: str) -> str:
    """Un nom de dossier ou de fichier, seul : ni chemin, ni nom caché."""
    text = _nfc(str(name or "")).strip()
    if (
        not text
        or text in {".", ".."}
        or text.startswith(".")
        or any(char in text for char in "/\\\x00")
    ):
        raise DomainValidationError(f"{what} illisible : {str(name)[:80]!r}.")
    return text


def read_files(data: object) -> list[tuple[str, str]]:
    """Les fichiers demandés, `{files: [{dest, name}]}`, vérifiés."""
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        raise DomainValidationError("La liste des fichiers manque.", field="files")
    if len(files) > MAX_FILES:
        raise DomainValidationError(
            f"{MAX_FILES} fichiers au plus par demande.", field="files"
        )
    out = []
    for one in files:
        if not isinstance(one, dict):
            raise DomainValidationError("Un fichier illisible.", field="files")
        out.append(
            (_plain(one.get("dest"), "Destination"), _plain(one.get("name"), "Nom"))
        )
    return out


def folder_of(dest: str) -> str:
    """Le dossier de la banque d'une destination de la vue Ajouter."""
    if dest == ROTATION:
        return ROTATION_TOP
    return f"{COLLECTIONS_TOP}/{dest}"


def _spot(path: str) -> tuple[str, str]:
    """Le dossier d'un titre et son nom sans extension."""
    pure = PurePosixPath(_nfc(path))
    return str(pure.parent), pure.stem


def _brief(entry: dict) -> dict:
    return {
        "id": entry["id"],
        "artist": entry["artist"],
        "title": entry["title"],
        "path": entry["path"],
        "zone": entry["zone"],
        "collection": entry["collection"],
    }


def _track(entry: dict) -> Track:
    return Track(
        title=entry["title"] or "",
        artist=entry["artist"] or "",
        album=entry["album"] or "",
        year=entry["year"] or 0,
        length=entry["duration"],
    )


def _recognized(fiche: Any, entry: dict) -> dict | None:
    """Ce que la recherche a reconnu d'un titre : le morceau qu'elle a trouvé."""
    if fiche is None or fiche.status not in RECOGNIZED or not fiche.evidence:
        return None
    result, wikidata = from_json(fiche.evidence)
    if result.match is None:
        return None
    row = build_row(_track(entry), result, wikidata)
    return {
        "artist": row.found_artists,
        "title": row.found_title,
        "level": fiche.level,
        "source": fiche.source,
    }


async def uploads_report(
    session: ormSession,
    entries: Iterable[dict],
    files: list[tuple[str, str]],
    *,
    fiches_on: bool,
) -> dict:
    """Ce que la banque sait de chaque fichier envoyé.

    `entries` : les titres de la bibliothèque, comme le tableau les lit
    (`title_of`). `fiches_on` : la recherche des fiches est allumée ; éteinte, rien
    ne sera reconnu, et la console n'attend pas.
    """
    entries = list(entries)
    by_spot: dict[tuple[str, str], dict] = {}
    for entry in entries:
        by_spot.setdefault(_spot(entry["path"]), entry)
    found = {
        (dest, name): by_spot.get((folder_of(dest), PurePosixPath(name).stem))
        for dest, name in files
    }
    # Les doublons d'un titre ne dépendent que des titres de sa clé.
    keys = {duplicate_key(entry) for entry in found.values() if entry}
    keys.discard(None)
    near = [entry for entry in entries if duplicate_key(entry) in keys]
    groups = duplicate_groups(near)
    others: dict[int, list[dict]] = {}
    for group in groups:
        for entry in group:
            others[entry["id"]] = [one for one in group if one["id"] != entry["id"]]
    ids = [entry["id"] for entry in found.values() if entry]
    fiches = {}
    if ids:
        rows = await session.scalars(select(Fiche).where(Fiche.beets_id.in_(ids)))
        fiches = {fiche.beets_id: fiche for fiche in rows}
    report = []
    for dest, name in files:
        entry = found[(dest, name)]
        if entry is None:
            report.append(
                {
                    "dest": dest,
                    "name": name,
                    "in_bank": False,
                    "id": None,
                    "path": None,
                    "duplicates": [],
                    "recognized": None,
                    "searched": False,
                }
            )
            continue
        fiche = fiches.get(entry["id"])
        twins = sorted(others.get(entry["id"], []), key=lambda one: one["path"])
        report.append(
            {
                "dest": dest,
                "name": name,
                "in_bank": True,
                "id": entry["id"],
                "path": entry["path"],
                "artist": entry["artist"],
                "title": entry["title"],
                "duplicates": [_brief(one) for one in twins],
                "recognized": _recognized(fiche, entry),
                "searched": fiche is not None,
            }
        )
    return {"fiches": fiches_on, "files": report}
