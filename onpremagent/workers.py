import logging
import threading
import time
from datetime import datetime

import requests

from onpremagent.connectors.base import BaseConnector
from onpremagent.settings import Settings
from onpremagent.types.firewall_rule import FirewallRule


class Heartbeat:
    def __init__(self) -> None:
        self._now = datetime.now()
        self._lock = threading.Lock()

    def beat(self) -> None:
        with self._lock:
            self._now = datetime.now()

    def get_last_beat(self) -> datetime:
        with self._lock:
            return self._now


class SyncWorker(threading.Thread):
    def __init__(
        self, settings: Settings, connector: BaseConnector, heartbeat: Heartbeat
    ) -> None:
        super().__init__()

        self.settings = settings
        self.connector = connector
        self.heartbeat = heartbeat

        self.logger = logging.getLogger("onpremagent.workers.SyncWorker")

    def run(self) -> None:
        logger = self.logger

        logger.info("Running sync worker...")

        session = requests.Session()

        while True:
            logger.info("Syncing firewall rules...")

            logger.info("Fetching flows from FlowSec...")

            try:
                res = session.get(
                    f"{self.settings.flowsec_url}/api/v3/fstats/{self.settings.identifier}/flows"
                )
                res.raise_for_status()

                flows = {}
                for status, i in res.json().items():
                    status: str

                    flows[status] = [FirewallRule.model_validate(j) for j in i]
            except Exception:
                logger.exception("Failed to fetch flows from FlowSec", exc_info=True)
                time.sleep(self.settings.sync_interval)
                continue
            else:
                self.heartbeat.beat()

            logger.info("Fetched %d flows from FlowSec", len(flows))

            logger.info("Fetching firewall rules from device...")

            try:
                rules = self.connector.list_firewall_rules()
            except Exception:
                logger.exception(
                    "Failed to fetch firewall rules from device", exc_info=True
                )
                time.sleep(self.settings.sync_interval)
                continue

            rules_in_device = [i.id for i in rules]

            logger.info("Fetched %d firewall rules from device", len(rules))

            applied = [i.id for i in flows.get("applied", [])]

            rule_remove_candidates = [rule for rule in rules if rule.id not in applied]

            if len(rule_remove_candidates) > 0:
                logger.info(
                    "Removing %d rules from device that are not in FlowSec in 'applied' status...",
                    len(rule_remove_candidates),
                )

                for rule in rule_remove_candidates:
                    logger.info("Removing firewall rule %s from device", rule.id)

                    try:
                        self.connector.remove_firewall_rule(rule.id)
                    except Exception:
                        logger.exception(
                            "Failed to remove firewall rule %s from device",
                            rule.id,
                            exc_info=True,
                        )
                    finally:
                        logger.info(
                            "Updating status of rule %s in FlowSec to 'removed'",
                            rule.id,
                        )

                        try:
                            res = session.post(
                                f"{self.settings.flowsec_url}/api/v3/fstats/{self.settings.identifier}/flows/{rule.id}/status/removed",
                            )
                            res.raise_for_status()
                        except Exception:
                            logger.exception(
                                "Failed to update status of rule %s in FlowSec to 'removed'",
                                rule.id,
                                exc_info=True,
                            )
                        else:
                            logger.info(
                                "Updated status of rule %s in FlowSec to 'removed'",
                                rule.id,
                            )

            flows_to_add = (
                flows.get("apply", [])
                + flows.get("moderation_approved", [])
                + flows.get("applied", [])
            )

            if len(flows_to_add) > 0:
                logger.info(
                    "Adding %d rules to device that are in FlowSec in 'apply', 'moderation_approved' or 'applied' status but not on device...",
                    len(flows_to_add),
                )

                for rule in flows_to_add:
                    if rule.id not in rules_in_device:
                        logger.info("Adding firewall rule %s to device", rule.id)

                        try:
                            self.connector.add_firewall_rule(rule)
                        except Exception:
                            logger.exception(
                                "Failed to add firewall rule %s to device",
                                rule.id,
                                exc_info=True,
                            )
                        finally:
                            logger.info(
                                "Updating status of rule %s in FlowSec to 'applied'",
                                rule.id,
                            )

                            try:
                                res = session.post(
                                    f"{self.settings.flowsec_url}/api/v3/fstats/{self.settings.identifier}/flows/{rule.id}/status/applied",
                                )
                                res.raise_for_status()
                            except Exception:
                                logger.exception(
                                    "Failed to update status of rule %s in FlowSec to 'applied'",
                                    rule.id,
                                    exc_info=True,
                                )
                            else:
                                logger.info(
                                    "Updated status of rule %s in FlowSec to 'applied'",
                                    rule.id,
                                )

            flows_remove = flows.get("remove", [])

            if len(flows_remove) > 0:
                logger.info(
                    "Removing %d rules from device that are in FlowSec in 'remove' status...",
                    len(flows_remove),
                )

                for rule in flows_remove:
                    if rule.id in rules_in_device:
                        logger.info("Removing firewall rule %s from device", rule.id)

                        try:
                            self.connector.remove_firewall_rule(rule.id)
                        except Exception:
                            logger.exception(
                                "Failed to remove firewall rule %s from device",
                                rule.id,
                                exc_info=True,
                            )
                        finally:
                            logger.info(
                                "Updating status of rule %s in FlowSec to 'removed'",
                                rule.id,
                            )
                    else:
                        try:
                            res = session.post(
                                f"{self.settings.flowsec_url}/api/v3/fstats/{self.settings.identifier}/flows/{rule.id}/status/removed",
                            )
                            res.raise_for_status()
                        except Exception:
                            logger.exception(
                                "Failed to update status of rule %s in FlowSec to 'removed'",
                                rule.id,
                                exc_info=True,
                            )
                        else:
                            logger.info(
                                "Updated status of rule %s in FlowSec to 'removed'",
                                rule.id,
                            )

            logger.info("Finished syncing firewall rules")

            time.sleep(self.settings.sync_interval)


