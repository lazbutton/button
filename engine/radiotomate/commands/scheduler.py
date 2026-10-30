import click

from . import radiotomate_cli


@radiotomate_cli.command()
@click.option(
    "--reload",
    is_flag=True,
    help="Reloads app on changes (when developing)",
)
@click.option(
    "--port",
    type=click.IntRange(1, 65535),
    default=6822,
    show_default=True,
    help="Port to listen on. The interface still calls 6822.",
)
@click.pass_obj
def scheduler(config_dict, reload, port):
    """
    Start the Radiotomate scheduler service
    """
    import asyncio

    from hypercorn.asyncio import serve

    from radiotomate.beets import BeetsIntegration
    from radiotomate.quart import CustomQuart, ShutdownManager
    from radiotomate.scheduler.watchdog import Watchdog
    from radiotomate.scheduler_app import app_factory

    beets = BeetsIntegration.default()
    app = app_factory(config_dict, beets)

    Watchdog(app)

    if reload:
        app.run(use_reloader=reload, host="0.0.0.0", port=port)
    else:

        @app.before_serving
        async def on_start():
            ShutdownManager().setup_signal_handler()

        config = CustomQuart.make_basic_hypercorn_config()
        config.bind = [f"0.0.0.0:{port}"]
        asyncio.run(serve(app, config, shutdown_trigger=ShutdownManager().wait))
