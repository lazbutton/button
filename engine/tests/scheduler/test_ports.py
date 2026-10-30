"""Listening ports of the interface and the scheduler, set on the command line."""

from radiotomate.beets import BeetsIntegration
from radiotomate.commands.interface import interface
from radiotomate.commands.scheduler import scheduler
from radiotomate.interface_app import app_factory as interface_factory
from radiotomate.scheduler_api import Scheduler


def _port_default(command) -> int:
    return next(param.default for param in command.params if param.name == "port")


def test_ports_default_to_the_station_ones():
    assert _port_default(interface) == 6811
    assert _port_default(scheduler) == 6822


async def test_demo_follows_the_interface_port(
    app_configration: dict,
    beets_integration: BeetsIntegration,
):
    Scheduler.reset_instance()
    iface = interface_factory(app_configration, False, beets_integration)
    demo = Scheduler.init(app_configration, iface, demo=True, interface_port=6911)
    try:
        assert demo.client.base_url.port == 6911
    finally:
        await demo.client.aclose()
        Scheduler.reset_instance()


async def test_scheduler_client_keeps_its_own_port(
    app_configration: dict,
    beets_integration: BeetsIntegration,
):
    Scheduler.reset_instance()
    iface = interface_factory(app_configration, False, beets_integration)
    real = Scheduler.init(app_configration, iface, interface_port=6911)
    try:
        assert real.client.base_url.port == 6822
    finally:
        await real.client.aclose()
        Scheduler.reset_instance()
