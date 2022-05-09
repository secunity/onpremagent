import argparse
import inspect
from typing import Optional, Union, Dict

from common.enums import VENDOR
from common.api_secunity import URL_SETTING_DEFAULTS, URL_SETTING_KEY
from common.consts import DEFAULTS, DEFAULT_KEYS


ARGS_DEFAULTS = {
    'title': 'Secunity\'s On-Prem Agent',
    'config_title': 'Config file full file path, overriding all other options',
    'host_title': 'Router IP Address',
    'port_title': 'Router Connect Port',
    'username_title': 'Router Connect User',
    'password_title': 'Router Connect Password',
    'key_filename_title': 'Router Connect Key Filename',
    'command_prefix_title': 'The prefix to wrap commands sent to the Router (for instance "cli" in Juniper)',
    'logfile_path':  "/var/log/secunity",
    'logfile_title': 'Full file path to log to',
    'verbose': True,
    'verbose_title': 'Indicates whether to log verbose data',
    'to_stdout_title': 'Log messages to stdout',
    'to_stdout_value': True,
    'to_stderr_title': 'Log errors to stderr',
    'to_stderr_value': False,
    'dump_title': 'Full file path to dump results',
    'url_title': 'Secunity\'s API URL',
    'url_scheme_title': 'Secunity\'s API URL scheme (http/https)',
    'url_host_title': 'Secunity\'s API URL host',
    'url_port_title': 'Secunity\'s API URL port',
    'url_path_title': 'Secunity\'s API URL path',
    'url_method_title': 'Secunity\'s API HTTP method',
    'url_method': 'POST',
    'comment_flow_prefix_title': 'Prefix in comment for flow Secunity\'s will add',
}


