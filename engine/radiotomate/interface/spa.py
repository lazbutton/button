"""Serve the React console's build when ``interface.console_dist`` is set.

In production the console has its own nginx: leave the setting empty.
"""

from pathlib import Path

from quart import Quart, current_app, send_from_directory


def console_dist() -> Path | None:
    configured = current_app.config.get("CONSOLE_DIST")
    if not configured:
        return None
    path = Path(str(configured))
    if path.is_dir() and (path / "index.html").is_file():
        return path
    return None


def register(app: Quart) -> None:
    # The console's own routes (console/src/App.tsx).
    @app.get("/antenne")
    @app.get("/conducteur")
    @app.get("/programmation")
    @app.get("/sons")
    @app.get("/reglages")
    async def spa_index():
        dist = console_dist()
        if dist is None:
            return "Console dist introuvable (npm run build).", 404
        return await send_from_directory(dist, "index.html")

    @app.get("/assets/<path:filename>")
    async def spa_assets(filename: str):
        dist = console_dist()
        if dist is None:
            return "Not found", 404
        return await send_from_directory(dist / "assets", filename)

    @app.get("/logo.svg")
    async def spa_logo():
        dist = console_dist()
        if dist is None:
            return "Not found", 404
        return await send_from_directory(dist, "logo.svg")
