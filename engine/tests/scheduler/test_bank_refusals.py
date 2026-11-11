"""Un bac dit les fichiers de son dossier qu'il n'a pas pris, et pourquoi."""

import os
import time
from pathlib import Path

import pytest
from sqlalchemy.orm import Session as ormSession

from radiotomate.beets import BeetsIntegration
from radiotomate.enums import CartMode, ScheduleMode
from radiotomate.models import Cart, User
from radiotomate.services import media_bank
from radiotomate.services.carts import sync_bank_folder
from tests.scheduler.test_admin_json import ASSETS, _admin_client

MP3 = ASSETS / "ohradiotomateoh.mp3"
TEXT = b"Ceci est un texte, pas un son.\n"
NOT_AUDIO = "ce n'est pas un fichier audio"
NO_LENGTH = "durée illisible"
TOO_MANY = "plus de 2000 fichiers audio : le bac ne prend plus rien de son dossier"


def _drop(path: Path, data: bytes, *, age: float = 60.0) -> Path:
    """Un fichier posé dans le dossier d'un bac il y a `age` secondes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "media"
    (root / "50-carts" / "depot").mkdir(parents=True)
    monkeypatch.setenv("MEDIA_ROOT", str(root))
    return root


@pytest.fixture
def folder(media: Path) -> Path:
    return media / "50-carts" / "depot"


@pytest.fixture
async def uploader_id(dbsession: ormSession, users_password: str) -> int:
    user = User(username="depot")
    user.update_password(users_password)
    dbsession.add(user)
    await dbsession.commit()
    return user.id


@pytest.fixture
async def cart_id(raw_app, dbsession: ormSession, media: Path) -> int:
    cart = Cart(
        title="Nouveautés",
        path=raw_app.config["DATA_ROOT"] / "nouveautes",
        mode=CartMode.PLAYLIST,
        schedule_mode=ScheduleMode.CLOCK,
        bank_folder="50-carts/depot",
    )
    dbsession.add(cart)
    await dbsession.commit()
    return cart.id


async def _sync(dbsession: ormSession, cart_id: int, uploader_id: int) -> list[str]:
    """Un passage du scheduler sur le dossier du bac : les sons qu'il prend."""
    dbsession.expire_all()
    cart = await Cart.from_id(dbsession, cart_id)
    assert cart is not None
    added = await sync_bank_folder(dbsession, cart, uploader_id)
    await dbsession.commit()
    return [sound.title for sound in added]


async def _titles(dbsession: ormSession, cart_id: int) -> list[str]:
    dbsession.expire_all()
    cart = await Cart.from_id(dbsession, cart_id, load_sounds=True)
    assert cart is not None
    return [sound.title for sound in cart.sounds]


async def test_a_fake_mp3_is_listed_until_a_real_sound_replaces_it(
    dbsession: ormSession, cart_id: int, uploader_id: int, folder: Path
):
    fake = _drop(folder / "faux.mp3", TEXT)

    assert await _sync(dbsession, cart_id, uploader_id) == []
    assert media_bank.read_refusals(folder) == [
        {"path": "faux.mp3", "reason": NOT_AUDIO}
    ]
    # Le passage suivant le saute encore, et la liste reste la même.
    assert await _sync(dbsession, cart_id, uploader_id) == []
    assert media_bank.read_refusals(folder) == [
        {"path": "faux.mp3", "reason": NOT_AUDIO}
    ]

    _drop(fake, MP3.read_bytes())
    assert await _sync(dbsession, cart_id, uploader_id) == ["faux.mp3"]
    assert media_bank.read_refusals(folder) == []
    assert not (folder / media_bank.REFUSALS_NAME).exists()


async def test_a_file_leaves_the_list_when_it_leaves_the_folder(
    dbsession: ormSession, cart_id: int, uploader_id: int, folder: Path
):
    _drop(folder / "a.mp3", TEXT)
    gone = _drop(folder / "Album" / "b.ogg", b"OggS" + bytes(60))

    await _sync(dbsession, cart_id, uploader_id)
    assert media_bank.read_refusals(folder) == [
        {"path": "a.mp3", "reason": NOT_AUDIO},
        {"path": "Album/b.ogg", "reason": NO_LENGTH},
    ]

    gone.unlink()
    await _sync(dbsession, cart_id, uploader_id)
    assert media_bank.read_refusals(folder) == [{"path": "a.mp3", "reason": NOT_AUDIO}]


async def test_a_folder_over_the_cap_gets_one_entry(
    dbsession: ormSession, cart_id: int, uploader_id: int, folder: Path
):
    for index in range(media_bank.MAX_BANK_ATTACH + 1):
        (folder / f"son-{index:04}.mp3").touch()

    assert await _sync(dbsession, cart_id, uploader_id) == []
    assert media_bank.read_refusals(folder) == [{"path": ".", "reason": TOO_MANY}]

    # Revenu à 2000, le dossier n'est plus refusé. Des fichiers vides ne sont pas
    # refusés : ils peuvent être en train d'arriver.
    (folder / "son-0000.mp3").unlink()
    assert await _sync(dbsession, cart_id, uploader_id) == []
    assert media_bank.read_refusals(folder) == []


async def test_the_refusal_list_never_enters_the_cart(
    dbsession: ormSession, cart_id: int, uploader_id: int, folder: Path
):
    _drop(folder / "faux.mp3", TEXT)
    _drop(folder / "vrai.mp3", MP3.read_bytes())

    assert await _sync(dbsession, cart_id, uploader_id) == ["vrai.mp3"]
    assert (folder / media_bank.REFUSALS_NAME).is_file()
    assert await _sync(dbsession, cart_id, uploader_id) == []
    assert await _titles(dbsession, cart_id) == ["vrai.mp3"]
    assert media_bank.iter_bank_audio(folder) == [
        (folder / "faux.mp3").resolve(),
        (folder / "vrai.mp3").resolve(),
    ]