def get_argarse(
        title: Optional[str] = None,
        config: Optional[bool] = True, config_title: Optional[str] = None,
        host: Optional[bool] = True,  host_title: Optional[str] = None,
        port: Optional[bool] = True, port_title: Optional[str] = None,
        username: Optional[bool] = True, username_title: Optional[str] = None,
        password: Optional[bool] = True, password_title: Optional[str] = None,
        key_filename: Optional[bool] = True, key_filename_title: Optional[str] = None,
        command_prefix: Optional[bool] = False, command_prefix_title: Optional[str] = None,
        vendor: Optional[bool] = True, default_vendor: Optional[Union[VENDOR, str]] = None,
        dump: Optional[bool] = False, dump_value: Optional[str] = None, dump_title: Optional[str] = None,
        log: Optional[bool] = True, logfile_path_value: Optional[str] = None, logfile_title: Optional[str] = None,
        verbose_value: Optional[bool] = None, verbose_title: Optional[str] = None,
        to_stdout_value: Optional[bool] = None, to_stdout_title: Optional[str] = None,
        to_stderr_value: Optional[bool] = None, to_stderr_title: Optional[str] = None,
        url: Optional[bool] = False, url_value: Optional[str] = None, url_title: Optional[str] = None,
        url_scheme_value: Optional[str] = None, url_scheme_title: Optional[str] = None,
        url_host_value: Optional[str] = None, url_host_title: Optional[str] = None,
        url_port_value: Optional[int] = None, url_port_title: Optional[str] = None,
        # url_path_value: str = None, url_path_title: str = None,
        url_method_value: Optional[str] = None, url_method_title: Optional[str] = None,
        parse: Optional[bool] = True) -> Dict[str, object]:

    if not title:
        title = ARGS_DEFAULTS['title']
    parser = argparse.ArgumentParser(description=title)

    if config:
        if not config_title:
            config_title = ARGS_DEFAULTS['config_title']
        parser.add_argument('-c', '--config', type=str, help=config_title, default=DEFAULTS[DEFAULT_KEYS.CONFIG])

    parser.add_argument('--identifier', '--id', type=str, help='Device ID', default=None)

    if vendor:
        if not default_vendor:
            default_vendor = VENDOR.DEFAULT_VENDOR
        parser.add_argument('-n', '--vendor', type=str, default=default_vendor, help='The Vendor of the Router')

    if host:
        if not host_title:
            host_title = ARGS_DEFAULTS['host_title']
        parser.add_argument('-s', '--host', '--ip', type=str, help='Router IP', default=host_title)
    if port:
        if not port_title:
            port_title = ARGS_DEFAULTS['port_title']
        parser.add_argument('-p', '--port', type=int, default=None, help=port_title)

    if username:
        if not username_title:
            username_title = ARGS_DEFAULTS['username_title']
        parser.add_argument('-u', '--user', '--username', type=str, default=None, help=username_title)
    if password:
        if not password_title:
            password_title = ARGS_DEFAULTS['password_title']
        parser.add_argument('-w', '--password', type=str, default=None, help=password_title)
    if key_filename:
        if not key_filename_title:
            key_filename_title = ARGS_DEFAULTS['key_filename_title']
        parser.add_argument('-k', '--key_filename', type=str, default=None, help=key_filename_title)

    if command_prefix:
        if not command_prefix_title:
            command_prefix_title = ARGS_DEFAULTS['command_prefix_title']
        parser.add_argument('--command_prefix', type=str, default=None, help=command_prefix_title)

    if log:
        if not logfile_title:
            logfile_title = ARGS_DEFAULTS['logfile_title']
        if logfile_path_value is None:
            logfile_path_value = ARGS_DEFAULTS['logfile_path']
        parser.add_argument('-lp', '--logfile_path', type=str, help=logfile_title, default=logfile_path_value)

        if not verbose_title:
            verbose_title = ARGS_DEFAULTS['verbose_title']
        if verbose_value not in (True, False):
            verbose_value = ARGS_DEFAULTS['verbose']
        parser.add_argument('-v', '--verbose', type=bool, help=verbose_title, default=verbose_value)

        if not to_stdout_title:
            to_stdout_title = ARGS_DEFAULTS['to_stdout_title']
        if to_stdout_value not in (True, False):
            to_stdout_value = ARGS_DEFAULTS['to_stdout_value']
        parser.add_argument('--to_stdout', '--stdout', type=str, help=to_stdout_title, default=to_stdout_value)

        if not to_stderr_title:
            to_stderr_title = ARGS_DEFAULTS['to_stderr_title']
        if to_stderr_value not in (True, False):
            to_stderr_value = ARGS_DEFAULTS['to_stderr_value']
        parser.add_argument('--to_stderr', '--stderr', type=str, help=to_stderr_title, default=to_stderr_value)

    if dump:
        if not dump_title:
            dump_title = ARGS_DEFAULTS['dump_title']
        parser.add_argument('-d', '--dump', type=str, help=dump_title, default=dump_value)

    if url:
        if not url_title:
            url_title = ARGS_DEFAULTS['url_title']
        parser.add_argument('--url', type=str, help=url_title, default=url_value)

        if not url_scheme_title:
            url_scheme_value = ARGS_DEFAULTS['url_scheme_title']
        if not url_scheme_value:
            url_scheme_value = URL_SETTING_DEFAULTS[URL_SETTING_KEY.SCHEME]
        parser.add_argument(f'--{URL_SETTING_KEY.SCHEME}', type=str, help=url_scheme_title, default=url_scheme_value)

        if not url_host_title:
            url_host_title = ARGS_DEFAULTS['url_host_title']
        if not url_host_value:
            url_host_value = URL_SETTING_DEFAULTS[URL_SETTING_KEY.HOST]
        parser.add_argument(f'--{URL_SETTING_KEY.HOST}', type=str, help=url_host_title, default=url_host_value)

        if not url_port_title:
            url_port_title = ARGS_DEFAULTS['url_port_title']
        if not url_port_value:
            url_port_value = URL_SETTING_DEFAULTS[URL_SETTING_KEY.PORT]
        parser.add_argument(f'--{URL_SETTING_KEY.PORT}', type=int, help=url_port_title, default=url_port_value)

        # if not url_path_title:
        #     url_path_title = ARGS_DEFAULTS['url_path_title']
        # if not url_path_value:
        #     url_path_value = URL_SETTING_DEFAULTS[URL_SETTING_KEY.PATH]
        # parser.add_argument(f'--{URL_SETTING_KEY.PATH}', type=str, help=url_path_title, default=url_path_value)

        if not url_method_title:
            url_method_title = ARGS_DEFAULTS['url_method']
        if not url_method_value:
            url_method_value = URL_SETTING_DEFAULTS[URL_SETTING_KEY.METHOD]
        parser.add_argument(f'--{URL_SETTING_KEY.METHOD}', type=str, help=url_method_title, default=url_method_value)

    if not parse:
        return argparse

    args = parser.parse_args()
    args = vars(args)
    return args


EMPTY_ARGPARSE_PARAMS = {
    _: None for _ in list(dict(inspect.signature(get_argarse).parameters).keys())
}
