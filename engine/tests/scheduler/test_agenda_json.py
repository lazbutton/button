"""Agenda JSON routes of the console: dated broadcasts, guests, weekly days off."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from tests.scheduler.test_admin_json import _admin_client

PARIS = ZoneInfo("Europe/Paris")


def _day(days: int) -> date:
    return datetime.now(PARIS).date() + timedelta(days=days)


def _wall(day: date, hour: int, minute: int = 0) -> str:
    return datetime.combine(day, time(hour, minute)).strftime("%Y-%m-%dT%H:%M")


async def _client(  # noqa: PLR0913
    raw_app, app_configration, beets_integration, dbsession, pw, name, perms=None
):
    _ = raw_app
    return await _admin_client(
        app_configration, beets_integration, dbsession, pw, name, perms
    )


async def _create(client, **fields) -> dict:
    response = await client.post("/agenda/diffusions.json", json=fields)
    body = await response.get_json()
    assert response.status_code == 201, body
    return body["diffusions"]


async def test_create_a_set_with_a_new_guest_and_read_the_agenda(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _client(
        raw_app, app_configration, beets_integration, dbsession, users_password, "ag-a"
    )
    day = _day(20)
    [row] = await _create(
        client,
        kind="set",
        title="Carte blanche",
        start=_wall(day, 22),
        end=_wall(day + timedelta(days=1), 0),
        guest_name="DJ Lou",
    )
    assert row["guest"]["name"] == "DJ Lou"
    assert len(row["guest"]["token"]) >= 40
    assert row["prep"] == "attendu"
    assert row["duration_min"] == 120
    assert row["deposit_open"] is True
    assert row["starts_at"].startswith(day.isoformat() + "T22:00")
    start = datetime.fromisoformat(row["starts_at"])
    assert datetime.fromisoformat(row["deadline_at"]) == start - timedelta(hours=24)

    last = day + timedelta(days=1)
    listed = await client.get(
        f"/agenda.json?from={day.isoformat()}&to={last.isoformat()}"
    )
    payload = await listed.get_json()
    assert listed.status_code == 200, payload
    assert payload["enabled"] is True
    assert [item["id"] for item in payload["diffusions"]] == [row["id"]]


async def test_overlaps_are_refused_and_previews_name_the_clash(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _client(
        raw_app, app_configration, beets_integration, dbsession, users_password, "ag-b"
    )
    day = _day(21)
    await _create(
        client,
        kind="set",
        title="Nuits Tomates",
        start=_wall(day, 22),
        end=_wall(day, 23, 30),
    )
    clash = await client.post(
        "/agenda/diffusions.json",
        json={
            "kind": "set",
            "title": "Autre",
            "start": _wall(day, 23),
            "end": _wall(day + timedelta(days=1), 1),
        },
    )
    body = await clash.get_json()
    assert clash.status_code == 409
    assert "Nuits Tomates" in body["error"]

    preview = await client.post(
        "/agenda/diffusions/preview.json",
        json={
            "kind": "set",
            "title": "Série",
            "start": _wall(day - timedelta(days=7), 23),
            "end": _wall(day - timedelta(days=7), 23, 45),
            "repeat": {"rule": "weekly", "count": 3},
        },
    )
    rows = (await preview.get_json())["occurrences"]
    assert preview.status_code == 200
    assert [bool(row["problem"]) for row in rows] == [False, True, False]
    assert "Nuits Tomates" in rows[1]["problem"]


async def test_a_series_keeps_the_dates_picked_and_drops_the_following(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _client(
        raw_app, app_configration, beets_integration, dbsession, users_password, "ag-c"
    )
    day = _day(22)
    fields = {
        "kind": "set",
        "title": "Résidence",
        "start": _wall(day, 20),
        "end": _wall(day, 21),
        "repeat": {"rule": "weekly", "count": 4},
    }
    preview = await (
        await client.post("/agenda/diffusions/preview.json", json=fields)
    ).get_json()
    starts = [row["start"] for row in preview["occurrences"]]
    created = await _create(client, **fields, only=[starts[0], starts[1], starts[3]])
    assert len(created) == 3
    assert len({row["series_id"] for row in created}) == 1

    deleted = await client.delete(
        f"/agenda/diffusions/{created[1]['id']}.json?suivantes=1"
    )
    assert (await deleted.get_json())["deleted"] == 2
    left = await client.get(f"/agenda/diffusions/{created[0]['id']}.json")
    assert left.status_code == 200
    gone = await client.get(f"/agenda/diffusions/{created[2]['id']}.json")
    assert gone.status_code == 404


async def test_a_weekly_show_is_replaced_or_cancelled_for_one_day(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _client(
        raw_app, app_configration, beets_integration, dbsession, users_password, "ag-d"
    )
    day = _day(23)
    weekly = await client.post(
        "/antenne/emissions.json",
        json={
            "scope": "weekly",
            "title": "Hop Pop Hop",
            "artist": "avec l'équipe",
            "day_of_week": day.weekday(),
            "start_minute": 20 * 60,
            "end_minute": 22 * 60,
        },
    )
    emission_id = (await weekly.get_json())["emission"]["id"]
    [dated] = await _create(
        client,
        kind="set",
        title="Invitée",
        start=_wall(day, 21),
        end=_wall(day, 22),
    )
    next_week = day + timedelta(days=7)
    cancel = await client.post(
        "/agenda/exceptions.json",
        json={"emission_id": emission_id, "date": next_week.isoformat()},
    )
    assert cancel.status_code == 201
    wrong_day = await client.post(
        "/agenda/exceptions.json",
        json={
            "emission_id": emission_id,
            "date": (day + timedelta(days=1)).isoformat(),
        },
    )
    assert wrong_day.status_code == 400

    payload = await (
        await client.get(
            f"/agenda.json?from={day.isoformat()}&to={next_week.isoformat()}"
        )
    ).get_json()
    occurrences = {row["date"]: row for row in payload["weekly"]}
    assert occurrences[day.isoformat()]["replaced_by"] == dated["id"]
    assert occurrences[next_week.isoformat()]["cancelled"] is True

    restore = await client.delete(
        f"/agenda/exceptions.json?emission_id={emission_id}&date={next_week.isoformat()}"
    )
    assert restore.status_code == 200
    payload = await (
        await client.get(
            f"/agenda.json?from={next_week.isoformat()}&to={next_week.isoformat()}"
        )
    ).get_json()
    assert payload["weekly"][0]["cancelled"] is False


async def test_an_animator_reads_but_does_not_write(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _client(
        raw_app,
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "ag-e",
        {"live": True},
    )
    assert (await client.get("/agenda.json")).status_code == 200
    day = _day(24)
    refused = await client.post(
        "/agenda/diffusions.json",
        json={
            "kind": "set",
            "title": "X",
            "start": _wall(day, 10),
            "end": _wall(day, 11),
        },
    )
    assert refused.status_code == 403


async def test_a_dated_live_needs_an_account_allowed_to_stream(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _client(
        raw_app, app_configration, beets_integration, dbsession, users_password, "ag-f"
    )
    await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "dj-direct",
        {"stream": True, "live": True},
    )
    day = _day(25)
    unknown = await client.post(
        "/agenda/diffusions.json",
        json={
            "kind": "live",
            "title": "Direct",
            "start": _wall(day, 18),
            "end": _wall(day, 19),
            "host_username": "personne",
        },
    )
    assert unknown.status_code == 400
    [row] = await _create(
        client,
        kind="live",
        title="Direct",
        start=_wall(day, 18),
        end=_wall(day, 19),
        host_username="dj-direct",
    )
    assert row["prep"] == "pret"
    assert row["host_username"] == "dj-direct"


async def test_bank_file_attach_and_detach(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    folder = tmp_path / "40-emissions" / "best-of" / "entiere"
    folder.mkdir(parents=True)
    (folder / "best-of.mp3").write_bytes(b"ID3")
    client = await _client(
        raw_app, app_configration, beets_integration, dbsession, users_password, "ag-g"
    )
    day = _day(26)
    [row] = await _create(
        client, kind="set", title="Best of", start=_wall(day, 14), end=_wall(day, 15)
    )
    outside = await client.put(
        f"/agenda/diffusions/{row['id']}/file.json", json={"path": "../etc/passwd"}
    )
    assert outside.status_code == 400
    attached = await client.put(
        f"/agenda/diffusions/{row['id']}/file.json",
        json={"path": "40-emissions/best-of/entiere/best-of.mp3", "duration": 3700},
    )
    body = (await attached.get_json())["diffusion"]
    assert attached.status_code == 200, body
    assert body["file"]["origin"] == "banque"
    assert body["file"]["duration"] == 3700
    assert body["overrun_seconds"] == 100
    detached = await client.delete(f"/agenda/diffusions/{row['id']}/file.json")
    assert (await detached.get_json())["diffusion"]["file"] is None
    assert (folder / "best-of.mp3").is_file()


async def test_guests_switch_and_stop(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    admin = await _client(
        raw_app, app_configration, beets_integration, dbsession, users_password, "ag-h"
    )
    created = await admin.post("/agenda/guests.json", json={"name": "DJ Kam"})
    guest = (await created.get_json())["guest"]
    renewed = await admin.post(f"/agenda/guests/{guest['id']}/token.json")
    assert (await renewed.get_json())["guest"]["token"] != guest["token"]

    day = _day(27)
    [row] = await _create(
        admin,
        kind="set",
        title="Pas encore",
        start=_wall(day, 9),
        end=_wall(day, 10),
        guest_id=guest["id"],
    )
    assert row["guest"]["id"] == guest["id"]
    stop = await admin.post(f"/agenda/diffusions/{row['id']}/stop.json")
    assert stop.status_code == 409

    programmer = await _client(
        raw_app,
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "ag-i",
        {"autodj": True, "carts": True, "live": True},
    )
    assert (
        await programmer.put("/agenda/settings.json", json={"enabled": False})
    ).status_code == 403
    off = await admin.put("/agenda/settings.json", json={"enabled": False})
    assert (await off.get_json())["enabled"] is False
    assert (await (await admin.get("/agenda.json")).get_json())["enabled"] is False
    on = await admin.put("/agenda/settings.json", json={"enabled": True})
    assert (await on.get_json())["enabled"] is True


async def test_deposit_auth_takes_a_team_session_or_a_guest_link(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    from tests.scheduler.test_studio_json import _interface_client

    admin = await _client(
        raw_app, app_configration, beets_integration, dbsession, users_password, "ag-j"
    )
    guest = (
        await (
            await admin.post("/agenda/guests.json", json={"name": "Lien"})
        ).get_json()
    )["guest"]
    assert (await admin.get("/agenda/deposit-auth")).status_code == 204
    anonymous = _interface_client(app_configration, beets_integration)
    assert (await anonymous.get("/agenda/deposit-auth")).status_code == 401
    good = await anonymous.get(
        "/agenda/deposit-auth", headers={"X-Invite-Token": guest["token"]}
    )
    assert good.status_code == 204
    bad = await anonymous.get(
        "/agenda/deposit-auth", headers={"X-Invite-Token": "x" * 43}
    )
    assert bad.status_code == 401
