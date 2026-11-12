"""Le réseau des fiches : seaux, disjoncteurs, pannes et absences.

Les cas de `tests/http.test.ts` et du bloc « sources » de
`tests/radio-catalogue.test.ts`, dans Hopper (« garde le 200 réduit et le 404, pas
les pannes »), sur un faux transport httpx et une horloge simulée.
"""

import contextlib

import httpx
import pytest

from radiotomate.fiches.http import (
    Cache,
    CircuitBreaker,
    CircuitOpenError,
    HttpError,
    Policy,
    TokenBucket,
    user_agent,
)
from tests.fiches.fakes import VERSION, FakeClock, Services, http


def test_the_user_agent_names_button_its_version_and_its_repository():
    """Jamais le nom d'une station, ni une adresse e-mail."""
    agent = user_agent("1.0.0")
    assert agent == "BUTTON/1.0.0 ( https://github.com/lazbutton/button )"
    assert "@" not in agent
    services = Services({"https://musicbrainz.org/ws/2/x": {"ok": True}})
    http(services).fetch("https://musicbrainz.org/ws/2/x", lambda body: body)
    assert services.headers()["User-Agent"] == user_agent(VERSION)


def test_musicbrainz_never_gets_two_requests_in_the_same_second():
    """Une requête par seconde, même quand la recherche en demande dix d'affilée."""
    services = Services(answer=lambda url: {"recordings": []})
    client = http(services)
    for index in range(10):
        client.fetch(f"https://musicbrainz.org/ws/2/recording/{index}", dict)
    gaps = [b - a for a, b in zip(services.times, services.times[1:], strict=False)]
    assert len(services.times) == 10
    assert min(gaps) >= 1.0
    assert all(
        int(a) != int(b)
        for a, b in zip(services.times, services.times[1:], strict=False)
    )


def test_musicbrainz_counts_its_second_from_the_last_answer():
    """Une requête qui attend sa connexion n'avance pas la suivante : à l'arrivée
    chez MusicBrainz, elles restent espacées d'une seconde au moins."""
    services = Services(
        answer=lambda url: {"recordings": []},
        delay=lambda index: 0.3 if index % 3 == 0 else 0.0,
    )
    client = http(services)
    for index in range(9):
        client.fetch(f"https://musicbrainz.org/ws/2/recording/{index}", dict)
    gaps = [b - a for a, b in zip(services.times, services.times[1:], strict=False)]
    assert min(gaps) >= 1.0


def test_the_deezer_bucket_lets_ten_through_then_one_every_150_ms():
    """Jamais plus de 44 requêtes en 5 s, pour une limite de 50."""
    services = Services(answer=lambda url: {"data": []})
    client = http(services)
    for index in range(60):
        client.fetch(f"https://api.deezer.com/track/{index}", dict)
    times = services.times
    assert times[9] == times[0]
    assert times[10] - times[9] == pytest.approx(0.15)
    windows = [
        sum(1 for other in times if start <= other < start + 5) for start in times
    ]
    assert max(windows) <= 44


def test_acoustid_gets_three_requests_a_second_at_most():
    clock = FakeClock()
    bucket = TokenBucket(1, 0.34, clock)
    times = []
    for _ in range(9):
        bucket.take()
        times.append(clock.now())
    assert all(
        sum(1 for other in times if start <= other < start + 1) <= 3 for start in times
    )


def test_the_breaker_opens_after_five_failures_and_closes_after_a_minute():
    clock = FakeClock()
    breaker = CircuitBreaker(clock)
    for _ in range(4):
        breaker.failure()
    assert not breaker.open
    breaker.failure()
    assert breaker.open
    clock.time += 59
    assert breaker.open
    clock.time += 1
    assert not breaker.open


