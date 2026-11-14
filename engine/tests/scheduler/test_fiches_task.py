"""La recherche des fiches en tâche de fond (FON-25), sur une vraie bibliothèque de
Beets temporaire. La recherche y est jouée titre par titre (`Played`), sauf dans le
passage de bout en bout, où le vrai `Searcher` interroge de faux services.
"""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import UTC, datetime, timedelta

import pytest
from beets.library import Item, Library
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from radiotomate.commands.update import do_update
from radiotomate.db import QuartAlchemy
from radiotomate.fiches.evidence import RULES_VERSION, text_key
from radiotomate.fiches.fingerprint import Print
from radiotomate.fiches.http import HttpError
from radiotomate.fiches.proposals import (
    DeezerAlbum,
    DeezerDetails,
    Details,
    Match,
    SearchResult,
)
from radiotomate.fiches.search import Search, Searcher
from radiotomate.models import Fiche, FicheDecision, Setting
from radiotomate.scheduler.fiches import (
    KEY_CHANGED,
    FichesTask,
    read_titles,
)
from radiotomate.scheduler.metrics import runtime_metrics
from radiotomate.services.fiches import SETTING_ENABLED
from tests.fiches.fakes import Services, http

NOW = datetime(2026, 11, 14, 12, 0)
DEEZER = "https://api.deezer.com"


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def _found(title: str, artist: str, album: str = "", label: str = "") -> Search:
    """Un titre trouvé chez Deezer, à la lettre près."""
    match = Match(
        source="deezer",
        platform="deezer",
        id=str(abs(hash(title)) % 10_000),
        url="https://www.deezer.com/track/1",
        title=title,
        artists=(artist,),
        album=album or None,
        duration_s=172,
    )
    details = Details(
        deezer=DeezerDetails(
            track_id="1",
            title=title,
            duration_s=172,
            album=DeezerAlbum(id="9", title=album, label=label or None)
            if album
            else None,
        )
    )
    return Search(SearchResult("trouvé", match, details))


class Played:
    """La recherche jouée : une réponse par titre de fichier, et les titres
    cherchés, dans l'ordre."""

    def __init__(self, answers: dict[str, Search | Exception]) -> None:
        self.answers = answers
        self.asked: list[str] = []
        self.prints: list[Print | None] = []

    def search(self, track, fingerprint=None):
        self.asked.append(track.title)
        self.prints.append(fingerprint)
        answer = self.answers[track.title]
        if isinstance(answer, Exception):
            return Search(
                SearchResult("erreur", error=str(answer)),
                failure=answer if isinstance(answer, HttpError) else None,
            )
        return answer


@pytest.fixture
async def db(tmp_path):
    db = QuartAlchemy()
    db.init_from_config({"url": f"sqlite+aiosqlite:///{tmp_path / 'engine.db'}"}, {})
    await do_update(db.engine)
    yield db
    await db.after_serving()


@pytest.fixture
def lib(tmp_path):
    root = tmp_path / "beets"
    root.mkdir()
    library = Library(str(root / "library.db"), str(root))
    yield library
    library._close()


def _add(lib, tmp_path, name: str, title: str, artist: str, **fields) -> Item:
    """Un titre de la banque, son fichier sous media/."""
    path = tmp_path / "media" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    added = fields.pop("added", _epoch(NOW) - 86400)
    item = Item(path=os.fsencode(path), title=title, artist=artist, length=172.0)
    item.update(fields)
    lib.add(item)
    # Beets pose l'heure d'ajout à l'ajout.
    item.added = added
    item.store()
    return item


def _epoch(naive_utc: datetime) -> float:
    return naive_utc.replace(tzinfo=UTC).timestamp()


async def _switch(db, on: bool = True) -> None:
    async with db.session() as session:
        await Setting.upsert(session, SETTING_ENABLED, "1" if on else "0")
        await session.commit()


async def _fiches(db) -> dict[int, Fiche]:
    async with db.session() as session:
        rows = await session.scalars(
            select(Fiche).options(selectinload(Fiche.propositions))
        )
        return {fiche.beets_id: fiche for fiche in rows}


def _proposed(fiche: Fiche) -> dict[str, tuple[str, str]]:
    return {one.field: (one.value, one.state) for one in fiche.propositions}


def _task(db, lib, played, clock=None, fpcalc=None) -> FichesTask:
    return FichesTask(
        db,
        lib,
        searcher=lambda settings: played,
        fpcalc=fpcalc or (lambda path: None),
        now=clock or Clock(),
    )


