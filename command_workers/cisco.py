from common.enums import VENDOR
from command_workers.bases import SshCommandWorker


class CiscoCommandWorker(SshCommandWorker):

    _get_stats_from_router_command = 'show flowspec vrf all ipv4 detail'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.CISCO
