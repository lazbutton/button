"""The lock of the bank's library, shared with the import loop (ARC-09).

The engine writes into the bank: it moves and renames titles
(``services/bank_moves.py``), and writes their tags (``services/title_edits.py``).
The import loop (deploy/scripts/beets-import-loop.sh) follows the disk on its
own: a file gone leaves the library, a file new enters it under a new id. Both
take the same lock, ``banque.lock`` next to library.db, an exclusive ``flock``,
around what they write: the loop never sees a file at its new name before the
library has it, nor reads a file half written.

Always this lock first, then the write lock of the engine's base: the base is
never held while the loop is awaited.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from radiotomate.domain.errors import DomainConflict

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from beets.library import Library

_log = logging.getLogger(__name__)

LOCK_NAME = "banque.lock"
STATE_NAME = "state.pickle"
# How long a gesture waits for the import loop to finish what it writes.
LOCK_WAIT = 5.0


class BankBusyError(DomainConflict):
    """The import loop holds the library: nothing changed."""

    code = "bank_busy"


@dataclass(frozen=True)
class BeetsPlace:
    """The library, and what lies next to it: its import history and the lock."""

    lib: Library
    statefile: Path
    lock: Path

    @classmethod
    def of(cls, lib: Library) -> BeetsPlace:
        # The import history the loop reads: $BEETSDIR/state.pickle, next to
        # $BEETSDIR/library.db.
        folder = Path(os.fsdecode(lib.path)).parent
        return cls(lib, folder / STATE_NAME, folder / LOCK_NAME)


@asynccontextmanager
async def bank_lock(
    place: BeetsPlace, wait: float | None = None
) -> AsyncIterator[None]:
    """The library's lock, held for the gesture.

    The loop holds it while it follows the disk and while it indexes a folder,
    which can take minutes for a large deposit: past ``wait``, nothing changes.
    """
    wait = LOCK_WAIT if wait is None else wait
    try:
        fd = os.open(place.lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o644)
    except OSError as exc:
        _log.warning("bank lock %s: %s", place.lock, exc)
        raise BankBusyError(
            "La bibliothèque de la banque ne s'ouvre pas : rien n'a changé."
        ) from exc
    try:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise BankBusyError(
                        "La banque est en cours d'indexation : rien n'a changé. "
                        "Réessaie dans une minute."
                    ) from None
                await asyncio.sleep(0.2)
        yield
    finally:
        os.close(fd)
