"""Les pochettes (FON-83) : par leur lien, dans la console seulement, derrière
`features.fiches_covers`, éteint par défaut. La fiche d'un titre (`GET
/fiches/<id>.json`) et le titre en cours (`GET /live.json`) ; rien dans `now.json`,
que le moteur ne fait pas."""

from __future__ import annotations

from datetime import datetime

from radiotomate.fiches.evidence import to_json
from radiotomate.fiches.proposals import (
    DeezerAlbum,
    DeezerDetails,
    Details,
    Match,
    SearchResult,
)
from radiotomate.interface import live as live_mod
from radiotomate.models import Fiche, Setting
from radiotomate.services import bank_titles, fiche_covers
from radiotomate.services.fiche_covers import _id_at, attach_cover, path_of
from radiotomate.services.fiches import SETTING_COVERS
from tests.scheduler.test_fiches_json import _beets, _client, _get

COVER = "https://cdn-images.dzcdn.net/images/cover/abc/500x500-000000-80-0-0.jpg"


def _evidence(cover: str | None, status: str = "trouvé") -> dict:
    match = Match(
        source="deezer",
        platform="deezer",
        id="1",
        url="https://www.deezer.com/track/1",
        title="Feeling Good",
        artists=("Nina Simone",),
        duration_s=170.0,
    )
    album = DeezerAlbum(id="7", title="I Put a Spell on You", cover=cover)
    details = Details(deezer=DeezerDetails(track_id="1", title="x", album=album))
    return to_json(SearchResult(status, match, details), {})


async def _fiche(dbsession, beets_id: int, cover: str | None, status="trouvé"):
    dbsession.add(
        Fiche(
            beets_id=beets_id,
            key=f"texte:{beets_id}",
            text_key=f"texte:{beets_id}",
            status=status,
            level="sûr" if status == "trouvé" else "rapproché",
            reasons=[],
            source="Deezer",
            url="https://www.deezer.com/track/1",
            rules_version=1,
            evidence=_evidence(cover, status),
            searched_at=datetime(2026, 11, 15, 12, 0),
        )
    )
    await dbsession.commit()


async def _covers(dbsession, on: bool) -> None:
    await Setting.upsert(dbsession, SETTING_COVERS, "1" if on else "0")
    await dbsession.commit()


async def test_the_cover_of_a_fiche_only_when_the_station_shows_them(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    await _fiche(dbsession, 1, COVER)
    await _fiche(dbsession, 2, "https://images.example/x.jpg")
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )

    # Éteint par défaut : rien.
    assert (await _get(client, "/fiches/1.json"))["evidence"]["cover"] is None
    await _covers(dbsession, True)
    assert (await _get(client, "/fiches/1.json"))["evidence"]["cover"] == COVER
    # Un lien d'un hôte que la politique de contenu n'admet pas ne se rend pas.
    assert (await _get(client, "/fiches/2.json"))["evidence"]["cover"] is None
    await _covers(dbsession, False)
    assert (await _get(client, "/fiches/1.json"))["evidence"]["cover"] is None


async def test_the_switch_is_set_in_the_settings_and_said_to_the_console(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration,
        _beets(tmp_path),
        dbsession,
        users_password,
        permissions={"admin": True},
    )
    assert (await _get(client, "/fiches/reglages.json"))["covers"] is False
    assert (await _get(client, "/account.json"))["features"]["fiche_covers"] is False
    response = await client.put("/fiches/reglages.json", json={"covers": True})
    assert response.status_code == 200, await response.get_data()
    assert (await response.get_json())["covers"] is True
    assert (await _get(client, "/account.json"))["features"]["fiche_covers"] is True
    refused = await client.put("/fiches/reglages.json", json={"covers": "oui"})
    assert refused.status_code == 400


def _playing(path: str, source: str = "autodj") -> dict:
    return live_mod.normalize_live(
        {
            "status": "playing",
            "source": source,
            "artist": "Nina Simone",
            "title": "Feeling Good",
            "initial_uri": f'annotate:radiotomate_sound_id="",liq_cue_in="0":{path}',
        }
    )


