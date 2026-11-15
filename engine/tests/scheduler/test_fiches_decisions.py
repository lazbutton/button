"""Accepter, refuser, revenir et chercher de nouveau (FON-27), sur de vrais fichiers
et une vraie bibliothèque Beets temporaire."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest
from mediafile import MediaFile
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from radiotomate.domain.errors import DomainConflict, DomainError, DomainValidationError
from radiotomate.models import (
    Fiche,
    FicheDecision,
    FicheProposition,
    JournalEntry,
    Setting,
    User,
)
from radiotomate.models.fiche import utcnow
from radiotomate.services import fiches_decisions
from radiotomate.services.fiches import SETTING_ENABLED, SETTING_FMG
from radiotomate.services.fiches_decisions import SEARCH_FIRST, decide, write_accepted
from radiotomate.services.title_edits import (
    SETTING_TITLE_EDITS,
    apply_waiting,
    undo_entry,
)
from tests.scheduler.test_studio_json import _interface_client, _login
from tests.scheduler.test_title_edits import _bank, _line, _open

DECISIONS = "/fiches/decisions.json"


def _written_elsewhere(beets, beets_id, album):
    """Un autre outil récrit l'album dans le fichier, plus tard."""
    item = beets.lib.get_item(beets_id)
    other = MediaFile(item.path)
    other.album = album
    other.save()
    later = item.mtime + 10
    os.utime(item.path, (later, later))


async def _fiche(dbsession, beets_id, proposals, *, level="sûr", key=None):
    """Une fiche cherchée, et ses propositions : (champ, avant, valeur[, niveau])."""
    fiche = Fiche(
        beets_id=beets_id,
        key=key or f"texte:titre-{beets_id}",
        text_key=f"texte:titre-{beets_id}",
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
                state="proposée",
            )
            for one in proposals
        ],
    )
    dbsession.add(fiche)
    await dbsession.commit()
    return [proposition.id for proposition in fiche.propositions]


async def _verdict_on(dbsession):
    dbsession.add(Setting(key=SETTING_FMG, value="1"))
    await dbsession.commit()


async def _states(dbsession, ids):
    rows = await dbsession.scalars(
        select(FicheProposition)
        .where(FicheProposition.id.in_(ids))
        .execution_options(populate_existing=True)
    )
    return {row.id: (row.state, row.error) for row in rows}


async def _fiche_of(dbsession, beets_id):
    return await dbsession.scalar(
        select(Fiche)
        .where(Fiche.beets_id == beets_id)
        .options(selectinload(Fiche.propositions))
        .execution_options(populate_existing=True)
    )


async def test_accepting_writes_the_file_then_beets_and_the_journal(
    raw_app, dbsession, tmp_path
):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(
        dbsession,
        mp3,
        [
            ("album", "Estuaire", "Ciel"),
            ("year", "2019", "1965"),
            ("label", "", "Philips"),
        ],
    )

    outcome = await decide(dbsession, beets, ids, [], username="programmatrice")

    assert (outcome.accepted, outcome.written, outcome.waiting, outcome.failed) == (
        3,
        3,
        [],
        [],
    )
    tags = MediaFile(beets.lib.get_item(mp3).path)
    assert (tags.album, tags.year, tags.label) == ("Ciel", 1965, "Philips")
    item = beets.lib.get_item(mp3)
    assert (item.album, item.year, item.label) == ("Ciel", 1965, "Philips")
    # La date du fichier est notée : la boucle d'import ne le relit pas pour rien.
    assert int(item.mtime) == int(Path(os.fsdecode(item.path)).stat().st_mtime)
    assert set((await _states(dbsession, ids)).values()) == {("écrite", "")}
    entry = await dbsession.scalar(select(JournalEntry))
    assert (entry.gesture, entry.username, outcome.entry) == (
        "accept",
        "programmatrice",
        entry.id,
    )
    decisions = list(await dbsession.scalars(select(FicheDecision)))
    assert {(one.field, one.value, one.decision) for one in decisions} == {
        ("album", "Ciel", "acceptée"),
        ("year", "1965", "acceptée"),
        ("label", "Philips", "acceptée"),
    }