async def test_switched_off_it_searches_nothing_then_on_it_keeps_what_it_found(
    db, lib, tmp_path
):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    played = Played({"feeling good": _found("Feeling Good", "Nina Simone")})
    task = _task(db, lib, played)

    assert await task.step() is False
    assert played.asked == []
    assert await _fiches(db) == {}

    await _switch(db)
    assert await task.step() is True
    fiche = (await _fiches(db))[item.id]
    assert (fiche.status, fiche.level, fiche.source) == ("trouvé", "sûr", "Deezer")
    assert fiche.key == text_key(read_titles(lib)[item.id].track)
    assert fiche.rules_version == RULES_VERSION
    assert fiche.evidence["result"]["status"] == "trouvé"
    assert _proposed(fiche) == {"title": ("Feeling Good", "proposée")}
    # Rien d'autre à chercher : la tâche se repose.
    assert await task.step() is False

    # Coupée de nouveau, elle s'arrête au titre suivant.
    _add(lib, tmp_path, "b.mp3", "sinnerman", "Nina Simone")
    await _switch(db, on=False)
    assert await task.step() is False
    assert played.asked == ["feeling good"]


async def test_a_new_title_goes_before_the_catalogue(db, lib, tmp_path):
    clock = Clock()
    old = _add(lib, tmp_path, "old.mp3", "old", "A")
    played = Played(
        {name: _found(name.title(), "A") for name in ("old", "new", "other")}
    )
    task = _task(db, lib, played, clock)
    await _switch(db)
    # Allumée maintenant : ce qui arrive ensuite est nouveau.
    async with db.session() as session:
        await Setting.upsert(session, "fiches.started_at", NOW.isoformat())
        await session.commit()
    new = _add(lib, tmp_path, "new.mp3", "new", "A", added=_epoch(NOW) + 60)
    _add(lib, tmp_path, "other.mp3", "other", "A")

    await task.step()
    assert played.asked == ["new"]
    await task.step()
    await task.step()
    assert played.asked == ["new", "old", "other"]
    assert set(await _fiches(db)) == {old.id, new.id, old.id + 2}


async def test_a_title_that_left_loses_its_propositions_not_its_decisions(
    db, lib, tmp_path
):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    # Un autre titre reste : une bibliothèque lue vide ne change rien.
    other = _add(lib, tmp_path, "b.mp3", "sinnerman", "Nina Simone")
    played = Played(
        {
            "feeling good": _found("Feeling Good", "Nina Simone"),
            "sinnerman": Search(SearchResult("rien")),
        }
    )
    task = _task(db, lib, played)
    await _switch(db)
    await task.step()
    await task.step()
    key = (await _fiches(db))[item.id].key
    async with db.session() as session:
        session.add(
            FicheDecision(
                key=key,
                field="title",
                value="Feeling Good",
                decision="refusée",
                username="nadia",
            )
        )
        await session.commit()

    item.remove()
    await task.step()

    assert set(await _fiches(db)) == {other.id}
    async with db.session() as session:
        decisions = list(await session.scalars(select(FicheDecision)))
    assert [(one.key, one.field, one.decision) for one in decisions] == [
        (key, "title", "refusée")
    ]


async def test_a_changed_value_makes_its_proposition_stale(db, lib, tmp_path):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    other = _add(lib, tmp_path, "b.mp3", "sinnerman", "Nina Simone")
    played = Played(
        {
            "feeling good": _found("Feeling Good", "Nina Simone", "Spell", "Philips"),
            "sinnerman": _found("Sinnerman", "Nina Simone"),
        }
    )
    clock = Clock()
    task = _task(db, lib, played, clock)
    await _switch(db)
    await task.step()
    await task.step()
    assert _proposed((await _fiches(db))[item.id]) == {
        "title": ("Feeling Good", "proposée"),
        "album": ("Spell", "proposée"),
        "label": ("Philips", "proposée"),
    }

    # Un tag corrigé ailleurs, à la valeur proposée ; un autre, à une autre valeur.
    item.title = "Feeling Good"
    item.album = "Pastel Blues"
    item.store()
    played.answers["Feeling Good"] = _found("Feeling Good", "Nina Simone", "Spell")
    clock.now += timedelta(minutes=2)
    assert await task.step() is True

    # Rechercher le titre avant le reste : la recherche donne de nouveau ses valeurs.
    assert played.asked[-1] == "Feeling Good"
    assert other.id in await _fiches(db)


