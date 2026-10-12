"""A guest's page, the catalog's deposit routes and the file analysis."""

import shutil
import subprocess
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.services import agenda
from tests.scheduler.test_admin_json import _admin_client
from tests.scheduler.test_studio_json import _interface_client

PARIS = ZoneInfo("Europe/Paris")
TOKEN = "24e32490bca776cfeddb44945268818eb9e98e0bde69497dc792428ac15ba992"


def _day(days: int) -> date:
    return datetime.now(PARIS).date() + timedelta(days=days)


def _wall(day: date, hour: int) -> str:
    return datetime.combine(day, time(hour)).strftime("%Y-%m-%dT%H:%M")


async def _setup(app_configration, beets_integration, dbsession, users_password, name):
    admin = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, name
    )
    day = _day(30)
    response = await admin.post(
        "/agenda/diffusions.json",
        json={
            "kind": "set",
            "title": "Carte blanche",
            "start": _wall(day, 22),
            "end": _wall(day, 23),
            "guest_name": "DJ Lou",
        },
    )
    [row] = (await response.get_json())["diffusions"]
    return admin, row


async def test_the_guest_page_shows_only_the_guests_dates(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin, row = await _setup(
        app_configration, beets_integration, dbsession, users_password, "pub-a"
    )
    token = row["guest"]["token"]
    guest = _interface_client(app_configration, beets_integration)
    page = await guest.get(f"/public/guest/{token}.json")
    payload = await page.get_json()
    assert page.status_code == 200, payload
    assert page.headers["Referrer-Policy"] == "no-referrer"
    assert "noindex" in page.headers["X-Robots-Tag"]
    assert page.headers["Cache-Control"] == "no-store"
    assert payload["guest"] == {"name": "DJ Lou"}
    assert payload["station"]
    assert [item["id"] for item in payload["diffusions"]] == [row["id"]]
    assert "token" not in str(payload)

    guests = await (await admin.get("/agenda/guests.json")).get_json()
    assert guests["guests"][0]["opened_at"] is not None

    missing = await guest.get(f"/public/guest/{'x' * 43}.json")
    assert missing.status_code == 404
    assert (await missing.get_json())["error"] == "Ce lien ne marche plus."


async def test_the_guest_fills_title_tracklist_and_rights(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    _admin, row = await _setup(
        app_configration, beets_integration, dbsession, users_password, "pub-b"
    )
    guest = _interface_client(app_configration, beets_integration)
    token = row["guest"]["token"]
    response = await guest.put(
        f"/public/guest/{token}/diffusions/{row['id']}.json",
        json={
            "set_title": "Lou en cavale",
            "tracklist": "1. Morceau\n2. Autre",
            "rights": True,
            "title": "pirate",
        },
    )
    body = (await response.get_json())["diffusion"]
    assert response.status_code == 200, body
    assert body["set_title"] == "Lou en cavale"
    assert body["rights"] is True
    assert body["title"] == "Carte blanche"


async def test_a_guest_route_ignores_the_console_csrf(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    from tests.scheduler.test_studio_json import _login

    _admin, row = await _setup(
        app_configration, beets_integration, dbsession, users_password, "pub-c"
    )
    from radiotomate.interface_app import app_factory

    iface = app_factory(app_configration, False, beets_integration)
    iface.config["CSRF_ENABLED"] = True
    client = iface.test_client()
    await _login(client, "pub-c", users_password)
    token = row["guest"]["token"]
    public = await client.put(
        f"/public/guest/{token}/diffusions/{row['id']}.json",
        json={"tracklist": "ok"},
    )
    assert public.status_code == 200
    console = await client.put(
        f"/agenda/diffusions/{row['id']}.json", json={"title": "Sans jeton"}
    )
    assert console.status_code == 403


async def test_the_catalog_checks_then_declares_a_deposit(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    admin, row = await _setup(
        app_configration, beets_integration, dbsession, users_password, "pub-d"
    )
    token = row["guest"]["token"]
    catalog = _interface_client(app_configration, beets_integration)
    headers = {"X-Auth-Token": TOKEN}
    unauthorized = await catalog.post(
        "/internal/agenda/deposit-check.json",
        json={"token": token, "diffusion_id": row["id"], "filename": "set.mp3"},
    )
    assert unauthorized.status_code == 401

    async def check(**fields):
        response = await catalog.post(
            "/internal/agenda/deposit-check.json",
            json={"token": token, "diffusion_id": row["id"], **fields},
            headers=headers,
        )
        return await response.get_json()

    ok = await check(filename="Mon set.WAV", size=10)
    assert ok["ok"] is True
    assert ok["folder"] == "40-emissions/carte-blanche/entiere"
    assert ok["filename"].endswith("DJ Lou - Carte blanche.wav")
    assert (await check(filename="set.exe"))["reason"] == "format inconnu"
    assert (await check(filename="set.mp3", size=5 * 1024**3))["reason"].startswith(
        "fichier trop gros"
    )
    bad = await catalog.post(
        "/internal/agenda/deposit-check.json",
        json={"token": "y" * 43, "diffusion_id": row["id"], "filename": "a.mp3"},
        headers=headers,
    )
    assert (await bad.get_json())["reason"] == "lien invalide"

    folder = tmp_path / ok["folder"]
    folder.mkdir(parents=True)
    first = folder / "first.mp3"
    first.write_bytes(b"ID3")
    declared = await catalog.post(
        "/internal/agenda/files.json",
        json={
            "token": token,
            "diffusion_id": row["id"],
            "path": f"{ok['folder']}/first.mp3",
            "original_name": "Mon set.mp3",
        },
        headers=headers,
    )
    assert declared.status_code == 201, await declared.get_json()
    second = folder / "second.mp3"
    second.write_bytes(b"ID3")
    await catalog.post(
        "/internal/agenda/files.json",
        json={
            "token": token,
            "diffusion_id": row["id"],
            "path": f"{ok['folder']}/second.mp3",
            "original_name": "Version 2.mp3",
        },
        headers=headers,
    )
    detail = await (await admin.get(f"/agenda/diffusions/{row['id']}.json")).get_json()
    current = detail["diffusion"]["file"]
    assert current["original_name"] == "Version 2.mp3"
    assert current["origin"] == "depot"
    assert current["late"] is False
    assert not first.exists()
    assert (tmp_path / "90-trash" / "first.mp3").exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")
async def test_analysis_converts_a_wav_and_measures_loudness(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    _admin, row = await _setup(
        app_configration, beets_integration, dbsession, users_password, "pub-e"
    )
    folder = tmp_path / "40-emissions" / "carte-blanche" / "entiere"
    folder.mkdir(parents=True)
    wav = folder / "set.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            str(wav),
        ],
        check=True,
    )
    item = await agenda.register_deposit(
        dbsession,
        {
            "token": row["guest"]["token"],
            "diffusion_id": row["id"],
            "path": "40-emissions/carte-blanche/entiere/set.wav",
            "original_name": "set.wav",
        },
    )
    await dbsession.commit()
    analysed = await agenda.analyse(dbsession, item.id)
    await dbsession.commit()
    assert analysed.path.endswith(".flac")
    assert not wav.exists()
    assert analysed.report["status"] == "ok"
    assert 2.9 < analysed.duration < 3.1
    assert analysed.report["lufs"] is not None
    assert analysed.gain == analysed.report["gain"]

    broken = folder / "broken.mp3"
    broken.write_bytes(b"not audio at all")
    other = await agenda.register_deposit(
        dbsession,
        {
            "token": row["guest"]["token"],
            "diffusion_id": row["id"],
            "path": "40-emissions/carte-blanche/entiere/broken.mp3",
            "original_name": "broken.mp3",
        },
    )
    await dbsession.commit()
    failed = await agenda.analyse(dbsession, other.id)
    assert failed.report["status"] == "error"
    assert failed.report["error"]
