import re
from typing import Optional, Dict, List, Callable
from command_workers.bases import SshCommandWorker
from common.enums import VENDOR


class HuaweiCommandWorker(SshCommandWorker):
    _default_vpn_name = 'LAB-VPN'
    _get_stats_from_router_command_v4 = 'display bgp flow vpnv4 vpn-instance {} routing-table'
    _get_stats_from_router_command_v6 = 'display bgp flow vpnv6 vpn-instance {} routing-table'
    _get_stats_for_sig_v4 = 'display flowspec vpnv4 vpn-instance {} statistics {}'
    _get_stats_for_sig_v6 = 'display flowspec vpnv6 vpn-instance {} statistics {}'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.HUAWEI

    def execute_cli(self, credentials: Dict[str, object], command: str = None,
                    exec_command: Optional[Callable] = None, **kwargs) -> List[str]:
        vpn_name = kwargs.get('vrf', self._default_vpn_name)
        is_ipv6 = kwargs.get('is_ipv6', False)  # Add this parameter to determine IPv4/IPv6

        # Choose the appropriate commands based on IPv4/IPv6
        if is_ipv6:
            main_command = self._get_stats_from_router_command_v6
            stats_command = self._get_stats_for_sig_v6
        else:
            main_command = self._get_stats_from_router_command_v4
            stats_command = self._get_stats_for_sig_v4

        connection = self.generate_connection(credentials, **kwargs)
        try:
            _, stdout, stderr = connection.exec_command(main_command.format(vpn_name))
            result = stdout.readlines()

            for idx in re.findall(r"ReIndex\s*:\s*(\d+)", '\n'.join(result)):
                _, stdout, stderr = connection.exec_command(stats_command.format(vpn_name, idx))
                result.extend(stdout.readlines())

            return [line.rstrip('\r\n') for line in result]
        finally:
            connection.close()