import re

from command_workers.bases import SshCommandWorker
from common.enums import VENDOR
from common.logs import Log
from common.sshutils import read_and_wait


class HuaweiCommandWorker(SshCommandWorker):
    _get_stats_from_router_command = "display bgp"

    SHELL_PROMPT = re.compile(r"<.*?>")

    VPN_DISPLAY_ROUTING_TABLE = (
        "display bgp flow vpnv4 vpn-instance {vpn_instance} routing-table | no-more"
    )
    VPN_DISPLAY_STATISTICS = "display flowspec vpnv4 vpn-instance {vpn_instance} statistics {re_index} | no-more"

    DISPLAY_ROUTING_TABLE = "display bgp flow routing-table | no-more"
    DISPLAY_STATISTICS = "display flowspec statistics {re_index} | no-more"

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.HUAWEI

    def execute_cli(self, credentials, command=None, exec_command=None, **kwargs):
        stats_type = kwargs.get("stats_type")
        if stats_type == "IPv6":
            Log.info("No IPv6 support")
            return []

        try:
            vpn_instance = kwargs.get("vrf")

            if vpn_instance:
                Log.info(f"Getting BGP statistics for VPN instance: {vpn_instance}")
                display_routing_table = self.VPN_DISPLAY_ROUTING_TABLE.format(
                    vpn_instance=vpn_instance
                )
                display_statistics = self.VPN_DISPLAY_STATISTICS.format(
                    vpn_instance=vpn_instance, re_index="{re_index}"
                )
            else:
                Log.info("Getting BGP statistics for global routing table")
                display_routing_table = self.DISPLAY_ROUTING_TABLE
                display_statistics = self.DISPLAY_STATISTICS.format(
                    re_index="{re_index}"
                )

            ssh_client = self.generate_connection(credentials, **kwargs)

            shell = ssh_client.invoke_shell()

            output_array = []

            output = read_and_wait(shell, self.SHELL_PROMPT)

            command = f"{display_routing_table}\n"
            Log.debug(f"Executing command: {command.strip()}")
            shell.sendall(command)
            output = read_and_wait(shell, self.SHELL_PROMPT)

            output_array += output.splitlines()

            for re_index in re.findall(r"ReIndex\s*:\s*(\d+)", output):
                Log.debug(f"Get statistics for: {re_index}")
                command = f"{display_statistics.format(vpn_instance=vpn_instance, re_index=re_index)}\n"
                shell.sendall(command)
                output = read_and_wait(shell, self.SHELL_PROMPT)

                output_array += ["\f"]
                output_array += output.splitlines()

            ssh_client.close()

            return output_array
        except Exception as e:
            Log.error(f"Error executing CLI command: {str(e)}")
            return []
