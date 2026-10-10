from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as ormSession

from radiotomate.models import User
from radiotomate.models.emission import Emission
from radiotomate.services.emissions import harbor_allowed

PARIS = ZoneInfo("Europe/Paris")
# Mercredi 30 septembre 2026.
INSIDE = datetime(2026, 9, 30, 20, 30, tzinfo=PARIS)
OUTSIDE = datetime(2026, 9, 30, 10, 0, tzinfo=PARIS)


async def test_stream_stays_open_until_a_host_is_named(
    dbsession: ormSession,
    user_can_stream: User,
):
    assert INSIDE.weekday() == 2
    assert await harbor_allowed(dbsession, user_can_stream, now=INSIDE)


async def test_named_host_only_during_their_slot(
    dbsession: ormSession,
    users_password: str,
):
    host = User(username="animateur")
    host.update_password(users_password)
    host.update_permissions({"can_stream": "true"})
    other = User(username="autre")
    other.update_password(users_password)
    other.update_permissions({"can_stream": "true"})
    admin = User(username="chef")
    admin.update_password(users_password)
    admin.update_permissions({"can_admin": "true"})
    dbsession.add_all([host, other, admin])
    dbsession.add(
        Emission(
            scope="weekly",
            title="Creative Camp",
            artist="NTF",
            day_of_week=INSIDE.weekday(),
            start_minute=20 * 60,
            end_minute=22 * 60,
            host_username="animateur",
        )
    )
    await dbsession.commit()

    assert await harbor_allowed(dbsession, host, now=INSIDE)
    assert not await harbor_allowed(dbsession, host, now=OUTSIDE)
    assert not await harbor_allowed(dbsession, other, now=INSIDE)
    assert await harbor_allowed(dbsession, admin, now=OUTSIDE)
