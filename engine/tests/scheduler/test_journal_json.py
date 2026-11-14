"""Le journal des gestes (FON-71) : la page, le détail d'un lot, « Annuler »."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mediafile import MediaFile
from sqlalchemy import update as sql_update

from radiotomate.models import JournalEntry, User
from radiotomate.services import journal
from tests.scheduler.test_studio_json import _interface_client, _login
from tests.scheduler.test_title_edits import _bank, _open

EDIT = "/media/titles/edit.json"


async def _client(app_configration, beets, dbsession, users_password, username):
    user = User(username=username, permissions={"autodj": True})
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, username, users_password)
    return client


def _lot(ids, values):
    return {"titles": [{"id": beets_id, "values": values} for beets_id in ids]}


async def _edit(client, ids, values) -> int:
    response = await client.post(EDIT, json=_lot(ids, values))
    assert response.status_code == 200, await response.get_data()
    return (await response.get_json())["entry"]


async def test_journal_is_for_the_programmateur(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, _ids = _bank(tmp_path, ("mp3",))
    client = _interface_client(app_configration, beets)
    assert (await client.get("/media/journal.json")).status_code == 401

    user = User(username="animateur", permissions={"live": True})
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    await _login(client, "animateur", users_password)
    assert (await client.get("/media/journal.json")).status_code == 403


async def test_journal_closed_while_the_switch_is_off(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, _ids = _bank(tmp_path, ("mp3",))
    client = await _client(
        app_configration, beets, dbsession, users_password, "programmatrice"
    )
    response = await client.get("/media/journal.json")
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_tidy_off"


async def test_journal_lists_who_did_what_and_filters(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3", "flac", "ogg"))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, "programmatrice"
    )
    first = await _edit(client, ids, {"album": "Ciel"})
    second = await _edit(client, ids[:1], {"year": "2001", "famille": "jazz"})

    response = await client.get("/media/journal.json")
    assert response.status_code == 200, await response.get_data()
    page = await response.get_json()
    assert [entry["id"] for entry in page["entries"]] == [second, first]
    latest = page["entries"][0]
    assert latest["gesture"] == "edit"
    assert latest["gesture_label"] == "Correction"
    assert latest["username"] == "programmatrice"
    assert latest["titles"] == 1
    assert latest["fields"] == ["famille", "year"]
    assert latest["created"].endswith(("+01:00", "+02:00"))
    assert latest["undoable"] is True
    assert latest["counts"]["done"] == 1
    assert page["entries"][1]["counts"]["done"] == 3
    assert page["gestures"] == [{"value": "edit", "label": "Correction", "count": 2}]
    assert page["people"] == [{"value": "programmatrice", "count": 2}]
    assert page["undo_days"] == 30

    # par personne, et page par page
    other = await client.get("/media/journal.json?username=quelqu'un")
    assert (await other.get_json())["entries"] == []
    one = await (await client.get("/media/journal.json?limit=1")).get_json()
    assert [entry["id"] for entry in one["entries"]] == [second]
    assert one["next"] == second
    rest = await (
        await client.get(f"/media/journal.json?limit=1&before={one['next']}")
    ).get_json()
    assert [entry["id"] for entry in rest["entries"]] == [first]
    assert rest["next"] is None
    bad = await client.get("/media/journal.json?limit=0")
    assert bad.status_code == 400


async def test_journal_detail_names_each_change(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, "programmatrice"
    )
    entry = await _edit(client, ids, {"album": "Ciel"})

    detail = await (await client.get(f"/media/journal/{entry}.json")).get_json()

    assert [
        (c["id"], c["field"], c["old"], c["new"], c["status"])
        for c in detail["changes"]
    ] == [
        (ids[0], "album", "Estuaire", "Ciel", "done"),
        (ids[1], "album", "Estuaire", "Ciel", "done"),
    ]
    assert detail["changes"][0]["label"] == "Les Marées Hautes \u2013 Titre mp3"
    assert (await client.get("/media/journal/999.json")).status_code == 404


async def test_annuler_undoes_a_whole_lot_and_says_who(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3", "flac", "ogg"))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, "programmatrice"
    )
    entry = await _edit(client, ids, {"album": "Ciel"})
    # un titre changé depuis par quelqu'un d'autre
    await _edit(client, ids[2:], {"album": "Autre"})

    response = await client.post(f"/media/journal/{entry}/undo.json")

    assert response.status_code == 200, await response.get_data()
    outcome = await response.get_json()
    assert outcome["written"] == 2
    assert [title["id"] for title in outcome["kept"]] == [ids[2]]
    assert [MediaFile(beets.lib.get_item(i).path).album for i in ids] == [
        "Estuaire",
        "Estuaire",
        "Autre",
    ]
    page = await (await client.get("/media/journal.json")).get_json()
    undone = next(item for item in page["entries"] if item["id"] == entry)
    assert undone["undone_by"]["username"] == "programmatrice"
    assert undone["undoable"] is False
    assert undone["why_not"] == "Ce lot a déjà été défait."
    assert page["entries"][0]["gesture_label"] == "Annulation"
    assert page["entries"][0]["undo_of"] == entry
    assert page["entries"][0]["counts"]["kept"] == 1

    again = await client.post(f"/media/journal/{entry}/undo.json")
    assert again.status_code == 409


async def test_a_lot_older_than_30_days_is_not_undone(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, "programmatrice"
    )
    entry = await _edit(client, ids, {"album": "Ciel"})
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=31)
    await dbsession.execute(
        sql_update(JournalEntry).where(JournalEntry.id == entry).values(created=old)
    )
    await dbsession.commit()

    page = await (await client.get("/media/journal.json")).get_json()
    assert page["entries"][0]["undoable"] is False
    assert "30 jours" in page["entries"][0]["why_not"]
    response = await client.post(f"/media/journal/{entry}/undo.json")
    assert response.status_code == 409
    assert "30 jours" in (await response.get_json())["message"]
    assert MediaFile(beets.lib.get_item(ids[0]).path).album == "Ciel"


def test_a_gesture_without_undo_says_so():
    entry = JournalEntry(gesture="rename", created=datetime(2026, 11, 14, 12))
    assert journal.why_not_undoable(entry, None, datetime(2026, 11, 14, 13)) == (
        "Ce geste ne s'annule pas encore."
    )
