"""Le réseau des fiches : un client httpx, un seau et un disjoncteur par service.

Le `lib/http.ts` et le `cachedFetch` de `sources.ts`, dans Hopper. Une réponse 200
est réduite aux champs utiles ; une absence (404, 400, « pas de données » chez
Deezer) donne `None` ; une panne (429, 5xx, délai dépassé, quota dépassé) lève
`HttpError`, jamais `None` : un titre ne passe jamais pour introuvable parce qu'un
service est tombé.

- Un seau par service, partagé par toute la recherche : MusicBrainz, une requête par
  seconde ; AcoustID, trois au plus ; Deezer, dix d'affilée puis une toutes les
  150 ms, sous sa limite de 50 en 5 s ; Wikidata, une par seconde.
- Un disjoncteur par service : cinq pannes de suite, et plus rien ne part vers lui
  pendant une minute.
- Une panne passagère (réseau, 429, 5xx, une réponse illisible, Deezer occupé ou
  au-delà de son quota) se réessaie une fois, et compte pour le disjoncteur si elle
  dure. Un délai dépassé ne se réessaie pas.
- Le User-Agent dit qui appelle : BUTTON, sa version et l'adresse de son dépôt.
  Jamais le nom d'une station, ni une adresse e-mail.

La recherche tourne dans un fil à part, un titre à la fois : le client est synchrone.
L'heure qui passe (`Clock`) se simule dans les tests.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self, TypeVar
from urllib.parse import urlsplit

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_log = logging.getLogger(__name__)

T = TypeVar("T")

# Le dépôt public de BUTTON : MusicBrainz demande à qui écrire.
REPOSITORY = "https://github.com/lazbutton/button"


def user_agent(version: str) -> str:
    """« BUTTON/1.0.0 ( https://github.com/lazbutton/button ) »."""
    return f"BUTTON/{version} ( {REPOSITORY} )"


class HttpError(Exception):
    """Une panne d'un service : 429, 5xx, délai dépassé, quota, réseau. Jamais une
    absence : le titre sera cherché de nouveau."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class CircuitOpenError(HttpError):
    """Le disjoncteur du service est ouvert : rien ne part vers lui avant une
    minute."""


class Clock:
    """L'heure qui passe, en secondes : `time.monotonic` et `time.sleep`."""

    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class TokenBucket:
    """Un seau à jetons : `capacity` requêtes d'affilée, puis un jeton toutes les
    `interval` secondes.

    Celui qui attend garde le seau : les requêtes partent dans l'ordre où elles le
    demandent, même de plusieurs fils.
    """

    def __init__(self, capacity: int, interval: float, clock: Clock) -> None:
        self.capacity = capacity
        self.interval = interval
        self._clock = clock
        self._tokens = float(capacity)
        self._updated = clock.now()
        self._lock = threading.Lock()

    def take(self) -> None:
        with self._lock:
            now = self._clock.now()
            elapsed = (now - self._updated) / self.interval
            self._tokens = min(self.capacity, self._tokens + elapsed)
            self._updated = now
            if self._tokens < 1:
                self._clock.sleep((1 - self._tokens) * self.interval)
                self._tokens = 1
                self._updated = self._clock.now()
            self._tokens -= 1

    def done(self) -> None:
        """La réponse est arrivée : le jeton suivant ne court qu'à partir d'ici. Deux
        requêtes arrivent ainsi au service espacées d'un intervalle au moins, même
        quand la première a attendu une connexion."""
        with self._lock:
            self._updated = max(self._updated, self._clock.now())


class CircuitBreaker:
    """Un disjoncteur : après `threshold` pannes de suite, il refuse tout pendant
    `pause` secondes."""

    def __init__(self, clock: Clock, threshold: int = 5, pause: float = 60.0) -> None:
        self.threshold = threshold
        self.pause = pause
        self._clock = clock
        self._failures = 0
        self._open_until = -math.inf
        self._lock = threading.Lock()

    @property
    def open(self) -> bool:
        return self._clock.now() < self._open_until

    def success(self) -> None:
        with self._lock:
            self._failures = 0

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold:
                self._open_until = self._clock.now() + self.pause
                self._failures = 0


@dataclass(frozen=True)
class Policy:
    """Les limites d'un service : son seau, et le délai d'une requête, en secondes.

    `after_response` : l'intervalle court depuis la fin de la réponse précédente, et
    non depuis son départ.
    """

    capacity: int
    interval: float
    timeout: float = 4.0
    after_response: bool = False


# Un peu sous les limites annoncées. Deezer : son seau de 40 d'affilée laissait
# passer 80 requêtes en 5 s après un temps mort, et un passage de toute une nuit en
# fait (« quota dépassé ») ; ici jamais plus de 44 en 5 s pour une limite de 50.
POLICIES = {
    "api.deezer.com": Policy(10, 0.15),
    # MusicBrainz refuse au-delà d'une requête par seconde, comptée à l'arrivée.
    "musicbrainz.org": Policy(1, 1.1, timeout=15.0, after_response=True),
    "query.wikidata.org": Policy(1, 1.0, timeout=60.0),
    "api.acoustid.org": Policy(1, 0.34, timeout=15.0),
}
# Un service sans limite connue : celles de Deezer.
_DEFAULT_POLICY = Policy(10, 0.15)


# Les erreurs que Deezer rend dans une réponse 200. Occupé : quota dépassé (4),
# service occupé (700) ; une panne, qui attend une seconde et se réessaie. Rien :
# pas de données (800), ou une requête refusée (500, 501, 600), qui ne réussirait
# pas mieux plus tard. Toute autre erreur est une panne.
DEEZER_BUSY = {4: "quota dépassé", 700: "service occupé"}
DEEZER_NOTHING = frozenset({500, 501, 600, 800})


def _error_code(body: Any) -> Any:
    """Le code de l'erreur d'une réponse 200 de Deezer, `{ error: { code } }`."""
    error = body.get("error") if isinstance(body, dict) else None
    return error.get("code") if isinstance(error, dict) else None


def _retry_after(response: httpx.Response) -> float:
    """Le délai que le service demande, 0,4 s sans lui, 2 s au plus."""
    try:
        seconds = float(response.headers.get("retry-after", ""))
    except ValueError:
        seconds = 0.4
    if not math.isfinite(seconds) or seconds < 0:
        seconds = 0.4
    return min(seconds, 2.0)


def _passing(response: httpx.Response, body: Any) -> float | None:
    """Une panne passagère : l'attente avant le nouvel essai, en secondes. Sinon
    None.

    Un 429 ou un 5xx ; un 200 qu'on ne sait pas lire, comme une page de maintenance ;
    Deezer occupé, ou au-delà de son quota, qui répond 200.
    """
    status = response.status_code
    if status == 429 or status >= 500:
        return _retry_after(response)
    if status == 200 and not isinstance(body, dict):
        return 0.4
    if status == 200 and _error_code(body) in DEEZER_BUSY:
        return 1.0
    return None


def _body(response: httpx.Response) -> Any:
    """Le corps lu comme JSON ; une page d'erreur reste du texte."""
    if not response.content:
        return None
    try:
        return json.loads(response.content)
    except ValueError:
        return response.text


def _said(body: Any) -> str:
    """Ce qu'un refus dit de lui-même, comme le « rate limit » de MusicBrainz."""
    said = body.get("error") if isinstance(body, dict) else None
    if not isinstance(said, str) or not said.strip():
        return ""
    said = " ".join(said.split())
    return f" ({said[:117]}…)" if len(said) > 120 else f" ({said})"


def _truthy(value: object) -> bool:
    """Vrai comme en JavaScript : un objet ou un tableau l'est toujours, même vide."""
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)):
        return value != 0 and not math.isnan(value)
    if isinstance(value, str):
        return value != ""
    return True


