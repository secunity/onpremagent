from common.enums import VENDOR
from command_workers.bases import SshCommandWorker


class JuniperCommandWorker(SshCommandWorker):
    __DEFAULT_INTERFACE_NAME__ = 'default'
    _get_stats_from_router_command = 'show firewall filter detail __flowspec_<INTERFACE_NAME>_inet__'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.JUNIPER

    def _prepare_stats_command(self, interface_name=None, ip_type='IPv4'):
        if not interface_name:
            interface_name = self.__DEFAULT_INTERFACE_NAME__
        self._get_stats_from_router_command = self._get_stats_from_router_command.replace(
            "<INTERFACE_NAME>", interface_name)
        if ip_type == 'IPv6':
            self._get_stats_from_router_command = self._get_stats_from_router_command.replace(
                "inet", "inet6")
        return self._get_stats_from_router_command
