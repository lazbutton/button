"""
A full run of `deploy/scripts/init-radiotomate.sh` with the real CLI: at every
start, it warns while the admin account still has the example password (SEC-06),
a new installation refuses the account password at the harbor, the Icecast
outputs take the mounts of `.env`, and so do the alerts, by ntfy and e-mail.
The secrets and mounts checks themselves are tested in
`services/catalog/test_init_secrets.py`.
"""

import os
import secrets
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

from ruamel.yaml import YAML

from radiotomate.services.stream_token import SETTING_ACCOUNT_PASSWORD, SETTING_OFF

INIT = Path(__file__).parents[2] / "deploy" / "scripts" / "init-radiotomate.sh"
MACHINE_SECRETS = [
    "ICECAST_SOURCE_PASSWORD",
    "ICECAST_ADMIN_PASSWORD",
    "RT_NOWPLAYING_SECRET",
    "MEILI_MASTER_KEY",
]
WARNING = "a encore le mot de passe change-me"


def _init(
    tmp_path: Path, user: str, password: str, **env: str
) -> subprocess.CompletedProcess:
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
            **env,
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


def _setting(tmp_path: Path, key: str) -> str | None:
    with closing(sqlite3.connect(tmp_path / "data" / "radiotomate.db")) as con:
        row = con.execute("select value from settings where key=?", (key,)).fetchone()
    return row[0] if row else None


def test_a_new_installation_refuses_the_account_password_at_the_harbor(tmp_path: Path):
    first = _init(tmp_path, "admin", "un mot de passe")
    assert first.returncode == 0, first.stderr
    assert "le harbor n'accepte que les jetons d'encodeur" in first.stdout
    assert _setting(tmp_path, SETTING_ACCOUNT_PASSWORD) == "0"
    assert "0" in SETTING_OFF

    # turned back on by the admin: a restart keeps it
    with closing(sqlite3.connect(tmp_path / "data" / "radiotomate.db")) as con, con:
        con.execute(
            "update settings set value='1' where key=?", (SETTING_ACCOUNT_PASSWORD,)
        )
    again = _init(tmp_path, "admin", "")
    assert again.returncode == 0, again.stderr
    assert _setting(tmp_path, SETTING_ACCOUNT_PASSWORD) == "1"


def test_an_existing_station_without_the_key_keeps_the_account_password(tmp_path: Path):
    assert _init(tmp_path, "admin", "un mot de passe").returncode == 0
    # a station installed before the key existed: accounts, and no key
    with closing(sqlite3.connect(tmp_path / "data" / "radiotomate.db")) as con, con:
        con.execute("delete from settings where key=?", (SETTING_ACCOUNT_PASSWORD,))
    again = _init(tmp_path, "admin", "")
    assert again.returncode == 0, again.stderr
    assert "jetons d'encodeur" not in again.stdout
    assert _setting(tmp_path, SETTING_ACCOUNT_PASSWORD) is None


def test_an_interrupted_installation_still_gets_the_key(tmp_path: Path):
    assert _init(tmp_path, "admin", "un mot de passe").returncode == 0
    # stopped after the schema, before the admin account: no account yet
    with closing(sqlite3.connect(tmp_path / "data" / "radiotomate.db")) as con, con:
        con.execute("delete from settings where key=?", (SETTING_ACCOUNT_PASSWORD,))
        con.execute("delete from users")
    again = _init(tmp_path, "admin", "un mot de passe")
    assert again.returncode == 0, again.stderr
    assert _setting(tmp_path, SETTING_ACCOUNT_PASSWORD) == "0"


def _outputs(tmp_path: Path) -> list[tuple[str, str]]:
    data = YAML().load(tmp_path / "data" / "radiotomate.yaml")
    outputs = data["playout_process_config"]["outputs"]
    return [(row["encoder"], row["mount"]) for row in outputs]


def test_the_outputs_take_the_mounts_of_the_env(tmp_path: Path):
    first = _init(tmp_path, "admin", "un mot de passe")
    assert first.returncode == 0, first.stderr
    # No station's name by default.
    assert _outputs(tmp_path) == [("mp3cbr", "radio.mp3"), ("wav", "studio.wav")]
    assert "le flux public passe" not in first.stderr

    # A station keeps the address of its stream: a leading slash is allowed.
    kept = _init(
        tmp_path,
        "admin",
        "",
        ICECAST_MOUNT="/antenne.mp3",
        ICECAST_MONITOR_MOUNT="casque.wav",
    )
    assert kept.returncode == 0, kept.stderr
    assert _outputs(tmp_path) == [("mp3cbr", "antenne.mp3"), ("wav", "casque.wav")]
    # The public stream moved: said, with the way back, without stopping.
    assert "le flux public passe de /radio.mp3 à /antenne.mp3" in kept.stderr
    assert "ICECAST_MOUNT=radio.mp3 dans .env" in kept.stderr

    again = _init(tmp_path, "admin", "", ICECAST_MOUNT="antenne.mp3")
    assert again.returncode == 0, again.stderr
    assert "le flux public passe" not in again.stderr


