from common.enums import VENDOR
from command_workers.bases import SshCommandWorker


class JuniperCommandWorker(SshCommandWorker):

    _get_stats_from_router_command = 'show firewall filter detail __flowspec_default_inet__'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.JUNIPER
