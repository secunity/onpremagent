import copy
import time
from abc import ABC, abstractmethod
from typing import Optional, Union, Dict, Protocol, List, Callable, TypeVar
import paramiko

from common.enums import VENDOR
from common.logs import Log
from common.sshutils import SSH_DEFAULTS

TCredentials = TypeVar('TCredentials', bound=Optional[Dict[str, Union[str, int, float, bool]]])


class ICommandWorker(Protocol):

    def parse_credentials(self,
                          credentials: Optional[TCredentials] = None,
                          **kwargs) -> Optional[TCredentials]:
        raise NotImplementedError()

    def get_flows_from_router(self,
                              credentials: Optional[TCredentials] = None,
                              **kwargs) -> List[str]:
        raise NotImplementedError()

    @property
    def vendor(self) -> VENDOR:
        raise NotImplementedError()

    @property
    def credentials(self) -> Optional[TCredentials]:
        raise NotImplementedError()

    @credentials.setter
    def credentials(self,
                    value: Optional[TCredentials]):
        raise NotImplementedError()


class CommandWorker(ABC, ICommandWorker):

    def __init__(self,
                 credentials: Optional[TCredentials] = None, **kwargs):
        self._credentials = self.parse_credentials(credentials, **kwargs) if credentials else {}

    @abstractmethod
    def parse_credentials(self,
                          credentials: Optional[TCredentials] = None,
                          **kwargs) -> Optional[TCredentials]:
        raise NotImplementedError()

    @abstractmethod
    def get_flows_from_router(self,
                              credentials: Optional[TCredentials] = None,
                              **kwargs) -> List[str]:
        raise NotImplementedError()

    @property
    @abstractmethod
    def vendor(self) -> VENDOR:
        raise NotImplementedError()

    @property
    def credentials(self) -> Optional[TCredentials]:
        return self._credentials

    @credentials.setter
    def credentials(self,
                    value: Optional[TCredentials]):
        if value is None:
            self._credentials = {}
        elif isinstance(value, dict):
            self._credentials = value
        else:
            Log.error_raise(f'invalid value type: "{type(value)}"')


TCommandWorker = TypeVar('TCommandWorker', bound=Union[ICommandWorker, CommandWorker])


class SshCommandWorker(CommandWorker, ABC):

    _get_stats_from_router_command: str = None

    def parse_credentials(self,
                          credentials: Optional[TCredentials] = None,
                          **kwargs) -> Optional[TCredentials]:
        update = {
            k: v for k, v in SSH_DEFAULTS.items()
            if credentials.get(k) is None
        }
        if credentials:
            credentials.update(update)
        else:
            credentials = update
        for key, keys in {
            'host': ('host', 'ip'),
            'user': ('user', 'username'),
            'password': ('password', 'pass'),
            'key_filename': ('key_filename', 'file')
        }.items():
            value = credentials.get(key)
            if not value:
                value = next((credentials.pop(_) for _ in keys if _ != key and credentials.get(_)), None)
                if not value:
                    value = next((kwargs[_] for _ in [key] + [__ for __ in keys] if kwargs.get(_)), None)
                if value:
                    credentials[key] = value

        return credentials

    def validate_ssh_credentials(self,
                                 credentials: TCredentials,
                                 **kwargs):
        if not credentials['host']:
            Log.error_raise('SSH host ("--host") was not specified')
        if credentials['user'] and not (credentials.get('password') or credentials.get('key_filename')):
            Log.error_raise('SSH user was specified without password or key_filename')

    def ssh_to_paramiko_params(self, params: dict) -> Dict[str, object]:
        self.validate_ssh_credentials(params)
        result = {
            'hostname': params['host'],
            'port': params['port'],
            'username': params['user'],
            'allow_agent': False,
            'look_for_keys': params['look_for_keys'] if params.get('look_for_keys') in (True, False) else False
        }

        if params.get('password'):
            result['password'] = params['password']
        else:
            result['key_filename'] = params['key_filename']
        if params.get('timeout'):
            result['timeout'] = params['timeout']

        return result

    def generate_connection(self, params: dict, **kwargs) -> paramiko.SSHClient:
        look_for_keys = [_.pop('look_for_keys', None) for _ in (kwargs, params)]
        offset = next((i + 1 for i, _ in enumerate(look_for_keys) if _ in (True, False)), None)
        params['look_for_keys'] = look_for_keys[offset - 1] if isinstance(offset, int) else False

        connection: paramiko.SSHClient = paramiko.SSHClient()
        connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        params: Dict[str: object] = self.ssh_to_paramiko_params(params)
        connection.connect(**params)
        return connection

    def execute_cli(self,
                    credentials: Dict[str, object],
                    command: str = None,
                    exec_command: Optional[Callable] = None,
                    **kwargs) -> List[str]:
        if not command and not exec_command:
            Log.error_raise('either "command" or "exec_command" must be specified')
        connection = None
        try:
            connection = self.generate_connection(credentials, **kwargs)
            if not exec_command:
                if not command.endswith('\n'):
                    command = f'{command}\n'

                def _exec_command(_connection, _command, **_kwargs):
                    stdin, stdout, stderr = _connection.exec_command(_command)

                    result = stdout.readlines()
                    lines = [_.rstrip('\r\n') for _ in result]
                    return lines

                exec_command = _exec_command

            return exec_command(connection, command, **kwargs)
        except paramiko.ssh_exception.AuthenticationException as cto_ex:
            time_to_sleep: int = 60 * 10
            time_to_sleep: int = 6
            Log.error(f'Authentication Error - Sleep for {str(time_to_sleep)} seconds')
            time.sleep(time_to_sleep)
            raise
        finally:
            if isinstance(connection, paramiko.SSHClient):
                connection.close()

    def _prepare_stats_command(self, interface_name=None, ip_type='IPv4'):
        if ip_type == 'IPv6':
            self._get_stats_from_router_command = self._get_stats_from_router_command.replace(
                "ipv4", "ipv6") if self._get_stats_from_router_command else None
        return self._get_stats_from_router_command

    def get_flows_from_router(self,
                              credentials: Optional[Dict[str, object]] = None,
                              **kwargs) -> List[str]:
        if not credentials:
            credentials = copy.deepcopy(self.credentials)
        if self._prepare_stats_command(kwargs.get('vrf'), kwargs.get('stats_type', 'IPv4')):
            Log.debug(f'SSH command: "{self._get_stats_from_router_command}"')
            result = self.execute_cli(command=self._get_stats_from_router_command,
                                      credentials=credentials, **kwargs)
            return result

        raise NotImplementedError()
