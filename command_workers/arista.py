from common.enums import VENDOR
from command_workers.bases import SshCommandWorker


class AristaCommandWorker(SshCommandWorker):

    _get_stats_from_router_command = 'sh flow-spec ipv4'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.ARISTA
