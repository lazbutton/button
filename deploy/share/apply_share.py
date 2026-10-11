#!/usr/bin/env python3
"""Comptes du volume Finder : groupes, mots de passe Samba, dossiers verrouillés.

Tourne dans le conteneur share, en root. Les mots de passe arrivent dans
SHARE_PRIVATE, jamais sur la médiathèque. La vue (.volume) reste en lecture
pour le partage : on ne peut pas y créer un dossier. Les fichiers se déposent
dans les dossiers réels, qui sont inscriptibles.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import refresh_volume

DEPOSER_GID = 2050
ORGANISER_GID = 2051
SHARE_UID = 2052
USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
EMISSION_KEEP = {"entiere", "podcasts"}
HABILLAGE_SLUGS = [slug for slug, _title in refresh_volume.HABILLAGE]


def share_name(raw: str) -> str:
    return refresh_volume.share_name(raw)


def bind_ok(bind: str, allow_public: bool) -> bool:
    """0.0.0.0 et :: n'écoutent que si la station l'a demandé explicitement."""
    value = (bind or "").strip()
    if value in {"", "0.0.0.0", "::", "*"}:
        return bool(allow_public) and value in {"0.0.0.0", "::", "*"}
    return True


def account_plan(roles: dict[str, str], pending: dict[str, dict]) -> dict:
    """Qui a le dossier, et quel mot de passe appliquer.

    enable : compte à garder, avec ses groupes, et un mot de passe s'il vient d'être posé.
    disable : compte à retirer (animateur, effacement, ou identifiant disparu).
    """
    enable: dict[str, dict] = {}
    disable: list[str] = []
    for username, role in roles.items():
        if not USERNAME.fullmatch(username):
            continue
        if role == "admin":
            enable[username] = {"groups": ["deposer", "organiser"]}
        elif role == "programmateur":
            enable[username] = {"groups": ["deposer"]}
        else:
            disable.append(username)
    for username, item in pending.items():
        if not USERNAME.fullmatch(username):
            continue
        action = item.get("action") if isinstance(item, dict) else None
        if username not in enable or action == "clear":
            enable.pop(username, None)
            disable.append(username)
            continue
        if action == "set" and isinstance(item.get("password"), str):
            enable[username]["password"] = item["password"]
    return {"enable": enable, "disable": sorted(set(disable))}


def smb_conf(station: str) -> str:
    name = share_name(station)
    return f"""[global]
   workgroup = WORKGROUP
   server role = standalone server
   security = user
   map to guest = never
   server min protocol = SMB2
   smb ports = 445
   disable netbios = yes
   unix charset = UTF-8
   dos charset = CP850
   unix extensions = no
   allow insecure wide links = yes
   load printers = no
   printing = bsd
   printcap name = /dev/null
   disable spoolss = yes
   mangled names = no
   ea support = yes
   vfs objects = fruit streams_xattr
   fruit:metadata = stream
   fruit:model = MacSamba
   fruit:posix_rename = yes
   fruit:veto_appledouble = no
   fruit:wipe_intentionally_left_blank_rfork = yes
   fruit:delete_empty_adfiles = yes
   private dir = /share-private/samba
   passdb backend = tdbsam:/share-private/samba/passdb.tdb

[{name}]
   path = /media/.volume
   comment = Mediatheque
   browseable = yes
   read only = no
   guest ok = no
   valid users = @deposer
   write list = @deposer
   force user = sharewrite
   force group = deposer
   create mask = 0666
   force create mode = 0666
   directory mask = 0777
   force directory mode = 0777
   follow symlinks = yes
   wide links = yes
   veto files = /.*/