async def test_a_changed_value_is_stale_before_the_search_again(db, lib, tmp_path):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    played = Played(
        {"feeling good": _found("Feeling Good", "Nina Simone", "Spell", "Philips")}
    )
    task = _task(db, lib, played)
    await _switch(db)
    await task.step()

    item.album = "Pastel Blues"
    item.store()
    from radiotomate.scheduler.fiches import reconcile

    async with db.session() as session:
        await reconcile(session, read_titles(lib), NOW)
        await session.commit()
    fiche = (await _fiches(db))[item.id]
    assert _proposed(fiche)["album"] == ("Spell", "périmée")
    assert _proposed(fiche)["title"] == ("Feeling Good", "proposée")
    assert fiche.next_at == KEY_CHANGED

    item.title = "Feeling Good"
    item.store()
    async with db.session() as session:
        await reconcile(session, read_titles(lib), NOW)
        await session.commit()
    # Sa clé a changé : le titre se cherche de nouveau ; la valeur écrite ailleurs
    # est celle qui était proposée.
    fiche = (await _fiches(db))[item.id]
    assert fiche.next_at == KEY_CHANGED
    assert _proposed(fiche)["title"] == ("Feeling Good", "écrite")


async def test_a_value_already_proposed_closes_its_proposition(db, lib, tmp_path):
    item = _add(lib, tmp_path, "a.mp3", "Feeling Good", "Nina Simone")
    played = Played(
        {"Feeling Good": _found("Feeling Good", "Nina Simone", "Spell", "Philips")}
    )
    task = _task(db, lib, played)
    await _switch(db)
    await task.step()
    item.label = "Philips"
    item.store()
    from radiotomate.scheduler.fiches import reconcile

    async with db.session() as session:
        await reconcile(session, read_titles(lib), NOW)
        await session.commit()
    fiche = (await _fiches(db))[item.id]
    assert _proposed(fiche)["label"] == ("Philips", "écrite")
    assert fiche.next_at is None


async def test_a_moved_file_keeps_its_fiche_without_a_request(db, lib, tmp_path):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    # Beets redonne l'identifiant le plus haut retiré : un autre titre au-dessus.
    above = _add(lib, tmp_path, "b.mp3", "sinnerman", "Nina Simone")
    played = Played(
        {
            "feeling good": _found("Feeling Good", "Nina Simone", "Spell", "Philips"),
            "sinnerman": Search(SearchResult("rien")),
        }
    )
    task = _task(db, lib, played)
    await _switch(db)
    await task.step()
    await task.step()
    key = (await _fiches(db))[item.id].key
    async with db.session() as session:
        session.add(
            FicheDecision(
                key=key,
                field="label",
                value="Philips",
                decision="refusée",
                username="nadia",
            )
        )
        await session.commit()

    # Déplacé : Beets le retire, puis le réindexe sous un autre identifiant.
    item.remove()
    moved = _add(lib, tmp_path, "jazz/a.mp3", "feeling good", "Nina Simone")
    assert moved.id != item.id
    assert await task.step() is False

    assert played.asked == ["feeling good", "sinnerman"]
    fiches = await _fiches(db)
    assert set(fiches) == {moved.id, above.id}
    assert fiches[moved.id].key == key
    # La valeur refusée ne se propose plus.
    assert _proposed(fiches[moved.id]) == {
        "title": ("Feeling Good", "proposée"),
        "album": ("Spell", "proposée"),
    }


async def test_a_failure_leaves_the_title_in_error_then_it_is_searched_again(
    db, lib, tmp_path
):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    played = Played({"feeling good": HttpError("Deezer : 503", 503)})
    clock = Clock()
    task = _task(db, lib, played, clock)
    await _switch(db)
    await task.step()
    fiche = (await _fiches(db))[item.id]
    assert (fiche.status, fiche.attempts) == ("erreur", 1)
    assert fiche.error == "Deezer : 503"
    assert fiche.next_at == NOW + timedelta(minutes=1)
    assert await task.step() is False

    clock.now += timedelta(minutes=1)
    await task.step()
    fiche = (await _fiches(db))[item.id]
    # Une attente qui double.
    assert fiche.attempts == 2
    assert fiche.next_at == clock.now + timedelta(minutes=2)

    played.answers["feeling good"] = _found("Feeling Good", "Nina Simone")
    clock.now += timedelta(minutes=2)
    await task.step()
    fiche = (await _fiches(db))[item.id]
    assert (fiche.status, fiche.attempts, fiche.next_at) == ("trouvé", 0, None)
    assert played.asked == ["feeling good"] * 3


