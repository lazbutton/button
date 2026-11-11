"""GET /system/version.json — la version de chaque service, pour un admin.

La commande station l'écrit dans versions.json, dans le dossier des données.
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from tests.scheduler.test_admin_json import _admin_client

EMPTY = {"version": None, "recorded_at": None, "services": []}


def _record(app_configration: dict, content: str) -> None:
    (Path(app_configration["data"]["root"]) / "versions.json").write_text(content)


async def test_version_is_for_admins_only(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration,
        beets_integration,
        dbsession,
        users_password,
        "version-prog",
        {"live": True, "carts": True, "autodj": True},
    )
    result = await client.get("/system/version.json")
    assert result.status_code == 403


async def test_version_without_record(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    client = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "version-none"
    )
    result = await client.get("/system/version.json")
    assert result.status_code == 200
    assert await result.get_json() == EMPTY
    _record(app_configration, "{pas du JSON")
    result = await client.get("/system/version.json")
    assert await result.get_json() == EMPTY


async def test_version_of_each_service(
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
):
    # As deploy/station writes it: the time in UTC, a service per container.
    _record(
        app_configration,
        json.dumps(
            {
                "recorded_at": "2026-11-12T03:01:07Z",
                "version": "1.0.0",
                "services": [
                    {
                        "service": "radiotomate-playout",
                        "image": "ghcr.io/lazbutton/button-playout:1.0.0",
                        "version": "1.0.0",
                    },
                    {"service": "caddy", "image": "caddy:2.11-alpine", "version": ""},
                    {"image": "sans-service:1"},
                ],
            }
        ),
    )
    client = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "version-all"
    )
    result = await client.get("/system/version.json")
    assert result.status_code == 200
    assert await result.get_json() == {
        "version": "1.0.0",
        "recorded_at": "2026-11-12T04:01+01:00",
        "services": [
            {"service": "caddy", "image": "caddy:2.11-alpine", "version": None},
            {
                "service": "radiotomate-playout",
                "image": "ghcr.io/lazbutton/button-playout:1.0.0",
                "version": "1.0.0",
            },
        ],
    }
