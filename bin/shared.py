import os
from typing import Tuple, Dict, Any, Union

from common.arg_parse import get_argarse
from common.configs import load_env_settings, parse_config_file
from common.enums import VENDOR


def parse_config_vendor() -> Tuple[Dict[str, Any], Union[VENDOR, str]]:
    args = get_argarse(vendor=True)
    env = load_env_settings()
    configs = [_ for _ in (env.get('config'), args.get('config')) if _]
    conf = next((_ for _ in configs if os.path.isfile(_)), None)
    if not conf:
        from common.logs import Log
        Log.error_raise(f'cannot find config file: "{configs}"')
    try:
        conf = parse_config_file(conf)
    except Exception as ex:
        from common.logs import Log
        Log.exception_raise(f'failed to parse config: "{str(ex)}"')
    vendor = conf.get('vendor')
    if not vendor:
        vendor = VENDOR.DEFAULT_VENDOR
    try:
        vendor = VENDOR.parse(vendor)
        if vendor not in VENDOR.ALL:
            from common.logs import Log
            Log.error_raise(f'invalid vendor: "{str(vendor)}"')
    except:
        from common.logs import Log
        Log.exception_raise(f'invalid vendor: "{str(vendor)}"')

    return conf, vendor