def test_a_transient_error_is_tried_again_once():
    calls = []

    def answer(url):
        calls.append(url)
        return (503, None, {"Retry-After": "1"}) if len(calls) == 1 else {"ok": True}

    services = Services(answer=answer)
    client = http(services)
    assert client.fetch("https://api.deezer.com/track/1", dict) == {"ok": True}
    assert len(calls) == 2
    assert 1.0 in services.clock.slept


def test_a_service_that_stays_down_is_an_error_never_an_absence():
    """Deux 503 de suite : une erreur, et une panne de plus pour le disjoncteur."""
    services = Services(answer=lambda url: (503, None))
    client = http(services)
    with pytest.raises(HttpError, match="503"):
        client.fetch("https://musicbrainz.org/ws/2/isrc/X", dict)
    for _ in range(4):
        with pytest.raises(HttpError):
            client.fetch("https://musicbrainz.org/ws/2/isrc/X", dict)
    asked = len(services.requests)
    # Cinq pannes : le disjoncteur s'ouvre, plus rien ne part pendant une minute.
    with pytest.raises(CircuitOpenError, match="disjoncteur ouvert"):
        client.fetch("https://musicbrainz.org/ws/2/isrc/X", dict)
    assert len(services.requests) == asked
    # Les autres services ne sont pas touchés.
    services.answer = lambda url: {"ok": True}
    assert client.fetch("https://api.deezer.com/track/1", dict) == {"ok": True}
    services.clock.time += 60
    assert client.fetch("https://musicbrainz.org/ws/2/isrc/X", dict) == {"ok": True}


def test_a_timeout_is_an_error_and_is_not_tried_again():
    services = Services(answer=lambda url: httpx.ReadTimeout("trop long"))
    with pytest.raises(HttpError, match="délai dépassé"):
        http(services).fetch("https://query.wikidata.org/sparql?query=x", dict)
    assert len(services.requests) == 1


def test_a_network_error_is_tried_again_once():
    calls = []

    def answer(url):
        calls.append(url)
        if len(calls) == 1:
            return httpx.ConnectError("refusé")
        return {"ok": True}

    services = Services(answer=answer)
    assert http(services).fetch("https://api.deezer.com/x", dict) == {"ok": True}
    services = Services(answer=lambda url: httpx.ConnectError("refusé"))
    with pytest.raises(HttpError, match="refusé"):
        http(services).fetch("https://api.deezer.com/x", dict)
    assert len(services.requests) == 2


def test_keeps_the_pruned_200_and_the_404_not_the_failures():
    """200 : la réponse réduite ; 404, 400, ou « pas de données » chez Deezer :
    rien, gardé aussi. Quota, 429, 5xx : une erreur, rien de gardé."""
    answers = {
        "https://x.test/ok": {"keep": 1, "drop": 2},
        "https://x.test/absent": (404, {"error": "Not Found"}),
        "https://x.test/refused": (400, {"error": "bad"}),
        "https://x.test/deezer": {"error": {"code": 800, "message": "no data"}},
        "https://x.test/quota": {"error": {"code": 4}},
        "https://x.test/panne": (503, None),
        "https://x.test/forbidden": (403, None),
    }
    services = Services(answers)
    client = http(services, cache=Cache())

    def keep(body):
        return {"keep": body["keep"]}

    assert client.fetch("https://x.test/ok", keep) == {"keep": 1}
    assert client.fetch("https://x.test/absent", keep) is None
    assert client.fetch("https://x.test/refused", keep) is None
    assert client.fetch("https://x.test/deezer", keep) is None
    with pytest.raises(HttpError, match="quota"):
        client.fetch("https://x.test/quota", keep)
    with pytest.raises(HttpError, match="503"):
        client.fetch("https://x.test/panne", keep)
    with pytest.raises(HttpError, match="403"):
        client.fetch("https://x.test/forbidden", keep)
    # Gardés : la réponse et les absences ; pas les pannes, redemandées.
    asked = len(services.requests)
    for url in answers:
        with contextlib.suppress(HttpError):
            client.fetch(url, keep)
    again = services.asked[asked:]
    assert sorted(set(again)) == [
        "https://x.test/forbidden",
        "https://x.test/panne",
        "https://x.test/quota",
    ]


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ({"error": {"code": 700, "message": "Service busy"}}, "service occupé"),
        ({"error": {"code": 4, "message": "Quota limit exceeded"}}, "quota dépassé"),
        ({"error": {"code": 200, "message": "Permission denied"}}, "Permission denied"),
        (b"", "illisible"),
        (b"<html><body>Maintenance</body></html>", "illisible"),
        (b"null", "illisible"),
        ([], "illisible"),
    ],
)
def test_a_200_that_is_a_failure_is_an_error_never_an_absence(body, error):
    """Deezer occupé, une page de maintenance, une réponse vide ou qu'on ne sait pas
    lire : une panne, réessayée une fois, jamais rien."""
    services = Services({"https://api.deezer.com/track/1": body})
    with pytest.raises(HttpError, match=error):
        http(services).fetch("https://api.deezer.com/track/1", dict)


