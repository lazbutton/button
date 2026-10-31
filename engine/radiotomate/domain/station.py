"""Pure rules for the station's settings: its name, the addresses of its stream and
of its harbor, the link to its source code.

A value is a string, or None when the station leaves it unset: the console then
keeps the one of its brand.json.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from radiotomate.domain.errors import DomainValidationError

# In the order of the payloads, and of the console's form.
KEYS = (
    "name",
    "short",
    "tagline",
    "locale",
    "public_stream_url",
    "now_url",
    "status_url",
    "harbor_host",
    "harbor_port",
    "harbor_mount",
    "source_url",
)
# What a listener may see, without a session: everything but the harbor.
PUBLIC_KEYS = tuple(key for key in KEYS if not key.startswith("harbor_"))

TEXT_LIMITS = {"name": 80, "short": 16, "tagline": 120}
URL_LIMIT = 500
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SPACE_OR_CONTROL = re.compile(r"[\s\x00-\x1f\x7f]")
LOCALE = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}")
LABEL = r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
HOSTNAME = re.compile(rf"{LABEL}(\.{LABEL})*")
PORT = re.compile(r"[0-9]{1,5}")
MOUNT = re.compile(r"/[A-Za-z0-9._~/-]{1,100}")

TIMEZONE_READ_ONLY = (
    "Le fuseau se règle à l'installation : c'est la variable TZ des conteneurs."
)


def clean_value(key: str, raw: object) -> str | None:
    """The value to store for ``key``, or None to unset it."""
    if key == "harbor_port":
        return _port(raw)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise DomainValidationError("Du texte attendu.", field=key)
    text = raw.strip()
    return CHECKS[key](key, text) if text else None


def clean_settings(data: dict) -> dict[str, str | None]:
    """The keys of ``data`` that are settings, checked. The others are ignored."""
    return {key: clean_value(key, data[key]) for key in KEYS if key in data}


def check_timezone(raw: object, current: str) -> None:
    """The time zone is the containers' ``TZ``, set at installation (ADR 0005)."""
    if raw is not None and raw != current:
        raise DomainValidationError(TIMEZONE_READ_ONLY, field="timezone")


def _text(key: str, text: str) -> str:
    if CONTROL.search(text):
        raise DomainValidationError("Une seule ligne de texte.", field=key)
    limit = TEXT_LIMITS[key]
    if len(text) > limit:
        raise DomainValidationError(f"{limit} caractères au plus.", field=key)
    return text


def _locale(key: str, text: str) -> str:
    if not LOCALE.fullmatch(text):
        raise DomainValidationError("Une langue comme fr ou fr-FR.", field=key)
    return text


def _url(key: str, text: str) -> str:
    if len(text) > URL_LIMIT:
        raise DomainValidationError(f"{URL_LIMIT} caractères au plus.", field=key)
    try:
        parts = urlsplit(text)
        port = parts.port  # raises on a port out of range
    except ValueError:
        parts = port = None
    if (
        parts is None
        or parts.scheme not in ("http", "https")
        or not parts.hostname
        or port == 0
        or SPACE_OR_CONTROL.search(text)
    ):
        raise DomainValidationError(
            "Une adresse complète, en http:// ou https://.", field=key
        )
    # Every address here is served without a session (GET /public/station.json).
    if "@" in parts.netloc:
        raise DomainValidationError(
            "Une adresse sans identifiant ni mot de passe : elle se lit sans compte.",
            field=key,
        )
    return text


def _host(key: str, text: str) -> str:
    if "/" in text:
        raise DomainValidationError(
            "Le nom d'hôte seul, sans http:// ni chemin, comme radio.example.",
            field=key,
        )
    try:
        ipaddress.ip_address(text)
    except ValueError:
        pass
    else:
        return text
    if "[" in text or "]" in text:
        raise DomainValidationError(
            "Une adresse IPv6 s'écrit sans crochets.", field=key
        )
    if ":" in text:
        raise DomainValidationError(
            "Le nom d'hôte seul : le port a son propre champ.", field=key
        )
    if len(text) > 253 or not HOSTNAME.fullmatch(text):
        raise DomainValidationError(
            "Un nom d'hôte comme radio.example, ou une adresse IP.", field=key
        )
    return text


def _mount(key: str, text: str) -> str:
    if not MOUNT.fullmatch(text):
        raise DomainValidationError(
            "Un mount qui commence par /, sans espace, comme /stream.", field=key
        )
    return text


def _port(raw: object) -> str | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if isinstance(raw, str) and PORT.fullmatch(raw.strip()):
        number = int(raw.strip())
    elif isinstance(raw, int) and not isinstance(raw, bool):
        number = raw
    else:
        number = 0
    if not 1 <= number <= 65535:
        raise DomainValidationError("Un port entre 1 et 65535.", field="harbor_port")
    return str(number)


CHECKS = {
    "name": _text,
    "short": _text,
    "tagline": _text,
    "locale": _locale,
    "public_stream_url": _url,
    "now_url": _url,
    "status_url": _url,
    "harbor_host": _host,
    "harbor_mount": _mount,
    "source_url": _url,
}
