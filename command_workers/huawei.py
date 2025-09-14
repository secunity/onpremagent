import re
from typing import Optional, Dict, List, Callable

from command_workers.bases import SshCommandWorker
from common.enums import VENDOR


class HuaweiCommandWorker(SshCommandWorker):
    _default_vpn_name = 'LAB-VPN'
    _get_stats_from_router_command = 'display bgp flow vpnv4 vpn-instance {} routing-table'
    _get_stats_for_sig = 'display flowspec vpnv4 vpn-instance {} statistics {}'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.HUAWEI

    def _prepare_stats_command(self, interface_name=None, ip_type='IPv4'):
        # For Huawei, we need different commands for IPv4 vs IPv6
        if ip_type == 'IPv6':
            self._get_stats_from_router_command = 'display bgp flow vpnv6 vpn-instance {} routing-table'
            self._get_stats_for_sig = 'display flowspec vpnv6 vpn-instance {} statistics {}'
        else:
            self._get_stats_from_router_command = 'display bgp flow vpnv4 vpn-instance {} routing-table'
            self._get_stats_for_sig = 'display flowspec vpnv4 vpn-instance {} statistics {}'

        return self._get_stats_from_router_command

    def execute_cli(self,
                    credentials: Dict[str, object],
                    command: str = None,
                    exec_command: Optional[Callable] = None,
                    **kwargs) -> List[str]:
        vpn_name = kwargs.get('vrf', self._default_vpn_name)

        connection = self.generate_connection(credentials, **kwargs)
        try:
            # Format the command with the VRF name
            formatted_command = self._get_stats_from_router_command.format(vpn_name)
            _, stdout, stderr = connection.exec_command(formatted_command)
            result = stdout.readlines()

            # Extract ReIndex values and get statistics for each
            for idx in re.findall(r"ReIndex\s*:\s*(\d+)", '\n'.join(result)):
                # Format the stats command with VRF name and index
                stats_command = self._get_stats_for_sig.format(vpn_name, idx)
                _, stdout, stderr = connection.exec_command(stats_command)
                result.extend(stdout.readlines())

            return [line.rstrip('\r\n') for line in result]
        finally:
            connection.close()