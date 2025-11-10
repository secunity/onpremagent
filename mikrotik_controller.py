import argparse
import collections
import logging
import threading
import time
from datetime import datetime, timedelta
from ipaddress import ip_network
from pathlib import Path
from typing import NotRequired, TypedDict

import httpx
import routeros_api
from routeros_api.api_structure import StringField
from routeros_api.exceptions import RouterOsApiError
from routeros_api.resource import RouterOsResource
from tenacity import retry, wait_fixed

from config import SECUNITY_API_URL, Config, read_config_file

FIREWALL_RULE_PREFIX = "SECUNITY_"

HTTP_TIMEOUT = 10.0

SYNC_FLOWS_INTERVAL = timedelta(seconds=10)

SEND_STATISTIC_INTERVAL = timedelta(seconds=60)

WITHDRAW_FIREWALL_RULES_INTERVAL = timedelta(seconds=300)

HEARTBEAT_MAX_TIMEOUT = timedelta(minutes=1)


logger = logging.getLogger("mikrotik-controller")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(lineno)s - %(message)s"
    )
)

logger.addHandler(console_handler)

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.DEBUG)

httpx_logger.addHandler(console_handler)


class FirewallRule(TypedDict, total=False):
    id: int
    comment: NotRequired[str]


class Flow(TypedDict, total=False):
    id: int
    status: str


Address = TypedDict("Address", {"dst-address": str, "src-address": str}, total=False)


class MikrotikController:
    last_heartbeat_lock = threading.Lock()
    last_heartbeat = datetime.now()

    def __init__(
        self,
        config: Config,
        prefix: str = FIREWALL_RULE_PREFIX,
        http_timeout: float = HTTP_TIMEOUT,
    ):
        self.config = config
        self.prefix = prefix

        self.http_client = httpx.Client(
            base_url=f"{SECUNITY_API_URL}/{config.identifier}",
            timeout=http_timeout,
            verify=False,
        )

        self.connection = routeros_api.RouterOsApiPool(
            host=config.host,
            username=config.username,
            password=config.password,
            plaintext_login=config.plaintext_login,
        )

        try:
            self.api = self.connection.get_api()
        except RouterOsApiError as err:
            logger.error("Failed to connect to MikroTik API. Error: %s", err)

            raise

        self.resource_ipv4 = self.api.get_resource(
            "/ip/firewall/raw",
            structure=collections.defaultdict(
                lambda: StringField(encoding=config.encoding)
            ),
        )
        self.resource_ipv6 = self.api.get_resource(
            "/ipv6/firewall/raw",
            structure=collections.defaultdict(
                lambda: StringField(encoding=config.encoding)
            ),
        )

    @classmethod
    def update_heartbeat(cls) -> None:
        with cls.last_heartbeat_lock:
            cls.last_heartbeat = datetime.now()

    def _get_resource(self, flow: Address) -> RouterOsResource:
        if flow.get("dst-address") and ip_network(flow["dst-address"]).version == 6:
            return self.resource_ipv6
        if flow.get("src-address") and ip_network(flow["src-address"]).version == 6:
            return self.resource_ipv6
        return self.resource_ipv4

    def _get_flows(self) -> list[Flow]:
        def inner(status: str) -> list[Flow]:
            try:
                response: httpx.Response = self.http_client.get(f"/flows/{status}")
                response.raise_for_status()

                return response.json()
            except httpx.HTTPError as err:
                logger.error(
                    "Failed to get flows with status '%s'. Error: %s", status, err
                )
                return []

        # TODO: We need to create one endpoint that returns all flows with their statuses

        logger.info("Getting flows from API")

        flows = inner("apply") + inner("remove") + inner("applied")

        # remove duplicates by id
        flows = list({flow["id"]: flow for flow in flows}.values())

        logger.info("Found %d flows to process: %s", len(flows), flows)

        return flows

    def _get_firewall_rules(self) -> dict[str, FirewallRule]:
        def inner(resource: RouterOsResource) -> list[FirewallRule]:
            try:
                return resource.get()
            except RouterOsApiError as err:
                logger.error(
                    "Failed to get firewall rules from resource: %s. Error: %s",
                    resource.path,
                    err,
                )

                raise

        logger.info("Getting firewall rules from MikroTik")

        firewall_rules = inner(self.resource_ipv4) + inner(self.resource_ipv6)

        logger.info("Found %d firewall rules", len(firewall_rules))

        rules = {
            i["comment"].removeprefix(self.prefix): i
            for i in firewall_rules
            if i.get("comment", "").startswith(self.prefix)
        }

        logger.info(
            "Filtered %d firewall rules with prefix '%s': %s",
            len(rules),
            self.prefix,
            rules,
        )

        return rules

    def _apply_flow(self, flow: Flow, firewall_rules: dict[str, FirewallRule]) -> None:
        key = flow.pop("id")

        try:
            logger.info("Adding flow to MikroTik: %s", flow)

            flow["comment"] = f"{self.prefix}{key}"

            self._get_resource(flow).add(**flow)

            logger.info("Flow added successfully: %s", flow)

            logger.info("Marking flow as applied in API: %s", flow)

            self.http_client.post(f"/flows/{key}/status/applied")

            logger.info("Flow marked as applied successfully: %s", flow)

            self.update_heartbeat()
        except RouterOsApiError as err:
            logger.error("Failed to add flow: %s. Error: %s", flow, err)

            raise
        except httpx.HTTPError as err:
            logger.error("Failed to mark flow as applied: %s. Error: %s", flow, err)

    def _remove_flow(self, flow: Flow, firewall_rules: dict[str, FirewallRule]) -> None:
        key = flow.pop("id")

        try:
            if key not in firewall_rules:
                logger.warning("Flow with key %s not found in router rules.", key)
            else:
                logger.info("Removing flow %s from MikroTik: %s", key, flow)

                self._get_resource(flow).remove(id=firewall_rules[key]["id"])

            logger.info("Flow removed successfully: %s", flow)

            logger.info("Marking flow as removed in API: %s", flow)

            self.http_client.post(f"/flows/{key}/status/removed")

            logger.info("Flow marked as removed successfully: %s", flow)

            self.update_heartbeat()
        except RouterOsApiError as err:
            logger.error("Failed to remove flow: %s. Error: %s", flow, err)

            raise
        except httpx.HTTPError as err:
            logger.error("Failed to mark flow as removed: %s. Error: %s", flow, err)

    def _reapply_flow(
        self, flow: Flow, firewall_rules: dict[str, FirewallRule]
    ) -> None:
        key = flow.get("id")

        if key not in firewall_rules:
            logger.error("Applied flow with key %s not found in router rules.", key)

            self._apply_flow(flow, firewall_rules)

    def send_statistics(self) -> None:
        err_ = None

        try:
            firewall_rules = self._get_firewall_rules()
        except Exception as err:
            data = f"{err}"

            err_ = err
        else:
            data = [
                {
                    **value,
                    "id": key,
                }
                for key, value in firewall_rules.items()
            ]

        payload = {"data": data}

        try:
            logger.info("Sending statistics to API: %s", payload)

            self.http_client.put("/flows/stat", json=payload)

            logger.info("Statistics sent successfully")
        except httpx.HTTPError as err:
            logger.error("Failed to send statistics. Error: %s", err)

        if err_ is not None:
            raise err_

        self.update_heartbeat()

    def sync_flows(self) -> None:
        flows = self._get_flows()

        flow_ids = {flow["id"] for flow in flows}

        firewall_rules = self._get_firewall_rules()

        firewall_rules_to_removed = set(firewall_rules.keys()) - flow_ids

        if len(firewall_rules_to_removed) > 0:
            logger.info(
                "Found %d firewall rules stuck in the router that are not in the API: %s",
                len(firewall_rules_to_removed),
                firewall_rules_to_removed,
            )

            self.withdraw_firewall_rules(
                [firewall_rules[key] for key in firewall_rules_to_removed]
            )

        for flow in flows:
            status = flow.pop("status")

            if status == "apply":
                self._apply_flow(flow, firewall_rules)
            elif status == "remove":
                self._remove_flow(flow, firewall_rules)
            elif status == "applied":
                self._reapply_flow(flow, firewall_rules)

    def withdraw_firewall_rules(
        self, firewall_rules: list[FirewallRule] | None = None
    ) -> None:
        if firewall_rules is None:
            firewall_rules_ = self._get_firewall_rules().values()
        else:
            firewall_rules_ = firewall_rules

        for value in firewall_rules_:
            try:
                self._get_resource(value).remove(id=value["id"])

                logger.info("Removed flow with ID: %s", value["id"])
            except RouterOsApiError as err:
                logger.error(
                    "Failed to remove flow with ID: %s. Error: %s", value["id"], err
                )

                raise


