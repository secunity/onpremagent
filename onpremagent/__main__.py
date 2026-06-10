import logging
import sys

import click
import yaml

from onpremagent.connectors.base import BaseConnector
from onpremagent.connectors.fortigate.connector import FortiGateConnector
from onpremagent.connectors.fortigate.settings import FortiGateSettings
from onpremagent.settings import Settings
from onpremagent.workers import (
    ConnectivityCheckerWorker,
    Heartbeat,
    SendStatisticsWorker,
    SyncWorker,
)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))

logger = logging.getLogger("onpremagent")
logger.addHandler(handler)


def connector_factory(settings: FortiGateSettings) -> BaseConnector:
    if settings.type == FortiGateSettings.name:
        return FortiGateConnector(settings)

    raise ValueError(f"Unsupported connector type: {settings.type}")


@click.group()
@click.option(
    "--config",
    "-c",
    default="./config.yaml",
    show_default=True,
    type=click.Path(exists=True),
    help="Path to config file",
)
@click.pass_context
def main(ctx, config):
    with open(config, "r") as f:
        data = yaml.safe_load(f)

    settings = Settings.model_validate(data)

    if settings.log_level:
        logger.setLevel(settings.log_level.upper())

    connector = connector_factory(settings.connector)

    ctx.obj = {"settings": settings, "connector": connector}


@main.command()
@click.pass_context
def sync(ctx):
    settings: Settings = ctx.obj["settings"]
    connector: BaseConnector = ctx.obj["connector"]

    heartbeat = Heartbeat()

    sync_worker = SyncWorker(settings, connector, heartbeat)
    send_statistics_worker = SendStatisticsWorker(settings, connector, heartbeat)
    connectivity_checker_worker = ConnectivityCheckerWorker(
        settings, connector, heartbeat
    )

    sync_worker.start()
    send_statistics_worker.start()
    connectivity_checker_worker.start()

    sync_worker.join()
    send_statistics_worker.join()
    connectivity_checker_worker.join()


@main.command()
@click.pass_context
def cleanup(ctx):
    # settings: Settings = ctx.obj["settings"]
    connector: BaseConnector = ctx.obj["connector"]

    connector.cleanup()


@main.command()
@click.pass_context
def setup(ctx):
    # settings: Settings = ctx.obj["settings"]
    connector: BaseConnector = ctx.obj["connector"]

    connector.setup()


if __name__ == "__main__":
    main()
