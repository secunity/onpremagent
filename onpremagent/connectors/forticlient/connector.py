import logging
import warnings
from ipaddress import IPv4Network, IPv6Network
from typing import Any, Literal, NotRequired, TypedDict, override

import requests
from urllib3.exceptions import InsecureRequestWarning

from onpremagent.connectors.base import BaseConnector
from onpremagent.connectors.forticlient.settings import FortiClientSettings
from onpremagent.types.firewall_rule import FirewallRule


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
    service: str
    action: Literal["accept", "deny"]
    comment: str
    bytes: NotRequired[int | None]
    packets: NotRequired[int | None]


class FortiClientError(Exception):
    pass


class FortiClientHttpError(FortiClientError):
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
        return {}
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


class FortiClientConnector(BaseConnector[FortiClientSettings]):
    def __init__(
        self,
        settings: FortiClientSettings,
    ) -> None:
        super().__init__(settings)

        if not self.settings.ssl_verify:
            warnings.filterwarnings("ignore", category=InsecureRequestWarning)

        self.session = requests.Session()
        self.session.verify = self.settings.ssl_verify
        self.session.headers.update({"Authorization": f"Bearer {self.settings.token}"})

        self.logger = logging.getLogger(
            f"onpremagent.connectors.{self.__class__.__name__}"
        )

    def _send_request(self, method: str, endpoint: str, **kwargs) -> dict:
        self.logger.debug(
            "Sending %s request to %s with params: %s", method, endpoint, kwargs
        )

        res = self.session.request(method, f"{self.settings.host}{endpoint}", **kwargs)

        try:
            res.raise_for_status()
        except requests.HTTPError as e:
            raise FortiClientHttpError(res.status_code, res.text) from e

        result = res.json()

        if result["status"] != "success":
            raise FortiClientError(f"API request failed: {res.text}")

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
        except FortiClientHttpError:
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
            "service": [{"name": policy["service"]}],
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
                    service=item["service"][0]["name"],
                    action=item["action"],
                    comment=item["comments"],
                    bytes=monitor.get("bytes"),
                    packets=monitor.get("packets"),
                )
            )

        return items

    def _move_firewall_policy(self, policy_id: int, before: int) -> None:
        req = {
            "action": "move",
            "before": before,
        }

        self._send_request("PUT", f"/api/v2/cmdb/firewall/policy/{policy_id}", json=req)

    @override
    def add_firewall_rule(self, rule: FirewallRule) -> None:
        if rule.packet_length is not None:
            raise ValueError("Packet length matching is not supported by FortiClient")

        if rule.tcp_flags is not None:
            raise ValueError("TCP flags matching is not supported by FortiClient")

        if rule.protocol is None:
            raise ValueError("Protocol must be specified for FortiClient")

        if rule.source_port is not None and isinstance(rule.source_port, list):
            if len(rule.source_port) > 1:
                raise ValueError(
                    "Multiple source ports are not supported by FortiClient"
                )
            else:
                rule.source_port = rule.source_port[0]

        if rule.destination_port is not None and isinstance(
            rule.destination_port, list
        ):
            if len(rule.destination_port) > 1:
                raise ValueError(
                    "Multiple destination ports are not supported by FortiClient"
                )
            else:
                rule.destination_port = rule.destination_port[0]

        if rule.action.type not in ("discard", "accept"):
            raise ValueError(f"Unsupported action type: {rule.action.type}")

        if rule.source_address is not None:
            source_address_name = (
                f"{self.settings.prefix}_{_address_to_id(rule.source_address)}"
            )

            if not self._check_firewall_address_exists(source_address_name):
                address = FirewallAddress(
                    name=source_address_name,
                    subnet=rule.source_address,
                    comment=self.settings.comment,
                )
                self._create_firewall_address(address)
        else:
            source_address_name = "all"

        if rule.destination_address is not None:
            destination_address_name = (
                f"{self.settings.prefix}_{_address_to_id(rule.destination_address)}"
            )

            if not self._check_firewall_address_exists(destination_address_name):
                address = FirewallAddress(
                    name=destination_address_name,
                    subnet=rule.destination_address,
                    comment=self.settings.comment,
                )
                self._create_firewall_address(address)
        else:
            destination_address_name = "all"

        if rule.action.type == "accept":
            action = "accept"
        else:
            action = "deny"

        service_name = f"{self.settings.prefix}_{rule.protocol}_{rule.source_port}_{rule.destination_port}"

        service = FirewallService(
            name=service_name,
            protocol=rule.protocol,
            src_port=rule.source_port if rule.source_port else None,
            dst_port=rule.destination_port if rule.destination_port else None,
            comment=self.settings.comment,
        )
        self._create_firewall_service(service)

        policy = FirewallPolicy(
            name=f"{self.settings.prefix}_{rule.id}",
            src_if=self.settings.src_if,
            dst_if=self.settings.dst_if,
            src_addr=source_address_name,
            dst_addr=destination_address_name,
            service=service_name,
            action=action,
            comment=self.settings.comment,
        )

        policy_id = self._create_firewall_policy(policy)

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
        if len(policies) == 0:
            raise ValueError(f"No firewall rule found with ID: {rule_id}")

        policy = policies[0]

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

        if policy["service"].startswith(f"{self.settings.prefix}_"):
            try:
                self._delete_firewall_service(policy["service"])
            except Exception as e:
                self.logger.warning(
                    "Failed to delete firewall service %s: %s", policy["service"], e
                )

    @override
    def list_firewall_rules(self) -> list[FirewallRule]:
        policies = self._get_firewall_policies(
            filter_prefix=f"{self.settings.prefix}_", monitor=True
        )

        rules = []

        for policy in policies:
            if policy["action"] == "deny":
                action_type = "discard"
            elif policy["action"] == "accept":
                action_type = "accept"

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

            service = policy["service"].removeprefix(f"{self.settings.prefix}_")

            protocol, source_port, destination_port = service.split("_")

            if source_port == "None":
                source_port = None
            if destination_port == "None":
                destination_port = None

            rule = FirewallRule.model_validate(
                {
                    "id": name,
                    "source_address": source_address,
                    "destination_address": destination_address,
                    "protocol": protocol,
                    "source_port": source_port,
                    "destination_port": destination_port,
                    "action": {"type": action_type},
                    "bytes": policy.get("bytes"),
                    "packets": policy.get("packets"),
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