async def test_the_family_and_the_verdict_never_touch_the_file(
    raw_app, dbsession, tmp_path
):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    before = Path(os.fsdecode(beets.lib.get_item(mp3).path)).stat().st_mtime
    await _verdict_on(dbsession)
    ids = await _fiche(dbsession, mp3, [("famille", "", "jazz"), ("fmg", "", "oui")])
    fiche = await _fiche_of(dbsession, mp3)
    fiche.propositions[1].source = "MusicBrainz : 4 membres connus sur 4 en 1989"
    await dbsession.commit()

    outcome = await decide(dbsession, beets, ids, [], username="programmatrice")

    assert outcome.written == 2
    item = beets.lib.get_item(mp3)
    assert (item["famille"], item["fmg"]) == ("jazz", "oui")
    assert item["fmg_source"] == "MusicBrainz : 4 membres connus sur 4 en 1989"
    assert Path(os.fsdecode(item.path)).stat().st_mtime == before


async def test_refusing_keeps_the_decision_and_writes_nothing(
    raw_app, dbsession, tmp_path
):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])

    outcome = await decide(dbsession, beets, [], ids, username="programmatrice")

    assert (outcome.refused, outcome.written) == (1, 0)
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Estuaire"
    assert (await _states(dbsession, ids))[ids[0]] == ("refusée", "")
    decision = await dbsession.scalar(select(FicheDecision))
    assert (decision.key, decision.decision) == (f"texte:titre-{mp3}", "refusée")
    assert await dbsession.scalar(select(JournalEntry)) is None


