"""The plays of a title in its fiche, read in the air log (FON-76)."""

from __future__ import annotations

from datetime import datetime, timedelta

from radiotomate.enums import CartMode, ScheduleMode
from radiotomate.models import (
    Cart,
    MetadataLog,
    ProgrammingVersion,
    RundownItem,
    Setting,
    User,
)
from radiotomate.services import bank_plays, bank_titles
from tests.scheduler.test_media_titles_json import _beets
from tests.scheduler.test_studio_json import _interface_client, _login

PATH = "/media/10-rotation/a.mp3"
ANNOTATED = 'annotate:pushed="1",radiotomate_queue="autodj":' + PATH


async def _air_log(dbsession, raw_app, now: datetime) -> Cart:
    cart = Cart(
        title="Nuit douce",
        path=raw_app.config["DATA_ROOT"] / "nuit",
        mode=CartMode.PLAYLIST,
        schedule_mode=ScheduleMode.CLOCK,
    )
    dbsession.add(cart)
    dbsession.add(ProgrammingVersion(id="pv-plays", source="test", description="x"))
    await dbsession.flush()
    dbsession.add(
        RundownItem(
            id="ri-agenda",
            programming_version_id="pv-plays",
            sequence=0,
            planned_at=now - timedelta(days=2),
            duration=200,
            kind="sound",
            when_mode="fixed",
            queue="carts",
            resource=PATH,
            origin="agenda",
        )
    )
    await dbsession.flush()
    entry = {"artist": "Orage", "title": "Été indien", "album": ""}
    dbsession.add_all(
        [
            # Three plays: the auto-DJ, a cart, the Agenda.
            MetadataLog(
                on_air=now - timedelta(hours=20),
                source="autodj",
                source_url=ANNOTATED,
                **entry,
            ),
            MetadataLog(
                on_air=now - timedelta(days=1, hours=3),
                source="carts",
                source_url=f'annotate:x="1":{PATH}',
                cart_id=cart.id,
                **entry,
            ),
            MetadataLog(
                on_air=now - timedelta(days=2),
                source="carts",
                source_url=PATH,
                rundown_item_id="ri-agenda",
                **entry,
            ),
            # Not plays: skipped before it played, too old, another file.
            MetadataLog(
                on_air=now - timedelta(hours=2),
                source="autodj",
                source_url=ANNOTATED,
                extra={"skipped": True},
                **entry,
            ),
            MetadataLog(
                on_air=now - timedelta(days=120),
                source="autodj",
                source_url=ANNOTATED,
                **entry,
            ),
            MetadataLog(
                on_air=now - timedelta(hours=1),
                source="autodj",
                source_url=f":{PATH}.bak",
                **entry,
            ),
            MetadataLog(
                on_air=now - timedelta(hours=1),
                source="autodj",
                source_url="/media/10-rotation/b.mp3",
                **entry,
            ),
        ]
    )
    await dbsession.commit()
    return cart


async def test_the_fiche_says_how_often_when_and_from_where(  # noqa: PLR0913
    raw_app, app_configration, dbsession, users_password, tmp_path, container_tz
):
    beets = _beets(tmp_path)
    item_id = next(item.id for item in beets.lib.items() if item.path == PATH.encode())
    now = datetime.now()
    cart = await _air_log(dbsession, raw_app, now)
    user = User(username="plays-json")
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    client = _interface_client(app_configration, beets)
    await _login(client, "plays-json", users_password)

    # FON-85 : le rangement coupé, la fiche d'un titre se lit encore.
    dbsession.add(Setting(key=bank_titles.SETTING_BANK_TIDY, value="0"))
    await dbsession.commit()

    response = await client.get(f"/media/titles/{item_id}/plays.json")
    assert response.status_code == 200
    payload = await response.get_json()
    assert payload["days"] == 90
    assert payload["count"] == 3
    assert payload["by_origin"] == {"autodj": 1, "bac": 1, "agenda": 1, "autre": 0}
    recent = payload["recent"]
    assert [row["origin"] for row in recent] == ["autodj", "bac", "agenda"]
    assert recent[1]["cart"] == {"id": cart.id, "title": "Nuit douce"}
    # The hour of Paris, with its offset, whatever the container's clock.
    expected = (now - timedelta(hours=20)).astimezone(bank_plays.PARIS)
    assert recent[0]["on_air"] == expected.isoformat(timespec="minutes")

    missing = await client.get("/media/titles/999999/plays.json")
    assert missing.status_code == 404


async def test_a_renamed_title_keeps_its_plays_by_its_former_paths(raw_app, dbsession):
    now = datetime.now()
    await _air_log(dbsession, raw_app, now)
    dbsession.add(
        MetadataLog(
            on_air=now - timedelta(hours=1),
            source="autodj",
            source_url='annotate:a="1":/media/10-rotation/Orage - Été indien.mp3',
            artist="Orage",
            title="Été indien",
            album="",
        )
    )
    await dbsession.commit()
    renamed = await bank_plays.title_plays(
        dbsession, ["/media/10-rotation/Orage - Été indien.mp3"], now=now
    )
    assert renamed["count"] == 1
    both = await bank_plays.title_plays(
        dbsession, ["/media/10-rotation/Orage - Été indien.mp3", PATH], now=now
    )
    assert both["count"] == 4
    assert (await bank_plays.title_plays(dbsession, [], now=now))["count"] == 0
