import datetime
import warnings
from ipaddress import IPv4Network, IPv6Network
from typing import Any, Literal, NotRequired, TypedDict, override

import requests
from urllib3.exceptions import InsecureRequestWarning

from onpremagent.connectors.base import BaseConnector
from onpremagent.connectors.fortigate.settings import FortiGateSettings
from onpremagent.types.firewall_rule import FirewallRule, FirewallRuleActionBpsLimit


class FirewallAddress(TypedDict):
    name: str
    subnet: IPv4Network | IPv6Network
    comment: str


class FirewallService(TypedDict):
    name: str
    protocol: str | int
    src_port: str | int | None
    dst_port: str | int | None
    comment: str


class FirewallPolicy(TypedDict):
    policy_id: NotRequired[int]
    name: str
    src_if: NotRequired[str]
    dst_if: NotRequired[str]
    src_addr: str
    dst_addr: str
    services: list[str]
    action: Literal["accept", "deny", "rate-limit"]
    comment: str
    traffic_shaper: NotRequired[str]
    dropped_bytes: NotRequired[int | None]
    dropped_packets: NotRequired[int | None]
    matched_bytes: NotRequired[int | None]
    matched_packets: NotRequired[int | None]


class FortiGateError(Exception):
    pass


class FortiGateHttpError(FortiGateError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")

        self.status_code = status_code
        self.message = message


def _parse_subnet(value: str) -> IPv4Network | IPv6Network:
    ip, netmask = value.split()
    if "." in ip:
        return IPv4Network(f"{ip}/{netmask}", strict=False)
    else:
        return IPv6Network(f"{ip}/{netmask}", strict=False)


def _format_subnet(subnet: IPv4Network | IPv6Network) -> str:
    return f"{subnet.network_address} {subnet.netmask}"


Protocol = TypedDict("Protocol", {"protocol": str, "protocol-number": NotRequired[str]})


def _parse_protocol(item: dict[str, Any]) -> str | int:
    if item["protocol"] == "IP":
        return int(item["protocol-number"])
    elif item["protocol"] == "ICMP":
        return "icmp"
    elif item["protocol"] == "ICMP6":
        return "icmp6"
    elif "udp-portrange" in item:
        return "udp"
    elif "tcp-portrange" in item:
        return "tcp"
    elif "sctp-portrange" in item:
        return "sctp"
    elif "udplite-portrange" in item:
        return "udplite"
    else:
        raise ValueError(f"Unsupported protocol: {item['protocol']}")


def _format_protocol(protocol: str | int) -> Protocol:
    match protocol:
        case 6:
            protocol = "TCP"
        case 17:
            protocol = "UDP"
        case 132:
            protocol = "SCTP"
        case 136:
            protocol = "UDPLITE"
        case 1:
            protocol = "ICMP"
        case 58:
            protocol = "ICMP6"

    if isinstance(protocol, int):
        return {"protocol": "IP", "protocol-number": str(protocol)}
    elif protocol.lower() in ("tcp", "udp", "sctp", "udplite"):
        return {"protocol": "TCP/UDP/UDP-Lite/SCTP"}
    elif protocol.lower() in ("icmp", "icmp6"):
        return {"protocol": "ICMP"}
    else:
        raise ValueError(f"Unsupported protocol: {protocol}")


def _parse_ports(item: dict[str, Any]) -> tuple[str | None, str | None]:
    if "udp-portrange" in item:
        value = item["udp-portrange"]
    elif "tcp-portrange" in item:
        value = item["tcp-portrange"]
    elif "sctp-portrange" in item:
        value = item["sctp-portrange"]
    elif "udplite-portrange" in item:
        value = item["udplite-portrange"]
    else:
        return None, None

    if ":" in value:
        dst_port, src_port = value.split(":")
    else:
        dst_port, src_port = value, None

    return dst_port, src_port


PortRange = TypedDict(
    "PortRange",
    {
        "udp-portrange": NotRequired[str],
        "tcp-portrange": NotRequired[str],
        "sctp-portrange": NotRequired[str],
        "udplite-portrange": NotRequired[str],
    },
)


def _format_ports(
    protocol: str | int, dst_port: str | int | None, src_port: str | int | None
) -> PortRange:
    if dst_port is None:
        dst_port = "0-65535"

    if src_port is not None:
        port_range = f"{dst_port}:{src_port}"
    else:
        port_range = str(dst_port)

    match protocol:
        case 6 | "tcp":
            protocol = "tcp"
        case 17 | "udp":
            protocol = "udp"
        case 132 | "sctp":
            protocol = "sctp"
        case 136 | "udplite":
            protocol = "udplite"
        case 1 | "icmp":
            protocol = "icmp"
        case 58 | "icmp6":
            protocol = "icmp6"
        case _:
            return {}

    assert isinstance(protocol, str)

    if protocol.lower() == "udp":
        return {"udp-portrange": port_range}
    elif protocol.lower() == "tcp":
        return {"tcp-portrange": port_range}
    elif protocol.lower() == "sctp":
        return {"sctp-portrange": port_range}
    elif protocol.lower() == "udplite":
        return {"udplite-portrange": port_range}
    else:
        raise ValueError(f"Unsupported protocol for ports: {protocol}")


def _address_to_id(value: Any) -> str:
    return str(value).replace("/", "_")


def _id_to_address(value: str) -> str:
    return value.replace("_", "/")


class FortiGateConnector(BaseConnector[FortiGateSettings]):
    def __init__(
        self,
        settings: FortiGateSettings,
    ) -> None:
        super().__init__(settings)

        if not self.settings.ssl_verify:
            warnings.filterwarnings("ignore", category=InsecureRequestWarning)

        self.session = requests.Session()
        self.session.verify = self.settings.ssl_verify
        self.session.headers.update({"Authorization": f"Bearer {self.settings.token}"})

    def _send_request(self, method: str, endpoint: str, **kwargs) -> dict:
        self.logger.debug(
            "Sending %s request to %s with params: %s", method, endpoint, kwargs
        )

        res = self.session.request(method, f"{self.settings.host}{endpoint}", **kwargs)

        try:
            res.raise_for_status()
        except requests.HTTPError as e:
            raise FortiGateHttpError(res.status_code, res.text) from e

        result = res.json()

        self.logger.debug("Received response: %s", result)

        if result["status"] != "success":
            raise FortiGateError(f"API request failed: {res.text}")

        return result

    def _create_firewall_address(self, address: FirewallAddress) -> None:
        subnet = _format_subnet(address["subnet"])

        req = {
            "name": address["name"],
            "type": "ipmask",
            "subnet": subnet,
            "comment": address["comment"],
        }

        self._send_request("POST", "/api/v2/cmdb/firewall/address", json=req)

    def _delete_firewall_address(self, name: str) -> None:
        self._send_request("DELETE", f"/api/v2/cmdb/firewall/address/{name}")

    def _get_firewall_addresses(
        self, filter_prefix: str | None = None
    ) -> list[FirewallAddress]:
        params = {"format": "name|subnet|comment"}
        if filter_prefix is not None:
            params["filter"] = f"name=@{filter_prefix}"

        result = self._send_request(
            "GET", "/api/v2/cmdb/firewall/address", params=params
        )

        items = []

        for item in result.get("results", []):
            subnet = _parse_subnet(item["subnet"])

            items.append(
                FirewallAddress(
                    name=item["name"],
                    subnet=subnet,
                    comment=item["comment"],
                )
            )

        return items

    def _check_firewall_address_exists(self, name: str) -> bool:
        try:
            self._send_request("GET", f"/api/v2/cmdb/firewall/address/{name}")
            return True
        except FortiGateHttpError:
            return False

    def _create_firewall_service(self, service: FirewallService) -> None:
        protocol = _format_protocol(service["protocol"])

        port_range = _format_ports(
            service["protocol"],
            service["dst_port"],
            service["src_port"],
        )

        req = {
            "name": service["name"],
            "comment": service["comment"],
            **protocol,
            **port_range,
        }

        self._send_request("POST", "/api/v2/cmdb/firewall.service/custom", json=req)

    def _delete_firewall_service(self, name: str) -> None:
        self._send_request("DELETE", f"/api/v2/cmdb/firewall.service/custom/{name}")

    def _get_firewall_services(
        self, filter_prefix: str | None = None
    ) -> list[FirewallService]:
        params = {
            "format": "name|protocol|protocol-number|udp-portrange|tcp-portrange|sctp-portrange|udplite-portrange|comment"
        }
        if filter_prefix is not None:
            params["filter"] = f"name=@{filter_prefix}"

        result = self._send_request(
            "GET", "/api/v2/cmdb/firewall.service/custom", params=params
        )

        items = []

        for item in result.get("results", []):
            protocol = _parse_protocol(item)
            dst_port, src_port = _parse_ports(item)

            items.append(
                FirewallService(
                    name=item["name"],
                    protocol=protocol,
                    src_port=src_port,
                    dst_port=dst_port,
                    comment=item["comment"],
                )
            )

        return items

    def _create_firewall_policy(self, policy: FirewallPolicy) -> int:
        req = {
            "name": policy["name"],
            "srcintf": [{"name": self.settings.src_if}],
            "dstintf": [{"name": self.settings.dst_if}],
            "srcaddr": [{"name": policy["src_addr"]}],
            "dstaddr": [{"name": policy["dst_addr"]}],
            "action": policy["action"],
            "schedule": "always",
            "service": [{"name": s} for s in policy["services"]],
            "status": "enable",
            "comments": policy["comment"],
        }

        result = self._send_request("POST", "/api/v2/cmdb/firewall/policy", json=req)

        return result["mkey"]

    def _delete_firewall_policy(self, policy_id: int) -> None:
        self._send_request("DELETE", f"/api/v2/cmdb/firewall/policy/{policy_id}")

    def _get_firewall_policies(
        self, filter_prefix: str | None = None, monitor: bool = False
    ) -> list[FirewallPolicy]:
        params = {"format": "policyid|name|srcaddr|dstaddr|service|action|comments"}
        if filter_prefix is not None:
            params["filter"] = f"name=@{filter_prefix}"

        result = self._send_request(
            "GET", "/api/v2/cmdb/firewall/policy", params=params
        )

        if monitor:
            params = {"format": "policyid|bytes|packets"}

            result_monitor = self._send_request(
                "GET", "/api/v2/monitor/firewall/policy", params=params
            )

            policy_monitor = {
                item["policyid"]: item for item in result_monitor.get("results", [])
            }
        else:
            policy_monitor = {}

        items = []

        for item in result.get("results", []):
            monitor = policy_monitor.get(item["policyid"], {})

            items.append(
                FirewallPolicy(
                    policy_id=item["policyid"],
                    name=item["name"],
                    src_addr=item["srcaddr"][0]["name"],
                    dst_addr=item["dstaddr"][0]["name"],
                    services=[s["name"] for s in item["service"]],
                    action=item["action"],
                    comment=item["comments"],
                    dropped_bytes=monitor.get("bytes"),
                    dropped_packets=monitor.get("packets"),
                    matched_bytes=monitor.get("bytes"),
                    matched_packets=monitor.get("packets"),
                )
            )

        return items

    def _move_firewall_policy(self, policy_id: int, before: int) -> None:
        req = {
            "action": "move",
            "before": before,
        }

        self._send_request(
            "PUT", f"/api/v2/cmdb/firewall/policy/{policy_id}", params=req
        )

    def _create_firewall_traffic_shaper(
        self, name: str, bandwidth_mbps: int, comment: str
    ) -> None:
        req = {
            "name": name,
            "bandwidth-unit": "mbps",
            "maximum-bandwidth": bandwidth_mbps,
            "guaranteed-bandwidth": bandwidth_mbps,
            "per-policy": "disable",
            "comment": comment,
        }

        self._send_request(
            "POST", "/api/v2/cmdb/firewall.shaper/traffic-shaper", json=req
        )

    def _delete_firewall_traffic_shaper(self, name: str) -> None:
        self._send_request(
            "DELETE", f"/api/v2/cmdb/firewall.shaper/traffic-shaper/{name}"
        )

    def _create_firewall_traffic_shaper_policy(self, policy: FirewallPolicy) -> int:
        req = {
            "name": policy["name"],
            "srcintf": [{"name": self.settings.src_if}],
            "dstintf": [{"name": self.settings.dst_if}],
            "srcaddr": [{"name": policy["src_addr"]}],
            "dstaddr": [{"name": policy["dst_addr"]}],
            "action": policy["action"],
            "schedule": "always",
            "service": [{"name": s} for s in policy["services"]],
            "status": "enable",
            "traffic-shaper": policy["traffic_shaper"],
            "comments": policy["comment"],
        }

        result = self._send_request(
            "POST", "/api/v2/cmdb/firewall/shaping-policy", json=req
        )

        return result["mkey"]

    def _delete_firewall_traffic_shaper_policy(self, policy_id: int) -> None:
        self._send_request(
            "DELETE", f"/api/v2/cmdb/firewall/shaping-policy/{policy_id}"
        )

    def _get_firewall_traffic_shaper_policies(
        self, filter_prefix: str | None = None, monitor: bool = False
    ) -> list[FirewallPolicy]:
        params = {"format": "id|name|srcaddr|dstaddr|service|traffic-shaper|comment"}
        if filter_prefix is not None:
            params["filter"] = f"name=@{filter_prefix}"

        result = self._send_request(
            "GET", "/api/v2/cmdb/firewall/shaping-policy", params=params
        )

        if monitor:
            result_monitor = self._send_request(
                "GET", "/api/v2/monitor/firewall/shaper"
            )

            policy_monitor = {
                item["name"]: item
                for item in result_monitor.get("results", {}).get("data", [])
            }
        else:
            policy_monitor = {}

        items = []

        for item in result.get("results", []):
            monitor = policy_monitor.get(item["traffic-shaper"], {})

            items.append(
                FirewallPolicy(
                    policy_id=item["id"],
                    name=item["name"],
                    src_addr=item["srcaddr"][0]["name"],
                    dst_addr=item["dstaddr"][0]["name"],
                    services=[s["name"] for s in item["service"]],
                    action="rate-limit",
                    traffic_shaper=item["traffic-shaper"],
                    comment=item["comment"],
                    dropped_bytes=monitor.get("dropped_bytes"),
                    dropped_packets=monitor.get("dropped_packets"),
                )
            )

        return items

    def _move_firewall_traffic_shaper_policy(self, policy_id: int, before: int) -> None:
        req = {
            "action": "move",
            "before": before,
        }

        self._send_request(
            "PUT", f"/api/v2/cmdb/firewall/shaping-policy/{policy_id}", params=req
        )

    @override
    def add_firewall_rule(self, rule: FirewallRule) -> None:
        comment = self.settings.comment.format(timestamp=str(datetime.datetime.now()))

        if rule.packet_length is not None:
            raise ValueError("Packet length matching is not supported by fortigate")

        if rule.tcp_flags is not None:
            raise ValueError("TCP flags matching is not supported by fortigate")

        if rule.action.type == "pps-limit":
            raise ValueError("pps-limit action is not supported by fortigate")

        if rule.source_address is not None:
            source_address_name = (
                f"{self.settings.prefix}_{_address_to_id(rule.source_address)}"
            )

            try:
                if not self._check_firewall_address_exists(source_address_name):
                    address = FirewallAddress(
                        name=source_address_name,
                        subnet=rule.source_address,
                        comment=comment,
                    )
                    self._create_firewall_address(address)
            except Exception as e:
                self.logger.warning(
                    "Failed to create firewall address for source %s: %s",
                    rule.source_address,
                    e,
                )
        else:
            source_address_name = "all"

        if rule.destination_address is not None:
            destination_address_name = (
                f"{self.settings.prefix}_{_address_to_id(rule.destination_address)}"
            )

            try:
                if not self._check_firewall_address_exists(destination_address_name):
                    address = FirewallAddress(
                        name=destination_address_name,
                        subnet=rule.destination_address,
                        comment=comment,
                    )
                    self._create_firewall_address(address)
            except Exception as e:
                self.logger.warning(
                    "Failed to create firewall address for destination %s: %s",
                    rule.destination_address,
                    e,
                )
        else:
            destination_address_name = "all"

        if rule.action.type == "accept":
            action = "accept"
        elif rule.action.type == "discard":
            action = "deny"
        else:
            action = "rate-limit"

        if rule.source_port is None or isinstance(rule.source_port, int):
            source_port = [rule.source_port]
        else:
            source_port = rule.source_port

        if rule.destination_port is None or isinstance(rule.destination_port, int):
            destination_port = [rule.destination_port]
        else:
            destination_port = rule.destination_port

        services = []

        for src_port in source_port:
            for dst_port in destination_port:
                service_name = (
                    f"{self.settings.prefix}_{rule.protocol}_{src_port}_{dst_port}"
                )
                services.append(service_name)

                service = FirewallService(
                    name=service_name,
                    protocol=0 if rule.protocol is None else rule.protocol,
                    src_port=src_port if src_port else None,
                    dst_port=dst_port if dst_port else None,
                    comment=comment,
                )

                try:
                    self._create_firewall_service(service)
                except Exception as e:
                    self.logger.warning(
                        "Failed to create firewall service %s: %s", service_name, e
                    )

        if isinstance(rule.action, FirewallRuleActionBpsLimit):
            traffic_shaper = f"{self.settings.prefix}_{rule.id[-12:]}_shaper"

            try:
                self._create_firewall_traffic_shaper(
                    traffic_shaper,
                    bandwidth_mbps=rule.action.bps // (1_024 * 1_024),
                    comment=comment,
                )
            except Exception as e:
                self.logger.warning(
                    "Failed to create firewall traffic shaper %s: %s", traffic_shaper, e
                )

            policy = FirewallPolicy(
                name=f"{self.settings.prefix}_{rule.id}",
                src_if=self.settings.src_if,
                dst_if=self.settings.dst_if,
                src_addr=source_address_name,
                dst_addr=destination_address_name,
                services=services,
                action=action,
                traffic_shaper=traffic_shaper,
                comment=comment,
            )

            try:
                policy_id = self._create_firewall_traffic_shaper_policy(policy)
            except Exception as e:
                self.logger.warning(
                    "Failed to create firewall traffic shaper policy %s: %s",
                    policy["name"],
                    e,
                )
                return

            try:
                self._move_firewall_traffic_shaper_policy(policy_id, before=1)
            except Exception as e:
                self.logger.warning(
                    "Failed to move firewall traffic shaper policy %d to the top: %s",
                    policy_id,
                    e,
                )
        else:
            policy = FirewallPolicy(
                name=f"{self.settings.prefix}_{rule.id}",
                src_if=self.settings.src_if,
                dst_if=self.settings.dst_if,
                src_addr=source_address_name,
                dst_addr=destination_address_name,
                services=services,
                action=action,
                comment=comment,
            )

            try:
                policy_id = self._create_firewall_policy(policy)
            except Exception as e:
                self.logger.warning(
                    "Failed to create firewall policy %s: %s", policy["name"], e
                )
                return

            try:
                self._move_firewall_policy(policy_id, before=1)
            except Exception as e:
                self.logger.warning(
                    "Failed to move firewall policy %d to the top: %s", policy_id, e
                )

    @override
    def remove_firewall_rule(self, rule_id: str) -> None:
        policies = self._get_firewall_policies(
            filter_prefix=f"{self.settings.prefix}_{rule_id}"
        )
        policies += self._get_firewall_traffic_shaper_policies(
            filter_prefix=f"{self.settings.prefix}_{rule_id}"
        )

        if len(policies) == 0:
            raise ValueError(f"Firewall rule with ID {rule_id} not found")

        policy = policies[0]
        if policy["name"] != f"{self.settings.prefix}_{rule_id}":
            raise ValueError(
                f"Firewall rule ID mismatch: {policy['name']} != {rule_id}"
            )

        if policy["action"] == "rate-limit":
            try:
                self._delete_firewall_traffic_shaper_policy(policy["policy_id"])
            except Exception as e:
                self.logger.warning(
                    "Failed to delete firewall traffic shaper policy %d: %s",
                    policy["policy_id"],
                    e,
                )

            if policy["traffic_shaper"].startswith(f"{self.settings.prefix}_"):
                try:
                    self._delete_firewall_traffic_shaper(policy["traffic_shaper"])
                except Exception as e:
                    self.logger.warning(
                        "Failed to delete firewall traffic shaper %s: %s",
                        policy["traffic_shaper"],
                        e,
                    )
        else:
            try:
                self._delete_firewall_policy(policy["policy_id"])
            except Exception as e:
                self.logger.warning(
                    "Failed to delete firewall policy %d: %s", policy["policy_id"], e
                )

        if policy["src_addr"].startswith(f"{self.settings.prefix}_"):
            try:
                self._delete_firewall_address(policy["src_addr"])
            except Exception as e:
                self.logger.warning(
                    "Failed to delete firewall address %s: %s", policy["src_addr"], e
                )

        if policy["dst_addr"].startswith(f"{self.settings.prefix}_"):
            try:
                self._delete_firewall_address(policy["dst_addr"])
            except Exception as e:
                self.logger.warning(
                    "Failed to delete firewall address %s: %s", policy["dst_addr"], e
                )

        for service in policy["services"]:
            if service.startswith(f"{self.settings.prefix}_"):
                try:
                    self._delete_firewall_service(service)
                except Exception as e:
                    self.logger.warning(
                        "Failed to delete firewall service %s: %s", service, e
                    )

    @override
    def list_firewall_rules(self) -> list[FirewallRule]:
        policies = self._get_firewall_policies(
            filter_prefix=f"{self.settings.prefix}_", monitor=True
        )
        policies += self._get_firewall_traffic_shaper_policies(
            filter_prefix=f"{self.settings.prefix}_", monitor=True
        )

        rules = []

        for policy in policies:
            if policy["action"] == "deny":
                action = {"type": "discard"}
            elif policy["action"] == "accept":
                action = {"type": "accept"}
            elif policy["action"] == "rate-limit":
                action = {"type": "bps-limit", "bps": 0}

            name = policy["name"].removeprefix(f"{self.settings.prefix}_")

            if policy["src_addr"] == "all":
                source_address = None
            else:
                source_address = policy["src_addr"].removeprefix(
                    f"{self.settings.prefix}_"
                )
                source_address = _id_to_address(source_address)

            if policy["dst_addr"] == "all":
                destination_address = None
            else:
                destination_address = policy["dst_addr"].removeprefix(
                    f"{self.settings.prefix}_"
                )
                destination_address = _id_to_address(destination_address)

            services = [
                s.removeprefix(f"{self.settings.prefix}_") for s in policy["services"]
            ]

            source_port = []
            destination_port = []

            for service in services:
                protocol, src_port, dst_port = service.split("_")

                if protocol == "None":
                    protocol = None
                if src_port == "None":
                    src_port = None
                if dst_port == "None" or dst_port == "0-65535":
                    dst_port = None

                source_port.append(src_port)
                destination_port.append(dst_port)

            rule = FirewallRule.model_validate(
                {
                    "id": name,
                    "source_address": source_address,
                    "destination_address": destination_address,
                    "protocol": protocol,
                    "source_port": None if None in source_port else source_port,
                    "destination_port": None
                    if None in destination_port
                    else destination_port,
                    "action": action,
                    "dropped_bytes": policy.get("dropped_bytes"),
                    "dropped_packets": policy.get("dropped_packets"),
                    "matched_bytes": policy.get("matched_bytes"),
                    "matched_packets": policy.get("matched_packets"),
                }
            )

            rules.append(rule)

        return rules

    @override
    def connect(self) -> None:
        pass

    @override
    def disconnect(self) -> None:
        pass

    @override
    def setup(self) -> None:
        pass

    @override
    def cleanup(self) -> None:
        for rule in self.list_firewall_rules():
            try:
                self.remove_firewall_rule(rule.id)
            except Exception as e:
                self.logger.warning(
                    "Failed to remove firewall rule %s during cleanup: %s", rule.id, e
                )
