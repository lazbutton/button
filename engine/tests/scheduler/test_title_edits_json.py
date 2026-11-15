"""POST /media/titles/edit.json et « Revenir » (FON-66), sur de vrais fichiers."""

from __future__ import annotations

from mediafile import MediaFile

from radiotomate.models import MusicCategory, Setting, User
from tests.scheduler.test_studio_json import _interface_client, _login
from tests.scheduler.test_title_edits import _bank, _open

EDIT = "/media/titles/edit.json"


async def _client(app_configration, beets, dbsession, users_password, perms):
    user = User(username="programmatrice", permissions=perms)
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "programmatrice", users_password)
    return client


def _lot(ids, values, expected=None):
    return {
        "titles": [
            {"id": beets_id, "values": values}
            | ({"expected": expected} if expected else {})
            for beets_id in ids
        ]
    }


async def test_edit_asks_for_a_session(raw_app, app_configration, tmp_path):
    beets, ids = _bank(tmp_path, ("mp3",))
    client = _interface_client(app_configration, beets)
    response = await client.post(EDIT, json=_lot(ids, {"album": "Ciel"}))
    assert response.status_code == 401


async def test_edit_is_for_the_programmateur(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, {"carts": True}
    )

    response = await client.post(EDIT, json=_lot(ids, {"album": "Ciel"}))

    assert response.status_code == 403
    assert MediaFile(beets.lib.get_item(ids[0]).path).album == "Estuaire"


async def test_edit_closed_while_the_switch_is_off(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3",))
    dbsession.add(Setting(key="features.bank_tidy", value="0"))
    await dbsession.commit()
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    response = await client.post(EDIT, json=_lot(ids, {"album": "Ciel"}))

    assert response.status_code == 409
    assert (await response.get_json())["code"] == "title_edits_off"


async def test_edit_writes_a_lot_then_revenir(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3", "flac", "ogg"))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    lot = _lot(ids, {"album": "Ciel", "famille": "jazz"}, {"album": "Estuaire"})
    response = await client.post(EDIT, json=lot)

    assert response.status_code == 200, await response.get_data()
    payload = await response.get_json()
    assert payload["dry_run"] is False
    assert (payload["written"], payload["waiting"], payload["unchanged"]) == (3, [], 0)
    for beets_id in ids:
        assert MediaFile(beets.lib.get_item(beets_id).path).album == "Ciel"

    undo = await client.post(f"/media/journal/{payload['entry']}/undo.json")
    assert undo.status_code == 200, await undo.get_data()
    assert (await undo.get_json())["written"] == 3
    for beets_id in ids:
        item = beets.lib.get_item(beets_id)
        assert MediaFile(item.path).album == "Estuaire"
        assert "famille" not in item
    again = await client.post(f"/media/journal/{payload['entry']}/undo.json")
    assert again.status_code == 409
    missing = await client.post("/media/journal/999/undo.json")
    assert missing.status_code == 404


async def test_edit_try_writes_nothing(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    dbsession.add(MusicCategory(name="Jazz", query="genres:Jazz"))
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    response = await client.post(
        EDIT, json=_lot(ids, {"genre": "Soul"}) | {"dry_run": True}
    )

    assert response.status_code == 200, await response.get_data()
    payload = await response.get_json()
    assert payload["dry_run"] is True
    assert payload["entry"] is None
    assert payload["written"] == 2
    assert [(s["name"], s["gained"], s["lost"]) for s in payload["selections"]] == [
        ("Jazz", 0, 2)
    ]
    assert MediaFile(beets.lib.get_item(ids[0]).path).genre == "Jazz"


async def test_edit_refused_says_which_titles_and_why(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    beets.lib.get_item(ids[1]).filepath.chmod(0o444)
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    response = await client.post(EDIT, json=_lot(ids, {"artist": "Orage"}))

    assert response.status_code == 409
    payload = await response.get_json()
    assert payload["code"] == "titles_refused"
    assert payload["message"].startswith("Rien n'a été écrit")
    assert [(t["id"], t["code"]) for t in payload["titles"]] == [(ids[1], "read_only")]
    assert payload["titles"][0]["label"] == "Les Marées Hautes \u2013 Titre flac"
    assert MediaFile(beets.lib.get_item(ids[0]).path).artist == "Les Marées Hautes"


async def test_edit_checks_what_it_is_sent(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    for body, field in (
        ({}, "titles"),
        ({"titles": [{"id": ids[0]}]}, "titles"),
        ({"titles": [{"id": "1", "values": {"album": "x"}}]}, "titles"),
        (_lot(ids, {"label": "x"}), "label"),
        (_lot(ids, {"year": "deux mille"}), "year"),
        (_lot(range(1, 502), {"album": "x"}), "titles"),
    ):
        response = await client.post(EDIT, json=body)
        assert response.status_code == 400, body
        assert (await response.get_json())["field"] == field
