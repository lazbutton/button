"""python test_layout.py — le rangement de la banque, tel que le catalogue le lit.

Le catalogue nomme les dossiers de la banque dans layout.py, et nulle part
ailleurs (docs/decisions/0019-le-rangement-de-la-banque.md). Ce test fige ce
qu'il tire d'un chemin : le genre d'un fichier, son regroupement, sa zone, où va
un dépôt de l'inbox, ce que la recherche garde.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as catalog
import inbox_api
import layout

HERE = Path(__file__).resolve().parent


class CatalogueReadsTheBankTest(unittest.TestCase):
    """What the catalogue makes of a path of the bank."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.media = Path(self.tmp.name).resolve()
        self.before = catalog.MEDIA_ROOT
        catalog.MEDIA_ROOT = self.media
        # No ffprobe on a file that is no sound: the tests read no duration.
        probe = mock.patch.object(catalog.subprocess, "check_output", side_effect=OSError("pas de ffprobe"))
        probe.start()
        self.addCleanup(probe.stop)

    def tearDown(self) -> None:
        catalog.MEDIA_ROOT = self.before
        self.tmp.cleanup()

    def put(self, rel: str, data: bytes = b"ID3 un son") -> Path:
        path = self.media / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_the_kind_comes_from_the_folder(self) -> None:
        cases = {
            "30-habillage/jingles/a.mp3": "jingle",
            "30-habillage/ids/a.mp3": "jingle",
            "30-habillage/stings/a.mp3": "jingle",
            "30-habillage/jingles/noel/a.mp3": "jingle",
            "30-habillage/pubs/a.mp3": "pub",
            "30-habillage/beds/a.mp3": "son",
            "30-habillage/sfx/a.mp3": "son",
            "30-habillage/a.mp3": "son",
            "10-rotation/a.mp3": "son",
            "20-archives/jazz/a.mp3": "son",
            "40-emissions/matinale/podcasts/a.mp3": "podcast",
            "40-emissions/matinale/entiere/a.mp3": "emission",
            "40-emissions/matinale/a.mp3": "son",
            "50-carts/3/a.mp3": "son",
            "ailleurs/a.mp3": "son",
        }
        for rel, kind in cases.items():
            self.assertEqual(catalog.kind_of(rel), kind, rel)

    def test_the_grouping_comes_from_the_folder(self) -> None:
        cases = {
            "10-rotation/a.mp3": "rotation",
            "10-rotation/vrac/a.mp3": "rotation",
            "20-archives/jazz/a.mp3": "jazz",
            "20-archives/jazz/live/a.mp3": "jazz",
            "40-emissions/matinale/entiere/a.mp3": "matinale",
            "30-habillage/jingles/a.mp3": "",
            "50-carts/3/a.mp3": "",
            "ailleurs/a.mp3": "",
            # A file left beside the collections takes its own name: no collection holds it.
            "20-archives/a.mp3": "a.mp3",
        }
        for rel, grouping in cases.items():
            self.assertEqual(catalog.grouping_of(rel), grouping, rel)

    def test_a_document_says_where_its_file_is(self) -> None:
        doc = catalog.document_for(self.put("20-archives/jazz/Ada - Song.mp3"))
        self.assertEqual(doc["path"], "20-archives/jazz/Ada - Song.mp3")
        self.assertEqual(doc["folder"], "20-archives/jazz")
        self.assertEqual(doc["top"], "20-archives")
        self.assertEqual(doc["grouping"], "jazz")
        self.assertEqual(doc["kind"], "son")

    def test_a_document_says_its_zone_without_naming_a_folder(self) -> None:
        # What the console filters on: the zone, and the kind of habillage.
        cases = {
            "10-rotation/a.mp3": ("rotation", ""),
            "20-archives/jazz/a.mp3": ("collections", ""),
            "30-habillage/beds/a.mp3": ("habillage", "beds"),
            "30-habillage/beds/noel/a.mp3": ("habillage", "beds"),
            "30-habillage/a.mp3": ("habillage", ""),
            "30-habillage/autre/a.mp3": ("habillage", ""),
            "40-emissions/matinale/entiere/a.mp3": ("emissions", ""),
            "50-carts/3/a.mp3": ("bacs", ""),
            "ailleurs/a.mp3": ("", ""),
        }
        for rel, expected in cases.items():
            doc = catalog.document_for(self.put(rel))
            self.assertEqual((doc["zone"], doc["habillage"]), expected, rel)

    def test_the_inbox_and_the_trash_are_not_indexed(self) -> None:
        self.assertIsNone(catalog.document_for(self.put("00-inbox/rotation/a.mp3")))
        self.assertIsNone(catalog.document_for(self.put("90-trash/a.mp3")))
        self.assertFalse(catalog.in_library("00-inbox/rotation/a.mp3"))
        self.assertFalse(catalog.in_library("90-trash/a.mp3"))
        self.assertTrue(catalog.in_library("10-rotation/a.mp3"))

    def test_after_a_prune_the_search_keeps_the_bacs(self) -> None:
        (self.media / catalog.CARTS_ONLY_FLAG).write_text("1\n")
        (self.media / catalog.CART_PATHS_FILE).write_text("30-habillage/jingles/a.mp3\n")
        self.assertTrue(catalog.in_library("50-carts/3/a.mp3"))
        self.assertTrue(catalog.in_library("30-habillage/jingles/a.mp3"))
        self.assertFalse(catalog.in_library("30-habillage/jingles/b.mp3"))
        self.assertFalse(catalog.in_library("10-rotation/a.mp3"))

    def test_each_inbox_folder_has_its_destination(self) -> None:
        (self.media / "20-archives" / "jazz").mkdir(parents=True)
        self.assertEqual(
            catalog.promote_rules(),
            [
                ("00-inbox/rotation", "10-rotation", "music"),
                ("00-inbox/habillage/jingles", "30-habillage/jingles", "file"),
                ("00-inbox/habillage/ids", "30-habillage/ids", "file"),
                ("00-inbox/habillage/pubs", "30-habillage/pubs", "file"),
                ("00-inbox/habillage/beds", "30-habillage/beds", "file"),
                ("00-inbox/habillage/stings", "30-habillage/stings", "file"),
                ("00-inbox/habillage/sfx", "30-habillage/sfx", "file"),
                ("00-inbox/archives/jazz", "20-archives/jazz", "music"),
            ],
        )

    def test_the_inbox_folders_the_catalogue_polls(self) -> None:
        (self.media / "20-archives" / "jazz").mkdir(parents=True)
        (self.media / "00-inbox" / "emissions" / "matinale").mkdir(parents=True)
        (self.media / "00-inbox" / "emissions" / ".cache").mkdir()
        polled = [path.relative_to(self.media).as_posix() for path in catalog.inbox_dirs()]
        self.assertEqual(
            polled,
            [
                "00-inbox/rotation",
                "00-inbox/habillage/jingles",
                "00-inbox/habillage/ids",
                "00-inbox/habillage/pubs",
                "00-inbox/habillage/beds",
                "00-inbox/habillage/stings",
                "00-inbox/habillage/sfx",
                "00-inbox/archives/jazz",
                "00-inbox/emissions/matinale/entiere",
                "00-inbox/emissions/matinale/podcasts",
            ],
        )

    def test_a_deposit_of_habillage_joins_its_folder(self) -> None:
        moved = catalog.promote_file(self.put("00-inbox/habillage/jingles/top.mp3"))
        self.assertEqual(moved, self.media / "30-habillage" / "jingles" / "top.mp3")
        self.assertTrue(moved.is_file())
        # A name already taken is never overwritten.
        again = catalog.promote_file(self.put("00-inbox/habillage/jingles/top.mp3"))
        self.assertEqual(again, self.media / "30-habillage" / "jingles" / "top-2.mp3")

    def test_a_deposit_of_a_show_joins_its_folder(self) -> None:
        moved = catalog.promote_file(self.put("00-inbox/emissions/matinale/entiere/lundi.mp3"))
        self.assertEqual(moved, self.media / "40-emissions" / "matinale" / "entiere" / "lundi.mp3")
        # Neither another folder of the show, nor a hidden show.
        self.assertIsNone(catalog.promote_file(self.put("00-inbox/emissions/matinale/brouillon/a.mp3")))
        self.assertIsNone(catalog.promote_file(self.put("00-inbox/emissions/.cache/entiere/a.mp3")))

    def test_music_without_tags_waits_in_the_inbox(self) -> None:
        # The Beets loop tags it from its name, then moves it: promote-inbox.sh.
        waiting = self.put("00-inbox/rotation/Ada - Song.mp3")
        self.assertIsNone(catalog.promote_file(waiting))
        self.assertTrue(waiting.is_file())
        self.assertIsNone(catalog.promote_file(self.put("00-inbox/archives/inconnue/a.mp3")))

    def test_the_quota_counts_the_inbox_the_rotation_and_the_collections(self) -> None:
        self.put("00-inbox/rotation/a.mp3", b"12345")
        self.put("10-rotation/b.mp3", b"123")
        self.put("20-archives/jazz/c.mp3", b"12")
        self.put("30-habillage/jingles/d.mp3", b"1234567")
        self.put("50-carts/3/e.mp3", b"1234567")
        self.assertEqual(inbox_api.used_bytes(self.media), 10)

    def test_the_refusals_are_noted_in_the_inbox(self) -> None:
        inbox_api.record_rejet(self.media, "a.exe", "rotation", "format inconnu")
        self.assertTrue((self.media / "00-inbox" / "_rejets.json").is_file())

    def test_the_console_is_told_where_a_collection_is_born(self) -> None:
        (self.media / "20-archives" / "jazz").mkdir(parents=True)
        status = inbox_api.inbox_status(self.media, None)
        self.assertEqual(status["collections"], {"folder": "20-archives"})
        self.assertEqual(
            [(row["id"], row["folder"]) for row in status["destinations"]],
            [("rotation", "10-rotation"), ("jazz", "20-archives/jazz")],
        )


