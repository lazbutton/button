"""Le verdict dans le tableau de la banque (FON-80) : allumé, une colonne, un
filtre, un rangement et sa part dans « La banque en chiffres » ; éteint, aucune
trace dans les réponses du moteur. Sur une bibliothèque temporaire."""

from __future__ import annotations

import pytest

from radiotomate.interface import bank_health as route
from radiotomate.models import Fiche, FicheProposition, Setting, User
from radiotomate.services import bank_titles
from radiotomate.services.fiches import SETTING_FMG
from tests.scheduler.test_media_titles_json import TITLES, _beets
from tests.scheduler.test_studio_json import _interface_client, _login

VERDICTS = {"Dune": "oui", "Brume": "oui", "Comète": "mixte", "Été indien": "non"}


def _with_verdicts(tmp_path):
    beets = _beets(tmp_path)
    for item in beets.lib.items():
        if item.title in VERDICTS:
            item["fmg"] = VERDICTS[item.title]
            item["fmg_source"] = "MusicBrainz : 1 membre connu sur 1"
            item.store()
    return beets


async def _client(app_configration, beets, dbsession, users_password):
    """Une programmatrice : le tableau, la Santé et les fiches lui sont ouverts."""
    user = User(username="nadia", permissions={"autodj": True})
    user.update_password(users_password)
    dbsession.add(user)
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "nadia", users_password)
    return client


@pytest.fixture(autouse=True)
def _fresh_counts():
    route.forget()
    yield
    route.forget()


async def _body(client, path: str) -> str:
    response = await client.get(path)
    assert response.status_code == 200, (path, await response.get_data())
    return (await response.get_data()).decode()


async def _with_a_proposed_verdict(dbsession, beets) -> int:
    beets_id = next(iter(beets.lib.items())).id
    dbsession.add(
        Fiche(
            beets_id=beets_id,
            key="texte:un",
            text_key="texte:un",
            status="trouvé",
            level="sûr",
            reasons=[],
            rules_version=1,
            propositions=[
                FicheProposition(
                    field="fmg", before="", value="oui", level="sûr", state="proposée"
                )
            ],
        )
    )
    await dbsession.commit()
    return beets_id


async def test_switched_off_the_verdict_leaves_no_trace(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, monkeypatch
):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    beets = _with_verdicts(tmp_path)
    client = await _client(app_configration, beets, dbsession, users_password)
    beets_id = await _with_a_proposed_verdict(dbsession, beets)

    await _body(client, "/media/health.json")
    await route.settle()
    for path in (
        "/account.json",
        "/media/titles.json?facets=famille",
        "/media/health.json",
        "/fiches.json",
        "/fiches.json?level=s%C3%BBr",
        f"/fiches/{beets_id}.json",
        "/fiches/familles.json",
    ):
        body = await _body(client, path)
        assert "fmg" not in body, path
        assert "verdict" not in body.lower(), path

    # Ni tri, ni rangement, ni filtre : un nom que le tableau ne connaît pas.
    for query in ("?sort=fmg", "?facets=fmg"):
        response = await client.get(f"/media/titles.json{query}")
        assert response.status_code == 400, query
    filtered = await (await client.get("/media/titles.json?fmg=oui")).get_json()
    assert filtered["matched"] == len(TITLES)
    refused = await client.get("/fiches.json?field=fmg")
    assert refused.status_code == 400


async def test_switched_on_a_column_a_filter_and_its_share(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, monkeypatch
):
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    beets = _with_verdicts(tmp_path)
    client = await _client(app_configration, beets, dbsession, users_password)
    dbsession.add(Setting(key=SETTING_FMG, value="1"))
    await dbsession.commit()

    account = await (await client.get("/account.json")).get_json()
    assert account["features"]["fiches_fmg"] is True

    page = await (await client.get("/media/titles.json?sort=fmg&facets=fmg")).get_json()
    assert [(row["title"], row["fmg"]) for row in page["titles"]][:4] == [
        ("Brume", "oui"),
        ("Dune", "oui"),
        ("Comète", "mixte"),
        ("Été indien", "non"),
    ]
    assert page["titles"][-1]["fmg"] == ""
    assert page["facets"]["fmg"] == [
        {"value": "mixte", "label": "Mixte", "count": 1},
        {"value": "non", "label": "Non", "count": 1},
        {"value": "oui", "label": "Oui", "count": 2},
        {"value": "", "label": "", "count": len(TITLES) - 4},
    ]
    oui = await (await client.get("/media/titles.json?fmg=oui")).get_json()
    assert sorted(row["title"] for row in oui["titles"]) == ["Brume", "Dune"]
    # Donné vide, le filtre prend les titres sans verdict.
    none = await (await client.get("/media/titles.json?fmg=")).get_json()
    assert none["matched"] == len(TITLES) - 4

    await _body(client, "/media/health.json")
    await route.settle()
    health = (await (await client.get("/media/health.json")).get_json())["health"]
    assert health["figures"]["verdicts"] == {"oui": 2, "mixte": 1, "non": 1}
    # Les listes de titres de la Santé ne portent jamais le verdict.
    assert "fmg" not in str(
        {key: value for key, value in health.items() if key != "figures"}
    )


async def test_the_tidying_off_the_table_still_reads_its_verdict(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, monkeypatch
):
    # FON-85 : coupé, l'interrupteur général laisse le tableau en lecture, la
    # colonne du verdict comprise quand il est allumé.
    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path / "media"))
    beets = _with_verdicts(tmp_path)
    client = await _client(app_configration, beets, dbsession, users_password)
    await Setting.upsert(dbsession, bank_titles.SETTING_BANK_TIDY, "0")
    dbsession.add(Setting(key=SETTING_FMG, value="1"))
    await dbsession.commit()

    account = await (await client.get("/account.json")).get_json()
    assert account["features"]["bank_tidy"] is False
    assert account["features"]["fiches_fmg"] is True
    oui = await (await client.get("/media/titles.json?fmg=oui&facets=fmg")).get_json()
    assert sorted(row["title"] for row in oui["titles"]) == ["Brume", "Dune"]
    assert {facet["value"] for facet in oui["facets"]["fmg"]} == {
        "oui",
        "mixte",
        "non",
        "",
    }
