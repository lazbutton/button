from pathlib import Path

import pytest

from radiotomate.domain.errors import DomainValidationError
from radiotomate.services import media_bank as bank

ASSETS = Path(__file__).resolve().parent / "assets"


@pytest.fixture
def media(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "media"
    (root / "30-habillage" / "jingles").mkdir(parents=True)
    monkeypatch.setenv("MEDIA_ROOT", str(root))
    return root


def test_canonical_jingles_and_prog(media: Path):
    assert bank.canonical_rel_for_cart(3, "Jingles") == "30-habillage/jingles"
    assert bank.canonical_rel_for_cart(8, "Prog") == "50-carts/8"
    assert bank.finder_rel(8, "Prog") == "Carts/8-Prog"


def test_ensure_tree_symlink_is_view_only(media: Path):
    rel = bank.ensure_cart_tree(3, "Jingles")
    assert rel == "30-habillage/jingles"
    real = (media / rel).resolve()
    view = media / "Carts" / "3-Jingles"
    assert view.is_symlink()
    assert view.resolve() == real


def test_prog_tree_is_real_dir(media: Path):
    rel = bank.ensure_cart_tree(8, "Prog")
    assert rel == "50-carts/8"
    assert (media / rel).is_dir()
    view = media / "Carts" / "8-Prog"
    assert view.is_symlink()
    assert view.resolve() == (media / rel).resolve()


def test_rename_refreshes_finder_slug_keeps_id_dir(media: Path):
    bank.ensure_cart_tree(8, "Prog")
    rel = bank.ensure_cart_tree(8, "Prog Prime", "50-carts/8")
    assert rel == "50-carts/8"
    assert not (media / "Carts" / "8-Prog").exists()
    assert (media / "Carts" / "8-Prog-Prime").is_symlink()


def test_reject_rotation_inbox_and_finder_view(media: Path):
    (media / "10-rotation").mkdir()
    (media / "00-inbox" / "x").mkdir(parents=True)
    (media / "Carts" / "x").mkdir(parents=True)
    with pytest.raises(DomainValidationError):
        bank.resolve_bank_dir("10-rotation")
    with pytest.raises(DomainValidationError):
        bank.resolve_bank_dir("00-inbox/x")
    with pytest.raises(DomainValidationError):
        bank.resolve_bank_dir("Carts/x")
    rel = bank.ensure_cart_tree(1, "X")
    assert rel == "50-carts/1"
    bank.resolve_bank_dir(rel)


def test_iter_skips_symlink_escape(media: Path):
    dest = media / "50-carts" / "1"
    dest.mkdir(parents=True)
    outside = media / "10-rotation"
    outside.mkdir(exist_ok=True)
    mp3 = ASSETS / "ohradiotomateoh.mp3"
    target = outside / "secret.mp3"
    target.write_bytes(mp3.read_bytes())
    (dest / "trap.mp3").symlink_to(target)
    (dest / "ok.mp3").write_bytes(mp3.read_bytes())
    files = {path.name for path in bank.iter_bank_audio(dest)}
    assert files == {"ok.mp3"}


def test_the_bank_names_its_folders_in_one_place():
    # Named once, in media_bank.py: these are the names a station has on its disk.
    assert bank.BANK_TOPS == ("30-habillage", "40-emissions", "50-carts")
    assert (bank.INBOX_TOP, bank.ROTATION_TOP) == ("00-inbox", "10-rotation")
    assert (bank.TRASH_TOP, bank.FINDER_CARTS) == ("90-trash", "Carts")
    assert bank.habillage_folders() == [
        "30-habillage/jingles",
        "30-habillage/ids",
        "30-habillage/pubs",
        "30-habillage/beds",
        "30-habillage/stings",
        "30-habillage/sfx",
    ]


def test_a_cart_named_after_habillage_takes_its_folder():
    assert bank.HABILLAGE_TITLES == {
        "jingles": "30-habillage/jingles",
        "jingle": "30-habillage/jingles",
        "ids": "30-habillage/ids",
        "id": "30-habillage/ids",
        "pubs": "30-habillage/pubs",
        "pub": "30-habillage/pubs",
        "beds": "30-habillage/beds",
        "bed": "30-habillage/beds",
        "stings": "30-habillage/stings",
        "sting": "30-habillage/stings",
        "sfx": "30-habillage/sfx",
    }
    assert bank.habillage_folder_for_title(" Stings ") == "30-habillage/stings"
    assert bank.habillage_folder_for_title("Prog") is None


def test_a_cart_is_told_its_zone_not_read_in_its_folder():
    assert bank.bank_zone("30-habillage/jingles") == "habillage"
    assert bank.bank_zone("/30-habillage/") == "habillage"
    assert bank.bank_zone("40-emissions/matinale/entiere") == "emissions"
    assert bank.bank_zone("50-carts/8") == "bacs"
    # No folder, as for a relay, or a folder no cart may follow.
    assert bank.bank_zone(None) is None
    assert bank.bank_zone("") is None
    assert bank.bank_zone("10-rotation") is None


def test_the_engine_names_the_folders_in_media_bank_only():
    """Changing how the bank is laid out changes media_bank.py, and no other file.

    The published migrations keep what they wrote: they never change. The
    catalogue and the station's scripts are compared with media_bank.py by
    services/catalog/test_layout.py.
    """
    package = Path(bank.__file__).resolve().parents[1]
    published = package / "commands" / "update"
    folders = ("00-inbox", "10-rotation", "20-archives", "30-habillage")
    folders += ("40-emissions", "50-carts", "90-trash", ".volume")
    found = []
    for path in sorted(package.rglob("*")):
        if path.suffix not in {".py", ".jinja", ".liq", ".js", ".json"}:
            continue
        if path == Path(bank.__file__).resolve() or published in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        found += [
            f"{path.relative_to(package)} : {name}" for name in folders if name in text
        ]
    assert found == []
