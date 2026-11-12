"""
The record of the versions by the station command (``record_versions``, in
``deploy/station``): a Python block that a container of the engine runs on
RT_DATA, a folder the engine holds, which may hold a link or a pipe. Here, with
the machine's Python, on a temporary folder (``BUTTON_DATA``).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

STATION = Path(__file__).parents[2] / "deploy" / "station"
BODY = (
    '"version":"0.2.0","services":[{"service":"radiotomate-playout",'
    '"image":"ghcr.io/lazbutton/button-playout:0.2.0","version":"0.2.0"}]'
)


def _block() -> str:
    text = STATION.read_text(encoding="utf-8")
    start = text.index("# relevé : versions.json")
    return text[start : text.index("\nPY\n", start)] + "\n"


def _record(data: Path, body: str = BODY) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-"],
        input=_block(),
        env={**os.environ, "BUTTON_DATA": str(data), "BUTTON_VERSIONS": body},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_versions_are_recorded_once_then_kept(tmp_path: Path):
    result = _record(tmp_path)
    assert result.returncode == 0, result.stderr
    path = tmp_path / "versions.json"
    text = path.read_text()
    # As GET /system/version.json reads it, and the tests of the command.
    assert text.startswith('{"recorded_at":"')
    assert text.endswith(f",{BODY}}}\n")
    assert json.loads(text)["recorded_at"].endswith("Z")
    assert oct(path.stat().st_mode & 0o777) == "0o644"
    # The same versions: the file and its time stay.
    os.utime(path, (1_000_000_000, 1_000_000_000))
    assert _record(tmp_path).returncode == 0
    assert path.stat().st_mtime == 1_000_000_000
    # Others: written again.
    assert _record(tmp_path, BODY.replace("0.2.0", "0.3.0")).returncode == 0
    assert json.loads(path.read_text())["version"] == "0.3.0"
    assert [item.name for item in tmp_path.iterdir()] == ["versions.json"]


def test_a_link_left_by_the_engine_leads_nowhere(tmp_path: Path):
    victim = tmp_path / "victime"
    victim.write_text("à root")
    data = tmp_path / "data"
    data.mkdir()
    (data / "versions.json").symlink_to(victim)
    result = _record(data)
    assert result.returncode == 0, result.stderr
    assert victim.read_text() == "à root"
    assert not (data / "versions.json").is_symlink()
    assert json.loads((data / "versions.json").read_text())["version"] == "0.2.0"


def test_a_pipe_left_by_the_engine_does_not_hold_it(tmp_path: Path):
    os.mkfifo(tmp_path / "versions.json")
    result = _record(tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "versions.json").read_text())["version"] == "0.2.0"
