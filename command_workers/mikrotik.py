import re
import time
from typing import Optional, Dict, List, Any, Union, Callable, Tuple
from bson.objectid import ObjectId
from common.api_secunity import send_request, REQUEST_TYPE, FORMAT_KEYS
from common.enums import VENDOR
from command_workers.bases import CommandWorker
from common.files_handler import FileLock
from common.flows import get_flows_by_status
from common.logs import Log, LException
from common.utils import parse_ip, get_ipv4, get_int, to_ObjectId


class MikrotikCommandWorker(CommandWorker):

    __VALIDATE_EXISTING__ = True

    __LOCK_FILE__ = '/tmp/secunity-mikrotik-cw.lock'

    class KEYS:
        FLOW_PREFIX = 'flow_prefix'
        USER = 'user'
        PASSWORD = 'password'

        RESOURCE_PATH = 'resource_path'
        FLOW_KEYS = 'flow_keys'
        FLOW_ID = 'flow_id'
        COMMENT = 'comment'

    __DEFAULTS__ = {
        KEYS.FLOW_PREFIX: 'SECUNITY_',
        KEYS.USER: 'admin',
        KEYS.PASSWORD: '',

        KEYS.RESOURCE_PATH: '/ip/firewall/raw',
        KEYS.FLOW_KEYS: {
            KEYS.FLOW_ID: 'id',
            KEYS.COMMENT: 'comment'
        }
    }

    @classmethod
    def resource_path(cls) -> str:
        return cls.__DEFAULTS__[cls.KEYS.RESOURCE_PATH]

    __IMPORTS__ = {
        'RouterOsApiPool': None,
    }

    @classmethod
    def get_import(cls,
                   key: str):
        value = cls.__IMPORTS__.get(key)
        if value:
            return value
        if key == 'RouterOsApiPool':
            from routeros_api import RouterOsApiPool
            cls.__IMPORTS__[key] = RouterOsApiPool
        else:
            return Log.error_raise(f'invalid key: "{str(key)}"')
        return cls.__IMPORTS__[key]

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.MIKROTIK

    def __init__(self,
                 credentials: Optional[Dict[str, object]] = None, **kwargs):
        if credentials:
            credentials = {k: v for k, v in credentials.items() if k in ('host',
                                                                         self.KEYS.USER,
                                                                         self.KEYS.PASSWORD)}
        super().__init__(credentials, **kwargs)

    def parse_credentials(self,
                          credentials: Optional[Dict[str, object]] = None,
                          **kwargs) -> Dict[str, object]:
        if not credentials:
            credentials = self.credentials
        if not credentials:
            Log.error_raise('No credentials were specified')

        host, user, password = credentials.get('host'), credentials.get('user'), credentials.get('password')
        credentials['host'] = parse_ip(host)
        if not credentials['host']:
            Log.error_raise(f'invalid host: "{str(host)}"')
        credentials['user'] = user.strip() if user and isinstance(user, str) else self.__DEFAULTS__[self.KEYS.USER]
        credentials['password'] = password.strip() if password and isinstance(password, str) else \
                                  self.__DEFAULTS__[self.KEYS.PASSWORD]
        return credentials

    def get_resource(self,
                     credentials: Dict[str, object],
                     resource_path: Optional[str] = None,
                     **kwargs):  #  RouterOsResource
        credentials = self.parse_credentials(credentials)
        if not resource_path:
            resource_path = self.resource_path()
        missing_key = next((_ for _ in ('host', 'user', 'password') if not credentials.get(_)), None)
        if missing_key:
            Log.error_raise(f'missing credentials parameters "{missing_key}"')
        try:
            pool = self.get_import('RouterOsApiPool')
        except Exception as ex:
            Log.exception_raise(f'cannot import mikrotik package (routeros_api.RouterOsApiPool)', ex=ex)
        try:
            connection = pool(host=credentials['host'],
                              username=credentials['user'],
                              password=credentials['password'],
                              plaintext_login=True)
        except Exception as ex:
            Log.exception_raise(f'failed to initialize connection to router: "{str(ex)}"', ex=ex)
        try:
            api = connection.get_api()
        except Exception as ex:
            Log.error_raise(f'failed to initialize router API connector: "{str(ex)}"')

        try:
            resource = api.get_resource(resource_path)
        except Exception as ex:
            Log.exception_raise(f'failed to get "{resource_path}" resource', ex=ex)

        return resource

    initialize_connection_and_api_connector = get_resource

    def set_flow_status_api(self,
                            identifier: str,
                            flow_id: Union[ObjectId, str],
                            status: Optional[str]) -> Optional[Dict]:
        try:
            result = send_request(request_type=REQUEST_TYPE.SET_FLOW,
                                  identifier=identifier,
                                  **{FORMAT_KEYS.FLOW_ID: flow_id,
                                     FORMAT_KEYS.STATUS: status})
        except Exception as ex:
            Log.exception(f'failed to retrieve flows raw data from api: "{str(ex)}"')
            return None

        return result

    def get_flows_from_api(self,
                           identifier: str,
                           flow_type: Optional[str] = None,
                           get_flow_status_callback: Optional[Callable[[Dict[str, Any], bool], str]] = None,
                           config: Optional[Dict[str, Any]] = None,
                           **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        if not flow_type:
            flow_type = 'apply_remove'
        try:
            flows = send_request(request_type=REQUEST_TYPE.GET_FLOWS,
                                 identifier=identifier,
                                 config=config,
                                 **{FORMAT_KEYS.FLOW_TYPE: flow_type})
        except Exception as ex:
            Log.exception_raise(f'failed to retrieve flows raw data from api: "{str(ex)}"')

        if flows is None:
            Log.error_raise('failed to get flows from api')

        Log.debug(f'found a total of {len(flows)} on the device')

        flows_by_status = get_flows_by_status(flows, pop_status=True, get_flow_status=get_flow_status_callback) \
                          if flows else {}
        return flows_by_status

    @classmethod
    def comment_prefix(cls):
        return cls.__DEFAULTS__[cls.KEYS.FLOW_PREFIX]

    @classmethod
    def id_key(cls,
               id_key: Optional[str] = None,
               *args, **kwargs) -> str:
        if id_key:
            return id_key

        id_key = next((kwargs[_] for _ in ('id', 'key') if kwargs.get(_)), None)
        if id_key:
            return id_key

        if len(args) == 1 and args[0]:
            return args[0]

        return cls.__DEFAULTS__[cls.KEYS.FLOW_KEYS][cls.KEYS.FLOW_ID]

    @classmethod
    def comment_key(cls,
                    comment_key: Optional[str] = None,
                    *args, **kwargs) -> str:
        if comment_key:
            return comment_key

        comment_key = next((kwargs[_] for _ in ('comment', 'key') if kwargs.get(_)), None)
        if comment_key:
            return comment_key

        if len(args) == 1 and args[0]:
            return args[0]

        return cls.__DEFAULTS__[cls.KEYS.FLOW_KEYS][cls.KEYS.COMMENT]

    @classmethod
    def flow_id_to_comment(cls,
                           flow: Dict[str, Any],
                           pop: Optional[bool] = True,
                           id_key: Optional[str] = None,
                           comment_key: Optional[str] = None) -> Dict[str, Any]:
        id_key = cls.id_key(id_key)
        comment_key = cls.comment_key(comment_key)
        _id = (flow.pop if pop else flow.get)(id_key)
        flow[comment_key] = f'{cls.comment_prefix()}{_id}'
        return flow

    @classmethod
    def is_secunity_flow(cls,
                         flow: Dict[str, Any],
                         comment_key: Optional[str] = None) -> bool:
        comment_key = cls.comment_key(comment_key)
        comment = flow.get(comment_key)
        return comment and comment.startswith(cls.comment_prefix())

    @classmethod
    def comment_to_flow_id(cls,
                           flow: Dict[str, Any],
                           id_key: Optional[str] = None,
                           comment_key: Optional[str] = None) -> Dict[str, Any]:
        id_key = cls.id_key(id_key)
        comment_key = cls.comment_key(comment_key)
        comment = flow.get(comment_key)
        prefix = cls.comment_prefix()
        if not comment or not comment.startswith(prefix):
            Log.error_raise(f'flow is missing or has an invalid comment: "{str(comment)}"')
        del flow[comment_key]
        flow[id_key] = comment[len(prefix):]
        return flow

    @classmethod
    def filter_flows_by_prefix(cls,
                               flows: List[Dict[str, Any]],
                               filter_prefix: Optional[str] = None,
                               comment_key: Optional[str] = None) -> List[Dict[str, Any]]:
        if not filter_prefix:
            filter_prefix = cls.comment_prefix()
        comment_key = cls.comment_key(comment_key)
        flows = [_ for _ in flows
                 if (_.get(comment_key) or '').startswith(filter_prefix)]
        return flows

    @classmethod
    def to_mkrotik_flow(cls,
                        flow: Dict[str, Any],
                        chain: Optional[str] = None,
                        as_str: Optional[bool] = False) -> Union[Dict[str, Any], List[str]]:
        cmd = {}

        flow_id = flow.get('id') or flow.get('_id')
        if not flow_id:
            Log.error_raise('flow id was not specified')

        for src, dst in {'source': 'src',
                         'destination': 'dst'}.items():
            value = flow.get(src)
            if not value or not isinstance(value, dict):
                continue
            ip = get_ipv4(value.get('ip'))
            mask = get_int(value.get('mask'))
            if ip and mask and 0 < mask <= 32:
                cmd[f'{dst}-address'] = f'{ip}/{mask}'
            ports = flow.get(f'{src}_ports')
            if ports:
                cmd[f'{dst}-port'] = ','.join([str(_) for _ in ports])

        protocol = flow.get('protocol')
        if protocol:
            cmd['protocol'] = list(protocol.values())[0].lower()

        tcp_flags: Optional[List[str]] = flow.get('tcp_flags')
        if tcp_flags:
            cmd['tcp-flags'] = ','.join([_.strip().lower() for _ in tcp_flags if _.strip()])

        packet_length = flow.get('packet_length')
        if packet_length:
            cmd['packet-size'] = str(packet_length)

        port = flow.get('port')
        if port:
            cmd['port'] = str(port)

        icmp = flow.get('icmp')
        if isinstance(icmp, dict):
            code = icmp.get('code')
            if code:
                cmd['icmp-options'] = code

        action = flow.get('apply_action')
        if action == 'rate_limit':
            action = 'drop'
            rate_limit = flow.get('rate_limit')
            if rate_limit and isinstance(rate_limit, Dict):
                value = get_int(rate_limit.get('bps'))
                if value:
                    cmd['connection-bytes'] = str(value)
                value = get_int(rate_limit.get('pps'))
                if value:
                    cmd['limit'] = str(value)
        elif action not in ('accept', 'discard'):
            action = 'drop'
        cmd['action'] = action

        cmd['comment'] = f'{cls.__DEFAULTS__[cls.KEYS.FLOW_PREFIX]}{flow_id}'

        if not chain:
            chain = 'input'
        cmd['chain'] = chain

        if as_str:
            cmd = ' '.join([f'{key}={value}' for key, value in cmd.items()])
        return cmd

    def flow_id(self,
                flow: Union[ObjectId, str, Dict[str, Any]]) -> str:
        flow_id = flow.get('id') or flow.get('_id') if isinstance(flow, dict) else flow
        return str(to_ObjectId(flow_id))

    def filter_existing_flows(self,
                              filter: Callable[[Dict[str, Any]], bool],
                              credentials: Optional[Dict[str, Any]] = None,
                              resource: Optional = None,
                              multiple: Optional[bool] = True,
                              lock: Optional[bool] = True,
                              flow_number: Optional[bool] = False,
                              **kwargs) -> Union[List[Dict[str, Any]],
                                                 Optional[Dict[str, Any]]]:
        flows = self.get_flows_from_router(credentials=credentials,
                                           resource=resource,
                                           filter_by_prefix=True,
                                           lock=lock,
                                           flow_number=flow_number, **kwargs)

        if multiple:
            flows = [_ for _ in flows if filter(_)]
            return flows
        else:
            flow = next((_ for _ in flows if filter(_)), None)
            return flow

    def has_existing_flow(self,
                          flow: Union[ObjectId, str, Dict[str, Any]],
                          credentials: Optional[Dict[str, Any]] = None,
                          resource: Optional = None,
                          lock: Optional[bool] = True,
                          **kwargs) -> bool:
        flow_id = self.flow_id(flow)
        flow = self.filter_existing_flows(filter=lambda _flow: self.flow_id(_flow) == flow_id,
                                          credentials=credentials,
                                          resource=resource,
                                          lock=lock,
                                          multiple=False, **kwargs)
        return flow is not None

    def get_flow_by_id_from_router(self,
                                   flow_id: Union[str, ObjectId],
                                   credentials: Optional[Dict[str, Any]] = None,
                                   resource: Optional = None,
                                   lock: Optional[bool] = True,
                                   **kwargs) -> Optional[Dict[str, Any]]:
        flows = self.get_flows_from_router(credentials=credentials,
                                           resource=resource,
                                           flow_number=True,
                                           lock=lock,
                                           **kwargs)
        if flows is None:
            Log.warning('cannot look for flow by id, no flows are applied on the router')
            return None

        if not flows:
            Log.info(f'flow with id "{flow_id}" does not exist on the router')
            return None

        flow_id = str(flow_id)
        flow = next((_ for _ in flows
                     if str(_.get('id') or '') == flow_id), None)
        return flow

    def get_flow_number(self,
                        flow_id: Union[str, ObjectId],
                        credentials: Optional[Dict[str, Any]] = None,
                        resource: Optional = None,
                        lock: Optional[bool] = True,
                        **kwargs) -> Optional[str]:
        flow = self.get_flow_by_id_from_router(flow_id=flow_id,
                                               credentials=credentials,
                                               resource=resource,
                                               lock=lock, **kwargs)
        if not flow:
            error = f'flow with id "{flow_id}" does not exist on the router'
            Log.warning(error)
            return None

        return flow.get('number')

    def remove_flow(self,
                    flow,
                    credentials: Optional[Dict[str, Any]] = None,
                    resource: Optional = None,
                    lock: Optional[bool] = True,
                    **kwargs) -> bool:
        flow_id = flow.get('id')
        if not flow_id:
            Log.error_raise('flow without id')
        if not resource:
            credentials: Dict[str, object] = self.parse_credentials(credentials)
            resource = self.initialize_connection_and_api_connector(credentials=credentials,
                                                                    resource_path='/ip/firewall/filter')
        existing_flow = self.get_flow_by_id_from_router(flow_id=flow_id,
                                                        credentials=credentials,
                                                        resource=resource,
                                                        lock=lock)
        if not existing_flow:
            Log.error(f'a flow with id "{flow_id}" does not exist on the router - not continuing')
            return True

        flow_number = flow.get('number')
        if not flow_number:
            flow_number = existing_flow.get('number')

        def _send_request():
            try:
                _id = flow_number
                if not _id.startswith('*'):
                    _id = f'*{_id}'
                _result = resource.remove(id=_id)
                while not _result.done:
                    time.sleep(0.05)
                return _result
            except Exception as ex:
                logged = f'logged - ' if isinstance(ex, LException) else ''
                Log.exception(f'failed to remove flow with id "{_id}" from router - {logged}error: "{str(ex)}"')
                return None

        if lock:
            with FileLock(self.__LOCK_FILE__):
                result = _send_request()
        else:
            result = _send_request()

        Log.debug(f'flow with id "{flow_id}" was removed successfully')
        return True

    def apply_flow(self,
                   flow,
                   credentials: Optional[Dict[str, Any]] = None,
                   resource: Optional = None,
                   validate_existing: Optional[bool] = True,
                   lock: Optional[bool] = True,
                   **kwargs) -> bool:
        if validate_existing not in (True, False):
            Log.exception_raise(f'got invalid value for validate_existing, expected bool, got "{type(validate_existing)}"')
        flow_id = flow.get('id')
        if not flow_id:
            Log.error_raise('flow without id')
        flow_id = str(flow_id)
        if not resource:
            credentials: Dict[str, object] = self.parse_credentials(credentials)
            resource = self.get_resource(credentials=credentials)
        if validate_existing and self.has_existing_flow(flow=flow_id,
                                                        resource=resource,
                                                        lock=lock):
            Log.warning(f'requested to apply an already applied flow ({flow_id})  - not reapplying it')
            return True
        if not flow_id.startswith(self.comment_prefix()):
            flow_id = f'{self.comment_prefix()}{flow_id}'
        flow['comment'] = flow_id
        flow.pop('id', None)

        def _send_request():
            try:
                _result = resource.add(**flow)
                while not _result.done:
                    time.sleep(0.05)
                return _result
            except Exception as ex:
                Log.exception_raise(f'failed to add a flow ("{flow_id}") to router - ex: "{str(ex)}"')
                return None

        if lock:
            with FileLock(self.__LOCK_FILE__):
                result = _send_request()
        else:
            result = _send_request()

        Log.debug(f'flow "{flow_id}" applied successfully')
        return True

    # def get_applied_flows(self,
    #                       credentials: Optional[Dict[str, Any]] = None,
    #                       filter_by_prefix: Optional[bool] = True,
    #                       filter_prefix: Optional[str] = None,
    #                       lock: Optional[bool] = True,
    #                       **kwargs) -> Optional[List[dict]]:
    #     return self

    def get_flows_from_router(self,
                              credentials: Optional[Dict[str, Any]] = None,
                              resource: Optional = None,
                              filter_by_prefix: Optional[bool] = True,
                              filter_prefix: Optional[str] = None,
                              lock: Optional[bool] = True,
                              flow_number: Optional[bool] = True,
                              **kwargs) -> List[Dict[str, Any]]:
        if not resource:
            credentials: Dict[str, object] = self.parse_credentials(credentials)
            resource = self.initialize_connection_and_api_connector(credentials=credentials)

        def _send_request():
            try:
                _result = resource.get()
                while not _result.done:
                    time.sleep(0.05)
                return list(_result)
            except Exception as ex:
                Log.exception_raise(f'failed to read list of flows (rules) from router: "{str(ex)}"')
                return []

        if lock:
            with FileLock(self.__LOCK_FILE__):
                flows = _send_request()
        else:
            flows = _send_request()

        Log.debug(f'found a total of {len(flows)} flows on the router')
        if filter_by_prefix:
            flows = self.filter_flows_by_prefix(flows, filter_prefix=filter_prefix)
            Log.debug(f'after filtering flows by prefix {len(flows)} remained')

        flows = [self.from_mikrotik_flow(_, flow_number=flow_number) for _ in flows]
        return flows

    @classmethod
    def from_mikrotik_flow(cls,
                           flow: Dict[str, Any],
                           flow_number: Optional[bool] = False,
                           **kwargs) -> Dict[str, Any]:
        prefix = cls.comment_prefix()
        comment_key = cls.comment_key()
        comment = flow.pop(comment_key, None)

        if flow_number:
            flow['number'] = re.match(r'^\s*\*?\s*([^\s]+)(\s.*|$)', flow['id']).groups()[0]

        if comment:
            flow['id'] = comment[len(prefix):]
        else:
            flow.pop('id', None)

        return flow
