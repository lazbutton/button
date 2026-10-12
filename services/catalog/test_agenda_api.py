"""cd services/catalog && python test_agenda_api.py"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import agenda_api


class FakeEngine:
    def __init__(self, answers: dict[str, dict | None]):
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, path: str, body: dict) -> dict | None:
        self.calls.append((path, body))
        return self.answers.get(path)


def v2(hook: str, upload: dict, token: str = "tok") -> dict:
    return {
        "Type": hook,
        "Event": {
            "Upload": upload,
            "HTTPRequest": {"Header": {"X-Invite-Token": [token]}},
        },
    }


class AgendaApiTest(unittest.TestCase):
    def test_reads_tusd_v2_and_v1_hooks(self) -> None:
        name, event = agenda_api.hook_event(v2("pre-create", {"Size": 3}), {})
        self.assertEqual(name, "pre-create")
        self.assertEqual(event["Upload"]["Size"], 3)
        self.assertEqual(agenda_api.invite_token(event), "tok")
        name, event = agenda_api.hook_event({"Upload": {}}, {"Hook-Name": "post-finish"})
        self.assertEqual(name, "post-finish")
        self.assertEqual(agenda_api.invite_token(event), "")

    def test_pre_create_asks_the_engine_and_keeps_the_folder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            engine = FakeEngine(
                {
                    "/internal/agenda/deposit-check.json": {
                        "ok": True,
                        "folder": "40-emissions/carte-blanche/entiere",
                        "filename": "2026-11-07 DJ Lou - Carte blanche.flac",
                    }
                }
            )
            _hook, event = agenda_api.hook_event(
                v2(
                    "pre-create",
                    {"Size": 10, "MetaData": {"filename": "set.flac", "diffusion": "7"}},
                ),
                {},
            )
            body = agenda_api.pre_create(event, "tok", media, engine)
            meta = body["ChangeFileInfo"]["MetaData"]
            self.assertEqual(meta["agenda_folder"], "40-emissions/carte-blanche/entiere")
            self.assertEqual(meta["filename"], "set.flac")
            path, sent = engine.calls[0]
            self.assertEqual(sent["diffusion_id"], "7")
            self.assertEqual(sent["token"], "tok")

            refused = FakeEngine(
                {"/internal/agenda/deposit-check.json": {"ok": False, "reason": "dépôt fermé"}}
            )
            body = agenda_api.pre_create(event, "tok", media, refused)
            self.assertTrue(body["RejectUpload"])
            self.assertEqual(body["HTTPResponse"]["Body"], "dépôt fermé")
            down = agenda_api.pre_create(event, "tok", media, FakeEngine({}))
            self.assertIn("indisponible", down["HTTPResponse"]["Body"])

    def test_finish_places_then_declares_or_trashes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw) / "media"
            tusd = Path(raw) / "tusd"
            media.mkdir()
            tusd.mkdir()

            def upload(uid: str) -> dict:
                (tusd / uid).write_bytes(b"audio")
                (tusd / f"{uid}.info").write_text("{}")
                return {
                    "ID": uid,
                    "Storage": {"Path": str(tusd / uid)},
                    "MetaData": {
                        "filename": "set.flac",
                        "diffusion": "7",
                        "agenda_folder": "40-emissions/carte-blanche/entiere",
                        "agenda_filename": "2026-11-07 DJ Lou - Carte blanche.flac",
                    },
                }

            engine = FakeEngine({"/internal/agenda/files.json": {"ok": True}})
            _hook, event = agenda_api.hook_event(v2("post-finish", upload("a")), {})
            result = agenda_api.finish(event, "tok", media, tusd, engine)
            self.assertTrue(result["ok"])
            placed = media / result["path"]
            self.assertTrue(placed.is_file())
            self.assertFalse((tusd / "a").exists())
            self.assertFalse((tusd / "a.info").exists())
            self.assertEqual(engine.calls[0][1]["path"], result["path"])

            _hook, event = agenda_api.hook_event(v2("post-finish", upload("b")), {})
            second = agenda_api.finish(event, "tok", media, tusd, engine)
            self.assertTrue(second["path"].endswith("Carte blanche (2).flac"))

            late = FakeEngine(
                {"/internal/agenda/files.json": {"ok": False, "error": "Trop tard"}}
            )
            _hook, event = agenda_api.hook_event(v2("post-finish", upload("c")), {})
            refused = agenda_api.finish(event, "tok", media, tusd, late)
            self.assertEqual(refused["error"], "Trop tard")
            self.assertEqual(len(list((media / "90-trash").iterdir())), 1)

    def test_finish_refuses_folders_outside_the_emissions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            media = Path(raw)
            event = {
                "Upload": {
                    "MetaData": {"agenda_folder": "../etc", "agenda_filename": "x.mp3"}
                }
            }
            result = agenda_api.finish(event, "tok", media, media, FakeEngine({}))
            self.assertEqual(result["error"], "dossier refusé")

    def test_playout_token_from_env_or_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "radiotomate.yaml"
            config.write_text(
                "db:\n  url: x\nplayout_process_config:\n  input_name: stream\n"
                "  token: abc123  # secret\noutputs: []\n"
            )
            old = agenda_api.PLAYOUT_YAML
            agenda_api.PLAYOUT_YAML = config
            os.environ.pop("RT_PLAYOUT_TOKEN", None)
            try:
                self.assertEqual(agenda_api.playout_token(), "abc123")
                os.environ["RT_PLAYOUT_TOKEN"] = "fromenv"
                self.assertEqual(agenda_api.playout_token(), "fromenv")
            finally:
                os.environ.pop("RT_PLAYOUT_TOKEN", None)
                agenda_api.PLAYOUT_YAML = old


if __name__ == "__main__":
    unittest.main()
