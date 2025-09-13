import re
from typing import Optional, Dict, List, Callable

from command_workers.bases import SshCommandWorker
from common.enums import VENDOR


class HuaweiCommandWorker(SshCommandWorker):

    _vpn_name = 'LAB-VPN'

    _get_stats_from_router_command = 'display bgp flow vpnv4 vpn-instance {} routing-table'
    _get_stats_for_sig = 'display flowspec vpnv4 vpn-instance LAB-VPN statistics {}'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.HUAWEI

    def execute_cli(self,
                    credentials: Dict[str, object],
                    command: str = None,
                    exec_command: Optional[Callable] = None,
                    **kwargs) -> List[str]:
        connection = self.generate_connection(credentials, **kwargs)
        try:
            _, stdout, stderr = connection.exec_command(self._get_stats_from_router_command.format(self._vpn_name))
            result = stdout.readlines()

            for idx in re.findall(r"ReIndex\s*:\s*(\d+)", '\n'.join(result)):
                _, stdout, stderr = connection.exec_command(self._get_stats_for_sig.format(idx))
                result.extend(stdout.readlines())

            return [line.rstrip('\r\n') for line in result]
        finally:
            connection.close()