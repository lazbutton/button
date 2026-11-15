"""Les familles, le verdict et les sélections de titres (FON-28), sur une vraie
bibliothèque Beets temporaire."""

from __future__ import annotations

from sqlalchemy import select

from radiotomate.models import (
    Fiche,
    FicheDecision,
    FicheProposition,
    MusicCategory,
    Setting,
    User,
)
from radiotomate.services.fiches import SETTING_FMG
from tests.scheduler.test_studio_json import _interface_client, _login
from tests.scheduler.test_title_edits import _bank, _open


def _mark(beets, beets_id, **fields):
    """Des champs flexibles, comme une proposition acceptée les écrit."""
    item = beets.lib.get_item(beets_id)
    for name, value in fields.items():
        item[name] = value
    item.store()


async def _client(app_configration, beets, dbsession, users_password, perms):
    user = User(username="nadia", permissions=perms)
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "nadia", users_password)
    return client


async def _selections(dbsession, *pairs):
    for name, query in pairs:
        dbsession.add(MusicCategory(name=name, query=query, empty_query=""))
    await dbsession.commit()


async def _counts(client) -> dict[str, int]:
    response = await client.get("/autodj/categories.json")
    return {
        one["name"]: one["count"] for one in (await response.get_json())["categories"]
    }


async def test_the_families_meet_the_selections(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, (one, two, three, four) = _bank(tmp_path, ("mp3", "flac", "ogg", "opus"))
    _mark(beets, one, famille="jazz")
    _mark(beets, two, famille="jazz")
    _mark(beets, three, famille="soul-funk")
    await _open(dbsession)
    await _selections(dbsession, ("Jazz", "famille:jazz"), ("Soul", "genres:Soul"))
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    response = await client.get("/fiches/familles.json")

    assert response.status_code == 200, await response.get_data()
    payload = await response.get_json()
    assert payload["library"] == 4
    # Le verdict éteint, la réponse n'en dit rien (FON-80).
    assert "verdict" not in payload
    selections = {one["name"]: one for one in payload["selections"]}
    assert selections["Jazz"]["count"] == 2
    assert selections["Jazz"]["families"] == [
        {"value": "jazz", "label": "Jazz", "count": 2}
    ]
    assert selections["Soul"]["count"] == 0
    assert "reads_verdict" not in selections["Jazz"]
    families = {one["value"]: one for one in payload["families"]}
    # Dans l'ordre des familles de Hopper, les titres sans famille à la fin.
    assert [one["value"] for one in payload["families"]] == ["jazz", "soul-funk", ""]
    assert (families["jazz"]["count"], families["jazz"]["uncategorized"]) == (2, 0)
    assert families["jazz"]["selections"] == [
        {"id": selections["Jazz"]["id"], "name": "Jazz", "count": 2}
    ]
    assert (families["soul-funk"]["count"], families["soul-funk"]["uncategorized"]) == (
        1,
        1,
    )
    assert [title["id"] for title in families["soul-funk"]["sample"]] == [three]
    assert (families[""]["count"], families[""]["uncategorized"]) == (1, 1)
    assert families[""]["sample"][0]["id"] == four

    # Accepté quand : une sélection famille:jazz compte les titres de famille jazz.
    assert (await _counts(client))["Jazz"] == 2


async def test_the_share_of_oui_reads_the_known_verdicts(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, (one, two, three) = _bank(tmp_path, ("mp3", "flac", "ogg"))
    _mark(beets, one, fmg="oui", fmg_source="MusicBrainz")
    _mark(beets, two, fmg="oui", fmg_source="Wikidata")
    _mark(beets, three, fmg="non", fmg_source="MusicBrainz")
    await _open(dbsession)
    dbsession.add(Setting(key=SETTING_FMG, value="1"))
    await dbsession.commit()
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    payload = await (await client.get("/fiches.json")).get_json()

    assert payload["verdict"] is True
    assert payload["verdicts"] == {"oui": 2, "mixte": 0, "non": 1}


async def test_erasing_the_verdicts_names_the_selections_then_empties_them(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, (one, two, three) = _bank(tmp_path, ("mp3", "flac", "ogg"))
    _mark(beets, one, fmg="oui", fmg_source="MusicBrainz", famille="jazz")
    _mark(beets, two, fmg="mixte", fmg_source="Wikidata")
    await _open(dbsession)
    await _selections(
        dbsession, ("Femmes", "fmg:oui"), ("Jazz", "famille:jazz -fmg:non")
    )
    fiche = Fiche(
        beets_id=three,
        key="texte:trois",
        text_key="texte:trois",
        status="trouvé",
        level="sûr",
        reasons=[],
        rules_version=1,
        propositions=[
            FicheProposition(
                field="fmg", before="", value="oui", level="sûr", state="proposée"
            ),
            FicheProposition(
                field="album", before="Estuaire", value="Ciel", level="sûr"
            ),
        ],
    )
    dbsession.add(fiche)
    dbsession.add(
        FicheDecision(
            key="texte:un",
            field="fmg",
            value="oui",
            decision="acceptée",
            username="nadia",
        )
    )
    await dbsession.commit()
    admin = await _client(
        app_configration, beets, dbsession, users_password, {"admin": True}
    )
    assert (await _counts(admin))["Femmes"] == 1

    # La console nomme d'abord les sélections qui se videront.
    summary = await (await admin.get("/fiches/verdicts.json")).get_json()
    assert (summary["titles"], summary["waiting"]) == (2, 1)
    assert [(one["name"], one["count"]) for one in summary["selections"]] == [
        ("Femmes", 1),
        ("Jazz", 1),
    ]

    response = await admin.post("/fiches/verdicts/effacer.json")

    assert response.status_code == 200, await response.get_data()
    assert (await response.get_json())["titles"] == 2
    for beets_id in (one, two):
        item = beets.lib.get_item(beets_id)
        assert "fmg" not in item
        assert "fmg_source" not in item
    assert beets.lib.get_item(one)["famille"] == "jazz"
    assert (await _counts(admin))["Femmes"] == 0
    left = list(await dbsession.scalars(select(FicheProposition.field)))
    assert left == ["album"]
    assert await dbsession.scalar(select(FicheDecision)) is None


async def test_a_programmateur_cannot_erase_the_verdicts(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, (one,) = _bank(tmp_path, ("mp3",))
    _mark(beets, one, fmg="oui")
    await _open(dbsession)
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    response = await client.post("/fiches/verdicts/effacer.json")

    assert response.status_code == 403
    assert beets.lib.get_item(one)["fmg"] == "oui"
    assert (await client.get("/fiches/verdicts.json")).status_code == 200


async def test_the_switch_off_keeps_them_closed(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, (one,) = _bank(tmp_path, ("mp3",))
    _mark(beets, one, fmg="oui")
    client = await _client(
        app_configration, beets, dbsession, users_password, {"admin": True}
    )
    for method, path in (
        ("get", "/fiches/familles.json"),
        ("get", "/fiches/verdicts.json"),
        ("post", "/fiches/verdicts/effacer.json"),
    ):
        response = await getattr(client, method)(path)
        assert response.status_code == 409, path
    assert beets.lib.get_item(one)["fmg"] == "oui"
