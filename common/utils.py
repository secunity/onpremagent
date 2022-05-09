import decimal
import re
import datetime
import ipaddress
import os.path
import uuid
from json import JSONEncoder
from typing import Optional, Any, Union, List, Iterable, Dict
from decimal import Decimal
from bson.objectid import ObjectId

from common.consts import BOOL_VALUES, DEFAULTS, DEFAULT_KEYS, PROGRAM

_cnf = {'__log_init__': False}


class classproperty:

    def __init__(self, getter):
        self.getter = getter

    def __get__(self, instance, owner):
        return self.getter(owner)


def get_float(item: Any,
              exception: Optional[bool] = True) -> Optional[float]:
    if isinstance(item, float):
        return item
    try:
        if isinstance(item, (int, Decimal)):
            return float(item)
        return float(str(item))
    except Exception as ex:
        if exception:
            raise ex
        return None


def to_ObjectId(o: Union[ObjectId, str, bytes] = None,
                *args) -> ObjectId:
    if not o and args:
        o = args[0]
    if o is None:
        raise ValueError('no input was specified')
    return o if isinstance(o, ObjectId) else \
        ObjectId(o.decode('utf-8') if isinstance(o, bytes) else o)


def is_ObjectId(o: Union[ObjectId, str, bytes],
                *args) -> bool:
    if not o and args:
        o = args[0]
    try:
        o = to_ObjectId(o)
        return True
    except:
        return False


def is_ipv4(ip: Any):
    return get_ipv4(ip) is not None


def get_ipv4(ip: Any) -> Optional[str]:
    try:
        return ipaddress.IPv4Address(ip)
    except:
        pass
    try:
        net = ipaddress.IPv4Network(ip)
        return str(min(net))
    except:
        return None


def get_int(i: Any) -> Optional[int]:
    if i is None or isinstance(i, int):
        return i
    if isinstance(i, (float, decimal.Decimal)):
        return int(i)
    elif not isinstance(i, str):
        try:
            return int(i)
        except:
            pass
        i = str(i)
    try:
        return int(i)
    except:
        return False


class ERROR:
    CONERROR = 'conerror'
    INVALID_CON_PARAMS = 'invalid-con-params'
    UNSUPPORTED_VENBDOR = 'unsupported-vendor'
    FORMATTING = 'formatting'

    __ALL__ = (CONERROR, INVALID_CON_PARAMS, UNSUPPORTED_VENBDOR, FORMATTING)

    @classmethod
    def has(cls, value):
        return value in cls.__ALL__


def parse_bool(x: Any,
               parse_str: Optional[bool] = None,
               *args):
    if x is None:
        return None
    elif x in BOOL_VALUES:
        return x
    if not is_bool(parse_str):
        parse_str = args[0] if args and is_bool(args[0]) else False

    if parse_str and isinstance(x, str):
        x = x.strip(' \r\n\t')
        if x.lower() == 'true':
            return True
        elif x.lower() == 'false':
            return False

    error = f'invalid bool: "{x}"'
    raise ValueError(error)


def is_bool(o: Optional[bool] = None,
            *args) -> bool:
    if o is None and args:
        o = args[0]
    return o in BOOL_VALUES


def parse_ip(ip, throw=False):
    try:
        ip = ipaddress.IPv4Address(ip)
        return str(ip)
    except Exception as ex:
        if throw:
            raise ex
        return None


def parse_identifier(identifier: Optional[Union[ObjectId, str, bytes]] = None,
                     as_ObjectId: Optional[bool] = False,
                     **kwargs) -> Optional[Union[ObjectId, str]]:
    if not identifier:
        identifier = next((kwargs.pop(_) for _ in ('device_identifier', 'device',)
                           if isinstance(kwargs.get(_), str) and kwargs[_]), None)
        if not identifier:
            return None
    try:
        identifier_oid = to_ObjectId(identifier)
    except:
        return None
    return identifier_oid if as_ObjectId else identifier


STRFTIME = '%Y-%m-%d %H:%M:%S'


def strftime(dt: datetime.datetime) -> str:
    return dt.strftime(STRFTIME)


def strptime(dt: str) -> datetime.datetime:
    return datetime.datetime.strptime(dt)


def get_supervisor_content() -> List[str]:
    supervisor_path = get_supervisor_path()
    if not os.path.isfile(supervisor_path):
        raise ValueError(f'invalid supervisor conf file path: "{supervisor_path}"')

    with open(supervisor_path, 'r') as f:
        content = f.read()

    return [_.strip('\r') for _ in content.split('\n')]


_supervisor_regexes = {
    'program': re.compile(r'^\s*\[\s*program\s*:\s*([^\]]+)\s*\]\s*$'),
    'autostart': re.compile(r'^\s*autostart\s*=\s*(false|true)\s*$'),
}


def get_supervisor_programs_autostart() -> Dict[Union[PROGRAM, str], bool]:
    content = get_supervisor_content()

    result = {}
    cur_program = None
    for i, line in enumerate(content):
        stripped_line = line.strip(' \r\n\t')
        if not stripped_line:
            continue
        match = _supervisor_regexes['program'].match(stripped_line)
        if match:
            cur_program = match.groups()[0]
            # result[cur_program] = []
        else:
            match = _supervisor_regexes['autostart'].match(stripped_line)
            if match:
                result[cur_program] = parse_bool(match.groups()[0], parse_str=True)

    return result


def update_supervisor_program_autostart(program: str,
                                        autostart: bool):
    content = get_supervisor_content()

    cur_program = None
    found = False
    for i, line in enumerate(content):
        stripped_line = line.strip(' \r\n\t')
        match = _supervisor_regexes['program'].match(stripped_line)
        if match:
            cur_program = match.groups()[0]
        elif cur_program == program:
            match = _supervisor_regexes['autostart'].match(stripped_line)
            if match:
                content[i] = f'autostart={str(autostart).lower()}'
                found = True
                break

    if not found:
        raise ValueError(f'program "{program}" was not found in supervisor conf')

    content = '\n'.join(content)
    supervisor_path = get_supervisor_path()
    with open(supervisor_path, 'w') as f:
        f.write(content)


def get_supervisor_path() -> str:
    return DEFAULTS[DEFAULT_KEYS.SUPERVISOR_PATH]


def remove_unserializable_types(obj: Any,
                                self: Optional[JSONEncoder] = None) -> Any:
    if obj is None:
        return obj
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, decimal.Decimal):
        return float(obj)
    elif isinstance(obj, (ObjectId, uuid.UUID)):
        return str(obj)
    elif isinstance(obj, bytes):
        return obj.decode('utf-8')
    elif isinstance(obj, dict):
        return {
            remove_unserializable_types(k, self=self): remove_unserializable_types(v, self=self)
            for k, v in obj.items()
        }
    elif isinstance(obj, (list, tuple, set)):
        return [remove_unserializable_types(_, self=self) for _ in obj]
    elif self:
        return JSONEncoder.default(self, obj)
    else:
        return obj


if __name__ == '__main__':
    print(get_supervisor_programs_autostart())

    update_supervisor_program_autostart(program='worker_sync_flows',
                                        autostart=False)
