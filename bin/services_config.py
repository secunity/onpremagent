#!/usr/bin/env python3
import copy
import datetime
import os.path
from typing import Dict, Any, Type

from common.arg_parse import EMPTY_ARGPARSE_PARAMS
from common.configs import load_env_settings, parse_config_file
from common.consts import DEFAULTS, DEFAULT_KEYS, PROGRAM
from common.enums import VENDOR
from common.utils import update_supervisor_program_autostart


def get_Log() -> Type:
    from common.logs import Log as _Log
    return _Log


def _write_tmp_err(err):
    now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    error = [f'{now} - error during Secunity init - no process will start']
    if err:
        error.append(err)
    error = '\n'.join(error)
    paths = ['/var/log/secunity', '/tmp']
    error_log_name = 'secunity-init-error.log'
    for path in paths:
        filename = os.path.join(path, error_log_name)
        try:
            with open(filename, 'a') as f:
                f.write(error)
            return
        except Exception as ex:
            pass

    print('failed to write error to all file')


def _parse_args() -> Dict[str, Any]:
    args = copy.deepcopy(EMPTY_ARGPARSE_PARAMS)
    env = load_env_settings()
    args.update(env)
    config = args.get('config')
    if config and os.path.isfile(config):
        try:
            cnf = parse_config_file(config)
        except Exception as ex:
            error = f'failed to parse config file "{config}" - ex: "{str(ex)}"'
            Log = get_Log()
            Log.exception(error)
            Log.logger().exception(error)
            _write_tmp_err(error)
            raise ex
        args.update(cnf)
    else:
        config = DEFAULTS[DEFAULT_KEYS.CONFIG]
        if config and os.path.isfile(config):
            try:
                cnf = parse_config_file(config)
            except Exception as ex:
                error = f'failed to parse config file "{config}" - ex: "{str(ex)}"'
                Log = get_Log()
                Log.exception(error)
                Log.logger().exception(error)
                _write_tmp_err(error)
                raise ex
            args.update(cnf)

    return args


def main():
    args = _parse_args()
    vendor, identifier = args.get('vendor'), args.get('identifier')
    if not vendor:
        error = 'Vendor was not specified'
        print(error)
        raise ValueError(error)

    vendor = VENDOR.parse(vendor) if vendor else VENDOR.DEFAULT_VENDOR
    if not vendor:
        error = f'Invalid vendor: "{vendor}"'
        print(error)
        raise ValueError(error)

    programs = [PROGRAM.STATS_FETCHER]
    if vendor in (VENDOR.MIKROTIK,):
        programs += [PROGRAM.FLOWS_SYNC, PROGRAM.FLOWS_APPLIER, PROGRAM.DEVICE_CONTROLLER]

    for program in PROGRAM.ALL:
        autostart = program in programs
        update_supervisor_program_autostart(program=program, autostart=autostart)


# def reload_supervisor():
    # cmd = 'supervisorctl '
    # check_output()


if __name__ == '__main__':
    main()
