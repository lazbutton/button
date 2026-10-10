from radiotomate.db import PathLike
from radiotomate.models import AutoDJSlot, Clock, User
from radiotomate.services.ntf_grille import JOUR, NUIT, apply_ntf_grille


async def test_ntf_grille_is_idempotent(
    dbsession,
    users_password: str,
):
    user = User(username="ntf-grille")
    user.update_password(users_password)
    user.update_permissions_map({"admin": True})
    dbsession.add(user)
    await dbsession.commit()

    media = PathLike.base_path / "ntf-media"
    first = await apply_ntf_grille(dbsession, media)
    await dbsession.commit()
    await apply_ntf_grille(dbsession, media)
    await dbsession.commit()

    jour = await Clock.from_name(dbsession, JOUR)
    nuit = await Clock.from_name(dbsession, NUIT)
    assert first["jour"] == JOUR
    assert jour is not None and nuit is not None
    loaded = await Clock.from_id(dbsession, jour.id, load_positions=True)
    assert [row.kind for row in loaded.sequential_positions()] == [
        "jingle",
        "musique",
        "musique",
        "musique",
    ]
    assert loaded.anchored_positions()[0].sync == "dure"
    night = await Clock.from_id(dbsession, nuit.id, load_positions=True)
    assert len(night.sequential_positions()) == 7
    assert night.anchored_positions()[0].sync == "molle"

    midnight = await AutoDJSlot.from_time(dbsession, 0, day_of_week=0, exact=True)
    morning = await AutoDJSlot.from_time(dbsession, 7 * 60, day_of_week=3, exact=True)
    assert midnight is not None and midnight.clock_id == nuit.id
    assert morning is not None and morning.title == JOUR
    jingles = list((media / "30-habillage" / "jingles").glob("REMPLACANT*.wav"))
    archives = list((media / "20-archives").rglob("REMPLACANT*.wav"))
    assert len(jingles) == 3
    assert len(archives) == 6
