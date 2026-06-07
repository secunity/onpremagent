from typing import Any, TypedDict, override

from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from lxml.etree import XML, Element, XMLParser, tostring
from pydantic import BaseModel

from onpremagent.connectors.base import BaseConnector
from onpremagent.connectors.juniper_netconf.settings import JuniperNetconfSettings
from onpremagent.types.firewall_rule import (
    Family,
    FirewallRule,
    FirewallRuleActionBpsLimit,
    FirewallRuleActionPpsLimit,
)


class FirewallCounter(TypedDict):
    name: str
    packet_count: int | None
    byte_count: int | None


def xml_doc(doc: str) -> Element:
    return XML(doc, XMLParser(remove_blank_text=True))


def xml_string(elem: Element) -> str:
    return tostring(elem, method="xml", pretty_print=True).decode()


class JuniperNetconfConnector(BaseConnector[JuniperNetconfSettings]):
    def __init__(self, settings) -> None:
        super().__init__(settings)

        kwargs: dict[str, Any] = {
            "host": self.settings.host,
            "user": self.settings.username,
            "port": self.settings.port,
            "password": self.settings.password.get_secret_value(),
        }

        if self.settings.timeout is not None:
            kwargs["timeout"] = self.settings.timeout

        self._device = Device(**kwargs)
        self._config = Config(
            self._device,
            mode="ephemeral",
            ephemeral_instance=self.settings.ephemeral_instance,
        )

    def _check_interface_exists(self, interface: str) -> bool:
        interface_info: Element = self._device.rpc.get_interface_information(
            interface_name=interface
        )

        return interface_info.find(".//physical-interface") is not None

    def _check_firewall_policer_exists(self, policer_name: str) -> bool:
        conf_xml = xml_doc(f"""
        <configuration>
            <firewall>
                <policer>
                    <name>{policer_name}</name>
                </policer>
            </firewall>
        </configuration>
        """)

        config = self._device.rpc.get_config(filter_xml=conf_xml)

        return config.find(".//policer") is not None

    def _remove_firewall_policer(self, policer_name: str) -> None:
        conf_xml = xml_doc(f"""
        <configuration>
            <firewall>
                <policer operation="delete">
                    <name>{policer_name}</name>
                </policer>
            </firewall>
        </configuration>
        """)

        self.logger.debug(
            "Removing firewall policer with XML:\n%s", xml_string(conf_xml)
        )

        self._config.load(conf_xml, format="xml")
        self._config.commit()

    def _add_firewall_policer(self, policer_name: str) -> None:
        conf_xml = xml_doc(f"""
        <configuration>
            <firewall>
                <policer operation="delete">
                    <name>{policer_name}</name>
                </policer>
            </firewall>
        </configuration>
        """)

        self.logger.debug("Adding firewall policer with XML:\n%s", xml_string(conf_xml))

        self._config.load(conf_xml, format="xml")
        self._config.commit()

    def _check_firewall_rule_exists(self, id: str, family: Family) -> bool:
        conf_xml = xml_doc(f"""
        <configuration>
            <firewall>
                <family>
                    <{family.value}>
                        <filter>
                            <name>{self.settings.filter_name}</name>
                            <term>
                                <name>{id}</name>
                            </term>
                        </filter>
                    </{family.value}>
                </family>
            </firewall>
        </configuration>
        """)

        self.logger.debug(
            "Checking firewall rule existence with filter XML:\n%s",
            xml_string(conf_xml),
        )

        config = self._device.rpc.get_config(filter_xml=conf_xml)

        return config.find(".//term") is not None

    def _create_firewall_filter(self, family: Family) -> None:
        config_xml = xml_doc(f"""
        <configuration>
            <firewall>
                <family>
                    <{family.value}>
                        <filter>
                            <name>{self.settings.filter_name}</name>
                            <term>
                                <name>default</name>
                                <then>
                                    <accept/>
                                </then>
                            </term>
                        </filter>
                    </{family.value}>
                </family>
            </firewall>
            <interfaces>
                <interface>
                    <name>{self.settings.interface}</name>
                    <unit>
                        <name>{self.settings.interface_unit}</name>
                        <family>
                            <{family.value}>
                                <filter>
                                    <input>
                                        <filter-name>{self.settings.filter_name}</filter-name>
                                    </input>
                                </filter>
                            </{family.value}>
                        </family>
                    </unit>
                </interface>
            </interfaces>
        </configuration>
        """)

        self.logger.debug(
            "Creating firewall filter with XML:\n%s", xml_string(config_xml)
        )

        self._config.load(config_xml, format="xml")
        self._config.commit()

    def _remove_firewall_inet_rule(self, id: str, family: Family) -> None:
        conf_xml = xml_doc(f"""
        <configuration>
            <firewall>
                <family>
                    <{family.value}>
                        <filter>
                            <name>{self.settings.filter_name}</name>
                            <term operation="delete">
                                <name>{id}</name>
                            </term>
                        </filter>
                    </{family.value}>
                </family>
            </firewall>
        </configuration>
        """)

        self.logger.debug("Removing firewall rule with XML:\n%s", xml_string(conf_xml))

        self._config.load(conf_xml, format="xml")
        self._config.commit()

    def _list_firewall_rules(self, family: Family) -> Element:
        conf_xml = xml_doc(f"""
        <configuration>
            <firewall>
                <family>
                    <{family.value}>
                        <filter>
                            <name>{self.settings.filter_name}</name>
                        </filter>
                    </{family.value}>
                </family>
            </firewall>
        </configuration>
        """)

        self.logger.debug(
            "Retrieving firewall rules with filter XML:\n%s", xml_string(conf_xml)
        )

        return self._device.rpc.get_config(filter_xml=conf_xml)

    def _add_firewall_rule(self, rule: FirewallRule) -> None:
        parts: list[str] = []

        if rule.source_address is not None:
            addresses = (
                rule.source_address
                if isinstance(rule.source_address, list)
                else [rule.source_address]
            )
            for addr in addresses:
                parts.append(f"<source-address><name>{addr}</name></source-address>")

        if rule.destination_address is not None:
            addresses = (
                rule.destination_address
                if isinstance(rule.destination_address, list)
                else [rule.destination_address]
            )
            for addr in addresses:
                parts.append(
                    f"<destination-address><name>{addr}</name></destination-address>"
                )

        if rule.protocol is not None:
            protocols = (
                rule.protocol if isinstance(rule.protocol, list) else [rule.protocol]
            )
            for proto in protocols:
                parts.append(f"<protocol>{proto}</protocol>")

        if rule.source_port is not None:
            ports = (
                rule.source_port
                if isinstance(rule.source_port, list)
                else [rule.source_port]
            )
            for p in ports:
                if "-" in str(p):
                    start, end = str(p).split("-", 1)
                    parts.append(f"<source-port>{start}-{end}</source-port>")
                else:
                    parts.append(f"<source-port>{p}</source-port>")

        if rule.destination_port is not None:
            ports = (
                rule.destination_port
                if isinstance(rule.destination_port, list)
                else [rule.destination_port]
            )
            for p in ports:
                if "-" in str(p):
                    start, end = str(p).split("-", 1)
                    parts.append(f"<destination-port>{start}-{end}</destination-port>")
                else:
                    parts.append(f"<destination-port>{p}</destination-port>")

        if rule.packet_length is not None:
            if "-" in str(rule.packet_length):
                start, end = str(rule.packet_length).split("-", 1)
                parts.append(f"<packet-length>{start}-{end}</packet-length>")
            else:
                parts.append(f"<packet-length>{rule.packet_length}</packet-length>")

        if rule.tcp_flags is not None:
            parts.append(f"<tcp-flags>{rule.tcp_flags:#x}</tcp-flags>")

        from_xml = f"<from>{''.join(parts)}</from>" if len(parts) > 0 else ""

        if rule.action.type == "accept":
            then = "<accept/>"
        elif rule.action.type == "discard":
            then = "<discard/>"
        elif rule.action.type in ("bps-limit", "pps-limit"):
            then = f"<policer>policer-{rule.id}</policer><accept/>"

        policer = rule.action

        if isinstance(policer, FirewallRuleActionBpsLimit):
            policer_xml = f"""
            <policer>
                <name>policer-{rule.id}</name>
                <if-exceeding>
                    <bandwidth-limit>{policer.bps}</bandwidth-limit>
                    <burst-size-limit>{policer.bps}</burst-size-limit>
                </if-exceeding>
                <then>
                    <discard/>
                </then>
            </policer>
            """
        elif isinstance(policer, FirewallRuleActionPpsLimit):
            policer_xml = f"""
            <policer>
                <name>policer-{rule.id}</name>
                <if-exceeding-pps>
                    <pps-limit>{policer.pps}</pps-limit>
                    <packet-burst>{policer.pps}</packet-burst>
                </if-exceeding-pps>
                <then>
                    <discard/>
                </then>
            </policer>
            """
        else:
            policer_xml = ""

        family = rule.family.value

        conf_xml = xml_doc(f"""
        <configuration>
            <firewall>
                {policer_xml}
                <family>
                    <{family}>
                        <filter>
                            <name>{self.settings.filter_name}</name>
                            <term>
                                <name>{rule.id}</name>
                                {from_xml}
                                <then>
                                    {then}
                                </then>
                            </term>
                        </filter>
                    </{family}>
                </family>
            </firewall>
        </configuration>
        """)

        self.logger.debug("Adding firewall rule with XML:\n%s", xml_string(conf_xml))

        self._config.load(conf_xml, format="xml")
        self._config.commit()

    def _parse_term_xml[T: BaseModel](self, term: Element, type: type[T]) -> T:
        rule: dict[str, Any] = {
            "id": term.findtext("name", "").strip(),
        }

        from_elem = term.find("from")
        if from_elem is not None:
            src_addrs = [
                elem.findtext("name", "").strip()
                for elem in from_elem.findall("source-address")
            ]
            if src_addrs:
                rule["source_address"] = (
                    src_addrs if len(src_addrs) > 1 else src_addrs[0]
                )

            dst_addrs = [
                elem.findtext("name", "").strip()
                for elem in from_elem.findall("destination-address")
            ]
            if dst_addrs:
                rule["destination_address"] = (
                    dst_addrs if len(dst_addrs) > 1 else dst_addrs[0]
                )

            protocols = [
                elem.text.strip() for elem in from_elem.findall("protocol") if elem.text
            ]
            if protocols:
                rule["protocol"] = protocols if len(protocols) > 1 else protocols[0]

            src_ports = [
                elem.text.strip()
                for elem in from_elem.findall("source-port")
                if elem.text
            ]
            if src_ports:
                rule["source_port"] = src_ports if len(src_ports) > 1 else src_ports[0]

            dst_ports = [
                elem.text.strip()
                for elem in from_elem.findall("destination-port")
                if elem.text
            ]
            if dst_ports:
                rule["destination_port"] = (
                    dst_ports if len(dst_ports) > 1 else dst_ports[0]
                )

            pkt_len = from_elem.findtext("packet-length")
            if pkt_len:
                rule["packet_length"] = pkt_len.strip()

            tcp_flags = from_elem.findtext("tcp-flags")
            if tcp_flags:
                rule["tcp_flags"] = tcp_flags.strip()

        then_elem = term.find("then")
        if then_elem is not None:
            if then_elem.find("accept") is not None:
                rule["action"] = {"type": "accept"}
            elif then_elem.find("discard") is not None:
                rule["action"] = {"type": "discard"}

            policer = then_elem.findtext("policer")
            if policer:
                rule["policer"] = policer.strip()

        return type.model_validate(rule)

    def _show_firewall_counters(self) -> list[FirewallCounter]:
        stats_xml = self._device.rpc.cli(
            f"show firewall filter {self.settings.filter_name}", format="xml"
        )

        results: list[FirewallCounter] = []
        for counter in stats_xml.findall(".//counter"):
            name = counter.findtext("counter-name", "").strip()
            if not name:
                continue

            entry: FirewallCounter = {"name": name, "packet_count": 0, "byte_count": 0}

            packet_count = counter.findtext("packet-count")
            if packet_count:
                entry["packet_count"] = int(packet_count.strip())

            byte_count = counter.findtext("byte-count")
            if byte_count:
                entry["byte_count"] = int(byte_count.strip())

            results.append(entry)

        return results

    @override
    def connect(self) -> None:
        self._device.open()

    @override
    def disconnect(self) -> None:
        self._device.close()

    @override
    def setup(self) -> None:
        self.logger.debug(
            "Verifying interface %s unit %d exists",
            self.settings.interface,
            self.settings.interface_unit,
        )

        interface_info: Element = self._device.rpc.get_interface_information(
            interface_name=self.settings.interface
        )

        if interface_info.find(".//physical-interface") is None:
            raise RuntimeError(f"Interface {self.settings.interface} does not exist")

        logical_unit_name = f"{self.settings.interface}.{self.settings.interface_unit}"
        logical_interfaces: list[str] = [
            li.findtext("name", "").strip()
            for li in interface_info.findall(".//logical-interface")
        ]

        self.logger.debug(
            "Available logical interfaces for %s: %s",
            self.settings.interface,
            logical_interfaces,
        )

        if logical_unit_name not in logical_interfaces:
            raise RuntimeError(f"Interface unit {logical_unit_name} does not exist")

        self.logger.debug(
            "Interface %s unit %d verified",
            self.settings.interface,
            self.settings.interface_unit,
        )

        self._create_firewall_filter(Family.INET)
        self._create_firewall_filter(Family.INET6)

    @override
    def cleanup(self) -> None:
        pass

    @override
    def add_firewall_rule(self, rule: FirewallRule) -> None:
        if self._check_firewall_rule_exists(rule.id, rule.family):
            raise RuntimeError(f"Firewall rule with ID {rule.id} already exists")

        self._add_firewall_rule(rule)

    @override
    def remove_firewall_rule(self, rule_id: str) -> None:
        if not self._check_firewall_rule_exists(
            rule_id, Family.INET
        ) and not self._check_firewall_rule_exists(rule_id, Family.INET6):
            raise RuntimeError(f"Firewall rule with ID {rule_id} does not exist")

        self._remove_firewall_inet_rule(rule_id, Family.INET)

        if self._check_firewall_policer_exists(f"policer-{rule_id}"):
            self._remove_firewall_policer(f"policer-{rule_id}")
        else:
            self.logger.debug(
                "No associated policer for firewall rule %s, skipping policer removal",
                rule_id,
            )

    @override
    def list_firewall_rules(self) -> list[FirewallRule]:
        conf_xml = self._list_firewall_rules(Family.INET)

        self.logger.debug("Firewall inet filter config XML:\n%s", xml_string(conf_xml))

        return [
            self._parse_term_xml(term, FirewallRule)
            for term in conf_xml.findall(".//term")
        ]