"""


def write_smb_conf() -> None:
    text = smb_conf(os.environ.get("STATION_NAME", "BUTTON"))
    path = Path("/etc/samba/smb.conf")
    path.write_text(text, encoding="utf-8")


def sweep_flat(directory: Path, keep: set[str] | None = None) -> int:
    """Retire les sous-dossiers directs. Les fichiers restent."""
    if not directory.is_dir() or directory.is_symlink():
        return 0
    removed = 0
    spared = keep or set()
    for child in list(directory.iterdir()):
        if child.is_symlink() or not child.is_dir():
            continue
        if child.name in spared:
            continue
        shutil.rmtree(child)
        removed += 1
    return removed


def sweep_media(media: Path) -> int:
    removed = sweep_flat(media / "10-rotation")
    archives = media / "20-archives"
    if archives.is_dir() and not archives.is_symlink():
        for bank in archives.iterdir():
            if bank.is_dir() and not bank.is_symlink() and not bank.name.startswith((".", "_")):
                removed += sweep_flat(bank)
    habillage = media / "30-habillage"
    for slug in HABILLAGE_SLUGS:
        removed += sweep_flat(habillage / slug)
    emissions = media / "40-emissions"
    if emissions.is_dir() and not emissions.is_symlink():
        for show in emissions.iterdir():
            if show.is_dir() and not show.is_symlink() and not show.name.startswith((".", "_")):
                removed += sweep_flat(show, EMISSION_KEEP)
    carts = media / "50-carts"
    if carts.is_dir() and not carts.is_symlink():
        for cart in carts.iterdir():
            if cart.is_dir() and not cart.is_symlink() and not cart.name.startswith((".", "_")):
                removed += sweep_flat(cart)
    return removed


def _run(args: list[str], data: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=data, text=True, capture_output=True, check=False)


def _ensure_group(name: str, gid: int) -> None:
    try:
        import grp

        grp.getgrnam(name)
        return
    except KeyError:
        pass
    if _run(["groupadd", "--gid", str(gid), name]).returncode != 0:
        _run(["groupadd", name])


def _ensure_sharewrite() -> None:
    _ensure_group("deposer", DEPOSER_GID)
    _ensure_group("organiser", ORGANISER_GID)
    try:
        import pwd

        pwd.getpwnam("sharewrite")
    except KeyError:
        _run(
            [
                "useradd",
                "--system",
                "--uid",
                str(SHARE_UID),
                "--gid",
                "deposer",
                "--no-create-home",
                "--shell",
                "/usr/sbin/nologin",
                "sharewrite",
            ]
        )


def _ensure_user(username: str, groups: list[str]) -> None:
    extra = [name for name in groups if name != "deposer"]
    try:
        import pwd

        pwd.getpwnam(username)
    except KeyError:
        args = [
            "useradd",
            "--system",
            "--gid",
            "deposer",
            "--no-create-home",
            "--shell",
            "/usr/sbin/nologin",
        ]
        if extra:
            args.extend(["--groups", ",".join(extra)])
        args.append(username)
        _run(args)
        return
    args = ["usermod", "--gid", "deposer"]
    if extra:
        args.extend(["--groups", ",".join(extra)])
    args.append(username)
    _run(args)


def _set_password(username: str, password: str) -> None:
    _run(["smbpasswd", "-a", "-s", username], f"{password}\n{password}\n")


def _drop_user(username: str) -> None:
    _run(["smbpasswd", "-x", username])
    _run(["userdel", username])


def _lock_view(volume: Path) -> None:
    for path in (volume, volume / "Banques", volume / "Habillage", volume / "Émissions"):
        if path.is_dir() and not path.is_symlink():
            try:
                os.chown(path, 0, 0)
            except OSError:
                pass
            os.chmod(path, 0o755)


def _open_dir(path: Path) -> None:
    if not path.is_dir() or path.is_symlink():
        return
    try:
        os.chown(path, 0, DEPOSER_GID)
    except OSError:
        pass
    os.chmod(path, 0o2775)


def _open_media(media: Path) -> None:
    _open_dir(media / "10-rotation")
    archives = media / "20-archives"
    if archives.is_dir():
        os.chmod(archives, 0o755)
        for bank in archives.iterdir():
            if bank.is_dir() and not bank.name.startswith((".", "_")):
                _open_dir(bank)
    for slug in HABILLAGE_SLUGS:
        _open_dir(media / "30-habillage" / slug)
    emissions = media / "40-emissions"
    if emissions.is_dir():
        for show in emissions.iterdir():
            if not show.is_dir() or show.name.startswith((".", "_")):
                continue
            _open_dir(show)
            for slot in EMISSION_KEEP:
                _open_dir(show / slot)
    carts = media / "50-carts"
    if carts.is_dir():
        os.chmod(carts, 0o755)
        for cart in carts.iterdir():
            if cart.is_dir() and not cart.name.startswith((".", "_")):
                _open_dir(cart)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _pending(directory: Path) -> dict[str, dict]:
    found: dict[str, dict] = {}
    if not directory.is_dir():
        return found
    for path in directory.glob("*.json"):
        data = _read_json(path)
        if not data:
            continue
        username = str(data.get("username") or path.stem)
        found[username] = data
    return found


def _roles(path: Path) -> dict[str, str] | None:
    data = _read_json(path)
    if data is None:
        return None
    rows = data.get("users")
    if not isinstance(rows, list):
        return {}
    found: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        username = str(row.get("username") or "")
        role = str(row.get("role") or "")
        if username:
            found[username] = role
    return found


def sync_once() -> None:
    private = Path(os.environ.get("SHARE_PRIVATE", "/share-private"))
    private.mkdir(parents=True, exist_ok=True)
    os.chmod(private, 0o1777)
    (private / "samba").mkdir(parents=True, exist_ok=True)
    media = Path(os.environ.get("MEDIA_ROOT", "/media"))
    volume = refresh_volume.refresh(media)
    _lock_view(volume)
    _ensure_sharewrite()
    _open_media(media)
    removed = sweep_media(media)
    if removed:
        print(f"dossiers retirés : {removed}", flush=True)

    roles = _roles(private / "roles.json")
    if roles is None:
        return
    pending_dir = private / "pending"
    plan = account_plan(roles, _pending(pending_dir))
    managed_path = private / "managed.json"
    managed_data = _read_json(managed_path) or {}
    managed = set(managed_data.get("users") or [])
    for username, item in plan["enable"].items():
        _ensure_user(username, item["groups"])
        password = item.get("password")
        if isinstance(password, str) and password:
            _set_password(username, password)
        managed.add(username)
    for username in plan["disable"]:
        if username in managed:
            _drop_user(username)
        managed.discard(username)
    tmp = managed_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"users": sorted(managed)}), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(managed_path)
    if pending_dir.is_dir():
        for path in pending_dir.glob("*.json"):
            path.unlink(missing_ok=True)
