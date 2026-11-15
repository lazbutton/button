"""Les propositions sûres, par nature de changement (FON-79)."""

from __future__ import annotations

import random

import pytest

from radiotomate.models import Fiche, FicheProposition, Setting, User
from radiotomate.services import bank_titles
from radiotomate.services.fiches_natures import EXAMPLES, nature_groups, nature_of
from tests.scheduler.test_fiches_json import _beets
from tests.scheduler.test_studio_json import _interface_client, _login


@pytest.mark.parametrize(
    ("field", "before", "value", "nature"),
    [
        # La graphie : le même texte une fois normalisé.
        ("title", "feeling good", "Feeling Good", "graphie"),
        ("artist", "Beyonce", "Beyoncé", "graphie"),
        ("album", "L'amour  toujours", "L\u2019Amour toujours", "graphie"),
        ("label", "philips", "Philips", "graphie"),
        # Ce qui manquait.
        ("album", "", "Ciel", "album"),
        ("year", "0", "1965", "annee"),
        ("year", "", "1965", "annee"),
        ("label", "", "Philips", "label_isrc"),
        ("label", "Polydor", "Philips", "label_isrc"),
        ("isrc", "", "FRZ039800212", "label_isrc"),
        ("famille", "", "jazz", "famille"),
        ("famille", "rock", "jazz", "famille"),
        # Ce qui dit autre chose se relit titre par titre.
        ("title", "Feeling good", "Sinnerman", ""),
        ("album", "Ciel", "Nuages", ""),
        ("year", "1990", "1965", ""),
        ("fmg", "", "oui", ""),
        ("title", "Brume", "Brume", ""),
    ],
)
def test_each_nature_is_recognized(field, before, value, nature):
    assert nature_of(field, before, value) == nature


def _row(beets_id: int, title: str, artist: str = "Nina Simone") -> tuple:
    return (beets_id, f"/media/10-rotation/{beets_id}.mp3".encode(), title, artist)


def _rows(count: int) -> list[tuple]:
    return [
        (*_row(index, f"Titre {index:03d}"), "", 0, "", 180.0, None)
        for index in range(1, count + 1)
    ]


async def _fiche(dbsession, beets_id, propositions, *, level="sûr"):
    """(champ, avant, valeur[, niveau[, état]])"""
    fiche = Fiche(
        beets_id=beets_id,
        key=f"texte:{beets_id}",
        text_key=f"texte:{beets_id}",
        status="trouvé",
        level=level,
        reasons=[],
        source="Deezer",
        rules_version=1,
        propositions=[
            FicheProposition(
                field=one[0],
                before=one[1],
                value=one[2],
                level=one[3] if len(one) > 3 else level,
                source="Deezer",
                state=one[4] if len(one) > 4 else "proposée",
            )
            for one in propositions
        ],
    )
    dbsession.add(fiche)
    await dbsession.commit()
    return [one.id for one in fiche.propositions]


async def test_a_group_takes_only_sure_propositions_still_to_read(raw_app, dbsession):
    (spelled, album) = await _fiche(
        dbsession, 1, [("title", "feeling good", "Feeling Good"), ("album", "", "Ciel")]
    )
    # À revoir : jamais dans un groupe, même pour une simple casse.
    await _fiche(dbsession, 2, [("title", "so what", "So What", "à revoir")])
    # Déjà décidée : plus à relire.
    await _fiche(dbsession, 3, [("title", "brume", "Brume", "sûr", "refusée")])
    # Un titre sorti de la bibliothèque.
    await _fiche(dbsession, 99, [("title", "parti", "Parti")])

    groups = await nature_groups(dbsession, _rows(3))

    assert [group["nature"] for group in groups] == ["graphie", "album"]
    graphie, albums = groups
    assert (graphie["count"], graphie["titles"], graphie["ids"]) == (1, 1, [spelled])
    assert graphie["label"] == "La graphie : casse, accents, ponctuation"
    assert graphie["examples"] == [
        {
            "id": spelled,
            "beets_id": 1,
            "title": "Titre 001",
            "artist": "Nina Simone",
            "field": "title",
            "before": "feeling good",
            "value": "Feeling Good",
        }
    ]
    assert albums["ids"] == [album]


async def test_ten_examples_taken_at_random(raw_app, dbsession):
    for beets_id in range(1, 26):
        await _fiche(dbsession, beets_id, [("artist", "nina simone", "Nina Simone")])

    first = await nature_groups(dbsession, _rows(25), rng=random.Random(1))
    second = await nature_groups(dbsession, _rows(25), rng=random.Random(2))

    (group,) = first
    assert (group["count"], group["titles"], len(group["ids"])) == (25, 25, 25)
    shown = [example["id"] for example in group["examples"]]
    assert len(shown) == len(set(shown)) == EXAMPLES
    assert set(shown) <= set(group["ids"])
    assert shown != [example["id"] for example in second[0]["examples"]]


async def _client(app_configration, beets, dbsession, users_password, perms):
    user = User(username="programmatrice", permissions=perms)
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "programmatrice", users_password)
    return client


async def test_natures_json_and_the_nature_filter(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets = _beets(tmp_path)
    (spelled, added) = await _fiche(
        dbsession, 1, [("title", "feeling good", "Feeling Good"), ("year", "0", "1965")]
    )
    await _fiche(dbsession, 2, [("title", "sinnerman", "Sinner Man")])
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    closed = await client.get("/fiches/natures.json")
    assert closed.status_code == 409
    assert (await closed.get_json())["code"] == "bank_tidy_off"
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
    await dbsession.commit()

    response = await client.get("/fiches/natures.json")

    assert response.status_code == 200, await response.get_data()
    groups = {group["nature"]: group for group in (await response.get_json())["groups"]}
    assert groups["graphie"]["ids"] == [spelled]
    assert groups["annee"]["ids"] == [added]
    # « Sinner Man » n'est pas « sinnerman » écrit autrement : un mot de plus.
    assert "sinnerman" not in str(groups)

    # Ouvrir un groupe : la page de la vue, ses seules propositions.
    page = await (await client.get("/fiches.json?nature=graphie")).get_json()
    assert [title["id"] for title in page["titles"]] == [1]
    assert [one["id"] for one in page["titles"][0]["propositions"]] == [spelled]
    assert page["total"] == 1
    bad = await client.get("/fiches.json?nature=casse")
    assert bad.status_code == 400
    assert (await bad.get_json())["field"] == "nature"


async def test_natures_json_is_for_the_programmateur(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="1"))
    client = await _client(
        app_configration, _beets(tmp_path), dbsession, users_password, {"carts": True}
    )
    assert (await client.get("/fiches/natures.json")).status_code == 403
