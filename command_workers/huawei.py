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
        # Override the parent method to handle both IPv4 and IPv6 properly
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

        # Determine IP type from kwargs or default to IPv4
        ip_type = kwargs.get('ip_type', 'IPv4')
        self._prepare_stats_command(ip_type=ip_type)

        connection = self.generate_connection(credentials, **kwargs)
        try:
            # Use the prepared command with the correct IP version
            main_command = self._get_stats_from_router_command.format(vpn_name)
            _, stdout, stderr = connection.exec_command(main_command)
            result = stdout.readlines()

            # Extract ReIndex values and get statistics for each
            for idx in re.findall(r"ReIndex\s*:\s*(\d+)", '\n'.join(result)):
                stats_command = self._get_stats_for_sig.format(vpn_name, idx)
                _, stdout, stderr = connection.exec_command(stats_command)
                result.extend(stdout.readlines())

            return [line.rstrip('\r\n') for line in result]
        finally:
            connection.close()

    def get_flows_from_router(self,
                              credentials: Optional[Dict[str, object]] = None,
                              **kwargs) -> List[str]:
        # Override to ensure proper IP type handling
        if not credentials:
            credentials = self.credentials.copy() if hasattr(self, 'credentials') else {}

        # Ensure IP type is passed correctly
        ip_type = kwargs.get('ip_type', 'IPv4')
        self._prepare_stats_command(ip_type=ip_type)

        if self._get_stats_from_router_command:
            self.logger.debug(f'SSH command: "{self._get_stats_from_router_command}"')
            result = self.execute_cli(
                command=self._get_stats_from_router_command,
                credentials=credentials,
                **kwargs
            )
            return result

        raise NotImplementedError()