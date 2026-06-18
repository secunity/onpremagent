import re
import time
from typing import override

from paramiko import AutoAddPolicy, Channel, SSHClient, SSHException

from onpremagent.connectors.base import BaseConnector
from onpremagent.connectors.ssh.settings import SSHSettings
from onpremagent.types.firewall_rule import Family


class SSHConnector(BaseConnector[SSHSettings]):
    def __init__(self, settings: SSHSettings) -> None:
        super().__init__(settings)

        self.ssh_client = SSHClient()
        self.ssh_client.set_missing_host_key_policy(AutoAddPolicy())

    def _exec(self, command: str) -> list[str]:
        self.logger.info("Executing command: %s", command)

        try:
            _, stdout, stderr = self.ssh_client.exec_command(
                f"{command}\n", timeout=self.ssh_timeout
            )

            stdout_lines: list[str] = stdout.readlines()
            stderr_lines: list[str] = stderr.readlines()

            self.logger.info("Command stdout: %s", stdout_lines)
            self.logger.error("Command stderr: %s", stderr_lines)

            return [_.rstrip("\r\n") for _ in stdout_lines]
        except SSHException:
            self.logger.exception("SSH command execution failed")
            return []

    def _read_and_wait(self, shell: Channel, prompt: re.Pattern) -> str:
        full_output = []

        while True:
            if shell.recv_ready():
                output = shell.recv(1024).decode("utf-8")
                full_output.append(output)

                if prompt.search(output):
                    break

            if shell.exit_status_ready():
                break

            if shell.closed or shell.eof_received or not shell.active:
                break

            time.sleep(0.1)

        return "".join(full_output)

    def _get_juniper_flows(
        self, vrf: str, inet_family: Family, model: str
    ) -> list[str]:
        if inet_family == Family.INET:
            inet_family_ = "inet"
        elif inet_family == Family.INET6:
            inet_family_ = "inet6"

        filter_name = "__flowspec_{interface_name}_{inet_family}__".format(
            interface_name=vrf if vrf else "default",
            inet_family=inet_family_,
        )

        if model and "acx" in model.lower():
            command = "show firewall application routing"
        else:
            command = f"show firewall filter detail {filter_name}"

        result = "\n".join(self._exec(command))

        filters = re.findall(
            r"Filter:\s+(?P<filter_name>\S+)(?P<data>.+?)(?=Filter:|\Z)",
            result,
            re.DOTALL | re.MULTILINE,
        )
        for filter_name, data in filters:
            if filter_name == filter_name:
                return [f"Filter: {filter_name}"] + data.splitlines()

        return []

    def _get_cisco_flows(self, vrf: str, inet_family: Family, model: str) -> list[str]:
        _ = vrf  # TODO: Support VRF for Cisco devices
        _ = model

        if inet_family == Family.INET:
            inet_family_ = "ipv4"
        elif inet_family == Family.INET6:
            inet_family_ = "ipv6"

        command = "show flowspec vrf all {inet_family} detail".format(
            inet_family=inet_family_,
        )

        return self._exec(command)

    def _get_arista_flows(self, vrf: str, inet_family: Family, model: str) -> list[str]:
        _ = vrf
        _ = model

        if inet_family == Family.INET:
            inet_family_ = "ipv4"
        elif inet_family == Family.INET6:
            inet_family_ = "ipv6"

        command = "sh flow-spec {inet_family}".format(inet_family=inet_family_)

        return self._exec(command)

    def _get_huawei_flows(self, vrf: str, inet_family: Family, model: str) -> list[str]:
        _ = model

        display_routing_table = ["display bgp flow"]
        display_statistics = ["display flowspec"]

        if vrf:
            display_routing_table.append(
                "vpnv6" if inet_family == Family.INET6 else "vpnv4"
            )

            display_routing_table.append(
                "vpn-instance {vpn_instance} routing-table | no-more"
            )
            display_statistics.append(
                "vpn-instance {vpn_instance} statistics {{re_index}} | no-more"
            )
        else:
            display_routing_table.append("ipv6" if inet_family == Family.INET6 else "")

            display_routing_table.append("routing-table | no-more")
            display_statistics.append("statistics {{re_index}} | no-more")

        shell_prompt = re.compile(r"<.*?>")

        cmd_display_routing_table = " ".join(display_routing_table).format(
            vpn_instance=vrf,
        )
        cmd_display_statistics = " ".join(display_statistics).format(
            vpn_instance=vrf,
        )

        try:
            shell = self.ssh_client.invoke_shell()

            output_array = []

            _ = self._read_and_wait(shell, shell_prompt)

            self.logger.info("Executing command: %s", cmd_display_routing_table)

            shell.sendall(f"{cmd_display_routing_table}\n")
            output = self._read_and_wait(shell, shell_prompt)

            output_array += output.splitlines()

            for re_index in re.findall(r"ReIndex\s*:\s*(\d+)", output):
                command = cmd_display_statistics.format(re_index=re_index)

                self.logger.info("Executing command: %s", command)
                shell.sendall(command)
                output = self._read_and_wait(shell, shell_prompt)

                output_array += ["\f"]
                output_array += output.splitlines()

            return output_array
        except Exception:
            self.logger.exception("Failed to get Huawei flows")
            return []

    @override
    def connect(self) -> None:
        self.logger.info(
            "Connecting to SSH server %s:%d as user %s",
            self.settings.host,
            self.settings.port,
            self.settings.username,
        )

        self.ssh_client.connect(
            hostname=self.settings.host,
            port=self.settings.port,
            username=self.settings.username,
            password=self.settings.password.get_secret_value(),
            timeout=self.settings.timeout,
        )

        self.logger.info(
            "Connected to SSH server %s:%d", self.settings.host, self.settings.port
        )

    @override
    def disconnect(self) -> None:
        self.logger.info(
            "Disconnecting from SSH server %s:%d",
            self.settings.host,
            self.settings.port,
        )

        self.ssh_client.close()

        self.logger.info(
            "Disconnected from SSH server %s:%d", self.settings.host, self.settings.port
        )

    @override
    def raw_statistics(self) -> dict[str, str]:
        get_flows_func = None

        if self.config.vendor == "juniper":
            get_flows_func = self._get_juniper_flows
        elif self.config.vendor == "cisco":
            get_flows_func = self._get_cisco_flows
        elif self.config.vendor == "arista":
            get_flows_func = self._get_arista_flows
        elif self.config.vendor == "huawei":
            get_flows_func = self._get_huawei_flows
        else:
            self.logger.error("Unsupported vendor: %s", self.settings.vendor)
            return []

        self.logger.info("Fetching flows for vendor: %s", self.settings.vendor)

        self.logger.info("Fetching flows for IPv4")
        flows_ipv4 = get_flows_func(self.settings.vrf, Family.INET, self.settings.model)

        self.logger.info("Fetching flows for IPv6")
        flows_ipv6 = get_flows_func(
            self.settings.vrf, Family.INET6, self.settings.model
        )

        flows = flows_ipv4 + flows_ipv6

        self.logger.info("Found %d flows: %s", len(flows), flows)

        return flows