ALERTS_ENV = {
    "DOMAIN": "radio.example",
    "BUTTON_ALERT_NTFY": "https://ntfy.sh/button-0123456789abcdef01234567",
    "BUTTON_ALERT_NTFY_TOKEN": "tk_jeton-de-test",
    "BUTTON_ALERT_EMAIL": "technique@radio.example, direction@radio.example",
    "BUTTON_ALERT_FROM": "alertes@radio.example",
    "BUTTON_ALERT_SMTP": "smtp.radio.example:587",
    "BUTTON_ALERT_SMTP_USER": "alertes@radio.example",
    "BUTTON_ALERT_SMTP_PASSWORD": "mot de passe $de test",
}


def _alerts(tmp_path: Path):
    return YAML().load(tmp_path / "data" / "radiotomate.yaml").get("alerts")


def test_the_alerts_of_the_env_go_to_the_yaml_and_leave_the_rest(tmp_path: Path):
    from radiotomate.scheduler.alerts import AlertSettings

    first = _init(tmp_path, "admin", "un mot de passe")
    assert first.returncode == 0, first.stderr
    # No ntfy, no e-mail: no alerts block, the loop stays off.
    assert _alerts(tmp_path) is None

    on = _init(tmp_path, "admin", "", **ALERTS_ENV)
    assert on.returncode == 0, on.stderr
    assert _alerts(tmp_path) == {
        "station": "radio.example",
        "ntfy": {
            "url": "https://ntfy.sh/button-0123456789abcdef01234567",
            "token": "tk_jeton-de-test",
        },
        "email": {
            "to": ["technique@radio.example", "direction@radio.example"],
            "from": "alertes@radio.example",
            "server": "smtp.radio.example:587",
            "user": "alertes@radio.example",
            "password": "mot de passe $de test",
        },
    }
    config = tmp_path / "data" / "radiotomate.yaml"
    assert config.stat().st_mode & 0o777 == 0o640
    # As the scheduler reads it: on, with both targets.
    settings = AlertSettings.from_config(dict(_alerts(tmp_path)))
    assert settings.enabled
    assert settings.targets == ["ntfy", "e-mail"]

    # A threshold set by the station stays; ntfy off keeps the e-mail.
    data = YAML().load(config)
    data["alerts"]["silence_seconds"] = 30
    YAML().dump(data, config)
    email_only = {k: v for k, v in ALERTS_ENV.items() if "NTFY" not in k}
    again = _init(tmp_path, "admin", "", **email_only)
    assert again.returncode == 0, again.stderr
    alerts = _alerts(tmp_path)
    assert set(alerts) == {"silence_seconds", "station", "email"}
    assert alerts["silence_seconds"] == 30

    # Both off: what the script wrote goes, the station's threshold stays.
    off = _init(tmp_path, "admin", "")
    assert off.returncode == 0, off.stderr
    assert _alerts(tmp_path) == {"silence_seconds": 30}


def test_the_sender_follows_the_account_unless_given(tmp_path: Path):
    """Without BUTTON_ALERT_FROM, the sender is the SMTP account when it is an
    address, else button@ the domain, as the station command chooses it. A
    password keeps its spaces, as the station sends it."""
    base = {k: v for k, v in ALERTS_ENV.items() if k != "BUTTON_ALERT_FROM"}
    base["BUTTON_ALERT_SMTP_PASSWORD"] = " espaces autour "
    run = _init(tmp_path, "admin", "un mot de passe", **base)
    assert run.returncode == 0, run.stderr
    email = _alerts(tmp_path)["email"]
    assert email["from"] == "alertes@radio.example"
    assert email["password"] == " espaces autour "

    no_account = {k: v for k, v in base.items() if "SMTP_USER" not in k}
    again = _init(tmp_path, "admin", "", **no_account)
    assert again.returncode == 0, again.stderr
    email = _alerts(tmp_path)["email"]
    assert email["from"] == "button@radio.example"
    assert "user" not in email
    assert "password" not in email


def test_alerts_turned_off_leave_no_empty_block(tmp_path: Path):
    assert _init(tmp_path, "admin", "un mot de passe", **ALERTS_ENV).returncode == 0
    assert _alerts(tmp_path)["ntfy"]
    off = _init(tmp_path, "admin", "")
    assert off.returncode == 0, off.stderr
    assert _alerts(tmp_path) is None
