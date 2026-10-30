"""
A full run of `deploy/scripts/init-radiotomate.sh` with the real CLI: at every
start, it warns while the admin account still has the example password (SEC-06).
The secrets check itself is tested in `services/catalog/test_init_secrets.py`.
"""

import os
import secrets
import subprocess
from pathlib import Path

INIT = Path(__file__).parents[2] / "deploy" / "scripts" / "init-radiotomate.sh"
MACHINE_SECRETS = [
    "ICECAST_SOURCE_PASSWORD",
    "ICECAST_ADMIN_PASSWORD",
    "RT_NOWPLAYING_SECRET",
    "MEILI_MASTER_KEY",
]
WARNING = "a encore le mot de passe change-me"


def _init(tmp_path: Path, user: str, password: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sh", str(INIT)],
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "RADIOTOMATE_DATA": str(tmp_path / "data"),
            "MEDIA_ROOT": str(tmp_path / "media"),
            "RT_ADMIN_USER": user,
            "RT_ADMIN_PASSWORD": password,
            **{name: secrets.token_hex(24) for name in MACHINE_SECRETS},
        },
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def _users(tmp_path: Path, *args: str):
    config = tmp_path / "data" / "radiotomate.yaml"
    subprocess.run(
        ["radiotomate", "-c", str(config), "users", *args],
        capture_output=True,
        check=True,
    )


def test_warns_while_the_admin_keeps_the_example_password(tmp_path: Path):
    first = _init(tmp_path, "autre", "un mot de passe")
    assert first.returncode == 0, first.stderr
    assert "admin user autre created" in first.stdout
    assert WARNING not in first.stderr

    # created before the check, from an unchanged .env.example
    _users(tmp_path, "add", "admin", "--admin", "--password", "change-me")
    # .env fixed, then emptied as the docs advise: the account keeps change-me
    warned = _init(tmp_path, "admin", "")
    assert warned.returncode == 0, warned.stderr
    assert f"« admin » {WARNING}" in warned.stderr

    _users(tmp_path, "mod", "admin", "--password", "nouveau")
    quiet = _init(tmp_path, "admin", "")
    assert quiet.returncode == 0, quiet.stderr
    assert WARNING not in quiet.stderr
