# ruff: noqa: E402 — patch ioctl before importing beets.ui (Python 3.14)
"""
This module contains classes and wrappers to interface more easily with Beets.
"""

from __future__ import annotations

import logging
from asyncio import CancelledError, Queue, get_running_loop, sleep
from random import randint
from typing import TYPE_CHECKING

from radiotomate.beets.compat import patch_beets_term_ioctl

patch_beets_term_ioctl()

from beets.dbcore import sort_from_strings
from beets.library import Item, Library
from beets.ui import _setup
from beets.ui import log as beets_log
from beetsplug.replaygain import ReplayGainPlugin
from quart import Quart, current_app

from radiotomate.models.sound import Sound
from radiotomate.quart import ShutdownError, or_shutdown

if TYPE_CHECKING:
    from radiotomate.db import QuartAlchemy

_log = logging.getLogger(__name__)


class SoundToItemProxy(Item):
    "Masquerades one of our Sound into a beet's Item"

    def __init__(self, sound: Sound):
        super().__init__()
        self._sound = sound
        self.path = str(sound.path.absolute()).encode()
        self.rg_track_gain = sound.gain
        self.rg_track_peak = sound.peak

    def store(self, fields=None):
        self._sound.gain = self.rg_track_gain
        self._sound.peak = self.rg_track_peak


