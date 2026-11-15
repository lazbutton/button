"""
Le banc de la banque (`banc.py`), sur des fichiers fabriqués.

Il rejoue, avec la vraie boucle de Beets, les gestes du catalogue. Le test
vérifie que le banc tient debout, pour que personne ne le découvre cassé le jour
où une copie de vraie banque arrive : il passe, un titre déplacé y garde son
identifiant (ARC-09), et son rapport ne nomme aucun titre.

Il tourne dans son propre processus : le banc pose `MEDIA_ROOT` et la base du
moteur, que les autres tests ne doivent pas voir.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).parents[2]
# Ce que fabrique `fabrique.py`, et qu'un rapport ne doit jamais redire.
NAMES = [
    "Ada Quartet",
    "Premier jour",
    "Bea Trio",
    "Cy Orchestre",
    "Hal Big Band",
    "Jingle",
    "Set du soir",
    "Emission test",
    "jazz",
    "Foo,",
]


def _banc(*args: str, **env: str) -> subprocess.CompletedProcess:
    # beet est dans le dossier de l'interpréteur : avec ou sans « poetry run ».
    path = f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"
    return subprocess.run(
        [sys.executable, "-m", "tests.banque.banc", *args],
        cwd=ENGINE,
        env={**os.environ, "PATH": path, "TZ": "Europe/Paris", **env},
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=600,
    )


def test_the_bench_runs_on_made_up_files(tmp_path: Path):
    report = tmp_path / "rapport.md"
    detail = tmp_path / "detail.txt"
    done = _banc("--fabrique", "--rapport", str(report), "--detail", str(detail))
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]

    text = report.read_text(encoding="utf-8")
    # un titre déplacé par le moteur garde son identifiant (ARC-09)
    assert "défaut connu" not in text
    assert "| déplacer | un titre déplacé garde son identifiant de Beets | ok" in text
    assert "**échec**" not in text
    # chaque geste y est, et les bacs et l'Agenda ont été vérifiés
    for geste in ("déplacer", "ramener", "annuler", "retirer", "santé", "arrivées"):
        assert f"| {geste} |" in text
    assert "les bacs gardent leurs sons et l'Agenda ses fichiers" in text
    assert "la boucle suivante ne réimporte rien" in text
    # le rapport se colle dans une PR : ni titre, ni nom de collection
    for name in NAMES:
        assert name not in text
    # ce que les numéros désignent n'est que dans le fichier à part
    assert "Ada Quartet" in detail.read_text(encoding="utf-8")


def test_the_bench_skips_without_a_sample():
    done = _banc(BUTTON_BANQUE_ECHANTILLON="")
    assert done.returncode == 75
    assert "BUTTON_BANQUE_ECHANTILLON" in done.stderr


def test_the_bench_refuses_a_sample_inside_the_repository():
    done = _banc("--echantillon", str(ENGINE / "tests" / "assets"))
    assert done.returncode == 64
    assert "dans le dépôt" in done.stderr


@pytest.mark.parametrize("folder", ["vide", "inconnu"])
def test_the_bench_refuses_a_folder_that_is_not_a_bank(tmp_path: Path, folder: str):
    sample = tmp_path / folder
    sample.mkdir()
    done = _banc("--echantillon", str(sample))
    assert done.returncode == 64
