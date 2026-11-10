"""cd services/catalog && python test_inbox_api.py"""

from __future__ import annotations

import errno
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import inbox_api

# A disk with 1 000 bytes left.
SMALL_DISK = SimpleNamespace(total=40_000, used=39_000, free=1_000)


class InboxApiTest(unittest.TestCase):
    def test_refuse_unknown_format_duplicate_and_quota(self) -> None:
        self.assertEqual(
            inbox_api.judge_upload("note.txt", "rotation", 12, used=0, limit=100, in_inbox=False, in_bank=False),
            "format inconnu",
        )
        self.assertEqual(
            inbox_api.judge_upload("a.mp3", "rotation", 12, used=0, limit=100, in_inbox=False, in_bank=True),
            "déjà dans la banque",
        )
        self.assertEqual(
            inbox_api.judge_upload("a.mp3", "rotation", 50, used=80, limit=100, in_inbox=False, in_bank=False),
            "quota dépassé",
        )
        self.assertIsNone(
            inbox_api.judge_upload("Artiste - Titre.flac", "ntf2", 20, used=0, limit=100, in_inbox=False, in_bank=False)
        )
        self.assertEqual(inbox_api.safe_name("../x.mp3"), "x.mp3")
        self.assertEqual(inbox_api.safe_name(".secret.mp3"), "")

    def test_the_disk_limits_before_the_quota(self) -> None:
        def judge(size: int, used: int, free: int | None) -> str | None:
            return inbox_api.judge_upload(
                "a.mp3", "rotation", size, used=used, limit=100, in_inbox=False, in_bank=False, free=free
            )

        # A new station: an empty bank, a quota bigger than the disk.
        self.assertEqual(judge(50, used=0, free=40), "pas assez de place sur le disque")
        self.assertIsNone(judge(40, used=0, free=40))
        # Both short: the disk comes first, raising the quota would not help.
        self.assertEqual(judge(50, used=80, free=40), "pas assez de place sur le disque")
        self.assertEqual(judge(30, used=80, free=40), "quota dépassé")
        # A disk that cannot be read leaves the quota alone.
        self.assertIsNone(judge(50, used=0, free=None))

    def test_status_gives_the_disk_under_the_bank(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            disk = inbox_api.inbox_status(media, None)["disk"]
            self.assertEqual(set(disk), {"total", "used", "free"})
            self.assertEqual(disk["total"], shutil.disk_usage(media).total)
            with mock.patch.object(inbox_api.shutil, "disk_usage", side_effect=FileNotFoundError):
                self.assertIsNone(inbox_api.inbox_status(media, None)["disk"])

    def test_hooks_refuse_what_the_disk_cannot_hold(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media = root / "media"
            tusd = root / "tusd"
            tusd.mkdir()
            meta = {"filename": "Artiste - Titre.mp3", "destination": "rotation"}
            with mock.patch.object(inbox_api.shutil, "disk_usage", return_value=SMALL_DISK):
                _status, body = inbox_api.hook_decision({"Upload": {"Size": 4096, "MetaData": meta}}, media, tusd)
                self.assertEqual(body["HTTPResponse"]["Body"], "pas assez de place sur le disque")
                # No room left by the end of the upload: tusd's copy goes, and its room with it.
                stored = tusd / "abc"
                stored.write_bytes(b"x" * 4096)
                event = {"Upload": {"ID": "abc", "Size": 4096, "MetaData": meta, "Storage": {"Path": str(stored)}}}
                _status, body = inbox_api.finish_upload(event, media, tusd)
            self.assertEqual(body, {"error": "pas assez de place sur le disque"})
            self.assertFalse(stored.exists())
            self.assertFalse((media / "00-inbox" / "rotation" / "Artiste - Titre.mp3").exists())

    def test_pre_create_counts_the_copy_through_tusd(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw) / "media"
            tusd = Path(raw) / "tusd"
            media.mkdir()
            tusd.mkdir()
            meta = {"filename": "set.wav", "destination": "rotation"}

            def body(size: int) -> dict:
                return inbox_api.hook_decision({"Upload": {"Size": size, "MetaData": meta}}, media, tusd)[1]

            # One disk: tusd's copy, then the bank's, before tusd's goes. 3 000 bytes hold 1 500 twice.
            disk = SimpleNamespace(total=10_000, used=7_000, free=3_000)
            with mock.patch.object(inbox_api.shutil, "disk_usage", return_value=disk):
                self.assertEqual(body(2_000)["HTTPResponse"]["Body"], "pas assez de place sur le disque")
                self.assertEqual(body(1_500), {})

            # Two disks: each must hold it once.
            def usage(path: Path) -> SimpleNamespace:
                free = 1_000 if Path(path) == tusd else 3_000
                return SimpleNamespace(total=10_000, used=10_000 - free, free=free)

            with (
                mock.patch.object(inbox_api.shutil, "disk_usage", side_effect=usage),
                mock.patch.object(inbox_api, "same_disk", return_value=False),
            ):
                self.assertEqual(body(1_500)["HTTPResponse"]["Body"], "pas assez de place sur le disque")
                self.assertEqual(body(1_000), {})

    def test_a_copy_cut_short_leaves_no_half_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw) / "media"
            tusd = Path(raw) / "tusd"
            tusd.mkdir()
            stored = tusd / "abc"
            stored.write_bytes(b"audio")
            (tusd / "abc.info").write_text("{}")
            target = media / "00-inbox" / "rotation" / "Artiste - Titre.mp3"

            def full(_src: str, dst: str) -> None:
                Path(dst).write_bytes(b"au")
                raise OSError(errno.ENOSPC, "No space left on device")

            meta = {"filename": target.name, "destination": "rotation"}
            event = {"Upload": {"ID": "abc", "Size": 5, "MetaData": meta, "Storage": {"Path": str(stored)}}}
            with mock.patch.object(inbox_api.shutil, "move", side_effect=full):
                _status, body = inbox_api.finish_upload(event, media, tusd)
            self.assertEqual(body, {"error": "pas assez de place sur le disque"})
            self.assertFalse(target.exists())
            self.assertFalse(stored.exists())
            self.assertFalse((tusd / "abc.info").exists())
            reasons = {row["name"]: row["reason"] for row in inbox_api.read_rejets(media)}
            self.assertEqual(reasons[target.name], "pas assez de place sur le disque")

    def test_queue_and_sitting_rejets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            inbox = media / "00-inbox" / "rotation"
            bank = media / "10-rotation"
            inbox.mkdir(parents=True)
            bank.mkdir(parents=True)
            (inbox / "wait.mp3").write_bytes(b"abc")
            (inbox / "note.txt").write_bytes(b"no")
            (inbox / "same.flac").write_bytes(b"x")
            (bank / "same.flac").write_bytes(b"y")
            status = inbox_api.inbox_status(media, None)
            names = {row["name"]: row for row in status["queue"]}
            self.assertIn("wait.mp3", names)
            self.assertIsNone(names["wait.mp3"]["reason"])
            reasons = {row["name"]: row["reason"] for row in status["rejected"]}
            self.assertEqual(reasons["note.txt"], "format inconnu")
            self.assertEqual(reasons["same.flac"], "déjà dans la banque")
            self.assertGreaterEqual(status["quota"]["used"], 3)

    def test_hook_records_the_reason(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            event = {"Upload": {"Size": 4, "MetaData": {"filename": "a.txt", "destination": "rotation"}}}
            status, body = inbox_api.hook_decision(event, media, Path(raw) / "tusd")
            self.assertEqual(status, 200)
            self.assertTrue(body["RejectUpload"])
            self.assertEqual(body["HTTPResponse"]["Body"], "format inconnu")
            saved = json.loads((media / "00-inbox" / "_rejets.json").read_text(encoding="utf-8"))
            self.assertEqual(saved[0]["reason"], "format inconnu")

    def test_finish_moves_an_accepted_file_into_the_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            media = root / "media"
            (media / "20-archives" / "ntf1").mkdir(parents=True)
            tusd = root / "tusd"
            tusd.mkdir()
            stored = tusd / "abc"
            stored.write_bytes(b"audio")
            event = {
                "Upload": {
                    "ID": "abc",
                    "Size": 5,
                    "MetaData": {"filename": "Artiste - Titre.mp3", "destination": "ntf1"},
                    "Storage": {"Path": str(stored)},
                }
            }
            status, body = inbox_api.finish_upload(event, media, tusd)
            self.assertEqual(status, 200)
            self.assertTrue(body.get("ok"))
            target = media / "00-inbox" / "archives" / "ntf1" / "Artiste - Titre.mp3"
            self.assertEqual(target.read_bytes(), b"audio")
            self.assertFalse(stored.exists())

    def test_banks_are_the_folders_of_20_archives(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            for name in ("ntf1", "jazz-live", ".cache", "_vieux", "rotation"):
                (media / "20-archives" / name).mkdir(parents=True)
            (media / "20-archives" / "notes.txt").write_text("pas un dossier")
            (media / "20-archives" / "jazz-live" / ".banque.json").write_text('{"nom": "Jazz en public"}')
            self.assertEqual(list(inbox_api.destinations(media)), ["rotation", "jazz-live", "ntf1"])
            rows = inbox_api.destination_list(media)
            self.assertEqual(
                [(row["id"], row["label"], row["group"]) for row in rows],
                [("rotation", "Rotation", "rotation"), ("jazz-live", "Jazz en public", "archives"), ("ntf1", "NTF 1", "archives")],
            )
            self.assertEqual(inbox_api.inbox_status(media, None)["destinations"], rows)

    def test_an_unknown_bank_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            event = {"Upload": {"Size": 4, "MetaData": {"filename": "a.mp3", "destination": "ntf9"}}}
            _status, body = inbox_api.hook_decision(event, media, media / "tusd")
            self.assertEqual(body["HTTPResponse"]["Body"], "destination inconnue")

    def test_create_bank(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            (media / "20-archives" / "ntf1").mkdir(parents=True)
            status, body = inbox_api.create_bank(media, "  Archives   jazz ", "jazz")
            self.assertEqual(status, 201)
            self.assertEqual(body["destination"]["label"], "Archives jazz")
            self.assertTrue((media / "00-inbox" / "archives" / "jazz").is_dir())
            self.assertEqual(inbox_api.bank_label(media, "jazz"), "Archives jazz")
            self.assertIn("jazz", inbox_api.destinations(media))
            for label, folder, code in [
                ("Autre", "jazz", 409),
                ("archives JAZZ", "jazz2", 409),
                ("ntf 1", "ntf1", 409),
                ("Rotation", "rot", 409),
                ("Musique", "rotation", 409),
                ("Sans dossier", "Jazz Live", 400),
                ("Sans dossier", "../x", 400),
                ("", "vide", 400),
            ]:
                self.assertEqual(inbox_api.create_bank(media, label, folder)[0], code, (label, folder))

    def test_the_tusd_volume_goes_to_tusd(self) -> None:
        # Docker crée le volume au nom de root, et tusd ne tourne pas en root.
        with tempfile.TemporaryDirectory() as raw:
            tusd = Path(raw)
            mine = tusd.stat()
            with mock.patch.object(inbox_api.os, "chown") as chown:
                self.assertIsNone(inbox_api.give_tusd_dir(tusd, f"{mine.st_uid + 1}:{mine.st_gid + 1}"))
                chown.assert_called_once_with(tusd, mine.st_uid + 1, mine.st_gid + 1)
                chown.reset_mock()
                # Déjà à tusd, ou sans dossier, comme en dev : rien ne change.
                self.assertIsNone(inbox_api.give_tusd_dir(tusd, f"{mine.st_uid}:{mine.st_gid}"))
                self.assertIsNone(inbox_api.give_tusd_dir(tusd / "absent", "1000:1000"))
                chown.assert_not_called()

    def test_a_tusd_volume_left_to_root_is_said(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tusd = Path(raw)
            mine = tusd.stat()
            refused = PermissionError(1, "Operation not permitted")
            with mock.patch.object(inbox_api.os, "chown", side_effect=refused):
                warning = inbox_api.give_tusd_dir(tusd, f"{mine.st_uid + 1}:{mine.st_gid + 1}")
            self.assertIn(f"{tusd} n'a pas pu être donné à tusd", warning or "")
            self.assertIn("« Si un envoi échoue »", warning or "")
            self.assertIn("n'a pas pu être donné", inbox_api.give_tusd_dir(tusd, "tusd") or "")


if __name__ == "__main__":
    unittest.main()