async def test_the_title_on_air_shows_its_cover_in_live_json_alone(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    fiche_covers.forget_ids()
    await _fiche(dbsession, 1, COVER)
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    live_mod.set_live_snapshot(_playing("/media/10-rotation/a.mp3"))
    try:
        assert "cover_url" not in await _get(client, "/live.json")
        await _covers(dbsession, True)
        assert (await _get(client, "/live.json"))["cover_url"] == COVER
        # Le relevé partagé, que lisent les autres, n'en garde rien.
        assert "cover_url" not in live_mod.get_live_snapshot()
    finally:
        live_mod.set_live_snapshot(None)


async def test_only_music_found_shows_a_cover_on_air(dbsession):
    fiche_covers.forget_ids()
    await _fiche(dbsession, 1, COVER)
    await _fiche(dbsession, 2, COVER, status="rapproché")
    await _covers(dbsession, True)
    await Setting.upsert(dbsession, bank_titles.SETTING_BANK_TIDY, "1")
    await dbsession.commit()
    ids = {"/media/a.mp3": 1, "/media/b.mp3": 2}
    asked: list[str] = []

    async def find(path: str) -> int | None:
        asked.append(path)
        return ids.get(path)

    async def cover(snapshot: dict) -> str | None:
        await attach_cover(dbsession, snapshot, find)
        return snapshot.get("cover_url")

    assert await cover(_playing("/media/a.mp3")) == COVER
    # Rapproché seulement : ce pourrait être un autre disque.
    assert await cover(_playing("/media/b.mp3")) is None
    # Un jingle, un direct : pas une musique de la banque.
    assert await cover(_playing("/media/a.mp3", source="jingles")) is None
    assert await cover(_playing("/media/a.mp3", source="live")) is None
    # Un fichier inconnu de Beets.
    assert await cover(_playing("/media/c.mp3")) is None
    # Beets n'est demandé qu'une fois par fichier.
    assert await cover(_playing("/media/a.mp3")) == COVER
    assert asked == ["/media/a.mp3", "/media/b.mp3", "/media/c.mp3"]


def test_the_file_of_a_request():
    assert path_of('annotate:a="1",b="x:/y":/media/z.mp3') == "/media/z.mp3"
    assert path_of("/media/z.mp3") == "/media/z.mp3"
    assert path_of("http://radio.example/flux") == ""
    assert path_of(None) == ""


async def test_a_file_beets_does_not_know_is_asked_again_after_a_minute():
    fiche_covers.forget_ids()
    clock = [100.0]
    answers = {"/media/a.mp3": None}
    asked: list[str] = []

    async def find(path: str) -> int | None:
        asked.append(path)
        return answers[path]

    def now() -> float:
        return clock[0]

    assert await _id_at("/media/a.mp3", find, now) is None
    clock[0] += 30
    assert await _id_at("/media/a.mp3", find, now) is None
    assert asked == ["/media/a.mp3"]
    # La boucle d'import l'a indexé entre-temps.
    answers["/media/a.mp3"] = 7
    clock[0] += 31
    assert await _id_at("/media/a.mp3", find, now) == 7
    clock[0] += 3600
    assert await _id_at("/media/a.mp3", find, now) == 7
    assert asked == ["/media/a.mp3", "/media/a.mp3"]


async def test_the_covers_stay_behind_the_general_switch_of_the_tidying(dbsession):
    """Le réglage des pochettes allumé, le rangement éteint : rien à l'antenne."""
    fiche_covers.forget_ids()
    await _fiche(dbsession, 1, COVER)
    await _covers(dbsession, True)

    async def find(path: str) -> int | None:
        return 1

    snapshot = _playing("/media/a.mp3")
    await attach_cover(dbsession, snapshot, find)
    assert "cover_url" not in snapshot
