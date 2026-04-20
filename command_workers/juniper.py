import re

from common.enums import VENDOR
from command_workers.bases import SshCommandWorker


class JuniperCommandWorker(SshCommandWorker):
    __DEFAULT_INTERFACE_NAME__ = 'default'
    _get_stats_from_router_command = 'show firewall filter detail __flowspec_<INTERFACE_NAME>_inet__'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.JUNIPER

    def _prepare_stats_command(self, interface_name=None, ip_type='IPv4', model=None):
        if not interface_name:
            interface_name = self.__DEFAULT_INTERFACE_NAME__
        if model and model.lower().startswith('acx'):
            self._get_stats_from_router_command = 'show firewall application routing'
        self._get_stats_from_router_command = self._get_stats_from_router_command.replace(
            "<INTERFACE_NAME>", interface_name)
        if ip_type == 'IPv6':
            self._get_stats_from_router_command = self._get_stats_from_router_command.replace(
                "inet", "inet6")
        return self._get_stats_from_router_command

    def _filter_result(self, result, interface_name=None, ip_type='IPv4', model=None):
        result = "\n".join(result)

        filter_fmt = "__flowspec_{interface_name}_{ip_type}__"
        if ip_type == 'IPv6':
            ip_type = 'inet6'
        else:
            ip_type = 'inet'
        if interface_name is None:
            interface_name = self.__DEFAULT_INTERFACE_NAME__
        expected_filter_name = filter_fmt.format(interface_name=interface_name, ip_type=ip_type)

        filters = re.findall(r"Filter:\s+(?P<filter_name>\S+)(?P<data>.+?)(?=Filter:|\Z)", result, re.DOTALL | re.MULTILINE)
        for filter_name, data in filters:
            if filter_name == expected_filter_name:
                return [f"Filter: {filter_name}"] + data.splitlines()

        return []