@pytest.mark.parametrize("code", [500, 501, 600, 800])
def test_a_request_deezer_refuses_or_has_no_data_for_is_nothing(code):
    services = Services(
        {"https://api.deezer.com/search?q=x": {"error": {"code": code}}}
    )
    assert http(services).fetch("https://api.deezer.com/search?q=x", dict) is None
    assert len(services.requests) == 1


def test_deezer_over_quota_waits_a_second_then_tries_again():
    """« Quota dépassé » attend."""
    calls = []

    def answer(url):
        calls.append(url)
        return {"error": {"code": 4}} if len(calls) == 1 else {"id": 1}

    services = Services(answer=answer)
    assert http(services).fetch("https://api.deezer.com/track/1", dict) == {"id": 1}
    assert len(calls) == 2
    assert 1.0 in services.clock.slept


def test_deezer_over_quota_title_after_title_opens_the_breaker():
    """Cinq requêtes de suite au-delà du quota, après leur nouvel essai : Deezer
    n'est plus appelé pendant une minute."""
    services = Services(answer=lambda url: {"error": {"code": 4}})
    client = http(services)
    for index in range(5):
        with pytest.raises(HttpError, match="quota"):
            client.fetch(f"https://api.deezer.com/track/{index}", dict)
    asked = len(services.requests)
    assert asked == 10
    with pytest.raises(CircuitOpenError):
        client.fetch("https://api.deezer.com/track/9", dict)
    assert len(services.requests) == asked


def test_the_same_address_read_two_ways_is_kept_apart():
    """Deux recherches lisent la même page d'album, chacune à sa façon : la seconde
    ne reçoit pas ce que la première en a gardé."""
    services = Services({"https://api.deezer.com/album/7": {"upc": "1", "title": "T"}})
    client = http(services, cache=Cache())

    def title(body):
        return body["title"]

    def upc(body):
        return body["upc"]

    assert client.fetch("https://api.deezer.com/album/7", title) == "T"
    assert client.fetch("https://api.deezer.com/album/7", upc) == "1"
    assert client.fetch("https://api.deezer.com/album/7", title) == "T"
    assert len(services.requests) == 2


def test_the_cache_forgets_the_oldest_answers_first():
    cache = Cache(size=2)
    cache.put("a", 1)
    cache.put("b", None)
    assert cache.lookup("a") == (True, 1)
    cache.put("c", 3)
    assert cache.lookup("a") == (True, 1)
    assert cache.lookup("b") == (False, None)
    assert cache.lookup("c") == (True, 3)
    assert len(cache) == 2


def test_a_service_without_known_limits_gets_a_bucket_and_a_breaker_too():
    services = Services(answer=lambda url: {"ok": True})
    client = http(services, policies={"x.test": Policy(1, 2.0)})
    client.fetch("https://x.test/a", dict)
    client.fetch("https://x.test/b", dict)
    assert services.times[1] - services.times[0] == pytest.approx(2.0)