class SearchFilterTest(unittest.TestCase):
    """The filters of GET /search, as Meilisearch receives them."""

    def test_the_console_filters_without_naming_a_folder(self) -> None:
        self.assertEqual(
            catalog.search_filter({"q": ["ada"], "zone": ["collections"]}),
            (['zone = "collections"'], ["zone"]),
        )
        self.assertEqual(
            catalog.search_filter({"habillage": ["beds,stings,sfx"]}),
            (['(habillage = "beds" OR habillage = "stings" OR habillage = "sfx")'], ["habillage"]),
        )

    def test_an_older_console_still_filters_by_folder(self) -> None:
        clauses, applied = catalog.search_filter(
            {
                "kind": ["son"],
                "grouping": ["matinale, jazz"],
                "folder": ["30-habillage/beds"],
                "top": ["20-archives"],
            }
        )
        self.assertEqual(
            clauses,
            [
                '(kind = "son" OR kind = "emission" OR kind = "podcast")',
                '(grouping = "matinale" OR grouping = "jazz")',
                'folder = "30-habillage/beds"',
                'top = "20-archives"',
            ],
        )
        self.assertEqual(applied, ["kind", "grouping", "folder", "top"])

    def test_a_search_without_a_filter(self) -> None:
        self.assertEqual(catalog.search_filter({"q": ["ada"]}), ([], []))
        self.assertEqual(catalog.search_filter({"kind": ['"'], "zone": [" , "]}), ([], []))

    def test_a_kind_is_one_word(self) -> None:
        clauses, applied = catalog.search_filter({"kind": ['jingle" OR kind != "']})
        self.assertEqual(clauses, ['kind = "jingleORkind"'])
        self.assertEqual(applied, ["kind"])


class OneListOfNamesTest(unittest.TestCase):
    """The folders of the bank are named in layout.py, and nowhere else."""

    def test_the_image_ships_every_module_of_the_catalogue(self) -> None:
        dockerfile = (HERE / "Dockerfile").read_text(encoding="utf-8")
        shipped = set(re.findall(r"services/catalog/(\w+\.py)", dockerfile))
        modules = {path.name for path in HERE.glob("*.py") if not path.name.startswith("test_")}
        self.assertEqual(shipped, modules)

    def test_the_catalogue_names_the_folders_in_layout_only(self) -> None:
        names = [
            layout.INBOX,
            layout.ROTATION,
            layout.COLLECTIONS,
            layout.HABILLAGE,
            layout.EMISSIONS,
            layout.CARTS,
            layout.TRASH,
        ]
        for path in sorted(HERE.glob("*.py")):
            if path.name == "layout.py" or path.name.startswith("test_"):
                continue
            text = path.read_text(encoding="utf-8")
            for name in names:
                self.assertNotIn(name, text, f"{path.name} nomme {name} : le lire dans layout.py")


if __name__ == "__main__":
    unittest.main()
