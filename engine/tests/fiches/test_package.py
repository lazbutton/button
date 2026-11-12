"""Le paquet des fiches ne dépend ni de Quart, ni de Beets. Seule la recherche parle
au réseau, par httpx.

Les règles se passent même de httpx : les propositions se refont ainsi sans réseau,
d'après les preuves gardées, quand les règles changent.
"""

import subprocess
import sys

import pytest

RULES = (
    "radiotomate.fiches.normalize",
    "radiotomate.fiches.variants",
    "radiotomate.fiches.rules",
    "radiotomate.fiches.loose",
    "radiotomate.fiches.third",
    "radiotomate.fiches.proposals",
)
SEARCH = (
    "radiotomate.fiches.http",
    "radiotomate.fiches.sources",
    "radiotomate.fiches.search",
    "radiotomate.fiches.fingerprint",
)


def _loaded(module, services):
    """Les services que le module charge, importé seul dans un processus neuf."""
    code = (
        "import importlib, sys\n"
        f"importlib.import_module({module!r})\n"
        "loaded = {name.split('.')[0] for name in sys.modules}\n"
        "print(*sorted(loaded & set(sys.argv[1:])))"
    )
    done = subprocess.run(
        [sys.executable, "-c", code, *services],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.split()


@pytest.mark.parametrize("module", RULES)
def test_the_rules_import_no_service(module):
    assert _loaded(module, ("quart", "beets", "httpx")) == []


@pytest.mark.parametrize("module", SEARCH)
def test_the_search_imports_neither_quart_nor_beets(module):
    assert _loaded(module, ("quart", "beets")) == []
