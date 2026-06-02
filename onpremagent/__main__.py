import logging
import sys

import click
import yaml

from onpremagent.connectors.base import BaseConnector
from onpremagent.connectors.forticlient.connector import FortiClientConnector
from onpremagent.connectors.forticlient.settings import FortiClientSettings
from onpremagent.settings import Settings

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(name)s - %(levelname)s - %(message)s"))

logger = logging.getLogger("fw")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


def connector_factory(settings: FortiClientSettings) -> BaseConnector:
    if settings.type == FortiClientSettings.name:
        return FortiClientConnector(settings)

    raise ValueError(f"Unsupported connector type: {settings.type}")


@click.command()
@click.option(
    "--config",
    "-c",
    default="./config.yaml",
    show_default=True,
    type=click.Path(exists=True),
    help="Path to config file",
)
def main(config):
    with open(config, "r") as f:
        data = yaml.safe_load(f)

    settings = Settings.model_validate(data)

    print(settings)

    connector = connector_factory(settings.connector)

    print(connector)


if __name__ == "__main__":
    main()
