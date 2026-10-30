"""
DB Schema upgrade system.

Each version of the schema is in a sub-module, named `vX.py`, where `X` is the version
number. Each sub-module must define functions `upgrade(conn)` and `downgrade(conn)`,
that will be called with a SQLAlchemy connection object.

Before the first upgrade, the database is copied to a `backups` folder next to it, as
`avant-vX-YYYYMMDDTHHMMSSZ.db`, where `X` is the first version to apply. If the copy
fails, no upgrade is applied. Once the upgrades succeeded, only the last
`BACKUPS_KEPT` copies are kept: while one fails, no copy is deleted.

"""

import re

import click

from .. import radiotomate_cli

BACKUPS_KEPT = 5
# backup-radiotomate.sh writes its archives in the same folder: they don't match
BACKUP_NAME = re.compile(r"avant-v\d+-(\d{8}T\d{6}Z)\.db")


def backup_database(db_path, first_version):
    """
    Copy the SQLite database at `db_path` to `backups/avant-vX-<UTC time>.db` next to
    it, `X` being `first_version`, and return the copy's path. Raises `OSError` or
    `sqlite3.Error` when anything fails.
    """
    import os
    import sqlite3
    from contextlib import closing
    from datetime import UTC, datetime

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    # what a copy killed midway left behind
    for leftover in backup_dir.glob("avant-v*.db.part*"):
        leftover.unlink()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"avant-v{first_version}-{stamp}.db"
    partial = backup_dir / f"{backup_path.name}.part"
    # owner only, like the archives of backup-radiotomate.sh: users' password
    # hashes are in there
    os.close(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    try:
        with (
            closing(sqlite3.connect(db_path)) as source,
            closing(sqlite3.connect(partial)) as target,
        ):
            source.backup(target)
            # a single file, readable without its -wal and -shm
            target.execute("PRAGMA journal_mode=DELETE")
        partial.replace(backup_path)
    finally:
        partial.unlink(missing_ok=True)

    if os.geteuid() == 0:
        # radiotomate-init runs as root, and gives the data folder back to its owner
        # only once done: after a failed migration, the copy must be readable too
        owner = db_path.stat()
        for path in (backup_dir, backup_path):
            os.chown(path, owner.st_uid, owner.st_gid)
    return backup_path


def backup_before_upgrade(db_path, first_version):
    """
    `backup_database`, with the command's messages: if the copy fails, say why and
    exit before any upgrade.
    """
    import sqlite3

    try:
        backup_path = backup_database(db_path, first_version)
    except (OSError, sqlite3.Error) as error:
        click.secho(
            f"Database backup failed, no schema change applied: {error}",
            fg="red",
            bold=True,
        )
        raise click.exceptions.Exit(1) from error
    click.echo(f"Database backed up to {backup_path}")
    return backup_path


def prune_backups(backup_path):
    """
    Delete the oldest copies beyond `BACKUPS_KEPT`, but never `backup_path`, the one
    just made, whatever the clock said when the others were made. Called once the
    upgrades went through: a failure only warns, the station must start.
    """
    try:
        others = sorted(
            (match[1], path)
            for path in backup_path.parent.iterdir()
            if path != backup_path and (match := BACKUP_NAME.fullmatch(path.name))
        )
        while len(others) >= BACKUPS_KEPT:
            others.pop(0)[1].unlink()
    except OSError as error:
        click.secho(f"Old database copies not deleted: {error}", fg="yellow")


async def do_update(engine, target_version=None):
    import sys
    from importlib import import_module
    from pathlib import Path
    from pkgutil import iter_modules

    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    async with engine.connect() as conn:
        try:
            q = text("select value from settings where key=:key")
            result = await conn.execute(q, {"key": "SCHEMA_VERSION"})
            current_version = int(result.scalars().first())
        except OperationalError:  # when table does not exist
            current_version = 0

        latest_version = 0
        updates_module = sys.modules[__name__]
        for modinfo in iter_modules(updates_module.__path__):
            name = modinfo.name
            if name.startswith("v"):
                version = int(name[1:])
                latest_version = max(version, latest_version)

        if target_version is None:
            target_version = latest_version

        if target_version > latest_version:
            click.secho(
                f"Version {target_version} does not exists",
                fg="red",
                bold=True,
            )
            raise click.exceptions.Exit(1)

        # a blank database (version 0) has nothing to save
        backup_path = None
        if 0 < current_version < target_version:
            backup_path = backup_before_upgrade(
                Path(engine.url.database), current_version + 1
            )

        if current_version < target_version:
            for i in range(current_version + 1, target_version + 1):
                click.echo(f"Applying schema change #{i}... ", nl=False)
                module = import_module(f"radiotomate.commands.update.v{i}")
                await module.upgrade(conn)
                q = text("update settings set value=:value where key=:key")
                await conn.execute(q, {"value": str(i), "key": "SCHEMA_VERSION"})
                await conn.commit()
                click.secho("OK", fg="green", bold=True)
            if backup_path:
                prune_backups(backup_path)
        elif current_version > target_version:
            for i in range(current_version, target_version, -1):
                click.echo(f"Reverting schema change # {i-1}... ", nl=False)
                module = import_module(f"radiotomate.commands.update.v{i}")
                await module.downgrade(conn)
                q = text("update settings set value=:value where key=:key")
                await conn.execute(q, {"value": str(i - 1), "key": "SCHEMA_VERSION"})
                await conn.commit()
                click.secho("OK", fg="green", bold=True)
        else:
            click.secho("DB is up-to-date", fg="green", bold=True)


@radiotomate_cli.command()
@click.option(
    "--target-version",
    help="Target version (may be used to downgrade)",
    type=int,
)
@click.pass_obj
def update(config, target_version=None):
    """
    Update a Radiotomate installation

    Before upgrading, the database is copied to a backups folder next to it.
    Downgrades make no copy: back up first.
    """
    import asyncio

    # do *not* import radiotomate.models from here, because their tables may not exist
    # yet. though, we use db.init_from_config() in order to have the same PRAGMAs
    # and settings as the app
    from radiotomate.db import QuartAlchemy

    db = QuartAlchemy()
    db.init_from_config(config["db"], {})
    asyncio.run(do_update(db.engine, target_version))
    asyncio.run(db.after_serving())