async def test_a_title_in_queue_waits_then_its_proposition_is_written(
    raw_app, dbsession, tmp_path
):
    beets, (queued,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    line = await _line(dbsession, queued, "in_queue")
    ids = await _fiche(dbsession, queued, [("album", "Estuaire", "Ciel")])

    outcome = await decide(dbsession, beets, ids, [], username="programmatrice")

    assert [issue["code"] for issue in outcome.waiting] == ["queued"]
    assert MediaFile(beets.lib.get_item(queued).path).album == "Estuaire"
    state, error = (await _states(dbsession, ids))[ids[0]]
    assert state == "acceptée"
    assert "en file" in error

    # Le titre passé, l'écriture qui attendait se fait ; la proposition le suit.
    line.status = "played"
    await dbsession.commit()
    assert await apply_waiting(dbsession, beets) == 1
    assert await write_accepted(dbsession, beets) == 0
    assert (await _states(dbsession, ids))[ids[0]] == ("écrite", "")
    assert MediaFile(beets.lib.get_item(queued).path).album == "Ciel"


async def test_a_read_only_file_says_so_and_nothing_changes(
    raw_app, dbsession, tmp_path
):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    path = beets.lib.get_item(mp3).path
    Path(os.fsdecode(path)).chmod(0o444)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    try:
        outcome = await decide(dbsession, beets, ids, [], username="programmatrice")
    finally:
        Path(os.fsdecode(path)).chmod(0o644)

    assert [issue["code"] for issue in outcome.failed] == ["read_only"]
    state, error = (await _states(dbsession, ids))[ids[0]]
    assert state == "en erreur"
    assert "droit d'écrire" in error
    assert MediaFile(path).album == "Estuaire"
    assert beets.lib.get_item(mp3).album == "Estuaire"


async def test_a_value_the_write_service_refuses_says_why(raw_app, dbsession, tmp_path):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(
        dbsession, mp3, [("famille", "", "inconnue"), ("album", "Estuaire", "Ciel")]
    )

    outcome = await decide(dbsession, beets, ids, [], username="programmatrice")

    assert [issue["code"] for issue in outcome.failed] == ["invalid"]
    states = await _states(dbsession, ids)
    assert states[ids[0]][0] == "en erreur"
    assert "famille" in states[ids[0]][1]
    assert states[ids[1]][0] == "acceptée"
    # L'autre s'écrit au passage suivant de la tâche de fond.
    await dbsession.execute(
        FicheProposition.__table__.update()
        .where(FicheProposition.id == ids[1])
        .values(modified=utcnow() - timedelta(minutes=2))
    )
    await dbsession.commit()
    assert await write_accepted(dbsession, beets) == 1
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Ciel"


async def test_a_value_changed_since_is_stale(raw_app, dbsession, tmp_path):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    _written_elsewhere(beets, mp3, "Marée basse")

    with pytest.raises(DomainConflict):
        await decide(dbsession, beets, ids, [], username="programmatrice")

    assert (await _states(dbsession, ids))[ids[0]][0] == "périmée"
    assert (await _fiche_of(dbsession, mp3)).next_at == SEARCH_FIRST
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Marée basse"
    assert await dbsession.scalar(select(FicheDecision)) is None


async def test_a_lot_that_mixes_levels_across_titles_is_refused(
    raw_app, dbsession, tmp_path
):
    beets, (one, two) = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    sure = await _fiche(dbsession, one, [("album", "Estuaire", "Ciel")])
    review = await _fiche(
        dbsession, two, [("album", "Estuaire", "Ciel")], level="à revoir"
    )

    with pytest.raises(DomainValidationError):
        await decide(dbsession, beets, sure + review, [], username="programmatrice")
    assert set((await _states(dbsession, sure + review)).values()) == {("proposée", "")}

    # Seul, un titre à revoir s'accepte.
    outcome = await decide(dbsession, beets, review, [], username="programmatrice")
    assert outcome.written == 1


async def test_revenir_gives_back_the_value_before(raw_app, dbsession, tmp_path):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    await decide(dbsession, beets, ids, [], username="programmatrice")

    outcome = await fiches_decisions.revert(
        dbsession, beets, ids[0], username="programmatrice"
    )

    assert outcome.written == 1
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Estuaire"
    assert beets.lib.get_item(mp3).album == "Estuaire"
    assert (await _states(dbsession, ids))[ids[0]] == ("revenue", "")
    # L'acceptation est oubliée : un fichier revenu ne la reçoit plus.
    assert await dbsession.scalar(select(FicheDecision)) is None
    with pytest.raises(DomainConflict):
        await fiches_decisions.revert(
            dbsession, beets, ids[0], username="programmatrice"
        )


async def test_annuler_in_the_journal_brings_the_proposition_back(
    raw_app, dbsession, tmp_path
):
    """« Annuler » le lot d'une acceptation dans le journal (FON-71) : la valeur
    d'avant revient, et la proposition le dit."""
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    outcome = await decide(dbsession, beets, ids, [], username="programmatrice")

    await undo_entry(dbsession, beets, outcome.entry, username="programmatrice")
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Estuaire"
    await write_accepted(dbsession, beets)

    assert (await _states(dbsession, ids))[ids[0]] == ("revenue", "")


async def test_revenir_keeps_a_value_changed_since(raw_app, dbsession, tmp_path):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    await decide(dbsession, beets, ids, [], username="programmatrice")
    _written_elsewhere(beets, mp3, "Marée basse")

    with pytest.raises(DomainConflict):
        await fiches_decisions.revert(
            dbsession, beets, ids[0], username="programmatrice"
        )
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Marée basse"
    assert (await _states(dbsession, ids))[ids[0]][0] == "écrite"


async def test_a_decision_applied_to_a_file_that_came_back_is_written(
    raw_app, dbsession, tmp_path
):
    """Un fichier revenu sous un autre identifiant : la recherche remet sa
    proposition « acceptée » d'après la décision gardée ; la tâche de fond
    l'écrit."""
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    dbsession.add(
        FicheDecision(
            key=f"texte:titre-{mp3}",
            field="album",
            value="Ciel",
            decision="acceptée",
            username="programmatrice",
        )
    )
    fiche = await _fiche_of(dbsession, mp3)
    fiche.propositions[0].state = "acceptée"
    await dbsession.commit()

    # Pas tout de suite : un geste peut être en train de l'écrire.
    assert await write_accepted(dbsession, beets) == 0
    fiche.propositions[0].modified = utcnow() - timedelta(minutes=2)
    await dbsession.commit()
    await dbsession.execute(
        FicheProposition.__table__.update()
        .where(FicheProposition.id == ids[0])
        .values(modified=utcnow() - timedelta(minutes=2))
    )
    await dbsession.commit()

    assert await write_accepted(dbsession, beets) == 1
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Ciel"
    assert (await _states(dbsession, ids))[ids[0]] == ("écrite", "")
    entry = await dbsession.scalar(select(JournalEntry))
    assert (entry.gesture, entry.username) == ("accept", "programmatrice")


async def test_z_after_accepting_writes_back_and_proposes_again(
    raw_app, dbsession, tmp_path
):
    """« Z » de la relecture au clavier (FON-78) : le titre revient comme avant le
    geste, et se relit de nouveau."""
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    # Le verdict ne se décide qu'allumé (FON-80).
    await _verdict_on(dbsession)
    ids = await _fiche(
        dbsession, mp3, [("album", "Estuaire", "Ciel"), ("fmg", "", "oui")]
    )
    accepted = await decide(dbsession, beets, ids, [], username="programmatrice")
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Ciel"

    outcome = await fiches_decisions.reopen(
        dbsession, beets, ids, username="programmatrice"
    )

    assert (outcome.written, outcome.waiting) == (2, [])
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Estuaire"
    item = beets.lib.get_item(mp3)
    assert (item.album, item.get("fmg", ""), item.get("fmg_source", "")) == (
        "Estuaire",
        "",
        "",
    )
    assert set((await _states(dbsession, ids)).values()) == {("proposée", "")}
    assert await dbsession.scalar(select(FicheDecision)) is None
    undo = await JournalEntry.from_id(dbsession, outcome.entry)
    assert (undo.gesture, outcome.entry != accepted.entry) == ("undo", True)

    # Relue de nouveau, elle s'accepte comme la première fois.
    again = await decide(dbsession, beets, ids[:1], [], username="programmatrice")
    assert again.written == 1
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Ciel"


async def test_z_after_refusing_proposes_again(raw_app, dbsession, tmp_path):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    await decide(dbsession, beets, [], ids, username="programmatrice")

    outcome = await fiches_decisions.reopen(
        dbsession, beets, ids, username="programmatrice"
    )

    assert (outcome.written, outcome.entry) == (0, None)
    assert (await _states(dbsession, ids))[ids[0]] == ("proposée", "")
    # Le refus est oublié : la valeur peut de nouveau être proposée.
    assert await dbsession.scalar(select(FicheDecision)) is None
    assert await dbsession.scalar(select(JournalEntry)) is None


async def test_z_cancels_a_write_still_waiting(raw_app, dbsession, tmp_path):
    beets, (queued,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    line = await _line(dbsession, queued, "in_queue")
    ids = await _fiche(dbsession, queued, [("album", "Estuaire", "Ciel")])
    await decide(dbsession, beets, ids, [], username="programmatrice")
    assert (await _states(dbsession, ids))[ids[0]][0] == "acceptée"

    await fiches_decisions.reopen(dbsession, beets, ids, username="programmatrice")

    assert (await _states(dbsession, ids))[ids[0]] == ("proposée", "")
    # Le titre passé, rien ne s'écrit : l'écriture qui attendait est défaite.
    line.status = "played"
    await dbsession.commit()
    assert await apply_waiting(dbsession, beets) == 0
    assert await write_accepted(dbsession, beets) == 0
    assert MediaFile(beets.lib.get_item(queued).path).album == "Estuaire"
    assert (await _states(dbsession, ids))[ids[0]] == ("proposée", "")


async def test_z_keeps_a_value_changed_since(raw_app, dbsession, tmp_path):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    await decide(dbsession, beets, ids, [], username="programmatrice")
    _written_elsewhere(beets, mp3, "Marée basse")

    with pytest.raises(DomainConflict):
        await fiches_decisions.reopen(dbsession, beets, ids, username="programmatrice")
    assert (await _states(dbsession, ids))[ids[0]] == ("écrite", "")


async def test_z_after_a_write_that_failed_proposes_again(raw_app, dbsession, tmp_path):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    beets.lib.get_item(mp3).filepath.chmod(0o444)
    await decide(dbsession, beets, ids, [], username="programmatrice")
    assert (await _states(dbsession, ids))[ids[0]][0] == "en erreur"

    outcome = await fiches_decisions.reopen(
        dbsession, beets, ids, username="programmatrice"
    )

    assert (outcome.written, outcome.entry) == (0, None)
    assert (await _states(dbsession, ids))[ids[0]] == ("proposée", "")
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Estuaire"


async def test_z_on_a_proposition_still_to_read_is_refused(
    raw_app, dbsession, tmp_path
):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    with pytest.raises(DomainConflict):
        await fiches_decisions.reopen(dbsession, beets, ids, username="programmatrice")
    with pytest.raises(DomainValidationError):
        fiches_decisions.parse_reopen({"ids": []})
    with pytest.raises(DomainValidationError):
        fiches_decisions.parse_reopen({"ids": [1, 1]})


async def test_accepting_asks_for_the_write_switch(raw_app, dbsession, tmp_path):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession, own="0")
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])

    with pytest.raises(DomainError):
        await decide(dbsession, beets, ids, [], username="programmatrice")
    assert (await _states(dbsession, ids))[ids[0]][0] == "proposée"
    assert await write_accepted(dbsession, beets) == 0
    # Refuser n'écrit rien : il reste ouvert.
    outcome = await decide(dbsession, beets, [], ids, username="programmatrice")
    assert outcome.refused == 1


