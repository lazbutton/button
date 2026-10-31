"""Pure rules for limiting login attempts.

Failures count by address, never by account: otherwise anyone could lock a host
out of their account just before their show (ADR 0013). Everything stays in
memory: a restart forgets every address.
"""

from __future__ import annotations

import ipaddress
import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# The fifth failure within WINDOW blocks the address for BLOCK seconds, then
# twice as long at each new block, MAX_BLOCK at most.
ATTEMPTS = 5
WINDOW = 15 * 60
BLOCK = 15 * 60
MAX_BLOCK = 24 * 60 * 60
# A quiet address is forgotten, with its blocks, a day after its last failure or
# the end of its last block.
FORGET = 24 * 60 * 60
# Beyond this, the addresses quiet for the longest are forgotten first: memory
# stays bounded, even facing many addresses.
MAX_ADDRESSES = 10_000

# nginx puts the client's address in X-Real-IP. It reaches the engine from the
# station's own network, as the engine's port is not published: the loopback,
# or Docker's private networks. Anyone else could write that header.
STATION_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "127.0.0.0/8",
        "::1/128",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
    )
)


@dataclass
class _Address:
    failures: list[float] = field(default_factory=list)
    blocks: int = 0
    blocked_until: float = 0.0

    def forgotten(self, now: float) -> bool:
        last = max(self.failures[-1] if self.failures else 0.0, self.blocked_until)
        return now >= last + FORGET


class LoginGuard:
    """Counts failed logins by address. ``clock`` gives seconds, like
    :func:`time.monotonic`."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        # In the order of their last failure: the quietest first.
        self._addresses: dict[str, _Address] = {}

    def retry_in(self, address: str) -> int:
        """Seconds before ``address`` may try again, 0 if it may now."""
        entry = self._addresses.get(address)
        if entry is None:
            return 0
        return max(0, math.ceil(entry.blocked_until - self._clock()))

    def failed(self, address: str) -> None:
        """Counts a failed login from ``address``."""
        now = self._clock()
        entry = self._addresses.pop(address, None)
        if entry is None or entry.forgotten(now):
            entry = _Address()
        self._addresses[address] = entry
        # A try sent just before the block started.
        if entry.blocked_until > now:
            return
        entry.failures = [at for at in entry.failures if at > now - WINDOW]
        entry.failures.append(now)
        self._forget(now)
        if len(entry.failures) < ATTEMPTS:
            return
        entry.blocked_until = now + min(BLOCK * 2**entry.blocks, MAX_BLOCK)
        entry.blocks += 1
        entry.failures.clear()

    def _forget(self, now: float) -> None:
        # The address just counted is the last one: never forgotten here.
        while len(self._addresses) > 1:
            address, entry = next(iter(self._addresses.items()))
            if len(self._addresses) <= MAX_ADDRESSES and not entry.forgotten(now):
                return
            del self._addresses[address]


def client_address(peer: str | None, real_ip: str | None) -> str:
    """The address whose failures count: X-Real-IP (``real_ip``) when the request
    comes from the station's network, the peer's own otherwise."""
    peer_ip = _ip(peer)
    if peer_ip is not None and any(peer_ip in net for net in STATION_NETWORKS):
        forwarded = _ip(real_ip)
        if forwarded is not None:
            return str(forwarded)
    return str(peer_ip) if peer_ip is not None else peer or ""


def too_many_attempts_message(retry_in: int) -> str:
    """What the HTMX login page says, in the console's words."""
    minutes = max(1, math.ceil(retry_in / 60))
    return f"Trop d'essais. Réessaie dans {minutes} minute{'s' if minutes > 1 else ''}."


def _ip(text: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        ip = ipaddress.ip_address((text or "").strip())
    except ValueError:
        return None
    # An IPv4 client seen through an IPv6 socket.
    return getattr(ip, "ipv4_mapped", None) or ip
