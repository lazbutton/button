"""A selection composed by filters (FON-73): its Beets query, and its count."""

from __future__ import annotations

import pytest

from radiotomate.models import Setting, User
from radiotomate.services import bank_titles
from radiotomate.services.beets_query import validate_selection_query
from radiotomate.services.selection_filters import SelectionFilters, selection_query
from tests.scheduler.test_media_titles_json import _beets
from tests.scheduler.test_studio_json import _interface_client, _login


async def _client(app_configration, beets, dbsession, users_password):
    user = User(username="selection-json")
    user.update_password(users_password)
    dbsession.add(user)
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "selection-json", users_password)
    return client


@pytest.mark.parametrize(
    ("args", "query"),
    [
        ({"famille": "jazz"}, "famille:=jazz"),
        ({"collection": "rotation"}, "path:/media/10-rotation"),
        ({"collection": "nuit"}, "path:/media/20-archives/nuit"),
        ({"artist": "Madame Orage"}, "'artist:=~Madame Orage'"),
        ({"album": "L'été"}, "'album:=~L'\"'\"'été'"),
        ({"genre": "Jazz"}, "genre:=~Jazz"),
        ({"year_from": "2015"}, "year:2015.."),
        ({"year_from": "2015", "year_to": "2019"}, "year:2015..2019"),
        ({"year_to": "1999"}, "year:1..1999"),
        ({"artist": "Earth, Wind,"}, "'artist::(?i)^Earth\\,\\ Wind\\,$'"),
        (
            {"famille": "jazz", "year_from": "2015", "collection": "nuit"},
            "famille:=jazz path:/media/20-archives/nuit year:2015..",
        ),
    ],
)
def test_each_filter_gives_a_valid_query(args, query):
    written = selection_query(SelectionFilters.from_args(args))
    assert written == query
    validate_selection_query(written)


def test_the_genre_follows_the_version_of_beets():
    filters = SelectionFilters.from_args({"genre": "Jazz"})
    assert selection_query(filters, genre_field="genres") == "genres:=~Jazz"


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"year_from": "15"},
        {"year_from": "2020", "year_to": "2010"},
        {"collection": "../x"},
    ],
)
def test_a_wrong_composition_is_refused(args):
    from radiotomate.domain.errors import DomainValidationError

    with pytest.raises(DomainValidationError):
        selection_query(SelectionFilters.from_args(args))


async def test_the_selection_counts_as_the_table(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    for args in (
        "artist=Orage",
        "famille=jazz&collection=nuit",
        "famille=jazz&year_from=2016",
        "genre=Jazz&year_from=2010&year_to=2016",
        "collection=rotation",
        "album=Ciel",
    ):
        composed = await (await client.get(f"/media/selection.json?{args}")).get_json()
        table = await (
            await client.get(f"/media/titles.json?{args}&limit=500")
        ).get_json()
        assert composed["count"] == table["matched"], args
        assert sorted(row["title"] for row in composed["sample"]) == sorted(
            row["title"] for row in table["titles"]
        ), args
        # The query the console saves counts the same, as the auto-DJ will.
        tested = await client.get(
            "/autodj/testquery.json",
            query_string={"query": composed["query"]},
        )
        assert (await tested.get_json())["count"] == composed["count"], args


async def test_an_artist_whose_name_is_in_another(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    payload = await (await client.get("/media/selection.json?artist=Orage")).get_json()
    assert payload["query"] == "artist:=~Orage"
    assert sorted(row["artist"] for row in payload["sample"]) == ["Orage", "Orage"]


async def test_no_filter_is_refused(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password
    )
    response = await client.get("/media/selection.json")
    assert response.status_code == 400