# -- les routes ---------------------------------------------------------------------


async def _client(app_configration, beets, dbsession, users_password, perms):
    user = User(username="programmatrice", permissions=perms)
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "programmatrice", users_password)
    return client


async def test_the_routes_ask_for_the_programming_right(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    client = await _client(
        app_configration, beets, dbsession, users_password, {"carts": True}
    )
    for path, body in (
        (DECISIONS, {"accept": ids}),
        (f"/fiches/propositions/{ids[0]}/revenir.json", {}),
        ("/fiches/decisions/annuler.json", {"ids": ids}),
        (f"/fiches/{mp3}/rechercher.json", {}),
    ):
        response = await client.post(path, json=body)
        assert response.status_code == 403, path


async def test_the_routes_decide_revert_and_search_again(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, (mp3, flac) = _bank(tmp_path, ("mp3", "flac"))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    other = await _fiche(dbsession, flac, [("album", "Estuaire", "Ciel")])
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )

    bad = await client.post(DECISIONS, json={"accept": ["un"]})
    assert bad.status_code == 400
    assert (await bad.get_json())["field"] == "accept"
    response = await client.post(DECISIONS, json={"accept": ids, "refuse": other})
    assert response.status_code == 200, await response.get_data()
    payload = await response.get_json()
    assert (payload["accepted"], payload["refused"], payload["written"]) == (1, 1, 1)
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Ciel"
    again = await client.post(DECISIONS, json={"accept": ids})
    assert again.status_code == 409

    listed = await client.get("/fiches.json?state=%C3%A9crite")
    title = (await listed.get_json())["titles"][0]
    assert title["propositions"][0]["state"] == "écrite"
    assert title["propositions"][0]["error"] == ""

    back = await client.post(f"/fiches/propositions/{ids[0]}/revenir.json")
    assert back.status_code == 200, await back.get_data()
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Estuaire"

    # « Z » : le refus défait, la proposition de nouveau à relire (FON-78).
    reopened = await client.post("/fiches/decisions/annuler.json", json={"ids": other})
    assert reopened.status_code == 200, await reopened.get_data()
    assert (await _states(dbsession, other))[other[0]] == ("proposée", "")
    bad_ids = await client.post("/fiches/decisions/annuler.json", json={"ids": "x"})
    assert bad_ids.status_code == 400
    assert (await bad_ids.get_json())["field"] == "ids"

    off = await client.post(f"/fiches/{mp3}/rechercher.json")
    assert off.status_code == 409
    assert (await off.get_json())["code"] == "fiches_off"
    dbsession.add(Setting(key=SETTING_ENABLED, value="1"))
    await dbsession.commit()
    queued = await client.post(f"/fiches/{mp3}/rechercher.json")
    assert queued.status_code == 200
    assert (await _fiche_of(dbsession, mp3)).next_at == SEARCH_FIRST
    unknown = await client.post("/fiches/999/rechercher.json")
    assert unknown.status_code == 404


async def test_the_routes_stay_closed_with_the_switch_off(
    raw_app, app_configration, dbsession, users_password, tmp_path
):
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    dbsession.add(Setting(key=SETTING_TITLE_EDITS, value="1"))
    dbsession.add(Setting(key="features.bank_tidy", value="0"))
    await dbsession.commit()
    ids = await _fiche(dbsession, mp3, [("album", "Estuaire", "Ciel")])
    client = await _client(
        app_configration, beets, dbsession, users_password, {"autodj": True}
    )
    response = await client.post(DECISIONS, json={"accept": ids})
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_tidy_off"
    assert MediaFile(beets.lib.get_item(mp3).path).album == "Estuaire"
    reopened = await client.post("/fiches/decisions/annuler.json", json={"ids": ids})
    assert reopened.status_code == 409
    assert (await reopened.get_json())["code"] == "bank_tidy_off"


async def test_the_verdict_switched_off_is_not_decided(raw_app, dbsession, tmp_path):
    """FON-80 : éteint, le verdict n'est pas montré, et ne se décide pas."""
    beets, (mp3,) = _bank(tmp_path, ("mp3",))
    await _open(dbsession)
    ids = await _fiche(dbsession, mp3, [("fmg", "", "oui")])

    with pytest.raises(DomainConflict):
        await decide(dbsession, beets, ids, [], username="programmatrice")
    assert "fmg" not in beets.lib.get_item(mp3)