@retry(wait=wait_fixed(SEND_STATISTIC_INTERVAL))
def send_statistics_worker(config: Config) -> None:
    controller = MikrotikController(config)

    while True:
        controller.send_statistics()
        time.sleep(SEND_STATISTIC_INTERVAL.total_seconds())


@retry(wait=wait_fixed(SYNC_FLOWS_INTERVAL))
def sync_flows_worker(config: Config) -> None:
    controller = MikrotikController(config)

    while True:
        controller.sync_flows()
        time.sleep(SYNC_FLOWS_INTERVAL.total_seconds())


@retry(wait=wait_fixed(WITHDRAW_FIREWALL_RULES_INTERVAL))
def withdraw_firewall_rules_worker(config: Config) -> None:
    controller = MikrotikController(config)

    while True:
        if datetime.now() - controller.last_heartbeat > HEARTBEAT_MAX_TIMEOUT:
            logger.warning(
                "No heartbeat received in the over %d seconds, removing all flows",
                HEARTBEAT_MAX_TIMEOUT.total_seconds(),
            )

            controller.withdraw_firewall_rules()

        time.sleep(WITHDRAW_FIREWALL_RULES_INTERVAL.total_seconds())


def main():
    parser = argparse.ArgumentParser(description="Mikrotik Controller")
    parser.add_argument(
        "--config", type=Path, required=True, help="Path to the config file"
    )
    args = parser.parse_args()

    config = read_config_file(args.config)

    logger.info("Starting Mikrotik Controller with config: %s", config)

    sync_flows_worker_thread = threading.Thread(
        target=sync_flows_worker,
        args=(config,),
    )
    sync_flows_worker_thread.start()

    send_statistics_worker_thread = threading.Thread(
        target=send_statistics_worker,
        args=(config,),
    )
    send_statistics_worker_thread.start()

    withdraw_firewall_rules_worker_thread = threading.Thread(
        target=withdraw_firewall_rules_worker,
        args=(config,),
    )
    withdraw_firewall_rules_worker_thread.start()

    sync_flows_worker_thread.join()
    send_statistics_worker_thread.join()
    withdraw_firewall_rules_worker_thread.join()


if __name__ == "__main__":
    main()
