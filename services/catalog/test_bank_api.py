"""cd services/catalog && python test_bank_api.py — voir et gérer le contenu de la banque."""

from __future__ import annotations

import errno
import json
import os
import re
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from mutagen.id3 import TIT2, TPE1
from mutagen.wave import WAVE

import app as catalog
import bank_api
import inbox_api


def sound(path: Path, seconds: float = 1.0, artist: str = "", title: str = "") -> Path:
    """A real sound, one mutagen measures: a silent WAV, with its tags if any."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00\x00" * int(8000 * seconds))
    if artist or title:
        audio = WAVE(path)
        audio.add_tags()
        if artist:
            audio.tags.add(TPE1(encoding=3, text=artist))
        if title:
            audio.tags.add(TIT2(encoding=3, text=title))
        audio.save()
    return path


class Bank(unittest.TestCase):
    """A temporary bank: rotation, and the collection « jazz », named « Jazz d'été »."""

    def setUp(self) -> None:
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        self.media = Path(raw.name).resolve() / "media"
        self.rotation = self.media / "10-rotation"
        self.jazz = self.media / "20-archives" / "jazz"
        self.trash = self.media / "90-trash"
        self.rotation.mkdir(parents=True)
        self.jazz.mkdir(parents=True)
        (self.jazz / ".banque.json").write_text(json.dumps({"nom": "Jazz d'été"}), encoding="utf-8")
        bank_api._TAGS.clear()

    def names(self, destination: str = "rotation", **more) -> list[str]:
        status, payload = bank_api.list_files(self.media, destination, **more)
        self.assertEqual(status, 200)
        return [row["name"] for row in payload["files"]]


