import re
from typing import Optional, Dict, List, Callable

from command_workers.bases import SshCommandWorker
from common.enums import VENDOR


class HuaweiCommandWorker(SshCommandWorker):
    _default_vpn_name = 'LAB-VPN'

    _get_stats_from_router_command = 'display bgp flow vpnv4 vpn-instance {} routing-table | no-more'
    _get_stats_for_sig = 'display flowspec vpnv4 vpn-instance {} statistics {} | no-more'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.HUAWEI

    def execute_cli(self,
                    credentials: Dict[str, object],
                    command: str = None,
                    exec_command: Optional[Callable] = None,
                    **kwargs) -> List[str]:
        vpn_name = kwargs.get('vrf', self._default_vpn_name)

        connection = self.generate_connection(credentials, **kwargs)
        try:
            _, stdout, stderr = connection.exec_command(self._get_stats_from_router_command.format(vpn_name))
            result = stdout.readlines()

            for idx in re.findall(r"ReIndex\s*:\s*(\d+)", '\n'.join(result)):
                try:
                    connection.close()
                    connection = self.generate_connection(credentials, **kwargs)

                    _, stdout, stderr = connection.exec_command(self._get_stats_for_sig.format(vpn_name, idx))
                    result += stdout.readlines()
                except Exception as er:
                    print(f"error idx {idx}: {er}")

            output = [line.rstrip('\r\n') for line in result]

            return output
        finally:
            connection.close()
