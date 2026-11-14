"""The search of the fiches, a background task of the scheduler (FON-25).

Like the ReplayGain analysis (`BeetsIntegration.background_analyzer`), it waits a
while after the scheduler started, then takes one title at a time, in a thread of
its own: the antenna never waits on it. It reads its switches between two titles:
`features.fiches` off, it searches nothing and writes nothing.

The order: the titles new since the search was switched on, then those whose key
changed, then the rest of the catalogue, then those due again: a title not found
after 90 days, a title in error after a wait that doubles.

At each round of the import loop, the propositions follow the library
(`reconcile`):
- a title that left the library loses its fiche and its propositions, not the
  decisions taken on them;
- a file moved or renamed comes back under another Beets id, with the same key: its
  fiche follows it, its propositions are made again from the evidence kept, without
  a request, and the decisions taken apply;
- a value changed since its proposition, a tag fixed elsewhere or a file replaced,
  makes the proposition stale, and the title is searched again; a value already
  equal to the proposed one closes the proposition, as written;
- new rules (`RULES_VERSION`) make the waiting propositions again from the evidence.

The evidence does not make the verdict again without the network: a proposition of
`fmg` stays as the search made it.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from radiotomate.fiches.evidence import (
    RULES_VERSION,
    from_json,
    print_key,
    text_key,
    to_json,
)
from radiotomate.fiches.fingerprint import Fpcalc
from radiotomate.fiches.http import Cache, CircuitOpenError, Http
from radiotomate.fiches.proposals import Track, build_row, proposals
from radiotomate.fiches.search import Searcher
from radiotomate.models import Fiche, FicheDecision, FicheProposition, Setting
from radiotomate.models.fiche import (
    ACCEPT,
    ACCEPTED,
    FAILED,
    NOT_FOUND,
    PROPOSED,
    REFUSE,
    STALE,
    WRITTEN,
    utcnow,
)
from radiotomate.quart import ShutdownError, or_shutdown
from radiotomate.services.fiches import FichesSettings, read_settings
from radiotomate.services.versions import read_versions

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from radiotomate.fiches.fingerprint import Print
    from radiotomate.fiches.search import Search

_log = logging.getLogger(__name__)

# The scheduler starts first; the antenna has the CPU to itself meanwhile.
START_DELAY_S = 60.0
# Nothing to search, or the search switched off: a look every minute.
IDLE_S = 60.0
# The propositions follow the library at most once a minute.
RECONCILE_EVERY = timedelta(minutes=1)
# A title not found is searched again: the sources change.
NOT_FOUND_AGAIN = timedelta(days=90)
# A title in error waits, then twice as long at each new error, up to a day.
RETRY_FIRST = timedelta(minutes=1)
RETRY_MOST = timedelta(days=1)
# A title whose key or value changed: before the rest of the catalogue.
KEY_CHANGED = datetime(1970, 1, 1)
# When the search was switched on: a title added after it is new.
SETTING_STARTED = "fiches.started_at"
# The propositions a new search, or the evidence, makes again. The others are a
# decision, or its consequence.
REMADE = frozenset({PROPOSED, STALE})
# The fields of a proposition, as Track has them.
FIELDS = ("title", "artist", "album", "year", "label", "isrc", "famille", "fmg")


@dataclass(frozen=True)
class Title:
    """A title of the library, as the search reads it."""

    id: int
    path: bytes
    added: float
    track: Track


def read_titles(lib: Any) -> dict[int, Title]:
    """Every title of the Beets library, read in one query: building 7 000 Items
    takes seconds. In a thread of its own."""
    directory = os.fsencode(lib.directory) if lib.directory else b""
    with lib.transaction() as tx:
        rows = tx.query(
            "SELECT i.id, i.path, i.added, i.title, i.artist, i.album, i.year, "
            "i.label, i.isrc, i.length, f.value, v.value FROM items i "
            "LEFT JOIN item_attributes f ON f.entity_id = i.id AND f.key = 'famille' "
            "LEFT JOIN item_attributes v ON v.entity_id = i.id AND v.key = 'fmg'"
        )
    titles = {}
    for row in rows:
        (item_id, path, added, title, artist, album, year, label, isrc, length) = row[
            :10
        ]
        famille, fmg = row[10], row[11]
        name = os.fsdecode(path or b"")
        # Absolute under BUTTON's root (ARC-06); relative under another root.
        if name and not Path(name).is_absolute():
            name = str(Path(os.fsdecode(directory)) / name)
        raw = os.fsencode(name)
        titles[item_id] = Title(
            item_id,
            raw,
            float(added or 0),
            Track(
                title=title or "",
                artist=artist or "",
                album=album or "",
                year=int(year or 0),
                label=label or "",
                isrc=isrc or "",
                length=float(length) if length else None,
                famille=famille or "",
                fmg=fmg or "",
            ),
        )
    return titles


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _retry_after(attempts: int, failure: Exception | None) -> timedelta:
    """The wait before searching a title in error again: one minute, then twice as
    long at each new error, up to a day. An open circuit waits its minute."""
    if isinstance(failure, CircuitOpenError):
        return RETRY_FIRST
    return min(RETRY_FIRST * 2 ** max(0, attempts - 1), RETRY_MOST)


@dataclass(frozen=True)
class Found:
    """A search of one title, made in its thread."""

    key: str
    search: Search
    track: Track


class FichesTask:
    """The search, one title at a time.

    `searcher`: makes the Searcher of the settings; a fake one in the tests.
    `fpcalc`: takes the fingerprint of a file. `now`: the time, naive UTC.
    """

    def __init__(  # noqa: PLR0913
        self,
        db: Any,
        lib: Any,
        *,
        version: str = "dev",
        searcher: Callable[[FichesSettings], Any] | None = None,
        fpcalc: Callable[[str], Print | None] | None = None,
        now: Callable[[], datetime] = utcnow,
        run: Callable[..., Any] | None = None,
    ) -> None:
        self.db = db
        self.lib = lib
        self.version = version
        self._make_searcher = searcher or self._searcher
        self.fpcalc = fpcalc or Fpcalc()
        self.now = now
        self._run = run or self._in_thread
        self._settings: FichesSettings | None = None
        self._searcher_now: Any = None
        self._reconciled_at: datetime | None = None
        self._library: frozenset[int] = frozenset()

    @classmethod
    def for_app(cls, app: Any) -> FichesTask:
        from radiotomate.beets import BeetsIntegration

        beets = app.extensions[BeetsIntegration.EXTENSION_NAME]
        version = "dev"
        root = app.config.get("DATA_ROOT")
        if root is not None:
            version = read_versions(root).get("version") or "dev"
        return cls(app.extensions["sqlalchemy"], beets.lib, version=version)

    def _searcher(self, settings: FichesSettings) -> Searcher:
        # A cache of its own, in memory, for the time of the search.
        http = Http(self.version, cache=Cache())
        return Searcher(
            http,
            acoustid_key=settings.acoustid_key,
            verdict=settings.verdict,
            sources=settings.sources,
        )

    async def _in_thread(self, function: Callable[..., Any], *args: Any) -> Any:
        return await asyncio.get_running_loop().run_in_executor(None, function, *args)

    # -- a step --------------------------------------------------------------

    async def step(self) -> bool:
        """One title searched, or nothing to do. True when a title was searched."""
        async with self.db.session() as session:
            settings = await read_settings(session)
            if not settings.enabled:
                return False
            started = await self._started(session)
        if settings != self._settings:
            # The switches, the key or the sources changed: a searcher anew.
            old = getattr(self._searcher_now, "http", None)
            if old is not None:
                old.close()
            self._settings = settings
            self._searcher_now = self._make_searcher(settings)
        titles = await self._run(read_titles, self.lib)
        now = self.now()
        library = frozenset(titles)
        # At once when a title came or went: a file moved keeps its fiche, without
        # a request.
        if (
            library != self._library
            or self._reconciled_at is None
            or now - self._reconciled_at >= RECONCILE_EVERY
        ):
            async with self.db.session() as session:
                await reconcile(session, titles, now)
                await session.commit()
            self._reconciled_at, self._library = now, library
        async with self.db.session() as session:
            title = await next_title(session, titles, started, now)
        if title is None:
            return False
        found = await self._run(self._search_one, title)
        async with self.db.session() as session:
            await keep(session, title, found, self.now())
            await session.commit()
        return True

    async def _started(self, session: Any) -> datetime:
        """When the search was switched on, noted the first time it runs."""
        row = await Setting.from_key(session, SETTING_STARTED)
        if row is not None:
            try:
                return datetime.fromisoformat(row.value)
            except ValueError:
                pass
        started = self.now()
        await Setting.upsert(session, SETTING_STARTED, started.isoformat())
        await session.commit()
        return started

    def _search_one(self, title: Title) -> Found:
        """The fingerprint, then the search. In a thread of its own."""
        fingerprint = None
        path = os.fsdecode(title.path)
        if path and Path(path).is_file():
            fingerprint = self.fpcalc(path)
        search = self._searcher_now.search(title.track, fingerprint)
        key = print_key(fingerprint) if fingerprint else text_key(title.track)
        return Found(key, search, title.track)


# -- choosing the next title ---------------------------------------------------


async def next_title(
    session: Any, titles: dict[int, Title], started: datetime, now: datetime
) -> Title | None:
    """The next title to search: new, then key changed, then the catalogue, then
    those due again."""
    searched = set((await session.scalars(select(Fiche.beets_id))).all())
    unsearched = [title for title in titles.values() if title.id not in searched]
    since = started.replace(tzinfo=started.tzinfo or UTC).timestamp()
    new = [title for title in unsearched if title.added >= since]
    if new:
        return max(new, key=lambda title: (title.added, title.id))
    changed = await session.scalars(
        select(Fiche)
        .where(Fiche.next_at <= KEY_CHANGED)
        .order_by(Fiche.next_at, Fiche.id)
    )
    for fiche in changed:
        if fiche.beets_id in titles:
            return titles[fiche.beets_id]
    if unsearched:
        return min(unsearched, key=lambda title: title.id)
    due = await session.scalars(
        select(Fiche).where(Fiche.next_at <= now).order_by(Fiche.next_at, Fiche.id)
    )
    for fiche in due:
        if fiche.beets_id in titles:
            return titles[fiche.beets_id]
    return None


# -- keeping a search ----------------------------------------------------------


async def _decisions(session: Any, key: str) -> dict[tuple[str, str], str]:
    rows = await session.scalars(select(FicheDecision).where(FicheDecision.key == key))
    return {(row.field, row.value): row.decision for row in rows}


def _propositions(
    fiche: Fiche,
    made: Iterable[Any],
    decisions: dict[tuple[str, str], str],
    *,
    keep_fields: frozenset[str] = frozenset(),
) -> None:
    """The propositions of a fiche made again: those a decision left stay; a value
    refused is not proposed; a value accepted waits to be written (FON-27)."""
    fiche.propositions[:] = [
        proposition
        for proposition in fiche.propositions
        if proposition.state not in REMADE or proposition.field in keep_fields
    ]
    taken = {
        (proposition.field, proposition.value) for proposition in fiche.propositions
    }
    for proposal in made:
        if proposal.key in keep_fields:
            continue
        value = _text(proposal.value)
        decision = decisions.get((proposal.key, value))
        if decision == REFUSE or (proposal.key, value) in taken:
            continue
        fiche.propositions.append(
            FicheProposition(
                field=proposal.key,
                before=_text(proposal.before),
                value=value,
                level=proposal.level,
                why=proposal.why,
                source=proposal.source,
                state=ACCEPTED if decision == ACCEPT else PROPOSED,
            )
        )


async def keep(session: Any, title: Title, found: Found, now: datetime) -> None:
    """A search kept: the fiche of the title, its evidence and its propositions."""
    fiche = await session.scalar(
        select(Fiche)
        .where(Fiche.beets_id == title.id)
        .options(selectinload(Fiche.propositions))
        .execution_options(populate_existing=True)
    )
    if fiche is None:
        fiche = Fiche(beets_id=title.id, propositions=[])
        session.add(fiche)
    search = found.search
    result = search.result
    fiche.text_key = text_key(found.track)
    fiche.searched_at = now
    fiche.rules_version = RULES_VERSION
    if result.status == FAILED:
        # A failure keeps what an earlier search found.
        fiche.key = fiche.key or found.key
        fiche.status = FAILED
        fiche.level = fiche.level or FAILED
        fiche.reasons = fiche.reasons or []
        fiche.attempts = (fiche.attempts or 0) + 1
        fiche.error = result.error or "erreur"
        fiche.next_at = now + _retry_after(fiche.attempts, search.failure)
        _log.info("fiches : %s en erreur (%s)", title.id, fiche.error)
        return
    evidence = search.evidence()
    row = build_row(found.track, result, search.wikidata)
    fiche.key = found.key
    fiche.status = NOT_FOUND if result.status == "rien" else result.status
    fiche.level = row.level
    fiche.reasons = list(row.reasons)
    fiche.source = row.found_at
    fiche.url = row.url
    fiche.evidence = to_json(evidence.result, evidence.wikidata)
    fiche.attempts = 0
    fiche.error = ""
    fiche.next_at = now + NOT_FOUND_AGAIN if fiche.status == NOT_FOUND else None
    _propositions(fiche, proposals(row), await _decisions(session, fiche.key))


def _remake(fiche: Fiche, track: Track, decisions: dict[tuple[str, str], str]) -> None:
    """The propositions made again from the evidence kept, without the network. The
    verdict stays as the search made it."""
    if not fiche.evidence:
        return
    result, wikidata = from_json(fiche.evidence)
    row = build_row(track, result, wikidata)
    fiche.level = row.level
    fiche.reasons = list(row.reasons)
    fiche.rules_version = RULES_VERSION
    _propositions(fiche, proposals(row), decisions, keep_fields=frozenset({"fmg"}))


# -- following the library -----------------------------------------------------


async def reconcile(  # noqa: PLR0912
    session: Any, titles: dict[int, Title], now: datetime
) -> None:
    """The fiches follow the library: see the docstring of the module. A library
    read empty changes nothing: a disk that is not mounted looks like that, and the
    import loop keeps its titles then."""
    if not titles:
        return
    fiches = list(
        (
            await session.scalars(
                select(Fiche)
                .options(selectinload(Fiche.propositions))
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    by_id = {fiche.beets_id: fiche for fiche in fiches}
    orphans = {
        fiche.text_key: fiche for fiche in fiches if fiche.beets_id not in titles
    }
    moved: set[int] = set()
    for title in titles.values():
        if title.id in by_id:
            continue
        orphan = orphans.pop(text_key(title.track), None)
        if orphan is not None:
            # A file moved: its fiche follows it, its key and evidence with it.
            orphan.beets_id = title.id
            by_id[title.id] = orphan
            moved.add(orphan.id)
    gone = [fiche.id for fiche in orphans.values()]
    if gone:
        await session.execute(
            delete(FicheProposition).where(FicheProposition.fiche_id.in_(gone))
        )
        await session.execute(delete(Fiche).where(Fiche.id.in_(gone)))
        _log.info("fiches : %s titre(s) sorti(s) de la bibliothèque", len(gone))
    for fiche in by_id.values():
        if fiche.id in gone or fiche.beets_id not in titles:
            continue
        track = titles[fiche.beets_id].track
        if fiche.id in moved:
            _remake(fiche, track, await _decisions(session, fiche.key))
            continue
        changed = False
        for proposition in fiche.propositions:
            if proposition.state != PROPOSED or proposition.field not in FIELDS:
                continue
            current = _text(getattr(track, proposition.field))
            if current == proposition.value:
                proposition.state = WRITTEN
            elif current != proposition.before:
                proposition.state = STALE
                changed = True
        if text_key(track) != fiche.text_key:
            _stale(fiche)
        elif changed:
            fiche.next_at = KEY_CHANGED
        elif (fiche.rules_version or 0) < RULES_VERSION:
            _remake(fiche, track, await _decisions(session, fiche.key))


def _stale(fiche: Fiche) -> None:
    """The key of a title changed: its propositions are stale, and it is searched
    again before the rest of the catalogue."""
    for proposition in fiche.propositions:
        if proposition.state == PROPOSED:
            proposition.state = STALE
    fiche.next_at = KEY_CHANGED


# -- the loop ------------------------------------------------------------------


async def loop(app: Any) -> None:
    """The background task of the scheduler."""
    try:
        await or_shutdown(asyncio.sleep(START_DELAY_S))
    except (ShutdownError, asyncio.CancelledError):
        return
    task = FichesTask.for_app(app)
    while True:
        try:
            searched = await task.step()
            await or_shutdown(asyncio.sleep(0 if searched else IDLE_S))
        except (ShutdownError, asyncio.CancelledError):
            break
        except Exception:
            _log.exception("fiches : la recherche a échoué, reprise dans une minute")
            try:
                await or_shutdown(asyncio.sleep(IDLE_S))
            except (ShutdownError, asyncio.CancelledError):
                break
