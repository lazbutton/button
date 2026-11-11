"""Les règles des fiches ne dépendent d'aucun service : ni Quart, ni Beets, ni httpx.

Les propositions se refont ainsi sans réseau, d'après les preuves gardées, quand les
règles changent. La recherche en ligne aura ses propres modules.
"""

import subprocess
import sys

import pytest

SERVICES = ("quart", "beets", "httpx")


@pytest.mark.parametrize(
    "module",
    [
        "radiotomate.fiches.normalize",
        "radiotomate.fiches.variants",
        "radiotomate.fiches.rules",
        "radiotomate.fiches.proposals",
    ],
)
def test_the_rules_import_no_service(module):
    """Importé seul, dans un processus neuf, le module ne charge aucun service."""
    code = (
        "import importlib, sys\n"
        f"importlib.import_module({module!r})\n"
        "loaded = {name.split('.')[0] for name in sys.modules}\n"
        "print(*sorted(loaded & set(sys.argv[1:])))"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", code, *SERVICES],
        capture_output=True,
        text=True,
        check=True,
    )
    assert loaded.stdout.split() == []
