"""Pure rules for the listening link (FON-84): the address of the service that
turns an artist and a title into a link that opens the track on each listener's
platform, and its partner key.

The address is the station's, set in Réglages: nothing in the software names a
real service.
"""

from __future__ import annotations

import re

from radiotomate.domain.errors import DomainValidationError
from radiotomate.domain.station import _url

KEY_LIMIT = 200
# A key travels in a header: one printable word, without space or control.
KEY_SHAPE = re.compile(r"[\x21-\x7e]+")
# A link the console and the website show as a link: http(s) only, never a
# ``javascript:`` or ``data:`` address that a service could answer.
LINK_LIMIT = 500


def clean_url(raw: object) -> str | None:
    """The address to store, or None to unset it."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise DomainValidationError("Du texte attendu.", field="url")
    text = raw.strip().rstrip("/")
    return _url("url", text) if text else None


def clean_key(raw: object) -> str | None:
    """The partner key to store, or None to unset it."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise DomainValidationError("Du texte attendu.", field="key")
    text = raw.strip()
    if not text:
        return None
    if len(text) > KEY_LIMIT or not KEY_SHAPE.fullmatch(text):
        raise DomainValidationError(
            "Une clé d'une seule ligne, sans espace, "
            f"de {KEY_LIMIT} caractères au plus.",
            field="key",
        )
    return text


def clean_link(raw: object) -> str | None:
    """A link answered by the service, or None when it is not a safe one."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or len(text) > LINK_LIMIT or re.search(r"[\s\x00-\x1f\x7f]", text):
        return None
    try:
        return _url("link", text)
    except DomainValidationError:
        return None
