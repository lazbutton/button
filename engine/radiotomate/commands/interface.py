import click

from . import radiotomate_cli


@radiotomate_cli.command()
@click.option("--demo", is_flag=True, help="Runs in demo mode")
@click.option(
    "--reload",
    is_flag=True,
    help="Reloads app on changes (when developing))",
)
@click.option(
    "--port",
    type=click.IntRange(1, 65535),
    default=6811,
    show_default=True,
    help="Port to listen on",
)
@click.pass_obj
def interface(config_dict, demo, reload, port):
    """
    Start the Radiotomate web application
    """
    import asyncio

    from hypercorn.asyncio import serve

    from radiotomate.interface_app import app_factory
    from radiotomate.quart import CustomQuart, ShutdownManager
    from radiotomate.scheduler_api import Scheduler

    if demo:
        from pathlib import Path

        from radiotomate.beets.demo import BeetsMockIntegration

        beets = BeetsMockIntegration(seed_root=Path(config_dict["data"]["root"]))
    else:
        from radiotomate.beets import BeetsIntegration

        beets = BeetsIntegration.default()

    app = app_factory(config_dict, reload, beets)
    Scheduler.init(config_dict, app, demo=demo, interface_port=port)
    if reload:
        app.run(use_reloader=reload, host="0.0.0.0", port=port)
    else:

        @app.before_serving
        async def on_start():
            ShutdownManager().setup_signal_handler()

        config = CustomQuart.make_basic_hypercorn_config()
        config.bind = [f"0.0.0.0:{port}"]
        asyncio.run(serve(app, config, shutdown_trigger=ShutdownManager().wait))

    if demo:
        beets.teardown()