class Cache:
    """Les réponses réduites déjà reçues, `size` au plus, les plus anciennes lues
    sortant d'abord. Une page d'artiste sert ainsi à tous ses titres.

    Une réponse se range sous son adresse et sous la fonction qui l'a réduite : deux
    recherches lisent parfois la même adresse, chacune à sa façon. En mémoire
    seulement : les membres d'un groupe y ont leur genre, qui ne se garde nulle part.
    """

    def __init__(self, size: int = 5000) -> None:
        self.size = size
        self._entries: OrderedDict[str, object] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def lookup(self, key: str) -> tuple[bool, object]:
        """Si la réponse est gardée, et laquelle."""
        with self._lock:
            if key not in self._entries:
                return False, None
            self._entries.move_to_end(key)
            return True, self._entries[key]

    def put(self, key: str, value: object) -> None:
        with self._lock:
            self._entries[key] = value
            self._entries.move_to_end(key)
            while len(self._entries) > self.size:
                self._entries.popitem(last=False)


class Http:
    """Le client des fiches : ses seaux et ses disjoncteurs, un par service.

    `version` : celle de BUTTON, pour le User-Agent. `transport` : un faux transport
    dans les tests (`httpx.MockTransport`). `cache` : les réponses réduites, gardées
    en mémoire le temps de la recherche.
    """

    def __init__(
        self,
        version: str,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Clock | None = None,
        policies: Mapping[str, Policy] | None = None,
        cache: Cache | None = None,
    ) -> None:
        self.clock = clock or Clock()
        self.cache = cache
        self._policies = POLICIES if policies is None else policies
        self._buckets: dict[str, TokenBucket] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": user_agent(version), "Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _policy(self, host: str) -> Policy:
        return self._policies.get(host, _DEFAULT_POLICY)

    def _bucket(self, host: str) -> TokenBucket:
        with self._lock:
            bucket = self._buckets.get(host)
            if bucket is None:
                policy = self._policy(host)
                bucket = TokenBucket(policy.capacity, policy.interval, self.clock)
                self._buckets[host] = bucket
            return bucket

    def breaker(self, host: str) -> CircuitBreaker:
        with self._lock:
            breaker = self._breakers.get(host)
            if breaker is None:
                breaker = CircuitBreaker(self.clock)
                self._breakers[host] = breaker
            return breaker

    def send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        data: Mapping[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Une requête, et son corps lu comme JSON.

        Une panne passagère (réseau, 429, 5xx, réponse illisible, Deezer occupé) se
        réessaie une fois ; une seconde compte pour le disjoncteur, et la réponse
        revient telle quelle. Un délai dépassé ne se réessaie pas.
        """
        host = urlsplit(url).hostname or ""
        breaker = self.breaker(host)
        if breaker.open:
            message = f"{host} : disjoncteur ouvert, nouvel essai dans une minute"
            raise CircuitOpenError(message)
        policy, bucket = self._policy(host), self._bucket(host)
        for attempt in (0, 1):
            bucket.take()
            try:
                response = self._client.request(
                    method, url, headers=headers, data=data, timeout=policy.timeout
                )
            except httpx.TimeoutException:
                breaker.failure()
                raise HttpError(f"{host} : délai dépassé") from None
            except httpx.HTTPError as error:
                if attempt == 0:
                    continue
                breaker.failure()
                raise HttpError(f"{host} : {error}") from error
            finally:
                if policy.after_response:
                    bucket.done()
            body = _body(response)
            wait = _passing(response, body)
            if wait is not None and attempt == 0:
                _log.info("%s : panne passagère, nouvel essai", host)
                self.clock.sleep(wait)
                continue
            if wait is not None:
                breaker.failure()
            else:
                breaker.success()
            return response.status_code, body
        raise AssertionError  # pragma: no cover

    def fetch(
        self,
        url: str,
        prune: Callable[[Any], T],
        headers: Mapping[str, str] | None = None,
    ) -> T | None:
        """Un GET : la réponse réduite par `prune`, ou `None` pour une absence.

        200 : la réponse réduite. 404, 400, ou les erreurs de Deezer « pas de
        données » et « requête refusée » : `None`. Un 429, un 5xx, une réponse 200
        illisible, Deezer occupé ou au-delà de son quota, toute autre erreur ou tout
        autre refus : `HttpError`. Une absence se garde dans le cache, jamais une
        panne.
        """
        key = f"{url}\n{prune.__module__}.{getattr(prune, '__qualname__', '')}"
        if self.cache is not None:
            kept, value = self.cache.lookup(key)
            if kept:
                return value  # type: ignore[return-value]
        host = urlsplit(url).hostname or ""
        status, body = self.send("GET", url, headers=headers)
        found: T | None = None
        if status == 200 and isinstance(body, dict):
            error = body.get("error")
            code = _error_code(body)
            if code in DEEZER_BUSY:
                raise HttpError(f"{host} : {DEEZER_BUSY[code]}")
            if _truthy(error) and code not in DEEZER_NOTHING:
                message = error.get("message") if isinstance(error, dict) else error
                raise HttpError(f"{host} : {message or f'erreur {code}'}")
            if not _truthy(error):
                found = prune(body)
        elif status == 200:
            raise HttpError(f"{host} : réponse illisible")
        elif status not in (400, 404):
            raise HttpError(f"{host} : réponse {status}{_said(body)}", status)
        if self.cache is not None:
            self.cache.put(key, found)
        return found
