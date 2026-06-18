import logging
import sys

import click
import yaml

from onpremagent.connectors.base import BaseConnector
from onpremagent.connectors.fortigate.connector import FortiGateConnector
from onpremagent.connectors.fortigate.settings import FortiGateSettings
from onpremagent.connectors.ssh.connector import SSHConnector
from onpremagent.connectors.ssh.settings import SSHSettings
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


def connector_factory(settings: FortiGateSettings | SSHSettings) -> BaseConnector:
    if settings.type == FortiGateSettings.name:
        return FortiGateConnector(settings)
    elif settings.type == SSHSettings.name:
        return SSHConnector(settings)

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

    workers = []

    if settings.run_sync_worker:
        workers.append(SyncWorker(settings, connector, heartbeat))
    if settings.run_statistics_worker:
        workers.append(SendStatisticsWorker(settings, connector, heartbeat))
    if settings.run_connectivity_checker:
        workers.append(ConnectivityCheckerWorker(settings, connector, heartbeat))

    for worker in workers:
        worker.start()

    for worker in workers:
        worker.join()


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
