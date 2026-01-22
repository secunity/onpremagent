import argparse
import logging
import re
import sys
import time
from datetime import timedelta
from enum import IntEnum
from pathlib import Path

import httpx
from paramiko import AutoAddPolicy, Channel, SSHClient
from paramiko.ssh_exception import SSHException
from tenacity import retry, wait_fixed

from config import SECUNITY_API_URL, CallableConfig, read_config_file

SEND_STATISTIC_INTERVAL = timedelta(seconds=60)

SSH_TIMEOUT = 30.0

HTTP_TIMEOUT = 10.0


logger = logging.getLogger("ssh-controller")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)8s - %(message)s")
)

logger.addHandler(console_handler)


class INetFamily(IntEnum):
    IPV4 = 0
    IPV6 = 1


class SSHController:
    def __init__(
        self,
        config_fn: CallableConfig,
        ssh_timeout: float = SSH_TIMEOUT,
        http_timeout: float = HTTP_TIMEOUT,
    ) -> None:
        config = config_fn()

        self.config = config
        self.ssh_timeout = ssh_timeout

        self.http_client = httpx.Client(
            base_url=f"{SECUNITY_API_URL}/{config.identifier}",
            timeout=http_timeout,
            verify=False,
        )

        self.ssh_client = SSHClient()
        self.ssh_client.set_missing_host_key_policy(AutoAddPolicy())

    def _connect(self) -> None:
        params = {
            "hostname": self.config.host,
            "port": self.config.port,
            "username": self.config.username,
            "password": self.config.password,
            "timeout": self.ssh_timeout,
        }

        self.ssh_client.connect(**params)

    def _exec(self, command: str) -> list[str]:
        try:
            self._connect()
        except SSHException:
            logger.exception("SSH connection failed")
            return []

        logger.info("Executing command: %s", command)

        try:
            _, stdout, stderr = self.ssh_client.exec_command(
                f"{command}\n", timeout=self.ssh_timeout
            )

            stdout_lines: list[str] = stdout.readlines()
            stderr_lines: list[str] = stderr.readlines()

            logger.info("Command stdout: %s", stdout_lines)
            logger.error("Command stderr: %s", stderr_lines)

            return [_.rstrip("\r\n") for _ in stdout_lines]
        except SSHException:
            logger.exception("SSH command execution failed")
            return []
        finally:
            self.ssh_client.close()

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

    def get_juniper_flows(self, vrf: str, inet_family: INetFamily) -> list[str]:
        if inet_family == INetFamily.IPV4:
            inet_family_ = "inet"
        elif inet_family == INetFamily.IPV6:
            inet_family_ = "inet6"

        command = "show firewall filter detail __flowspec_{interface_name}_{inet_family}__".format(
            interface_name=vrf,
            inet_family=inet_family_,
        )

        return self._exec(command)

    def get_cisco_flows(self, vrf: str, inet_family: INetFamily) -> list[str]:
        if inet_family == INetFamily.IPV4:
            inet_family_ = "ipv4"
        elif inet_family == INetFamily.IPV6:
            inet_family_ = "ipv6"

        command = "show ip flow {interface_name} {inet_family}".format(
            interface_name=vrf,
            inet_family=inet_family_,
        )

        return self._exec(command)

    def get_arista_flows(self, vrf: str, inet_family: INetFamily) -> list[str]:
        if inet_family == INetFamily.IPV4:
            inet_family_ = "ipv4"
        elif inet_family == INetFamily.IPV6:
            inet_family_ = "ipv6"

        command = "sh flow-spec {inet_family}".format(inet_family=inet_family_)

        return self._exec(command)

    def get_huawei_flows(self, vrf: str, inet_family: INetFamily) -> list[str]:
        if inet_family == INetFamily.IPV4:
            inet_family_ = "vpnv4"
        elif inet_family == INetFamily.IPV6:
            inet_family_ = "vpnv6"

        shell_prompt = re.compile(r"<.*?>")

        display_routing_table = "display bgp flow {inet_family} vpn-instance {vpn_instance} routing-table | no-more".format(
            inet_family=inet_family_,
            vpn_instance=vrf,
        )
        display_statistics = "display flowspec {inet_family} vpn-instance {vpn_instance} statistics {{re_index}} | no-more".format(
            inet_family=inet_family_,
            vpn_instance=vrf,
        )

        try:
            self._connect()

            shell = self.ssh_client.invoke_shell()

            output_array = []

            _ = self._read_and_wait(shell, shell_prompt)

            logger.info("Executing command: %s", display_routing_table)

            shell.sendall(f"{display_routing_table}\n")
            output = self._read_and_wait(shell, shell_prompt)

            output_array += output.splitlines()

            for re_index in re.findall(r"ReIndex\s*:\s*(\d+)", output):
                command = display_statistics.format(re_index=re_index)

                logger.info("Executing command: %s", command)
                shell.sendall(command)
                output = self._read_and_wait(shell, shell_prompt)

                output_array += ["\f"]
                output_array += output.splitlines()

            self.ssh_client.close()

            return output_array
        except Exception:
            logger.exception("Failed to get Huawei flows")
            return []

    def send_statistics(self) -> None:
        get_flows_func = None

        if self.config.vendor == "juniper":
            get_flows_func = self.get_juniper_flows
        elif self.config.vendor == "cisco":
            get_flows_func = self.get_cisco_flows
        elif self.config.vendor == "arista":
            get_flows_func = self.get_arista_flows
        elif self.config.vendor == "huawei":
            get_flows_func = self.get_huawei_flows
        else:
            logger.error("Unsupported vendor: %s", self.config.vendor)
            return

        logger.info("Fetching flows for vendor: %s", self.config.vendor)

        logger.info("Fetching flows for IPv4")
        flows_ipv4 = get_flows_func(self.config.vrf, INetFamily.IPV4)

        logger.info("Fetching flows for IPv6")
        flows_ipv6 = get_flows_func(self.config.vrf, INetFamily.IPV6)

        flows = flows_ipv4 + flows_ipv6

        logger.info("Found %d flows: %s", len(flows), flows)

        try:
            response = self.http_client.put(
                "/flows/stat",
                json={
                    "data": flows,
                },
            )
            response.raise_for_status()

            logger.info("Statistics sent successfully")
        except httpx.HTTPError:
            logger.exception("Failed to send statistics")


@retry(wait=wait_fixed(SEND_STATISTIC_INTERVAL))
def send_statistics_worker(config: CallableConfig) -> None:
    controller = SSHController(config)

    while True:
        controller.send_statistics()
        time.sleep(SEND_STATISTIC_INTERVAL.total_seconds())


def main():
    parser = argparse.ArgumentParser(description="SSh Controller")
    parser.add_argument(
        "--config", type=Path, required=True, help="Path to the config file"
    )
    args = parser.parse_args()

    config = lambda: read_config_file(args.config)

    logger.info("Starting SSH Controller")

    send_statistics_worker(config)


if __name__ == "__main__":
    main()
