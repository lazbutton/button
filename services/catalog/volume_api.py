"""Mot de passe du dossier Finder et droit de créer une banque.

Le catalogue dépose le mot de passe dans SHARE_PRIVATE. Il ne le garde pas.
"""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")


def share_name(raw: str) -> str:
    """Même règle que refresh_volume.share_name : le nom annoncé par /volume.json."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (raw or "").strip()).strip(".-")
    return cleaned[:32] or "BUTTON"


def username_ok(name: str) -> bool:
    return bool(USERNAME.fullmatch(name or ""))


def finder_role(perms: dict | None) -> str:
    flags = perms or {}
    if flags.get("admin"):
        return "admin"
    if flags.get("carts") or flags.get("autodj"):
        return "programmateur"
    return "animateur"


def password_problem(password: str) -> str | None:
    if "\n" in password or "\r" in password or "\x00" in password:
        return "Mot de passe refusé."
    if len(password) < 8:
        return "Mot de passe trop court : 8 caractères au moins."
    if len(password) > 128:
        return "Mot de passe trop long."
    return None


def published(host: str, root: Path) -> bool:
    return bool((host or "").strip()) and root.is_dir()


def open_share_private(root: Path) -> str | None:
    """Ouvre SHARE_PRIVATE à la boucle Beets, comme /tmp. Rend un avertissement, ou None.

    Docker crée ce volume au nom de root, et la boucle Beets du moteur, qui y
    écrit roles.json, ne tourne pas en root. En 1777, comme le laisse aussi le
    service share : elle y ajoute ses fichiers, mais ne peut ni retirer ni
    déplacer ceux de root, où passent les mots de passe. Propriétaire du
    volume, elle le pourrait.
    """
    if not root.is_dir():
        return None
    try:
        if stat.S_IMODE(root.stat().st_mode) != 0o1777:
            os.chmod(root, 0o1777)
    except OSError as exc:
        return (
            f"Attention : {root} n'a pas pu être ouvert à la boucle Beets : {exc}. "
            "Les rôles des comptes n'arriveront pas au dossier partagé : voir "
            "docs/exploitation/dossier-reseau.md, « Si les rôles n'arrivent pas au dossier »."
        )
    return None


def queue_password(root: Path, username: str, password: str | None) -> None:
    """password None efface l'accès. Le fichier est lisible par root seulement."""
    pending = root / "pending"
    pending.mkdir(mode=0o700, exist_ok=True)
    os.chmod(pending, 0o700)
    if password is None:
        payload: dict = {"username": username, "action": "clear"}
    else:
        payload = {"username": username, "action": "set", "password": password}
    target = pending / f"{username}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(target)
    os.chmod(target, 0o600)
