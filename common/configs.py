import copy
import os
import re
from typing import Optional, Union, Dict, Any

from common.logs import Log

try:
    import jstyleson as json
except:
    import json

from common.consts import BOOL_VALUES
from common.enums import VENDOR
from common.utils import parse_ip

_cnf = {}

__CLONE_CONFIG_REQUEST__ = True


def _parse_clone(clone: bool = None):
    if clone is None:
        clone = __CLONE_CONFIG_REQUEST__
    elif clone not in BOOL_VALUES:
        raise ValueError('clone must be of type bool')
    return clone


def set_conf(config: Dict,
             replace: Optional[bool] = None,
             clone: Optional[bool] = None
             ) -> Dict:
    clone = _parse_clone(clone)

    if replace is None:
        replace = False
    elif replace not in BOOL_VALUES:
        raise ValueError('replace is not of type bool')

    if not config:
        raise ValueError('config was not set')
    elif isinstance(config, str):
        config = parse_config_file(config=config, )

    global _cnf
    if replace:
        _cnf = copy.deepcopy(config)
    else:
        _cnf.update(config)

    return copy.deepcopy(_cnf) if clone else _cnf


def cnf_get(key: str,
            default: Optional[Any] = None,
            clone: Optional[bool] = None) -> Any:
    clone = _parse_clone(clone)

    value = _cnf.get(key, default=default)
    return copy.deepcopy(value) if clone else value


def cnf_get_regex(regex: Union[str, Any],
                  config: Optional[Dict[str, Any]] = None,
                  clone: Optional[bool] = None) -> Dict[str, Any]:
    clone = _parse_clone(clone)
    if not config:
        config = _cnf
    if isinstance(regex, str):
        regex = re.compile(regex)
    value = {k: v for k, v in config.items() if regex.match(k)}
    return copy.deepcopy(value) if clone else value


def get_url_params(config: Optional[Dict[str, Any]] = None):
    return cnf_get_regex(regex=r'^url_[a-z0-9_]+', config=config)


def load_env_settings(args: Optional[dict] = None) -> Dict[str, Any]:
    return {}

    if not isinstance(args, dict):
        args = {}
    update = {
        _: os.environ.get(f'{ENV_PREFIX}{_.upper()}')
        for _ in CONFIG_KEYS
        if args.get(_) is None and os.environ.get(f'{ENV_PREFIX}{_.upper()}') is not None
    }
    if update:
        args.update(update)
    return args


def parse_config_file(config: str,  # full file path
                      remove_empty: Optional[bool] = True,
                      **kwargs) -> Dict[str, Any]:
    if not os.path.isfile(config):
        error = f'missing config file: {config}'
        Log.error(error)
        raise ValueError(error)

    match = re.match(r'(.*/project)/[^/]*\.conf', config)
    if match:
        filename = match.groups()[0]
        if not os.path.isfile(filename):
            from common.consts import DEFAULTS, DEFAULT_KEYS
            config = DEFAULTS[DEFAULT_KEYS.CONFIG]
    try:
        with open(config, 'r') as f:
            cnf = json.load(f)
    except Exception as ex:
        Log.exception(f'config file ({config}) is not valid: "{str(ex)}"')
        raise ex

    if remove_empty:
        cnf = {k: v for k, v in cnf.items() if v is not None}
    return cnf


_type_parse_methods = {
    'ip': None,
    'bool': None,
}


def parse_bool(*args, **kwargs):
    if not _type_parse_methods['bool']:
        from common.utils import parse_bool
        _type_parse_methods['bool'] = parse_bool
    return _type_parse_methods['bool'](*args, **kwargs)


_config_types_mutation = {
    str: lambda x: x.strip(' \r\n\t') if isinstance(x, str) else str(x),
    int: lambda x: x if isinstance(x, int) else int(x.strip(' \r\n\t') if isinstance(x, str) else x),
    'bool_str': lambda x: parse_bool(x, parse_str=True),
    bool: parse_bool,
    'vendor': VENDOR.parse,
    'ip': parse_ip,
}


def update_config_types(config: dict,
                        clone: bool = None) -> dict:
    clone = _parse_clone(clone)

    for key, _type in CONFIG_KEYS.items():
        value = config.get(key)
        if value is not None:
            mutation = _config_types_mutation.get(_type)
            if mutation:
                config[key] = mutation(value)

    return copy.deepcopy(config) if clone else config


ENV_PREFIX = 'SECUNITY_'


class CONFIG_KEY:
    CONFIG = 'config'
    LOGFILE = 'logfile'
    LOG = 'log'
    VERBOSE = 'verbose'
    DUMP = 'dump'
    TO_STDERR = 'to_stderr'
    TO_STDOUT = 'to_stdout'

    IDENTIFIER = 'identifier'
    HOST = 'host'
    PORT = 'port'
    VENDOR = 'vendor'
    USERNAME = 'username'
    PASSWORD = 'password'
    COMMAND_PREFIX = 'command_prefix'

    URL_SCHEME = 'url_scheme'
    URL_HOST = 'url_host'
    URL_PORT = 'url_port'
    URL_PATH = 'url_path'
    URL_METHOD = 'url_method'

    SSH_CONFIG_KEYS = (HOST, PORT, USERNAME, PASSWORD)


CONFIG_KEYS = {
    CONFIG_KEY.CONFIG: str,
    # CONFIG_KEY.LOGFILE: str,
    CONFIG_KEY.LOG: 'bool_str',
    CONFIG_KEY.VERBOSE: 'bool_str',
    CONFIG_KEY.DUMP: str,
    CONFIG_KEY.TO_STDERR: 'bool_str',
    CONFIG_KEY.TO_STDOUT: 'bool_str',

    CONFIG_KEY.IDENTIFIER: str,

    CONFIG_KEY.HOST: 'ip',
    CONFIG_KEY.PORT: int,
    CONFIG_KEY.VENDOR: str,
    CONFIG_KEY.USERNAME: str,
    CONFIG_KEY.PASSWORD: str,
    CONFIG_KEY.COMMAND_PREFIX: str,

    CONFIG_KEY.URL_SCHEME: str,
    CONFIG_KEY.URL_HOST: str,
    CONFIG_KEY.URL_PORT: int,
    CONFIG_KEY.URL_PATH: str,
    CONFIG_KEY.URL_METHOD: str,
}


# def get_ssh_credentials(config: Dict[Union[CONFIG_KEYS, str], Any]) -> Dict[Union[CONFIG_KEYS, str], Any]:
#     result = {
#         k: v for k, v in config.items()
#         if k in CONFIG_KEY.SSH_CONFIG_KEYS
#         and v is not None
#     }
#     return result
