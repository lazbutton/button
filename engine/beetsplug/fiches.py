# ruff: noqa: INP001 — beetsplug is the namespace of Beets: no __init__.py here
"""The fiches of the library, in Beets (FON-25).

A thin plugin: it declares the flexible fields that the fiches write once accepted,
`famille`, `fmg` and `fmg_source`, which Beets never puts in a file, and a command,
`beet fiches`, which says where the search stands, as `radiotomate maintenance
fiches` does. The work is in the `radiotomate.fiches` package, and the search runs
in the scheduler (`radiotomate/scheduler/fiches.py`).

`init-radiotomate.sh` adds `fiches` to the plugins of the station. Beets 2.14 loads
only a class defined in the module of the plugin (`_get_plugin`, `beets/plugins.py`).
"""

from __future__ import annotations

import os
from pathlib import Path

from beets import ui
from beets.dbcore import types
from beets.plugins import BeetsPlugin


def engine_database() -> Path:
    """The engine's database: in the data folder of the station, next to its YAML."""
    data = os.environ.get("RADIOTOMATE_DATA")
    if data:
        return Path(data) / "radiotomate.db"
    config = Path(os.environ.get("RTCONFIG", "/data/radiotomate.yaml"))
    return config.parent / "radiotomate.db"


class FichesPlugin(BeetsPlugin):
    """The flexible fields of the fiches, and `beet fiches`."""

    item_types = {  # noqa: RUF012 — as Beets declares them
        "famille": types.STRING,
        "fmg": types.STRING,
        "fmg_source": types.STRING,
    }

    def commands(self) -> list[ui.Subcommand]:
        command = ui.Subcommand("fiches", help="où en est la recherche des fiches")
        command.func = self._show
        return [command]

    def _show(self, lib, opts, args) -> None:
        from radiotomate.services.fiches import describe, library_count, read_progress

        database = engine_database()
        if not database.is_file():
            raise ui.UserError(f"base du moteur introuvable : {database}")
        titles = library_count(Path(os.fsdecode(lib.path)))
        ui.print_(describe(read_progress(database, titles)))
