"""Poser et retirer les étiquettes de la station sur un lot (FON-74).

Sur de vrais fichiers, comme les tests de FON-66 : une étiquette ne vit que dans
la bibliothèque, jamais dans le fichier, et le geste se note au journal.
"""

from __future__ import annotations

import pytest

from radiotomate.domain.errors import DomainValidationError
from radiotomate.models import MusicCategory, User
from radiotomate.services import station_tags
from radiotomate.services.beets_query import validate_selection_query
from radiotomate.services.station_tags import (
    clean_field,
    clean_tag,
    format_tags,
    parse_tags,
    tag_query,
    with_tags,
)
from radiotomate.services.title_edits import TitleEditsOff, undo_entry
from radiotomate.services.title_tags import tag_titles
from tests.scheduler.test_studio_json import _interface_client, _login
from tests.scheduler.test_title_edits import _bank, _entries, _open

TAGS = "/media/titles/tags.json"


@pytest.mark.parametrize(
    ("raw", "tag"),
    [
        ("nuit", "nuit"),
        ("  Fin   de SOIRÉE ", "fin de soirée"),
        # la même lettre, composée ou non
        ("été", "été"),
        ("x" * station_tags.MAX_TAG, "x" * station_tags.MAX_TAG),
    ],
)
def test_clean_tag(raw, tag):
    assert clean_tag(raw) == tag


@pytest.mark.parametrize(
    "raw",
    [
        *("", "   ", "a|b", "nuit,", "a,b", 'dit "oui"', "a\\b", "a\tb\x00"),
        *(None, 3, "x" * (station_tags.MAX_TAG + 1)),
    ],
)
def test_clean_tag_refuses(raw):
    with pytest.raises(DomainValidationError):
        clean_tag(raw)


def test_the_field_keeps_its_tags_sorted_between_separators():
    assert format_tags(["nuit", "instrumental", "nuit"]) == "|instrumental|nuit|"
    assert format_tags([]) == ""
    assert parse_tags("|instrumental|nuit|") == ["instrumental", "nuit"]
    assert parse_tags(None) == parse_tags("") == []
    assert with_tags("|instrumental|", ["nuit"], []) == "|instrumental|nuit|"
    assert with_tags("|instrumental|nuit|", [], ["nuit"]) == "|instrumental|"
    assert with_tags("|nuit|", [], ["nuit"]) == ""
    assert clean_field("|Nuit|instrumental|") == "|instrumental|nuit|"
    assert clean_field("") == ""
    with pytest.raises(DomainValidationError):
        clean_field("|a,b|")


def test_the_query_of_a_tag_is_valid():
    validate_selection_query(tag_query("nuit"))
    assert tag_query("nuit") == "etiquettes:|nuit|"