async def test_a_title_not_found_is_searched_again_after_90_days(db, lib, tmp_path):
    item = _add(lib, tmp_path, "a.mp3", "rare", "Nobody")
    played = Played({"rare": Search(SearchResult("rien"))})
    clock = Clock()
    task = _task(db, lib, played, clock)
    await _switch(db)
    await task.step()
    fiche = (await _fiches(db))[item.id]
    assert (fiche.status, fiche.level) == ("introuvable", "introuvable")
    assert fiche.next_at == NOW + timedelta(days=90)
    clock.now += timedelta(days=89)
    assert await task.step() is False
    clock.now += timedelta(days=1)
    assert await task.step() is True
    assert played.asked == ["rare", "rare"]


async def test_new_rules_make_the_waiting_propositions_again_without_a_request(
    db, lib, tmp_path
):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    played = Played(
        {"feeling good": _found("Feeling Good", "Nina Simone", "Spell", "Philips")}
    )
    task = _task(db, lib, played)
    await _switch(db)
    await task.step()
    # Comme d'anciennes règles : une version de moins, une proposition de moins.
    async with db.session() as session:
        fiche = await session.scalar(
            select(Fiche).options(selectinload(Fiche.propositions))
        )
        fiche.rules_version = RULES_VERSION - 1
        fiche.propositions[:] = [
            one for one in fiche.propositions if one.field != "album"
        ]
        await session.commit()

    from radiotomate.scheduler.fiches import reconcile

    async with db.session() as session:
        await reconcile(session, read_titles(lib), NOW)
        await session.commit()

    fiche = (await _fiches(db))[item.id]
    assert fiche.rules_version == RULES_VERSION
    assert _proposed(fiche)["album"] == ("Spell", "proposée")
    assert played.asked == ["feeling good"]


async def test_the_fingerprint_gives_the_key(db, lib, tmp_path):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    played = Played({"feeling good": _found("Feeling Good", "Nina Simone")})
    taken = Print("AQADtEmUaFKSJEmS", 172.0)
    task = _task(db, lib, played, fpcalc=lambda path: taken)
    await _switch(db)
    await task.step()
    assert played.prints == [taken]
    assert (await _fiches(db))[item.id].key.startswith("empreinte:")


async def test_from_the_library_to_the_fiche_with_the_real_search(db, lib, tmp_path):
    """Le vrai `Searcher`, sur de faux services : Deezer trouve le titre à la lettre
    près ; les autres services ne disent rien."""
    item = _add(lib, tmp_path, "a.mp3", "swarm behaviour", "Seleem")
    services = Services(
        answer=lambda url: {
            "data": [
                {
                    "id": 42,
                    "title": "Swarm Behaviour",
                    "duration": 172,
                    "artist": {"id": 7, "name": "Seleem"},
                }
            ]
        }
        if url.startswith(f"{DEEZER}/search?q=")
        else None
    )
    task = FichesTask(
        db,
        lib,
        searcher=lambda settings: Searcher(http(services)),
        fpcalc=lambda path: None,
        now=Clock(),
    )
    await _switch(db)
    assert await task.step() is True
    fiche = (await _fiches(db))[item.id]
    assert (fiche.status, fiche.url) == ("trouvé", "https://www.deezer.com/track/42")
    assert _proposed(fiche)["title"] == ("Swarm Behaviour", "proposée")
    assert services.asked[0].startswith(f"{DEEZER}/search?q=")


async def test_the_scheduler_answers_while_a_title_is_searched(
    client, raw_app, lib, tmp_path
):
    """La recherche tourne dans un fil à part : le scheduler répond pendant ce
    temps."""
    db = raw_app.extensions["sqlalchemy"]
    _add(lib, tmp_path, "a.mp3", "slow", "A")
    started, release = threading.Event(), threading.Event()

    class Slow:
        def search(self, track, fingerprint=None):
            started.set()
            release.wait(10)
            return Search(SearchResult("rien"))

    task = FichesTask(
        db,
        lib,
        searcher=lambda settings: Slow(),
        fpcalc=lambda path: None,
    )
    await _switch(db)
    step = asyncio.create_task(task.step())
    await asyncio.get_running_loop().run_in_executor(None, started.wait, 10)
    runtime_metrics.heartbeat()
    runtime_metrics.playout_connected = True
    try:
        ready = await client.get("/health/ready")
        assert ready.status_code == 200
    finally:
        release.set()
    assert await step is True


async def test_a_library_read_empty_keeps_the_fiches(db, lib, tmp_path):
    item = _add(lib, tmp_path, "a.mp3", "feeling good", "Nina Simone")
    played = Played({"feeling good": _found("Feeling Good", "Nina Simone")})
    task = _task(db, lib, played)
    await _switch(db)
    await task.step()
    from radiotomate.scheduler.fiches import reconcile

    async with db.session() as session:
        await reconcile(session, {}, NOW)
        await session.commit()
    assert set(await _fiches(db)) == {item.id}
