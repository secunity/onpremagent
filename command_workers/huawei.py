import re

from command_workers.bases import SshCommandWorker
from common.enums import VENDOR
from common.logs import Log
from common.sshutils import read_and_wait


class HuaweiCommandWorker(SshCommandWorker):
    _get_stats_from_router_command = "display bgp"

    SHELL_PROMPT = re.compile(r"<.*?>")

    DISPLAY_ROUTING_TABLE = "display bgp flow vpnv4 vpn-instance {vpn_instance} routing-table | no-more"
    DISPLAY_STATISTICS = "display flowspec vpnv4 vpn-instance {vpn_instance} statistics {re_index} | no-more"

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.HUAWEI

    def execute_cli(self, credentials, command = None, exec_command = None, **kwargs):
        stats_type = kwargs.get("stats_type")
        if stats_type == "IPv6":
            Log.info("No IPv6 support")
            return []

        try:
            vpn_instance = kwargs.get("vrf")

            ssh_client = self.generate_connection(credentials, **kwargs)

            shell = ssh_client.invoke_shell()

            output_array = []

            output = read_and_wait(shell, self.SHELL_PROMPT)

            command = f"{self.DISPLAY_ROUTING_TABLE.format(vpn_instance=vpn_instance)}\n"
            Log.debug(f"Executing command: {command.strip()}")
            shell.sendall(command)
            output = read_and_wait(shell, self.SHELL_PROMPT)

            output_array += output.splitlines()

            for re_index in re.findall(r"ReIndex\s*:\s*(\d+)", output):
                Log.debug(f"Get statistics for: {re_index}")
                command = f"{self.DISPLAY_STATISTICS.format(vpn_instance=vpn_instance, re_index=re_index)}\n"
                shell.sendall(command)
                output = read_and_wait(shell, self.SHELL_PROMPT)

                output_array += ["\f"]
                output_array += output.splitlines()

            ssh_client.close()

            return output_array
        except Exception as e:
            Log.error(f"Error executing CLI command: {str(e)}")
            return []
