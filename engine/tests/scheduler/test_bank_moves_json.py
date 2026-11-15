"""POST /media/move.json : le catalogue y passe ses déplacements (ARC-09)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from radiotomate.interface import bank_moves as route
from radiotomate.models.setting import Setting
from tests.scheduler.test_admin_json import _admin_client
from tests.scheduler.test_bank_moves import _path_of, _title, media, place  # noqa: F401

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session as ormSession

    from radiotomate.beets import BeetsIntegration
    from radiotomate.services.bank_lock import BeetsPlace

MOVE = {
    "moves": [
        {"from": "10-rotation/Ada - Un.mp3", "to": "20-archives/jazz/Ada - Un.mp3"}
    ]
}


@pytest.fixture
def engine_library(
    place: BeetsPlace,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> BeetsPlace:
    monkeypatch.setattr(route.BeetsPlace, "of", classmethod(lambda cls, lib: place))
    return place


async def _tidying_on(dbsession: ormSession) -> None:
    dbsession.add(Setting(key="features.bank_tidy", value="1"))
    await dbsession.commit()


async def test_a_move_keeps_the_title(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    media: Path,  # noqa: F811
    engine_library: BeetsPlace,
):
    item = _title(engine_library, media / "10-rotation" / "Ada - Un.mp3")
    await _tidying_on(dbsession)
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "prog",
        {"autodj": True},
    )

    response = await client.post("/media/move.json", json=MOVE)

    assert response.status_code == 200
    assert await response.get_json() == {
        "moved": [
            {
                "from": "10-rotation/Ada - Un.mp3",
                "to": "20-archives/jazz/Ada - Un.mp3",
                "beets_ids": [item.id],
            }
        ],
        "failed": [],
        "left": [],
        "entry": 1,
    }
    assert (
        _path_of(engine_library, item.id)
        == media / "20-archives" / "jazz" / "Ada - Un.mp3"
    )


async def test_the_switches_say_who_moves(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    media: Path,  # noqa: F811
    engine_library: BeetsPlace,
):
    source = media / "10-rotation" / "Ada - Un.mp3"
    _title(engine_library, source)
    dbsession.add(Setting(key="features.bank_tidy", value="0"))
    await dbsession.commit()
    client = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "admin"
    )

    response = await client.post("/media/move.json", json=MOVE)

    # FON-85: the general switch off, the catalogue does not move either.
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_tidy_off"
    assert source.is_file()
    # The switch of the moves alone off: the catalogue moves, as before ARC-09.
    await Setting.upsert(dbsession, "features.bank_tidy", "1")
    dbsession.add(Setting(key="features.bank_moves_keep_identity", value="0"))
    await dbsession.commit()
    response = await client.post("/media/move.json", json=MOVE)
    assert response.status_code == 409
    assert (await response.get_json())["code"] == "bank_moves_off"
    assert source.is_file()


async def test_who_may_not_deposit_may_not_move(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    media: Path,  # noqa: F811
    engine_library: BeetsPlace,
):
    source = media / "10-rotation" / "Ada - Un.mp3"
    _title(engine_library, source)
    await _tidying_on(dbsession)
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "voix",
        {"live": True},
    )

    response = await client.post("/media/move.json", json=MOVE)

    assert response.status_code == 403
    assert source.is_file()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"moves": []},
        {"moves": ["10-rotation/a.mp3"]},
        {"moves": [{"from": "10-rotation/a.mp3"}]},
        {"moves": [{"from": "10-rotation/a.mp3", "to": "x"}] * 501},
    ],
)
async def test_a_request_out_of_shape_is_refused(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    media: Path,  # noqa: F811
    engine_library: BeetsPlace,
    body: dict,
):
    await _tidying_on(dbsession)
    client = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "admin"
    )

    response = await client.post("/media/move.json", json=body)

    assert response.status_code == 400