class ListTest(Bank):
    def test_the_list_reads_the_disk(self) -> None:
        sound(self.rotation / "Zoé - Nuit.wav")
        sound(self.rotation / "ada - Song.wav")
        sound(self.rotation / "Élan - Fleuve.wav")
        sound(self.rotation / "Album" / "01 Piste.wav")
        (self.rotation / "notes.txt").write_text("à trier")
        # Hidden: a file half written by the tagging pass, a folder of the Finder.
        (self.rotation / ".Ada - Song.partial.wav").write_bytes(b"une moitie")
        sound(self.rotation / ".cache" / "caché.wav")

        status, payload = bank_api.list_files(self.media, "rotation")
        self.assertEqual(status, 200)
        # By name, accents and case aside, a file of a subfolder under its path.
        self.assertEqual(
            [row["name"] for row in payload["files"]],
            ["ada - Song.wav", "Album/01 Piste.wav", "Élan - Fleuve.wav", "notes.txt", "Zoé - Nuit.wav"],
        )
        self.assertEqual((payload["total"], payload["matched"], payload["partial"]), (5, 5, False))
        self.assertEqual(payload["bytes"], sum(row["bytes"] for row in payload["files"]))
        self.assertEqual(
            payload["destination"], {"id": "rotation", "label": "Rotation", "group": "rotation", "folder": "10-rotation"}
        )
        # The label of a collection is not one of its titles.
        self.assertEqual(self.names("jazz"), [])
        self.assertEqual(bank_api.list_files(self.media, "jazz")[1]["destination"]["label"], "Jazz d'été")

    def test_tags_come_from_the_file_then_from_its_name(self) -> None:
        sound(self.rotation / "01.wav", seconds=2, artist="Ada Lovelace", title="Le chant des machines")
        sound(self.rotation / "Bea_Sans_Tag.wav", seconds=1)
        (self.rotation / "notes.txt").write_text("pas un son")
        rows = {row["name"]: row for row in bank_api.list_files(self.media, "rotation")[1]["files"]}

        tagged = rows["01.wav"]
        self.assertEqual((tagged["artist"], tagged["title"]), ("Ada Lovelace", "Le chant des machines"))
        self.assertAlmostEqual(tagged["duration"], 2.0, places=1)
        self.assertEqual((rows["Bea_Sans_Tag.wav"]["artist"], rows["Bea_Sans_Tag.wav"]["title"]), ("", "Bea Sans Tag"))
        # Not audio: listed all the same, without a length, and without waiting on ffprobe.
        self.assertEqual((rows["notes.txt"]["title"], rows["notes.txt"]["duration"]), ("notes", None))
        self.assertRegex(tagged["modified"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")

    def test_a_file_that_changed_is_read_again(self) -> None:
        path = sound(self.rotation / "a.wav", artist="Avant")
        self.assertEqual(bank_api.list_files(self.media, "rotation")[1]["files"][0]["artist"], "Avant")
        sound(path, seconds=3, artist="Après")
        row = bank_api.list_files(self.media, "rotation")[1]["files"][0]
        self.assertEqual(row["artist"], "Après")
        self.assertAlmostEqual(row["duration"], 3.0, places=1)

    def test_pages_and_newest_first(self) -> None:
        for index, name in enumerate(["a.wav", "b.wav", "c.wav", "d.wav"]):
            path = sound(self.rotation / name)
            stamp = (1_700_000_000 + index * 60) * 1_000_000_000
            os.utime(path, ns=(stamp, stamp))
        self.assertEqual(self.names(offset=1, limit=2), ["b.wav", "c.wav"])
        self.assertEqual(self.names(sort="recent", limit=2), ["d.wav", "c.wav"])
        # A page is never bigger than PAGE_MAX, never empty by mistake.
        self.assertEqual(self.names(offset=-3, limit=0), ["a.wav"])
        status, payload = bank_api.list_files(self.media, "rotation", offset=3, limit=10_000)
        self.assertEqual(([row["name"] for row in payload["files"]], payload["total"]), (["d.wav"], 4))

    def test_search_reads_names_then_tags(self) -> None:
        sound(self.rotation / "01 piste.wav", artist="Élise Caron", title="Chanson d'été")
        sound(self.rotation / "Bob - Elise.wav")
        sound(self.rotation / "Cy - Autre.wav")
        self.assertEqual(self.names(query="elise"), ["01 piste.wav", "Bob - Elise.wav"])
        # Every word, wherever it is: one in the name, one in the title.
        self.assertEqual(self.names(query="  PISTE   été "), ["01 piste.wav"])
        self.assertEqual(self.names(query="elise autre"), [])
        status, payload = bank_api.list_files(self.media, "rotation", query="cy")
        self.assertEqual((payload["total"], payload["matched"], payload["partial"]), (3, 1, False))

    def test_a_search_out_of_time_says_so_and_reads_on(self) -> None:
        sound(self.rotation / "01.wav", artist="Ada")
        sound(self.rotation / "Ada - Song.wav")
        with mock.patch.object(bank_api, "SEARCH_BUDGET", -1):
            status, payload = bank_api.list_files(self.media, "rotation", query="ada")
        # The name answers at once; the tags of 01.wav were not read in time.
        self.assertEqual(([row["name"] for row in payload["files"]], payload["partial"]), (["Ada - Song.wav"], True))
        deadline = time.monotonic() + 5
        while bank_api._WARMING and time.monotonic() < deadline:
            time.sleep(0.01)
        with mock.patch.object(bank_api, "SEARCH_BUDGET", -1):
            status, payload = bank_api.list_files(self.media, "rotation", query="ada")
        self.assertEqual(
            ([row["name"] for row in payload["files"]], payload["partial"]), (["01.wav", "Ada - Song.wav"], False)
        )

    def test_an_unknown_collection_is_not_found(self) -> None:
        for destination in ("", "inconnue", "../10-rotation", ".cache", "_modele"):
            self.assertEqual(
                bank_api.list_files(self.media, destination), (404, {"error": "Collection introuvable."}), destination
            )
        # A rotation folder not there yet is an empty rotation.
        self.rotation.rmdir()
        self.assertEqual(self.names(), [])

    def test_the_summary_counts_each_collection(self) -> None:
        sound(self.rotation / "a.wav")
        sound(self.jazz / "b.wav")
        sound(self.jazz / "c.wav")
        rows = bank_api.summary(self.media)["destinations"]
        self.assertEqual([(row["id"], row["label"], row["count"]) for row in rows], [("rotation", "Rotation", 1), ("jazz", "Jazz d'été", 2)])
        self.assertEqual(rows[1]["bytes"], (self.jazz / "b.wav").stat().st_size * 2)

    def test_only_a_file_of_the_collection_is_listed_and_played(self) -> None:
        inside = sound(self.rotation / "Ada - Song.wav")
        outside = sound(self.media.parent / "ailleurs.wav", artist="Secret")
        (self.rotation / "lien.wav").symlink_to(outside)
        (self.rotation / "voisin.wav").symlink_to(sound(self.jazz / "Bea - Live.wav"))
        (self.rotation / "copie.wav").symlink_to(inside)

        # A link that stays in the collection is one of its titles; the others are not read.
        self.assertEqual(self.names(), ["Ada - Song.wav", "copie.wav"])
        self.assertEqual(bank_api.file_path(self.media, "rotation", "Ada - Song.wav"), inside)
        self.assertEqual(bank_api.file_path(self.media, "rotation", "copie.wav"), inside)
        for name in ("lien.wav", "voisin.wav", "", "../20-archives/jazz/Bea - Live.wav", "/etc/passwd", ".banque.json"):
            self.assertIsNone(bank_api.file_path(self.media, "rotation", name), name)
        for name in ("absent.wav", "a\x00b"):
            self.assertIsNone(bank_api.file_path(self.media, "rotation", name), name)
        self.assertIsNone(bank_api.file_path(self.media, "inconnue", "Ada - Song.wav"))

    def test_a_link_out_of_the_collection_is_never_touched(self) -> None:
        outside = sound(self.media.parent / "ailleurs.wav")
        (self.rotation / "lien.wav").symlink_to(outside)
        self.assertEqual(
            bank_api.remove_files(self.media, "rotation", ["lien.wav"]),
            (200, {"removed": [], "failed": [{"name": "lien.wav", "reason": "fichier introuvable"}]}),
        )
        self.assertEqual(bank_api.move_files(self.media, "rotation", "jazz", ["lien.wav"])[1]["moved"], [])
        self.assertTrue((self.rotation / "lien.wav").is_symlink() and outside.is_file())
        self.assertFalse(self.trash.exists() and any(self.trash.iterdir()))

    def test_a_link_in_the_collection_goes_to_the_trash_as_a_link(self) -> None:
        inside = sound(self.rotation / "Ada - Song.wav")
        (self.rotation / "copie.wav").symlink_to(inside.name)
        self.assertEqual(bank_api.remove_files(self.media, "rotation", ["copie.wav"])[1]["removed"], ["copie.wav"])
        # The link left; the sound it named stays where it was, with one name only.
        self.assertTrue((self.trash / "copie.wav").is_symlink())
        self.assertEqual((inside.stat().st_nlink, self.names()), (1, ["Ada - Song.wav"]))


class RemoveTest(Bank):
    def test_a_removed_title_goes_to_the_trash(self) -> None:
        sound(self.rotation / "Ada - Song.wav")
        sound(self.rotation / "Album" / "Bea - Live.wav")
        sound(self.rotation / "Cy - Reste.wav")
        status, payload = bank_api.remove_files(
            self.media, "rotation", ["Ada - Song.wav", "Album/Bea - Live.wav", "absent.wav", "Ada - Song.wav"]
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["removed"], ["Ada - Song.wav", "Album/Bea - Live.wav"])
        self.assertEqual(payload["failed"], [{"name": "absent.wav", "reason": "fichier introuvable"}])
        self.assertEqual(self.names(), ["Cy - Reste.wav"])
        self.assertEqual(sorted(path.name for path in self.trash.iterdir()), ["Ada - Song.wav", "Bea - Live.wav"])

    def test_the_trash_never_loses_a_file_of_the_same_name(self) -> None:
        self.trash.mkdir()
        (self.trash / "Ada - Song.wav").write_bytes(b"le premier")
        (self.trash / "Ada - Song (2).wav").write_bytes(b"le second")
        sound(self.rotation / "Ada - Song.wav")
        status, payload = bank_api.remove_files(self.media, "rotation", ["Ada - Song.wav"])
        self.assertEqual((status, payload), (200, {"removed": ["Ada - Song.wav"], "failed": []}))
        self.assertEqual((self.trash / "Ada - Song.wav").read_bytes(), b"le premier")
        self.assertEqual((self.trash / "Ada - Song (2).wav").read_bytes(), b"le second")
        self.assertTrue((self.trash / "Ada - Song (3).wav").is_file())

    def test_a_name_never_leaves_its_collection(self) -> None:
        kept = sound(self.jazz / "Bea - Live.wav")
        outside = sound(self.media.parent / "ailleurs.wav")
        (self.rotation / "dehors").symlink_to(self.media.parent)
        names = ["../20-archives/jazz/Bea - Live.wav", "/etc/passwd", ".banque.json", "dehors/ailleurs.wav", "", 3]
        status, payload = bank_api.remove_files(self.media, "rotation", names[:-1])
        self.assertEqual(status, 200)
        self.assertEqual(payload["removed"], [])
        self.assertEqual([row["reason"] for row in payload["failed"]], ["fichier introuvable"] * 5)
        self.assertTrue(kept.is_file() and outside.is_file())
        self.assertEqual(list(self.trash.iterdir()), [])
        # Not a list of names: nothing is tried.
        for bad in (names, [], None, "Ada - Song.wav"):
            self.assertEqual(bank_api.remove_files(self.media, "rotation", bad), (400, {"error": "Aucun titre choisi."}))
        many = [f"{index}.wav" for index in range(bank_api.MAX_NAMES + 1)]
        self.assertEqual(
            bank_api.remove_files(self.media, "rotation", many),
            (400, {"error": "Trop de titres à la fois : 500 au plus."}),
        )
        self.assertEqual(bank_api.remove_files(self.media, "inconnue", ["a.wav"])[0], 404)


class MoveTest(Bank):
    def test_titles_move_to_another_collection(self) -> None:
        sound(self.rotation / "Ada - Song.wav")
        sound(self.rotation / "Album" / "Bea - Live.wav")
        status, payload = bank_api.move_files(self.media, "rotation", "jazz", ["Ada - Song.wav", "Album/Bea - Live.wav"])
        self.assertEqual((status, payload), (200, {"moved": ["Ada - Song.wav", "Album/Bea - Live.wav"], "failed": []}))
        self.assertEqual(self.names(), [])
        # A collection is flat: the title of a subfolder lands at its root.
        self.assertEqual(self.names("jazz"), ["Ada - Song.wav", "Bea - Live.wav"])
        status, payload = bank_api.move_files(self.media, "jazz", "rotation", ["Ada - Song.wav"])
        self.assertEqual(payload["moved"], ["Ada - Song.wav"])
        self.assertEqual(self.names(), ["Ada - Song.wav"])

    def test_a_move_never_replaces_a_title(self) -> None:
        sound(self.rotation / "Ada - Song.wav", seconds=2)
        (self.jazz / "Ada - Song.wav").write_bytes(b"celui qui y est")
        status, payload = bank_api.move_files(self.media, "rotation", "jazz", ["Ada - Song.wav", "absent.wav"])
        self.assertEqual(status, 200)
        self.assertEqual(payload["moved"], [])
        self.assertEqual(
            payload["failed"],
            [
                {"name": "Ada - Song.wav", "reason": "déjà dans Jazz d'été"},
                {"name": "absent.wav", "reason": "fichier introuvable"},
            ],
        )
        self.assertEqual((self.jazz / "Ada - Song.wav").read_bytes(), b"celui qui y est")
        self.assertTrue((self.rotation / "Ada - Song.wav").is_file())

    def test_a_move_names_two_collections(self) -> None:
        sound(self.rotation / "Ada - Song.wav")
        self.assertEqual(
            bank_api.move_files(self.media, "rotation", "rotation", ["Ada - Song.wav"]),
            (400, {"error": "Ces titres y sont déjà."}),
        )
        for source, target in (("rotation", "inconnue"), ("inconnue", "jazz"), ("rotation", "")):
            self.assertEqual(
                bank_api.move_files(self.media, source, target, ["Ada - Song.wav"]),
                (404, {"error": "Collection introuvable."}),
            )
        self.assertEqual(bank_api.move_files(self.media, "rotation", "jazz", [])[0], 400)
        self.assertEqual(self.names(), ["Ada - Song.wav"])

    def test_a_move_to_another_disk_copies(self) -> None:
        sound(self.rotation / "Ada - Song.wav")
        # A collection on its own disk, or a file system without hard links.
        with mock.patch.object(bank_api.os, "link", side_effect=OSError(errno.EXDEV, "autre disque")):
            status, payload = bank_api.move_files(self.media, "rotation", "jazz", ["Ada - Song.wav"])
            self.assertEqual(payload, {"moved": ["Ada - Song.wav"], "failed": []})
            # Even then, a title already there stays.
            sound(self.rotation / "Ada - Song.wav")
            status, payload = bank_api.move_files(self.media, "rotation", "jazz", ["Ada - Song.wav"])
            self.assertEqual(payload["failed"], [{"name": "Ada - Song.wav", "reason": "déjà dans Jazz d'été"}])
        self.assertEqual((self.names(), self.names("jazz")), (["Ada - Song.wav"], ["Ada - Song.wav"]))

    def test_a_copy_cut_short_leaves_the_title_where_it_was(self) -> None:
        sound(self.rotation / "Ada - Song.wav")
        full = OSError(errno.ENOSPC, "disque plein")
        with (
            mock.patch.object(bank_api.os, "link", side_effect=OSError(errno.EXDEV, "autre disque")),
            mock.patch.object(inbox_api.shutil, "move", side_effect=full),
        ):
            status, payload = bank_api.move_files(self.media, "rotation", "jazz", ["Ada - Song.wav"])
        self.assertEqual(
            payload, {"moved": [], "failed": [{"name": "Ada - Song.wav", "reason": "pas assez de place sur le disque"}]}
        )
        self.assertEqual((self.names(), self.names("jazz")), (["Ada - Song.wav"], []))


class CollectionTest(Bank):
    def test_a_new_name_keeps_the_folder(self) -> None:
        (self.jazz / ".banque.json").write_text(json.dumps({"nom": "Jazz d'été", "note": "à garder"}), encoding="utf-8")
        status, payload = inbox_api.rename_bank(self.media, "jazz", "  Jazz   du soir ")
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["destination"],
            {"id": "jazz", "label": "Jazz du soir", "group": "archives", "folder": "20-archives/jazz"},
        )
        self.assertEqual(inbox_api.bank_label(self.media, "jazz"), "Jazz du soir")
        self.assertEqual(
            json.loads((self.jazz / ".banque.json").read_text(encoding="utf-8")),
            {"nom": "Jazz du soir", "note": "à garder"},
        )
        self.assertEqual([path.name for path in self.jazz.iterdir()], [".banque.json"])
        # The same name again, another case: it is still its own.
        self.assertEqual(inbox_api.rename_bank(self.media, "jazz", "JAZZ DU SOIR")[0], 200)

    def test_a_new_name_is_checked_like_the_first(self) -> None:
        (self.media / "20-archives" / "nuit").mkdir()
        cases = [
            ("rotation", "Musique", 400, "La Rotation garde son nom."),
            ("jazz", "   ", 400, "Donne un nom à la collection."),
            ("jazz", "x" * 61, 400, "Nom trop long : 60 caractères au plus."),
            ("jazz", "Rotation", 409, "« rotation » est réservé à la musique de l'auto-DJ."),
            ("jazz", "NUIT", 409, "Une collection porte déjà ce nom."),
            ("inconnue", "Nom", 404, "Collection introuvable."),
            ("../jazz", "Nom", 404, "Collection introuvable."),
        ]
        for name, label, status, error in cases:
            self.assertEqual(inbox_api.rename_bank(self.media, name, label), (status, {"error": error}), (name, label))
        self.assertEqual(inbox_api.bank_label(self.media, "jazz"), "Jazz d'été")

    def test_only_an_empty_collection_is_deleted(self) -> None:
        inbox = self.media / "00-inbox" / "archives" / "jazz"
        inbox.mkdir(parents=True)
        title = sound(self.jazz / "Ada - Song.wav")
        self.assertEqual(
            inbox_api.delete_bank(self.media, "jazz"),
            (409, {"error": "La collection contient encore 1 fichier : retire ou déplace d'abord ses titres."}),
        )
        title.unlink()
        waiting = sound(inbox / "Bea - Live.wav")
        sound(inbox / "Cy - Tune.wav")
        self.assertEqual(
            inbox_api.delete_bank(self.media, "jazz"),
            (409, {"error": "2 envois attendent encore dans le dépôt de la collection : réessaie une fois rangé."}),
        )
        self.assertTrue(self.jazz.is_dir() and waiting.is_file())
        for path in inbox.iterdir():
            path.unlink()
        # What the Finder and the tagging pass leave behind does not hold a collection.
        (self.jazz / ".DS_Store").write_bytes(b"finder")
        (self.jazz / "vide").mkdir()
        self.assertEqual(inbox_api.delete_bank(self.media, "jazz"), (200, {"deleted": "jazz"}))
        self.assertFalse(self.jazz.exists() or inbox.exists())
        self.assertEqual([row["id"] for row in inbox_api.destination_list(self.media)], ["rotation"])

    def test_what_is_not_a_plain_collection_stays(self) -> None:
        self.assertEqual(inbox_api.delete_bank(self.media, "rotation"), (400, {"error": "La Rotation ne se supprime pas."}))
        for name in ("inconnue", "", "../10-rotation"):
            self.assertEqual(inbox_api.delete_bank(self.media, name), (404, {"error": "Collection introuvable."}), name)
        elsewhere = self.media.parent / "disque"
        elsewhere.mkdir()
        (self.media / "20-archives" / "lien").symlink_to(elsewhere)
        status, payload = inbox_api.delete_bank(self.media, "lien")
        self.assertEqual((status, payload["error"][:28]), (409, "Ce dossier est un lien ou un"))
        self.assertTrue(elsewhere.is_dir() and self.rotation.is_dir())

    def test_a_title_that_just_arrived_is_never_deleted(self) -> None:
        late = sound(self.jazz / "Ada - Song.wav")
        # It came in between the count and the removal.
        with mock.patch.object(inbox_api, "_visible_files", return_value=0):
            status, payload = inbox_api.delete_bank(self.media, "jazz")
        self.assertEqual(status, 409)
        self.assertTrue(late.is_file())
        self.assertEqual(inbox_api.bank_label(self.media, "jazz"), "Jazz d'été")


class Engine(BaseHTTPRequestHandler):
    """A fake engine: who is behind a cookie, and what they may do."""

    rights = {
        "session=animateur": {"live": True},
        "session=programmateur": {"carts": True},
        "session=admin": {"admin": True},
    }
    down = False

    def do_GET(self) -> None:  # noqa: N802
        rights = Engine.rights.get(self.headers.get("Cookie") or "")
        if Engine.down or self.path != "/account.json" or rights is None:
            self.send_response(503 if Engine.down else 401)
            self.end_headers()
            return
        data = json.dumps({"username": "cam", "permissions": rights}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        return


class RoutesTest(Bank):
    @classmethod
    def setUpClass(cls) -> None:
        cls.servers = [_serve(Engine), _serve(catalog.CatalogHandler)]
        cls.engine, cls.base = (f"http://127.0.0.1:{server.server_address[1]}" for server in cls.servers)

    @classmethod
    def tearDownClass(cls) -> None:
        for server in cls.servers:
            server.shutdown()
            server.server_close()

    def setUp(self) -> None:
        super().setUp()
        Engine.down = False
        patches = [
            mock.patch.object(catalog, "AUTOMATE_URL", self.engine),
            mock.patch.object(catalog, "MEDIA_ROOT", self.media),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        sound(self.rotation / "Ada - Song.wav", artist="Ada", title="Song")
        sound(self.jazz / "Bea - Live.wav")

    def call(self, path: str, cookie: str | None = "session=admin", payload: dict | None = None, **headers) -> tuple:
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        if cookie is not None:
            request.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.read()

    def json(self, path: str, **more) -> tuple:
        status, body = self.call(path, **more)
        return status, json.loads(body)

    def test_the_whole_team_sees_and_listens(self) -> None:
        cookie = "session=animateur"
        status, payload = self.json("/collection/list.json", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual([(row["id"], row["count"]) for row in payload["destinations"]], [("rotation", 1), ("jazz", 1)])
        status, payload = self.json("/collection/files.json?id=rotation&q=ada&limit=abc&offset=", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual([(row["name"], row["artist"]) for row in payload["files"]], [("Ada - Song.wav", "Ada")])
        self.assertEqual(self.json("/collection/files.json?id=inconnue", cookie=cookie)[0], 404)
        status, body = self.call("/collection/file?id=rotation&name=Ada%20-%20Song.wav", cookie=cookie, Range="bytes=0-3")
        self.assertEqual((status, body), (206, b"RIFF"))
        self.assertEqual(self.call("/collection/file?id=rotation&name=..%2F..%2Fsecret", cookie=cookie)[0], 404)

    def test_nothing_opens_without_a_session(self) -> None:
        gets = ("/collection/list.json", "/collection/files.json?id=rotation", "/collection/file?id=rotation&name=Ada%20-%20Song.wav")
        posts = ("/collection/remove.json", "/collection/move.json", "/collection/rename.json", "/collection/delete.json")
        for cookie in (None, "session=fermee"):
            for path in gets:
                self.assertEqual(self.json(path, cookie=cookie), (401, {"error": "session expirée"}), path)
            for path in posts:
                payload = {"id": "jazz", "names": ["Bea - Live.wav"], "to": "rotation", "label": "Autre"}
                self.assertEqual(self.json(path, cookie=cookie, payload=payload), (401, {"error": "session expirée"}), path)
        Engine.down = True
        self.assertEqual(self.json(gets[0]), (502, {"error": "automate injoignable"}))
        for path in posts:
            self.assertEqual(self.json(path, payload={"id": "jazz"}), (502, {"error": "automate injoignable"}), path)
        self.assertEqual(self.names("jazz"), ["Bea - Live.wav"])
        self.assertEqual(inbox_api.bank_label(self.media, "jazz"), "Jazz d'été")

    def test_titles_change_for_who_may_deposit(self) -> None:
        remove = {"id": "rotation", "names": ["Ada - Song.wav"]}
        move = {"id": "jazz", "to": "rotation", "names": ["Bea - Live.wav"]}
        self.assertEqual(
            self.json("/collection/remove.json", cookie="session=animateur", payload=remove),
            (403, {"error": "droit insuffisant"}),
        )
        self.assertEqual(self.json("/collection/move.json", cookie="session=animateur", payload=move)[0], 403)
        self.assertEqual((self.names(), self.names("jazz")), (["Ada - Song.wav"], ["Bea - Live.wav"]))

        cookie = "session=programmateur"
        self.assertEqual(
            self.json("/collection/remove.json", cookie=cookie, payload=remove),
            (200, {"removed": ["Ada - Song.wav"], "failed": []}),
        )
        self.assertEqual(
            self.json("/collection/move.json", cookie=cookie, payload=move),
            (200, {"moved": ["Bea - Live.wav"], "failed": []}),
        )
        self.assertEqual((self.names(), self.names("jazz")), (["Bea - Live.wav"], []))
        self.assertEqual([path.name for path in self.trash.iterdir()], ["Ada - Song.wav"])

    def test_a_collection_changes_for_an_admin(self) -> None:
        rename = {"id": "jazz", "label": "Jazz du soir"}
        for cookie in ("session=animateur", "session=programmateur"):
            self.assertEqual(
                self.json("/collection/rename.json", cookie=cookie, payload=rename),
                (403, {"error": "réservé à un admin"}),
            )
            self.assertEqual(self.json("/collection/delete.json", cookie=cookie, payload={"id": "jazz"})[0], 403)
        status, payload = self.json("/collection/rename.json", payload=rename)
        self.assertEqual((status, payload["destination"]["label"]), (200, "Jazz du soir"))
        self.assertEqual(self.json("/collection/delete.json", payload={"id": "jazz"})[0], 409)
        (self.jazz / "Bea - Live.wav").unlink()
        self.assertEqual(self.json("/collection/delete.json", payload={"id": "jazz"}), (200, {"deleted": "jazz"}))
        self.assertFalse(self.jazz.exists())

    def test_a_change_comes_from_the_console_in_json(self) -> None:
        payload = {"id": "rotation", "names": ["Ada - Song.wav"]}
        self.assertEqual(
            self.json("/collection/remove.json", payload=payload, **{"Sec-Fetch-Site": "cross-site"}),
            (403, {"error": "requête d'un autre site"}),
        )
        self.assertEqual(
            self.json("/collection/remove.json", payload=payload, **{"Content-Type": "text/plain"}),
            (415, {"error": "JSON attendu"}),
        )
        request = urllib.request.Request(
            self.base + "/collection/remove.json",
            data=b"[1, 2",
            headers={"Content-Type": "application/json", "Cookie": "session=admin"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=4)
        with caught.exception as answer:
            self.assertEqual((answer.code, json.loads(answer.read())), (400, {"error": "json illisible"}))
        self.assertEqual(self.names(), ["Ada - Song.wav"])


class ImageTest(unittest.TestCase):
    def test_the_image_ships_every_module_of_the_catalogue(self) -> None:
        here = Path(__file__).resolve().parent
        source = (here / "app.py").read_text(encoding="utf-8")
        local = {path.stem for path in here.glob("*.py") if not path.name.startswith("test_")}
        imported = set(re.findall(r"^(?:import|from) (\w+)", source, flags=re.MULTILINE)) & local
        copied = set(re.findall(r"services/catalog/(\w+)\.py", (here / "Dockerfile").read_text(encoding="utf-8")))
        # A module left out of the COPY stops the catalogue at its first import.
        self.assertEqual(imported - copied, set())
        self.assertIn("bank_api", imported)


def _serve(handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    unittest.main()
