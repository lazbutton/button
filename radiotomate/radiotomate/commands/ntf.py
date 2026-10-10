import asyncio
from pathlib import Path

import click

from . import radiotomate_cli


@radiotomate_cli.command("ntf-grille")
@click.option(
    "--media",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Racine de la banque. Défaut : <data>/media",
)
@click.pass_obj
def ntf_grille(config, media: Path | None):
    """Pose la grille NTF et des sons de remplacement."""
    from radiotomate.db import PathLike, QuartAlchemy
    from radiotomate.services.ntf_grille import apply_ntf_grille

    data_root = Path(config["data"]["root"])
    PathLike.base_path = data_root
    if media is None:
        media = data_root / "media"
    db = QuartAlchemy()
    db.init_from_config(config["db"], {})

    async def run(session_factory):
        async with session_factory.begin() as session:
            return await apply_ntf_grille(session, media)

    result = asyncio.run(run(db.session))
    click.echo(
        f"Grille NTF : {result['jour']} le jour, {result['nuit']} la nuit. "
        f"Sons de remplacement dans {result['media']}."
    )