class SendStatisticsWorker(threading.Thread):
    def __init__(
        self, settings: Settings, connector: BaseConnector, heartbeat: Heartbeat
    ) -> None:
        super().__init__()

        self.settings = settings
        self.connector = connector
        self.heartbeat = heartbeat

        self.logger = logging.getLogger("onpremagent.workers.SendStatisticsWorker")

    def run(self) -> None:
        logger = self.logger

        logger.info("Running send statistics worker...")

        session = requests.Session()

        while True:
            logger.info("Connecting to device to fetch firewall rules statistics...")

            try:
                self.connector.connect()
            except Exception:
                logger.exception("Failed to connect to device", exc_info=True)
                time.sleep(self.settings.send_statistics_interval)
                continue

            if self.settings.raw_statistics:
                try:
                    data = self.connector.get_raw_statistics()
                    success = True
                except Exception:
                    logger.exception(
                        "Failed to fetch raw statistics from device", exc_info=True
                    )
                    data = []
                    success = False
            else:
                try:
                    rules = self.connector.list_firewall_rules()

                    data = [i.model_dump(mode="json") for i in rules]
                    success = True
                except Exception:
                    logger.exception(
                        "Failed to fetch firewall rules from device", exc_info=True
                    )

                    data = []
                    success = False
                else:
                    logger.info("Fetched %d firewall rules from device", len(rules))

                    self.heartbeat.beat()

            logger.info("Sending firewall rules statistics to FlowSec...")

            try:
                res = session.put(
                    f"{self.settings.flowsec_url}/api/v3/fstats/{self.settings.identifier}/flows/stat",
                    json={"data": data, "success": success},
                )
                res.raise_for_status()
            except Exception:
                logger.exception(
                    "Failed to send firewall rules statistics to FlowSec", exc_info=True
                )
            else:
                logger.info("Finished sending firewall rules statistics to FlowSec")

            try:
                self.connector.disconnect()
            except Exception:
                logger.exception("Failed to disconnect from device", exc_info=True)

            time.sleep(self.settings.send_statistics_interval)


class ConnectivityCheckerWorker(threading.Thread):
    def __init__(
        self, settings: Settings, connector: BaseConnector, heartbeat: Heartbeat
    ) -> None:
        super().__init__()

        self.settings = settings
        self.connector = connector
        self.heartbeat = heartbeat

        self.logger = logging.getLogger("onpremagent.workers.ConnectivityCheckerWorker")

    def run(self) -> None:
        logger = self.logger

        logger.info("Running connectivity checker worker...")

        while True:
            now, last_beat = datetime.now(), self.heartbeat.get_last_beat()

            if (now - last_beat).total_seconds() > self.settings.connectivity_timeout:
                logger.warning(
                    "No heartbeat received in the last %d seconds. Last heartbeat was at %s.",
                    self.settings.connectivity_timeout,
                    last_beat.isoformat(),
                )

                logger.info("Performing cleanup on connector...")

                try:
                    for rule in self.list_firewall_rules():
                        try:
                            self.remove_firewall_rule(rule.id)
                        except Exception as e:
                            self.logger.warning(
                                "Failed to remove firewall rule %s during cleanup: %s",
                                rule.id,
                                e,
                            )
                except Exception:
                    logger.exception(
                        "Failed to perform cleanup on connector", exc_info=True
                    )
                else:
                    logger.info("Finished performing cleanup on connector")

            time.sleep(self.settings.connectivity_checker_interval)
