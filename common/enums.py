from typing import Union


class VENDOR:
    CISCO = 'cisco'
    JUNIPER = 'juniper'
    ARISTA = 'arista'
    MIKROTIK = 'mikrotik'

    DEFAULT_VENDOR = CISCO

    __mapping__ = {
        'CISCO': CISCO,
        'JUNIPER': JUNIPER,
        'ARISTA': ARISTA,
        'MIKROTIK': MIKROTIK,
    }

    @classmethod
    def parse(cls, vendor: Union['VENDOR', str]):
        if not vendor:
            raise ValueError(f'invalid vendor: "{vendor}"')
        vendor_lower = vendor.lower()
        result = next((_ for _ in cls.__mapping__.values() if _.lower() == vendor_lower), None) or \
            next((_ for _ in cls.__mapping__.keys() if _.lower() == vendor_lower), None)
        if not result:
            raise ValueError(f'invalid vendor: "{str(vendor)}"')
        return result

    ALL = (CISCO, JUNIPER, ARISTA, MIKROTIK)


class ACTION_FLOW_STATUS:
    APPLIED = 'applied'
    REMOVED = 'removed'


class ERROR:
    CONNECTION_ERROR = 'connection_error'
    INVALID_CONNECTION_PARAMS = 'invalid_connection_params'
    UNSUPPORTED_VENDOR = 'unsupported_vendor'
    FORMATTING = 'formatting'

    __ALL__ = (CONNECTION_ERROR, INVALID_CONNECTION_PARAMS, UNSUPPORTED_VENDOR, FORMATTING)

    @classmethod
    def has(cls, value):
        return value in cls.__ALL__


class FLOW_TYPE:
    APPLY = 'apply'
    REMOVE = 'remove'
    APPLY_REMOVE = 'apply_remove'

    APPLIED = 'applied'

    ALL = (APPLY, REMOVE, APPLY_REMOVE, APPLIED)
