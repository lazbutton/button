#!/usr/bin/env python3
"""Écrit les rôles des comptes pour le volume Finder. Aucun mot de passe.

Tourne dans radiotomate-dropbox, qui a déjà la base. Le fichier va dans
SHARE_PRIVATE. S'il n'est pas monté, on ne fait rien.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def role_of(perms: dict | None) -> str:
    flags = perms or {}
    if flags.get("admin"):
        return "admin"
    if flags.get("carts") or flags.get("autodj"):
        return "programmateur"
    return "animateur"


def write_roles(rows: list[dict], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"users": rows}, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(dest)


async def load_rows() -> list[dict]:
    from radiotomate.commands import load_config
    from radiotomate.db import QuartAlchemy
    from radiotomate.models import User

    config = load_config(Path(os.environ.get("RTCONFIG", "/data/radiotomate.yaml")))
    db = QuartAlchemy()
    db.init_from_config(config["db"], {})
    async with db.session() as session:
        users = await User.all(session)
        return [
            {"username": user.username, "role": role_of(dict(user.permissions or {}))}
            for user in users
        ]


def main() -> int:
    dest = Path(os.environ.get("SHARE_PRIVATE", "/share-private"))
    if not dest.is_dir():
        return 0
    try:
        rows = asyncio.run(load_rows())
    except Exception as exc:
        print(f"rôles du dossier : {exc}", file=sys.stderr)
        return 1
    write_roles(rows, dest / "roles.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
