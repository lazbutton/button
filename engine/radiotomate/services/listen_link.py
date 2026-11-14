"""« Retrouver ce titre » (FON-84): when a track goes on air, asks the listening
link service for the link that opens it on each listener's platform, and hands it
to nowplaying (``now.json``) and to the console (``/live.json``).

- Off by default: ``features.listen_link``. Off, or without an address, no request
  leaves the station. What leaves is the artist and the title on air, and the
  partner key in ``X-Hopper-Key`` when the station has one.
- The service is never waited for by the antenna: the request runs in a background
  task of the scheduler, short (``TIMEOUT``), without a retry, and behind a breaker.
  A failure leaves the track without a link.
- Only a sure answer is kept: a 422 (nothing sure to the letter) or a failure
  gives no link, never a guess.
- The partner key is a secret: no route returns it (``admin_payload`` says only
  that it is set), and it is never logged.
- The scheduler and the interface are two processes: the scheduler keeps the link of
  the track on air in the ``settings`` table (``listen_link.current``), and the
  interface reads it back for ``/live.json``.
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, ClassVar

import httpx
from sqlalchemy import delete

from radiotomate.domain.errors import DomainValidationError
from radiotomate.domain.listen_link import clean_key, clean_link, clean_url
from radiotomate.models import Setting

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as ormSession

_log = logging.getLogger(__name__)

SETTING_SWITCH = "features.listen_link"
SETTING_URL = "listen_link.url"
SETTING_KEY = "listen_link.key"
SETTING_CURRENT = "listen_link.current"
_SETTING_ON = {"1", "true", "on", "yes"}

RESOLVE_PATH = "/api/resolve"
KEY_HEADER = "X-Hopper-Key"
# What the antenna may lose to the service: nothing, but this much of a
# background task's time.
TIMEOUT = 3.0
# An answer is kept in memory: a sure link a week, a « not sure » a day, so that
# a title played again is not asked again.
CACHE_SIZE = 500
TTL_FOUND = 7 * 24 * 3600
TTL_UNSURE = 24 * 3600
# Three failures in a row: nothing leaves for a minute.
BREAKER_FAILURES = 3
BREAKER_PAUSE = 60.0
# The sources the automation plays music from: a live or a relay carries
# whatever its encoder sends.
MUSIC_SOURCES = ("autodj", "carts")


class _State:
    cache: ClassVar[OrderedDict[tuple[str, str], tuple[float, str | None]]] = (
        OrderedDict()
    )
    failures = 0
    open_until = 0.0


def reset_state() -> None:
    _State.cache = OrderedDict()
    _State.failures = 0
    _State.open_until = 0.0


class Settings:
    """What the station set: the switch, the address, the partner key."""

    def __init__(self, enabled: bool, url: str | None, key: str | None) -> None:
        self.enabled = enabled
        self.url = url
        self.key = key

    @property
    def active(self) -> bool:
        return self.enabled and bool(self.url)


async def _value(session: ormSession, key: str) -> str | None:
    row = await Setting.from_key(session, key)
    return row.value.strip() if row and row.value and row.value.strip() else None


async def load_settings(session: ormSession) -> Settings:
    switch = await _value(session, SETTING_SWITCH)
    return Settings(
        enabled=switch is not None and switch.lower() in _SETTING_ON,
        url=await _value(session, SETTING_URL),
        key=await _value(session, SETTING_KEY),
    )


async def admin_payload(session: ormSession) -> dict:
    """``GET /listen-link.json``: never the key, only whether it is set."""
    settings = await load_settings(session)
    return {
        "enabled": settings.enabled,
        "url": settings.url,
        "key_set": settings.key is not None,
    }


async def update_settings(session: ormSession, data: dict) -> None:
    """Sets the keys present in ``data``, all or none: the checks run first. An empty
    address or key unsets it. A key absent from ``data`` keeps its value."""
    changes: dict[str, str | None] = {}
    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            raise DomainValidationError("Vrai ou faux attendu.", field="enabled")
        changes[SETTING_SWITCH] = "1" if data["enabled"] else "0"
    if "url" in data:
        changes[SETTING_URL] = clean_url(data["url"])
    if "key" in data:
        changes[SETTING_KEY] = clean_key(data["key"])
    for key, value in changes.items():
        if value is not None:
            await Setting.upsert(session, key, value)
            continue
        await session.execute(delete(Setting).where(Setting.key == key))
    # A new address or key forgets what the old service said.
    if SETTING_URL in changes or SETTING_KEY in changes:
        reset_state()
        await session.execute(delete(Setting).where(Setting.key == SETTING_CURRENT))


def _norm(artist: str, title: str) -> tuple[str, str]:
    return " ".join(artist.split()).casefold(), " ".join(title.split()).casefold()


def _cached(name: tuple[str, str], now: float) -> tuple[bool, str | None]:
    found = _State.cache.get(name)
    if found is None:
        return False, None
    expires, link = found
    if expires < now:
        del _State.cache[name]
        return False, None
    _State.cache.move_to_end(name)
    return True, link


def _remember(name: tuple[str, str], link: str | None, now: float) -> None:
    ttl = TTL_FOUND if link else TTL_UNSURE
    _State.cache[name] = (now + ttl, link)
    _State.cache.move_to_end(name)
    while len(_State.cache) > CACHE_SIZE:
        _State.cache.popitem(last=False)


async def resolve(
    settings: Settings,
    artist: str,
    title: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    now: float | None = None,
) -> str | None:
    """The link of the track, or None when the service is not sure, is down, is too
    slow, or the feature is off. Never raises."""
    artist, title = artist.strip(), title.strip()
    if not settings.active or not artist or not title:
        return None
    now = time.monotonic() if now is None else now
    name = _norm(artist, title)
    known, link = _cached(name, now)
    if known:
        return link
    if _State.open_until > now:
        return None
    headers = {"Content-Type": "application/json"}
    if settings.key:
        headers[KEY_HEADER] = settings.key
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT), transport=transport
        ) as client:
            response = await client.post(
                f"{settings.url}{RESOLVE_PATH}",
                json={"track": {"artist": artist, "title": title}},
                headers=headers,
            )
        if response.status_code == 422:
            # Nothing sure to the letter: an answer, not a failure.
            _State.failures = 0
            _remember(name, None, now)
            return None
        response.raise_for_status()
        body = response.json()
        link = clean_link(body.get("url")) if isinstance(body, dict) else None
    except (httpx.HTTPError, ValueError) as exc:
        # The class only: a message could carry the address, and the key must never
        # be written.
        _log.warning("listen link service failed: %s", type(exc).__name__)
        _State.failures += 1
        if _State.failures >= BREAKER_FAILURES:
            _State.open_until = now + BREAKER_PAUSE
            _State.failures = 0
        return None
    _State.failures = 0
    _remember(name, link, now)
    return link


def is_music(source: object) -> bool:
    return str(source or "") in MUSIC_SOURCES


async def keep_current(
    session: ormSession, artist: str, title: str, link: str | None
) -> None:
    """The link of the track on air, for the interface. None clears the last one."""
    if link is None:
        await session.execute(delete(Setting).where(Setting.key == SETTING_CURRENT))
        return
    await Setting.upsert(
        session,
        SETTING_CURRENT,
        json.dumps({"artist": artist, "title": title, "url": link}, ensure_ascii=False),
    )


async def attach_to_live(session: ormSession, snapshot: dict) -> None:
    """Adds ``listen_url`` to the live snapshot when the link kept is the one of the
    track on air, and the feature is on."""
    artist = str(snapshot.get("artist") or "").strip()
    title = str(snapshot.get("title") or "").strip()
    if not artist or not title or not is_music(snapshot.get("source")):
        return
    switch = await _value(session, SETTING_SWITCH)
    if switch is None or switch.lower() not in _SETTING_ON:
        return
    raw = await _value(session, SETTING_CURRENT)
    if raw is None:
        return
    try:
        kept = json.loads(raw)
    except ValueError:
        return
    if not isinstance(kept, dict):
        return
    if _norm(str(kept.get("artist") or ""), str(kept.get("title") or "")) != _norm(
        artist, title
    ):
        return
    link = clean_link(kept.get("url"))
    if link:
        snapshot["listen_url"] = link
