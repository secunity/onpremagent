from typing import Union

from command_workers.bases import TCommandWorker
from common.enums import VENDOR
from common.logs import Log


__command_worker_by_vendor__ = {
    _: '' for _ in VENDOR.ALL
}


def get_command_worker_class(vendor: Union[VENDOR, str]) -> TCommandWorker:
    vendor = VENDOR.parse(vendor)
    cls = __command_worker_by_vendor__.get(vendor)
    if cls is None:
        Log.error_raise(f'unsupported vendor: "{vendor}"')
    if not cls:
        if vendor == VENDOR.CISCO:
            from command_workers.cisco import CiscoCommandWorker
            cls = CiscoCommandWorker
        elif vendor == VENDOR.JUNIPER:
            from command_workers.juniper import JuniperCommandWorker
            cls = JuniperCommandWorker
        elif vendor == VENDOR.HUAWEI:
            from command_workers.huawei import HuaweiCommandWorker
            cls = HuaweiCommandWorker
        elif vendor == VENDOR.ARISTA:
            from command_workers.arista import AristaCommandWorker
            cls = AristaCommandWorker
        elif vendor == VENDOR.MIKROTIK:
            from command_workers.mikrotik import MikrotikCommandWorker
            cls = MikrotikCommandWorker
        __command_worker_by_vendor__[vendor] = cls
    return cls


def init_command_worker(vendor: Union[VENDOR, str],
                        *args, **kwargs) -> TCommandWorker:
    command_worker_cls = get_command_worker_class(vendor=vendor)
    if not args:
        args = tuple()
    if not kwargs:
        kwargs = dict()
    return command_worker_cls(*args, **kwargs)