async def test_a_file_on_its_way_in_is_not_refused_yet(
    dbsession: ormSession, cart_id: int, uploader_id: int, folder: Path
):
    # La fin d'un ogg n'est pas encore arrivée : sa durée ne se lit pas encore.
    arriving = _drop(folder / "en-route.ogg", b"OggS" + bytes(60), age=0)
    await _sync(dbsession, cart_id, uploader_id)
    assert media_bank.read_refusals(folder) == []

    _drop(arriving, b"OggS" + bytes(60))
    await _sync(dbsession, cart_id, uploader_id)
    assert media_bank.read_refusals(folder) == [
        {"path": "en-route.ogg", "reason": NO_LENGTH}
    ]

    # Une autre copie arrive : le fichier garde sa raison tant qu'elle arrive.
    _drop(arriving, TEXT, age=0)
    await _sync(dbsession, cart_id, uploader_id)
    assert media_bank.read_refusals(folder) == [
        {"path": "en-route.ogg", "reason": NO_LENGTH}
    ]
    _drop(arriving, TEXT)
    await _sync(dbsession, cart_id, uploader_id)
    assert media_bank.read_refusals(folder) == [
        {"path": "en-route.ogg", "reason": NOT_AUDIO}
    ]


def test_the_list_is_written_only_when_it_changes(tmp_path: Path):
    entries = [{"path": "faux.mp3", "reason": NOT_AUDIO}]
    note = tmp_path / media_bank.REFUSALS_NAME

    assert media_bank.write_refusals(tmp_path, entries) is True
    assert note.read_text(encoding="utf-8") == (
        '[\n{"path": "faux.mp3", "reason": "ce n\'est pas un fichier audio"}\n]\n'
    )
    assert media_bank.write_refusals(tmp_path, entries) is False
    assert media_bank.write_refusals(tmp_path, []) is True
    assert not note.exists()
    assert media_bank.write_refusals(tmp_path, []) is False
    assert sorted(path.name for path in tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "content",
    [
        "pas du json",
        '{"path": "faux.mp3", "reason": "durée illisible"}',
        '[{"path": "faux.mp3"}, "faux.mp3", {"path": 3, "reason": "x"}]',
        "[" * 100_000,
    ],
)
def test_a_damaged_list_reads_as_empty(tmp_path: Path, content: str):
    (tmp_path / media_bank.REFUSALS_NAME).write_text(content, encoding="utf-8")
    assert media_bank.read_refusals(tmp_path) == []


async def test_the_cart_json_gives_the_skipped_files(  # noqa: PLR0913
    raw_app,
    app_configration: dict,
    beets_integration: BeetsIntegration,
    dbsession: ormSession,
    users_password: str,
    media: Path,
):
    client = await _admin_client(
        app_configration, beets_integration, dbsession, users_password, "refus"
    )
    created = await client.post(
        "/carts.json",
        json={"title": "Dépôts", "mode": "playlist", "schedule_mode": "timed"},
    )
    assert created.status_code == 201, await created.get_data(as_text=True)
    cart = (await created.get_json())["cart"]
    assert cart["skipped_files"] == []
    folder = media / cart["bank_folder"]
    _drop(folder / "faux.mp3", TEXT)
    user = await User.from_username(dbsession, "refus")
    assert user is not None
    await _sync(dbsession, cart["id"], user.id)

    async def skipped() -> list[dict]:
        listed = await (await client.get("/carts.json")).get_json()
        row = next(row for row in listed["carts"] if row["id"] == cart["id"])
        return row["skipped_files"]

    assert await skipped() == [{"path": "faux.mp3", "reason": NOT_AUDIO}]

    # Ce qui a changé depuis le passage du scheduler ne compte plus : un fichier
    # parti, ou un fichier que le bac a pris entre-temps, ici par la console.
    _drop(folder / "pris.mp3", MP3.read_bytes())
    media_bank.write_refusals(
        folder,
        [
            {"path": "faux.mp3", "reason": NOT_AUDIO},
            {"path": "parti.mp3", "reason": NOT_AUDIO},
            {"path": "pris.mp3", "reason": NO_LENGTH},
        ],
    )
    attached = await client.post(
        f"/carts/{cart['id']}/sounds.json",
        json={"paths": [f"{cart['bank_folder']}/pris.mp3"]},
    )
    assert attached.status_code == 201, await attached.get_data(as_text=True)
    body = await attached.get_json()
    assert body["cart"]["skipped_files"] == [{"path": "faux.mp3", "reason": NOT_AUDIO}]
    assert await skipped() == [{"path": "faux.mp3", "reason": NOT_AUDIO}]

    # Un relais ne suit pas de dossier.
    relay = await client.put(
        f"/carts/{cart['id']}.json",
        json={
            "version": body["cart"]["version"],
            "mode": "relay",
            "url": "https://radio.example/flux.mp3",
            "max_duration": 600,
        },
    )
    assert relay.status_code == 200, await relay.get_data(as_text=True)
    assert (await relay.get_json())["cart"]["skipped_files"] == []

    # Supprimé, le bac envoie ses fichiers à la corbeille, pas sa liste.
    deleted = await client.delete(f"/carts/{cart['id']}.json")
    assert deleted.status_code == 200, await deleted.get_data(as_text=True)
    trash = sorted(path.name for path in (media / "90-trash").iterdir())
    assert trash == ["faux.mp3", "pris.mp3"]
