import argparse
import logging
import os
import sys
from pathlib import Path

import mikrotik_controller
import ssh_controller
from config import (
    DEFAULT_CONFIG_PATH,
    MIKROTIK_VENDOR,
    SSH_VENDORS,
    CallableConfig,
    read_config_file,
)

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)8s - %(lineno)s - %(message)s"


logger = logging.getLogger("agent")


def run(config_fn: CallableConfig, dry_run: bool = False) -> None:
    config = config_fn()

    if config is None:
        raise RuntimeError("Failed to load the configuration")

    vendor = config.vendor

    logger.info("Configured vendor: %s", vendor)

    if vendor == MIKROTIK_VENDOR:
        mikrotik_controller.run(config_fn, dry_run=dry_run)
    elif vendor in SSH_VENDORS:
        ssh_controller.run(config_fn, dry_run=dry_run)
    else:
        raise RuntimeError(
            f"Unsupported vendor: {vendor}. "
            f"Supported vendors: {', '.join(sorted(SSH_VENDORS | {MIKROTIK_VENDOR}))}"
        )


def main():
    parser = argparse.ArgumentParser(description="FlowSec OnPrem Agent")
    parser.add_argument(
        "--config", type=Path, required=True, default=DEFAULT_CONFIG_PATH, help="Path to the config file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Enable dry run mode (read only, never update the router or the API)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", default="INFO"),
        help="Logging level (defaults to the LOG_LEVEL env var, or INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        stream=sys.stdout,
        format=LOG_FORMAT,
    )

    run(lambda: read_config_file(args.config), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
