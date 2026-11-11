"""Requêtes Beets des sélections : virgule en trop, requête illisible, tirage."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.beets.demo import BeetsMockIntegration
from radiotomate.domain.errors import DomainValidationError
from radiotomate.models import MusicCategory
from radiotomate.scheduler.music_rules import _pick_music
from radiotomate.services.beets_query import (
    BAD_VALUE,
    EXTRA_COMMA,
    TRAILING_BACKSLASH,
    UNCLOSED_QUOTE,
    playable_query,
    validate_selection_query,
)
from tests.scheduler.test_admin_json import _admin_client

# La bibliothèque de test : 105 titres `rotation`, et ici trois titres `jazz`.
JAZZ = 3


@pytest.fixture
def jazz_library():
    beets = BeetsMockIntegration()
    for i in range(JAZZ):
        beets.helper.add_item(
            artist=f"Trio {i}",
            title=f"Swing {i}",
            grouping="jazz",
            path=f"/media/20-archives/jazz/swing-{i}.mp3",
        )
    yield beets
    beets.teardown()


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("grouping:jazz,", EXTRA_COMMA),
        ("grouping:jazz ,", EXTRA_COMMA),
        (", grouping:jazz", EXTRA_COMMA),
        (",", EXTRA_COMMA),
        ("grouping:jazz , , genre:Jazz", EXTRA_COMMA),
        # Un tri seul ne filtre rien : la partie d'après prend tout.
        ("grouping:jazz, year+", EXTRA_COMMA),
        ('title:"Swing', UNCLOSED_QUOTE),
        ("grouping:jazz\\", TRAILING_BACKSLASH),
        ("year:abc", BAD_VALUE),
        ("title::(", BAD_VALUE),
    ],
)
def test_refused_queries(beets_integration: BeetsIntegration, query, message):
    with pytest.raises(DomainValidationError) as caught:
        validate_selection_query(query, field="empty_query")
    assert caught.value.message == message
    assert caught.value.field == "empty_query"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "grouping:jazz",
        "grouping:jazz genre:Jazz",
        # Un vrai « ou » : chaque partie filtre.
        "grouping:jazz , grouping:rotation",
        "grouping:jazz, genre:Jazz year+",
        # Une virgule dans une valeur reste une valeur.
        "grouping:jazz,rock",
        '"grouping:jazz, blues"',
        "year+",
        "year:1990..2000",
    ],
)
def test_accepted_queries(beets_integration: BeetsIntegration, query):
    validate_selection_query(query)


def test_playable_query_drops_only_the_empty_parts(jazz_library):
    def count(query):
        return len(list(jazz_library.lib.items(playable_query(query))))

    whole = len(list(jazz_library.lib.items("")))
    assert whole > JAZZ
    assert count("grouping:jazz") == JAZZ
    assert count("grouping:jazz,") == JAZZ
    assert count(", grouping:jazz ,") == JAZZ
    assert count("grouping:jazz, , grouping:rotation") == whole
    assert count(",") == whole
    # Ce qu'il ne touche pas, il le rend tel quel.
    assert playable_query("grouping:jazz") == "grouping:jazz"
    assert playable_query('title:"Swing') == 'title:"Swing'


async def test_autodj_skips_the_extra_comma_of_a_saved_selection(
    raw_app,
    app_configration: dict,
    jazz_library: BeetsMockIntegration,
    dbsession: ormSession,
    users_password: str,
):
    # Enregistrée avant la règle : la base la garde telle quelle.
    category = MusicCategory(name="Jazz", query="grouping:jazz,", empty_query="")
    dbsession.add(category)
    await dbsession.commit()

    pos = SimpleNamespace(category=category)
    now = datetime(2026, 11, 11, 14, 0)
    for _ in range(20):
        item = await _pick_music(dbsession, jazz_library, pos, now)
        assert item.grouping == "jazz"

    client = await _admin_client(
        app_configration, jazz_library, dbsession, users_password, "jazz-admin"
    )
    listed = await (await client.get("/autodj/categories.json")).get_json()
    jazz = next(row for row in listed["categories"] if row["name"] == "Jazz")
    assert (jazz["query"], jazz["count"]) == ("grouping:jazz,", JAZZ)
    # La modifier demande d'abord de retirer la virgule.
    renamed = await client.put(
        f"/autodj/categories/{category.id}.json",
        json={"name": "Jazz bis", "query": jazz["query"]},
    )
    assert renamed.status_code == 400
    assert (await renamed.get_json())["field"] == "query"
