"""GET /system/disk.json — bibliothèque, programmateur et admin."""

from unittest.mock import patch

from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from tests.scheduler.test_admin_json import _admin_client


class _Usage:
    def __init__(self, total: int, used: int, free: int):
        self.total = total
        self.used = used
        self.free = free


async def test_disk_forbidden_for_animator(
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
        "disk-animator",
        {"live": True},
    )
    result = await client.get("/system/disk.json")
    assert result.status_code == 403


async def test_disk_for_programmer_matches_usage(
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
        "disk-prog",
        {"live": True, "carts": True, "autodj": True},
    )
    usage = _Usage(40 * 1024**3, 32 * 1024**3, 8 * 1024**3)
    with patch("radiotomate.interface.system.shutil.disk_usage", return_value=usage):
        result = await client.get("/system/disk.json")
    assert result.status_code == 200
    payload = await result.get_json()
    assert payload["total"] == usage.total
    assert payload["used"] == usage.used
    assert payload["free"] == usage.free
    assert payload["path"]


async def test_disk_for_admin(
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
        "disk-admin",
    )
    usage = _Usage(100, 10, 90)
    with patch("radiotomate.interface.system.shutil.disk_usage", return_value=usage):
        result = await client.get("/system/disk.json")
    assert result.status_code == 200
    payload = await result.get_json()
    assert payload["free"] == 90
