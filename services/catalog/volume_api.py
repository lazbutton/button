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
# Les dossiers de root dans SHARE_PRIVATE : les mots de passe en attente, et la
# base de Samba, le private dir du service share.
PRIVATE_DIRS = ("pending", "samba")
PRIVATE_DIRS_DOC = "docs/exploitation/dossier-reseau.md, « Si pending/ ou samba/ n'est pas à root »"


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


def claim_dir(path: Path) -> str | None:
    """Crée ce dossier de SHARE_PRIVATE à root, en 700, ou le reprend. Rend ce qui en empêche l'usage, ou None.

    Ouvert comme /tmp, le volume laisse la boucle Beets y créer pending/ ou
    samba/ avant root, ou y poser un lien. Root ne suit pas un lien et ne
    retire rien. Il reprend un dossier qui n'est pas à lui : chown, puis 700.
    Mais ce qu'un autre y a laissé reste à l'autre, et pourrait lui servir à
    lire ce que root y écrit : tant qu'il en reste, le dossier ne sert pas.

    Même code que claim_dir dans deploy/share/apply_share.py : test_share.py
    vérifie qu'ils s'accordent.
    """
    uid, gid = os.geteuid(), os.getegid()
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return f"{path} n'est pas un dossier : un lien ou un fichier porte son nom."
    try:
        found = os.fstat(fd)
        if (found.st_uid, found.st_gid) != (uid, gid):
            os.fchown(fd, uid, gid)
        if stat.S_IMODE(found.st_mode) != 0o700:
            os.fchmod(fd, 0o700)
        # À root, dans un volume à root avec le sticky bit, il ne bouge plus.
        # Avant, son propriétaire a pu le remplacer.
        now = os.lstat(path)
        if (now.st_dev, now.st_ino) != (found.st_dev, found.st_ino):
            return f"{path} a été remplacé pendant que root le reprenait."
        with os.scandir(fd) as entries:
            strangers = sorted(entry.name for entry in entries if entry.stat(follow_symlinks=False).st_uid != uid)
    except OSError as exc:
        return f"{path} n'a pas pu être repris par root : {exc}."
    finally:
        os.close(fd)
    if strangers:
        names = ", ".join(strangers[:5]) + ("…" if len(strangers) > 5 else "")
        return f"{path} contient des fichiers qui ne sont pas à root : {names}."
    return None


def open_share_private(root: Path) -> str | None:
    """Ouvre SHARE_PRIVATE à la boucle Beets, comme /tmp. Rend un avertissement, ou None.

    Docker crée ce volume au nom de root, et la boucle Beets du moteur, qui y
    écrit roles.json, ne tourne pas en root. En 1777, comme le laisse aussi le
    service share : elle y ajoute ses fichiers, mais ne peut ni retirer ni
    déplacer ceux de root, où passent les mots de passe. Propriétaire du
    volume, elle le pourrait : root le reprend s'il n'est plus à lui. Avant
    de l'ouvrir, il y prend aussi pending/ et samba/ : sinon, la boucle
    pourrait les créer la première.
    """
    if not root.is_dir():
        return None
    warnings = []
    try:
        found = root.stat()
        if (found.st_uid, found.st_gid) != (os.geteuid(), os.getegid()):
            os.chown(root, os.geteuid(), os.getegid())
        for name in PRIVATE_DIRS:
            problem = claim_dir(root / name)
            if problem:
                warnings.append(
                    f"Attention : {problem} Ni le catalogue ni le service share ne s'en servent : "
                    f"voir {PRIVATE_DIRS_DOC}."
                )
        if stat.S_IMODE(found.st_mode) != 0o1777:
            os.chmod(root, 0o1777)
    except OSError as exc:
        warnings.append(
            f"Attention : {root} n'a pas pu être ouvert à la boucle Beets : {exc}. "
            "Les rôles des comptes n'arriveront pas au dossier partagé : voir "
            "docs/exploitation/dossier-reseau.md, « Si les rôles n'arrivent pas au dossier »."
        )
    return " ".join(warnings) or None


def queue_password(root: Path, username: str, password: str | None) -> str | None:
    """password None efface l'accès. Le fichier est lisible par root seulement.

    Rend None, ou pourquoi rien n'a été déposé : pending/ n'est pas à root.
    """
    pending = root / "pending"
    problem = claim_dir(pending)
    if problem:
        return f"Rien n'est enregistré : {problem} Voir {PRIVATE_DIRS_DOC}."
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
    return None