async def test_tags_are_put_and_taken_off_without_touching_the_file(
    raw_app, dbsession, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    first = beets.lib.get_item(ids[0])
    first["etiquettes"] = "|instrumental|"
    first.store()
    before = [beets.lib.get_item(beets_id).filepath.read_bytes() for beets_id in ids]

    put = await tag_titles(
        dbsession, beets, ids, ["Nuit"], [], username="programmatrice"
    )

    assert put.written == ids
    assert beets.lib.get_item(ids[0])["etiquettes"] == "|instrumental|nuit|"
    assert beets.lib.get_item(ids[1])["etiquettes"] == "|nuit|"
    after = [beets.lib.get_item(beets_id).filepath.read_bytes() for beets_id in ids]
    assert after == before
    (entry,) = await _entries(dbsession)
    assert (entry.gesture, entry.titles) == ("edit", 2)

    off = await tag_titles(
        dbsession, beets, ids, [], ["instrumental"], username="programmatrice"
    )

    # un titre qui n'a pas l'étiquette reste tel quel
    assert (off.written, off.unchanged) == ([ids[0]], [ids[1]])
    assert beets.lib.get_item(ids[0])["etiquettes"] == "|nuit|"

    last = await tag_titles(
        dbsession, beets, ids, [], ["nuit"], username="programmatrice"
    )

    assert last.written == ids
    assert all("etiquettes" not in beets.lib.get_item(beets_id) for beets_id in ids)

    # « Revenir » sur la pose remet chaque titre comme avant elle
    await undo_entry(dbsession, beets, last.entry_id, username="programmatrice")
    await undo_entry(dbsession, beets, off.entry_id, username="programmatrice")
    assert beets.lib.get_item(ids[0])["etiquettes"] == "|instrumental|nuit|"
    assert beets.lib.get_item(ids[1])["etiquettes"] == "|nuit|"


async def test_the_try_names_the_selections_a_tag_feeds(raw_app, dbsession, tmp_path):
    beets, ids = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    dbsession.add_all(
        [
            MusicCategory(name="Nuit", query="etiquettes:|nuit|"),
            MusicCategory(name="Minuit", query="etiquettes:|minuit|"),
        ]
    )
    await dbsession.commit()

    outcome = await tag_titles(
        dbsession, beets, ids, ["nuit"], [], username="programmatrice", dry_run=True
    )

    assert {(s.name, s.gained, s.lost) for s in outcome.selections} == {("Nuit", 2, 0)}
    assert all("etiquettes" not in beets.lib.get_item(beets_id) for beets_id in ids)
    assert await _entries(dbsession) == []


@pytest.mark.parametrize(
    ("ids", "add", "remove", "field"),
    [
        ([], ["nuit"], [], "ids"),
        ("1", ["nuit"], [], "ids"),
        ([1, 1], ["nuit"], [], "ids"),
        ([True], ["nuit"], [], "ids"),
        ([1], [], [], "add"),
        ([1], "nuit", [], "add"),
        ([1], ["a|b"], [], "add"),
        ([1], [], ["nuit,"], "remove"),
        ([1], ["nuit"], ["Nuit"], "remove"),
    ],
)
async def test_a_wrong_gesture_is_refused(  # noqa: PLR0913
    raw_app, dbsession, tmp_path, ids, add, remove, field
):
    beets, _ = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    with pytest.raises(DomainValidationError) as refused:
        await tag_titles(dbsession, beets, ids, add, remove, username="programmatrice")
    assert refused.value.field == field


async def test_tags_wait_for_the_switch(raw_app, dbsession, tmp_path):
    beets, ids = _bank(tmp_path, ("mp3",))
    with pytest.raises(TitleEditsOff):
        await tag_titles(dbsession, beets, ids, ["nuit"], [], username="programmatrice")
    assert "etiquettes" not in beets.lib.get_item(ids[0])


async def _client(app_configration, beets, dbsession, users_password, perms):
    user = User(username="programmatrice", permissions=perms)
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "programmatrice", users_password)
    return client


async def test_tags_json(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    tried = await client.post(TAGS, json={"ids": ids, "add": ["nuit"], "dry_run": True})
    assert tried.status_code == 200, await tried.get_data()
    assert (await tried.get_json())["dry_run"] is True
    assert "etiquettes" not in beets.lib.get_item(ids[0])

    response = await client.post(TAGS, json={"ids": ids, "add": ["nuit"]})

    assert response.status_code == 200, await response.get_data()
    payload = await response.get_json()
    assert (payload["dry_run"], payload["written"]) == (False, 2)
    assert beets.lib.get_item(ids[0])["etiquettes"] == "|nuit|"
    table = await (
        await client.get("/media/titles.json?etiquette=nuit&facets=etiquette")
    ).get_json()
    assert table["matched"] == 2
    assert table["facets"]["etiquette"] == [
        {"value": "nuit", "label": "nuit", "count": 2}
    ]
    undo = await client.post(f"/media/journal/{payload['entry']}/undo.json")
    assert undo.status_code == 200, await undo.get_data()
    assert "etiquettes" not in beets.lib.get_item(ids[0])

    refused = await client.post(TAGS, json={"ids": ids, "add": ["a|b"]})
    assert refused.status_code == 400
    assert (await refused.get_json())["field"] == "add"


async def test_tags_json_is_for_the_programmateur(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, ids = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, {"carts": True}
    )
    response = await client.post(TAGS, json={"ids": ids, "add": ["nuit"]})
    assert response.status_code == 403
    assert "etiquettes" not in beets.lib.get_item(ids[0])
