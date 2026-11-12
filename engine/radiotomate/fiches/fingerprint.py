"""L'empreinte d'un fichier, prise par `fpcalc`, de Chromaprint.

`fpcalc` lit les 120 premières secondes du fichier, en priorité basse : il tourne à
côté de l'antenne. Absent, la passe de l'empreinte est sautée, et le journal le dit
une fois. Les fiches ne passent ni par `chroma`, qui ne prend l'empreinte qu'à
l'étiquetage automatique, que BUTTON ne fait pas, ni par `pyacoustid`, qui
interrogerait AcoustID avec la clé de Beets.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

_log = logging.getLogger(__name__)

# La lecture bornée : `fpcalc` ne prend que le début du fichier, comme `chroma`.
LENGTH_S = 120
# Un fichier qu'il ne lit pas en deux minutes ne donnera rien.
TIMEOUT_S = 120.0


@dataclass(frozen=True)
class Print:
    """L'empreinte d'un fichier, et la durée que `fpcalc` lui lit, en secondes."""

    fingerprint: str
    duration: float


class Fpcalc:
    """`fpcalc`, lancé en priorité basse, une lecture bornée à 120 s.

    Une seule instance pour toute la recherche : elle ne dit qu'une fois au journal
    que `fpcalc` manque.
    """

    def __init__(self, command: str = "fpcalc", *, timeout: float = TIMEOUT_S) -> None:
        self.command = command
        self.timeout = timeout
        self._missing_said = False

    def command_line(self, executable: str, path: str) -> list[str]:
        """La commande : `nice -n 19` devant, quand le système l'a."""
        command = [executable, "-json", "-length", str(LENGTH_S), path]
        nice = shutil.which("nice")
        return [nice, "-n", "19", *command] if nice else command

    def __call__(self, path: str | os.PathLike[str]) -> Print | None:
        """L'empreinte du fichier, ou None : `fpcalc` manque, ou ne le lit pas."""
        executable = shutil.which(self.command)
        if executable is None:
            if not self._missing_said:
                self._missing_said = True
                _log.warning(
                    "fiches : fpcalc introuvable, la passe de l'empreinte est sautée"
                )
            return None
        name = os.fspath(path)
        try:
            done = subprocess.run(
                self.command_line(executable, name),
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            _log.warning("fiches : fpcalc n'a pas lu %s en %d s", name, self.timeout)
            return None
        except OSError as error:
            _log.warning("fiches : fpcalc ne se lance pas (%s)", error)
            return None
        if done.returncode != 0:
            message = done.stderr.decode("utf-8", "replace").strip()
            _log.info("fiches : fpcalc ne lit pas %s (%s)", name, message)
            return None
        try:
            data = json.loads(done.stdout)
            return Print(str(data["fingerprint"]), float(data["duration"]))
        except (ValueError, KeyError, TypeError):
            _log.info("fiches : fpcalc n'a pas rendu d'empreinte pour %s", name)
            return None
