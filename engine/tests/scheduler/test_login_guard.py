"""Pure rules of the login guard: failures by address, blocks that double, the
address nginx hands on."""

import pytest

from radiotomate.domain import login_guard
from radiotomate.domain.login_guard import (
    LoginGuard,
    client_address,
    too_many_attempts_message,
)

MINUTE = 60
HOUR = 60 * MINUTE
CLIENT = "203.0.113.7"
OTHER = "198.51.100.4"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float):
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def guard(clock: Clock) -> LoginGuard:
    return LoginGuard(clock=clock)


def fail(guard: LoginGuard, address: str, times: int):
    for _ in range(times):
        guard.failed(address)


def test_the_fifth_failure_blocks_the_address_15_minutes(guard, clock):
    fail(guard, CLIENT, 4)
    assert guard.retry_in(CLIENT) == 0
    guard.failed(CLIENT)
    assert guard.retry_in(CLIENT) == 15 * MINUTE
    clock.advance(10 * MINUTE)
    assert guard.retry_in(CLIENT) == 5 * MINUTE
    clock.advance(5 * MINUTE)
    assert guard.retry_in(CLIENT) == 0


def test_a_blocked_address_leaves_the_others_free(guard):
    fail(guard, CLIENT, 5)
    assert guard.retry_in(CLIENT) > 0
    assert guard.retry_in(OTHER) == 0


def test_failures_count_over_15_minutes(guard, clock):
    fail(guard, CLIENT, 4)
    clock.advance(15 * MINUTE)
    guard.failed(CLIENT)
    assert guard.retry_in(CLIENT) == 0
    fail(guard, CLIENT, 3)
    assert guard.retry_in(CLIENT) == 0
    guard.failed(CLIENT)
    assert guard.retry_in(CLIENT) == 15 * MINUTE


def test_each_new_block_lasts_twice_as_long_24_hours_at_most(guard, clock):
    blocks = []
    for _ in range(9):
        fail(guard, CLIENT, 5)
        blocks.append(guard.retry_in(CLIENT))
        clock.advance(blocks[-1])
    assert blocks == [
        15 * MINUTE,
        30 * MINUTE,
        1 * HOUR,
        2 * HOUR,
        4 * HOUR,
        8 * HOUR,
        16 * HOUR,
        24 * HOUR,
        24 * HOUR,
    ]


def test_after_a_block_it_takes_five_new_failures(guard, clock):
    fail(guard, CLIENT, 5)
    clock.advance(15 * MINUTE)
    fail(guard, CLIENT, 4)
    assert guard.retry_in(CLIENT) == 0
    guard.failed(CLIENT)
    assert guard.retry_in(CLIENT) == 30 * MINUTE


def test_a_failure_during_the_block_changes_nothing(guard, clock):
    fail(guard, CLIENT, 5)
    clock.advance(15 * MINUTE - 1)
    guard.failed(CLIENT)
    assert guard.retry_in(CLIENT) == 1
    clock.advance(1)
    fail(guard, CLIENT, 4)
    assert guard.retry_in(CLIENT) == 0


def test_a_quiet_day_forgets_the_blocks(guard, clock):
    fail(guard, CLIENT, 5)
    clock.advance(15 * MINUTE + 23 * HOUR)
    fail(guard, CLIENT, 5)
    assert guard.retry_in(CLIENT) == 30 * MINUTE
    clock.advance(30 * MINUTE + 24 * HOUR)
    fail(guard, CLIENT, 5)
    assert guard.retry_in(CLIENT) == 15 * MINUTE


def test_memory_stays_bounded(guard, monkeypatch):
    monkeypatch.setattr(login_guard, "MAX_ADDRESSES", 2)
    fail(guard, CLIENT, 5)
    guard.failed(OTHER)
    assert guard.retry_in(CLIENT) > 0
    # The quietest address goes first, even blocked.
    guard.failed("192.0.2.1")
    assert guard.retry_in(CLIENT) == 0
    guard.failed(OTHER)
    assert len(guard._addresses) == 2


@pytest.mark.parametrize(
    "nginx",
    ["127.0.0.1", "::1", "10.0.0.2", "172.18.0.5", "192.168.1.10", "fd00::5"],
)
def test_the_address_nginx_hands_on_counts(nginx: str):
    assert client_address(nginx, CLIENT) == CLIENT
    assert client_address(nginx, " 2001:DB8::1 ") == "2001:db8::1"
    assert client_address(nginx, "::ffff:203.0.113.7") == CLIENT


@pytest.mark.parametrize("peer", [CLIENT, "2001:db8::1", "100.64.0.1"])
def test_a_client_cannot_choose_its_address(peer: str):
    assert client_address(peer, OTHER) == peer


def test_without_a_usable_header_the_peer_counts():
    assert client_address("172.18.0.5", None) == "172.18.0.5"
    assert client_address("172.18.0.5", "") == "172.18.0.5"
    assert client_address("172.18.0.5", "unknown") == "172.18.0.5"
    assert client_address("::ffff:172.18.0.5", None) == "172.18.0.5"
    # Quart's test client has no socket.
    assert client_address("<local>", OTHER) == "<local>"


def test_the_message_rounds_up_to_the_minute():
    assert too_many_attempts_message(15 * MINUTE) == (
        "Trop d'essais. Réessaie dans 15 minutes."
    )
    assert too_many_attempts_message(14 * MINUTE + 1) == (
        "Trop d'essais. Réessaie dans 15 minutes."
    )
    assert too_many_attempts_message(1) == "Trop d'essais. Réessaie dans 1 minute."
    assert too_many_attempts_message(61) == "Trop d'essais. Réessaie dans 2 minutes."