class BeetsIntegration:
    """
    This class wraps a Beets library and provides high-level helpers for our AutoDJ and
    replaygain analysis (this implies that replaygain level is set in the Beets
    configuration).

    It can also register as a Quart extension, so its instance can be easily found by
    views and awaited.
    """

    EXTENSION_NAME = "RadiotomateBeetsIntegration"

    # background analysis are started only after this delay, so the application and
    # playout process have all CPU available while starting
    BACKGROUND_ANALYSIS_DELAY = 30.0

    def __init__(self, lib: Library):
        self.lib: Library = lib
        self.rg = ReplayGainPlugin()
        self.analyzer_q = Queue()
        # logging.getLogger("beets.replaygain").setLevel(logging.DEBUG)

    @classmethod
    def default(cls) -> BeetsIntegration:
        """
        Instantiates Beets using its default config path (``BEETSDIR``). In
        Beets 2.14, ``_setup`` takes no argument, and no longer sets the level of
        its log, which Beets 2.5 set to INFO.
        """
        beets_log.set_global_level(logging.INFO)
        subcommands, lib = _setup()
        return BeetsIntegration(lib)

    @classmethod
    def get(cls) -> BeetsIntegration:
        """
        Find the instance wrapped in ``current_app``
        """
        return current_app.extensions[cls.EXTENSION_NAME]

    def init_app(self, app: Quart) -> None:
        if self.EXTENSION_NAME in app.extensions:
            raise RuntimeError(
                "An sqlalchemy extension has already been registered on this app",
            )
        app.extensions[self.EXTENSION_NAME] = self

    async def random_pick(self, query) -> Item | None:
        """
        Like "beet random [query]", returns the path ot a track matching given query
        """

        def fetch_items(q):
            return list(self.lib.items(q))

        loop = get_running_loop()
        objs = await loop.run_in_executor(None, fetch_items, query)
        if objs:
            index = randint(0, len(objs) - 1)
            obj = objs[index]
            return obj
        else:
            return None

    async def search(self, query) -> list[Item]:
        """
        Like "beet [query]", returns matching Items
        """

        def fetch_items(q):
            sort = sort_from_strings(Item, ["artist+"])
            return list(self.lib.items(q, sort=sort))

        loop = get_running_loop()
        objs = await loop.run_in_executor(None, fetch_items, query)
        return objs

    async def background_analyzer(self, db: QuartAlchemy):
        """
        This should be started as a background task
        """
        try:
            await or_shutdown(sleep(self.BACKGROUND_ANALYSIS_DELAY))
        except (ShutdownError, CancelledError):
            return
        async with db.session() as session:
            ids = await Sound.ids_without_gain(session)
            for i in ids:
                await self.analyzer_q.put(i)
            if ids:
                _log.info(
                    "Queue'd %d sounds catching up their replaygain analysis", len(ids)
                )

        job = None
        while True:
            try:
                job = await or_shutdown(self.analyzer_q.get())
                if isinstance(job, tuple) and job and job[0] == "beets":
                    await self.ensure_item_gain(int(job[1]))
                    continue
                async with db.session() as dbsession:
                    sound = await Sound.from_id(dbsession, job)
                    if sound:
                        await self._do_analyze_rg(sound)
                        await dbsession.commit()
            except (ShutdownError, CancelledError):
                return
            except Exception:
                _log.exception("while attempting analysis job=%r", job)

    async def _do_analyze_rg(self, sound: Sound):
        """
        Fill ReplayGain columns on sound
        """
        proxied = SoundToItemProxy(sound)
        loop = get_running_loop()
        await loop.run_in_executor(None, self.rg.handle_track, proxied, False)

    async def _do_analyze_item(self, item: Item):
        """
        Fill ReplayGain fields on a library Item (stored in the Beets DB, not the tags).
        """
        loop = get_running_loop()
        await loop.run_in_executor(None, self.rg.handle_track, item, False)

    async def title_rows(self) -> list[tuple]:
        """
        Every title of the library, as the bank's table reads it (FON-64): id, path,
        title, artist, album, year, genre, length, and the ``famille`` and
        ``etiquettes`` flexible fields (FON-74).
        One SQL query, not ``lib.items()``: building 7 000 Items takes seconds.
        """
        loop = get_running_loop()
        return await loop.run_in_executor(None, self._title_rows)

    def _genre_column(self, tx) -> str:
        """Beets 2.14 keeps the genres of a title in `genres` (ARC-06)."""
        columns = {row[1] for row in tx.query("PRAGMA table_info(items)")}
        return "genres" if "genres" in columns else "genre"

    async def genre_field(self) -> str:
        """The genre's field in a query: `genre`, or `genres` with Beets 2.14."""

        def read() -> str:
            with self.lib.transaction() as tx:
                return self._genre_column(tx)

        return await get_running_loop().run_in_executor(None, read)

    def _title_rows(self) -> list[tuple]:
        with self.lib.transaction() as tx:
            genre = self._genre_column(tx)
            return list(
                tx.query(
                    "SELECT i.id, i.path, i.title, i.artist, i.album, i.year, "
                    f"i.{genre}, i.length, a.value, t.value FROM items i "
                    "LEFT JOIN item_attributes a "
                    "ON a.entity_id = i.id AND a.key = 'famille' "
                    "LEFT JOIN item_attributes t "
                    "ON t.entity_id = i.id AND t.key = 'etiquettes'"
                )
            )

    async def get_item(self, beets_id: int) -> Item | None:
        loop = get_running_loop()
        return await loop.run_in_executor(None, self.lib.get_item, beets_id)

    async def ensure_item_gain(self, beets_id: int) -> str | None:
        """
        Return the ReplayGain track gain of a library Item, analysing it on the spot
        when the Beets import did not compute it (no ``replaygain`` plugin, old
        import…). Returns ``None`` when the item is unknown or the analysis failed.
        """
        item = await self.get_item(beets_id)
        if item is None:
            return None
        gain = item.get("rg_track_gain")
        if gain is None:
            try:
                await self._do_analyze_item(item)
            except Exception:
                _log.exception("ReplayGain analysis failed for beets item %s", beets_id)
                return None
            gain = item.get("rg_track_gain")
            if gain is None:
                return None
            _log.info("Computed ReplayGain %.2f dB for beets item %s", gain, beets_id)
        return str(gain)

    async def analyze_soon(self, sound_id: int):
        """
        Add a sound to the replaygain analysis queue
        """
        await self.analyzer_q.put(sound_id)

    def analyze_item_soon(self, beets_id: int) -> None:
        """
        Queue a Beets library Item for ReplayGain analysis (used when the forecast
        picks a track that has no gain yet, so it is ready by the time it is pushed).
        """
        self.analyzer_q.put_nowait(("beets", int(beets_id)))
