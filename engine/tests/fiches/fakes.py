"""De faux services pour les tests de la recherche : un faux transport httpx
(`MockTransport`) qui répond par adresse, et une horloge simulée.

Les réponses viennent des cas de Hopper : elles sont réduites à ce que les sources
en lisent.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl

import httpx

from radiotomate.fiches.http import Clock, Http

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

VERSION = "0.0.0-test"


class FakeClock(Clock):
    """Une horloge qui n'avance que quand on attend."""

    def __init__(self, start: float = 1000.0) -> None:
        self.time = start
        self.slept: list[float] = []

    def now(self) -> float:
        return self.time

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.time += max(0.0, seconds)


# Une réponse : un corps JSON, rendu en 200 ; des octets, rendus tels quels en 200 ;
# (statut, corps) ou (statut, corps, en-têtes) ; ou une exception httpx à lever.
# None : 404.
Answer = Any


class Services:
    """Les réponses des services, par adresse exacte, ou par une fonction de
    l'adresse ; et les requêtes reçues, avec l'heure simulée de leur arrivée.

    `delay` : le temps qu'une requête met à arriver, selon son rang, comme une
    connexion à ouvrir.
    """

    def __init__(
        self,
        answers: dict[str, Answer] | None = None,
        answer: Callable[[str], Answer] | None = None,
        clock: FakeClock | None = None,
        delay: Callable[[int], float] | None = None,
    ) -> None:
        self.answers = dict(answers or {})
        self.answer = answer
        self.clock = clock or FakeClock()
        self.delay = delay
        self.requests: list[httpx.Request] = []
        self.times: list[float] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.delay is not None:
            self.clock.time += self.delay(len(self.requests))
        self.requests.append(request)
        self.times.append(self.clock.now())
        url = str(request.url)
        found = self.answers.get(url)
        if found is None and self.answer is not None:
            found = self.answer(url)
        if found is None:
            return httpx.Response(404, json={"error": "Not Found"})
        if isinstance(found, Exception):
            raise found
        if isinstance(found, bytes):
            return httpx.Response(200, content=found)
        if isinstance(found, tuple):
            status, body, *headers = found
            return httpx.Response(
                status, json=body, headers=headers[0] if headers else {}
            )
        return httpx.Response(200, json=found)

    @property
    def asked(self) -> list[str]:
        """Les adresses demandées, dans l'ordre."""
        return [str(request.url) for request in self.requests]

    def form(self, index: int = -1) -> dict[str, str]:
        """Le corps d'un POST de formulaire."""
        return dict(parse_qsl(self.requests[index].content.decode()))

    def headers(self, index: int = -1) -> httpx.Headers:
        return self.requests[index].headers


def http(services: Services, **options: Any) -> Http:
    """Le client des fiches, branché sur les faux services et leur horloge."""
    return Http(
        VERSION,
        transport=httpx.MockTransport(services),
        clock=services.clock,
        **options,
    )


def fake_fpcalc(folder: Path, fingerprint: str, duration: float) -> str:
    """Un faux `fpcalc`, qui rend toujours la même empreinte."""
    script = folder / "fpcalc"
    answer = json.dumps({"duration": duration, "fingerprint": fingerprint})
    script.write_text(f"#!{sys.executable}\nprint({answer!r})\n", encoding="utf-8")
    script.chmod(0o755)
    return str(script)
