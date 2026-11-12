"""`fpcalc`, avec un faux `fpcalc` : une lecture bornée à 120 s, en priorité basse ;
absent, la passe de l'empreinte est sautée, et le journal le dit une fois."""

import json
import logging
import shutil
import sys

import pytest

from radiotomate.fiches.fingerprint import Fpcalc, Print


def _fake(tmp_path, body):
    """Un faux `fpcalc` : il note ses arguments et sa priorité, puis fait `body`."""
    script = tmp_path / "fpcalc"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        "here = os.path.dirname(os.path.abspath(__file__))\n"
        "with open(os.path.join(here, 'appel.json'), 'w') as out:\n"
        "    json.dump({'args': sys.argv[1:], 'nice': os.nice(0)}, out)\n"
        f"{body}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


def _call(tmp_path):
    return json.loads((tmp_path / "appel.json").read_text(encoding="utf-8"))


def test_reads_the_first_120_seconds_at_low_priority(tmp_path):
    answer = {"duration": 245.07, "fingerprint": "AQADtEmUaFKSJEmS"}
    command = _fake(tmp_path, f"print(json.dumps({answer!r}))")
    audio = tmp_path / "un titre.mp3"
    audio.write_bytes(b"")
    assert Fpcalc(command)(audio) == Print("AQADtEmUaFKSJEmS", 245.07)
    call = _call(tmp_path)
    assert call["args"] == ["-json", "-length", "120", str(audio)]
    if shutil.which("nice"):
        assert call["nice"] >= 19


def test_without_fpcalc_the_pass_is_skipped_and_said_once(tmp_path, caplog):
    fpcalc = Fpcalc(str(tmp_path / "absent"))
    with caplog.at_level(logging.WARNING, logger="radiotomate.fiches.fingerprint"):
        assert fpcalc(tmp_path / "a.mp3") is None
        assert fpcalc(tmp_path / "b.mp3") is None
    messages = [record.message for record in caplog.records]
    assert messages == [
        "fiches : fpcalc introuvable, la passe de l'empreinte est sautée"
    ]


@pytest.mark.parametrize(
    "body",
    [
        "sys.stderr.write('ERROR: Could not open the input file'); sys.exit(2)",
        "print('pas du JSON')",
        "print(json.dumps({'duration': 12}))",
    ],
)
def test_a_file_fpcalc_cannot_read_gives_no_fingerprint(tmp_path, body):
    assert Fpcalc(_fake(tmp_path, body))(tmp_path / "abime.mp3") is None


def test_fpcalc_stuck_on_a_file_is_stopped(tmp_path):
    command = _fake(tmp_path, "time.sleep(10)")
    assert Fpcalc(command, timeout=0.5)(tmp_path / "long.wav") is None
