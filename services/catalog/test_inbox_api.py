"""cd services/catalog && python test_inbox_api.py"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import inbox_api


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


if __name__ == "__main__":
    unittest.main()
