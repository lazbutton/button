"""python test_refresh_volume.py — vue Finder, à côté des tests du catalogue."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "scripts"))

import refresh_volume  # noqa: E402


class RefreshVolumeTest(unittest.TestCase):
    def test_five_names_and_a_bank_label(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            (media / "00-inbox" / "rotation").mkdir(parents=True)
            (media / "90-trash").mkdir()
            (media / "10-rotation").mkdir()
            bank = media / "20-archives" / "jazz"
            bank.mkdir(parents=True)
            (bank / ".banque.json").write_text(json.dumps({"nom": "Jazz en public"}), encoding="utf-8")
            (media / "40-emissions" / "_modele" / "entiere").mkdir(parents=True)
            (media / "40-emissions" / "matin").mkdir()
            (media / "Carts").mkdir()
            (media / "00-inbox" / "rotation" / "secret.mp3").write_bytes(b"no")

            volume = refresh_volume.refresh(media)
            refresh_volume.refresh(media)

            self.assertEqual(
                sorted(path.name for path in volume.iterdir()),
                ["Bacs", "Banques", "Habillage", "Rotation", "Émissions"],
            )
            self.assertEqual((volume / "Rotation").resolve(), (media / "10-rotation").resolve())
            self.assertEqual((volume / "Bacs").resolve(), (media / "Carts").resolve())
            jazz = volume / "Banques" / "Jazz en public"
            self.assertTrue(jazz.is_symlink())
            self.assertEqual(jazz.resolve(), bank.resolve())
            self.assertEqual((volume / "Habillage" / "Idents").resolve(), (media / "30-habillage" / "ids").resolve())
            self.assertEqual((volume / "Habillage" / "Effets").resolve(), (media / "30-habillage" / "sfx").resolve())
            self.assertTrue((volume / "Émissions" / "matin").is_symlink())
            self.assertFalse((volume / "Émissions" / "_modele").exists())
            self.assertFalse((volume / "00-inbox").exists())
            self.assertFalse((volume / "90-trash").exists())

            (jazz / "deja.mp3").write_bytes(b"audio")
            self.assertEqual((bank / "deja.mp3").read_bytes(), b"audio")

    def test_same_label_stays_distinct_and_rerun_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            for slug in ("jazz", "jazz-2"):
                folder = media / "20-archives" / slug
                folder.mkdir(parents=True)
                (folder / ".banque.json").write_text('{"nom": "Jazz en public"}', encoding="utf-8")
            volume = refresh_volume.refresh(media)
            names = sorted(path.name for path in (volume / "Banques").iterdir())
            self.assertEqual(names, ["Jazz en public", "Jazz en public (jazz-2)"])
            first = [os_read(path) for path in (volume / "Banques").iterdir()]
            refresh_volume.refresh(media)
            second = [os_read(path) for path in (volume / "Banques").iterdir()]
            self.assertEqual(first, second)


def os_read(path: Path) -> str:
    return path.readlink() if path.is_symlink() else path.name


if __name__ == "__main__":
    unittest.main()
