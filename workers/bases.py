import os
from abc import ABC, abstractmethod
import datetime
import time
from typing import Union, Optional, Dict, Callable, Any, Tuple, List

try:
    import jstyleson as json
except:
    import json
from dateutil.parser import parse as date_parse

from common.consts import DEFAULTS, DEFAULT_KEYS
from command_workers import init_command_worker
from command_workers.bases import ICommandWorker, TCommandWorker
from common.api_secunity import URL_SETTING_KEY, URL_SETTING_DEFAULTS
from common.configs import load_env_settings, parse_config_file, update_config_types
from common.enums import VENDOR
from common.files_handler import FILE, read_file, write_line, MODE
from common.logs import Log, LException
from common.schedulers import add_job, start_scheduler, shutdown_scheduler
from common.sshutils import get_ssh_credentials_from_config
from common.utils import get_float


class BaseWorker(ABC):

    @classmethod
    @abstractmethod
    def module_name(cls) -> str:
        raise NotImplementedError()

    _argparse_params: Union[tuple, list] = tuple()
    _seconds_interval: int = -1
    _argparse_title: str = None

    def __init__(self, *args, **kwargs):
        self._identifier = None
        self._args: Dict[str, Any] = self.initialize_start(**kwargs)
        try:
            self._vendor = VENDOR.parse(self._args.get('vendor', 'unknown'))
        except Exception as ex:
            Log.warning(f'failed to parse vendor - error: "{str(ex)}"')
            self._vendor = ''
        self._jobs = []
        self._command_worker = None

    def initialize_start(self, **kwargs) -> dict:
        # argsparse_params = self.get_argsparse_params(title=self._argparse_title, **kwargs)
        # args = get_argarse(**argsparse_params)
        args = load_env_settings()
        config_paths = [kwargs.get('config'),
                        args.get('config'),
                        DEFAULTS[DEFAULT_KEYS.CONFIG]]
        config = next((_ for _ in config_paths if _ and os.path.isfile(_)), None)
        if config:
            config = parse_config_file(config)
            if config:
                args.update(config)
        args.pop('config', None)
        args = update_config_types(config=args)
        enabled = args.get('log') is True or args.get('verbose') is True
        Log.initialize(module=self.module_name(), enabled=enabled, **args)
        self._identifier = args.get('identifier')
        return args

    def _initialize_url_settings(self,
                                 **kwargs) -> Dict[URL_SETTING_KEY, Any]:
        result = {
            key: kwargs[key] if kwargs.get(key) is not None else URL_SETTING_DEFAULTS[key]
            for key in URL_SETTING_KEY.ALL
        }
        return result

    def add_job(self,
                func: Optional[Callable] = None,
                seconds_interval: Optional[int] = None,
                func_kwargs: Optional[Dict] = None,
                start: Optional[bool] = True,
                **kwargs):
        if not func:
            func = self.work
        seconds_interval = get_float(seconds_interval if seconds_interval else self.seconds_interval)
        if not func_kwargs:
            func_kwargs = self.args
        next_run_time = datetime.timedelta(seconds=2) if start else None
        job = add_job(func=func,
                      interval=seconds_interval,
                      func_kwargs=func_kwargs,
                      next_run_time=next_run_time)
        self._jobs.append(job)
        return job

    def _start_pre_infinite_loop(self):
        pass

    def start(self,
              seconds_interval: Optional[Union[int, float]] = None,
              scheduler: Optional[bool] = True,
              add_job: Optional[bool] = True,
              start_job: Optional[bool] = True):
        if not isinstance(seconds_interval, (int, float)):
            seconds_interval = self.seconds_interval
        if seconds_interval <= 0:
            Log.error_raise(f'invalid seconds-interval: "{seconds_interval}"')
        if scheduler not in (True, False):
            scheduler = True
        if add_job not in (True, False):
            add_job = True
        if start_job not in (True, False):
            start_job = True
        start_scheduler(start=scheduler)
        if add_job:
            self.add_job(func=self.work,
                         seconds_interval=self.seconds_interval,
                         start=start_job)
        self._start_pre_infinite_loop()
        if scheduler:
            try:
                while True:
                    time.sleep(1)
            except Exception as ex:
                Log.warning(f'Stop signal received, shutting down')
                shutdown_scheduler()
                Log.warning('scheduler stopped')
                Log.warning('quiting')

    @property
    def args(self) -> dict:
        return self._args

    @property
    def seconds_interval(self) -> int:
        return self._seconds_interval

    def _pre_validate_work_params(self, **kwargs) -> bool:
        if not self.identifier:
            Log.error('no identifier was specified')
            return False

        if kwargs.get('cloud'):
            Log.debug('cloud mode is enabled')
            return True

        if not self.vendor:
            Log.error('no vendor was specified')
            return False

        return True

    @abstractmethod
    def work(self, *args, **kwargs):
        raise NotImplementedError()

    @classmethod
    def get_argsparse_params(cls,
                             title: str = None,
                             config: str = None,
                             **kwargs) -> Dict[str, Any]:
        d = {
            _: kwargs[_] if kwargs.get(_) is not None else True
            for _ in cls._argparse_params
        }
        if title:
            d['title'] = title
        if config:
            d['config'] = config
        return d

    @property
    def vendor(self) -> VENDOR:
        return self._vendor

    @property
    def identifier(self) -> str:
        return self._args.get('identifier') if self._args else None

    @property
    def command_worker(self) -> Optional[ICommandWorker]:
        return self._command_worker

    def init_command_worker(self,
                            credentials: Optional[Dict[str, Any]] = None) -> Optional[ICommandWorker]:
        if not credentials:
            credentials = get_ssh_credentials_from_config(self._args)
        try:
            return init_command_worker(vendor=self.vendor,
                                       credentials=credentials)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to initialize command_worker - vendor: "{self.vendor}" - {logged}error: "{str(ex)}"')
            return None

    def report_task_success(self,
                            *args, **kwargs):
        return True

    def report_task_failure(self,
                            *args, **kwargs):
        return False

    @staticmethod
    def _write_file(file: FILE,
                    data: Optional[Union[str, Dict]] = None,
                    now: Optional[datetime.datetime] = None):
        if not now:
            now = datetime.datetime.utcnow().isoformat()
        if data:
            if not isinstance(data, str):
                data = json.dumps(data)
            line = f'"{now}",{data}'
        else:
            line = now
        write_line(file=file, line=line, lock=True, mode=MODE.WRITE)

    @staticmethod
    def _read_last_time(file: FILE,
                        **kwargs) -> Optional[datetime.datetime]:
        lines = read_file(file=file, lock=True)
        if not lines:
            return None

        def try_parse(date_str) -> Optional[datetime.datetime]:
            try:
                return date_parse(date_str.strip())
            except:
                return None

        dt = next((try_parse(_) for _ in lines if try_parse(_)), None)
        return dt

    def set_success_api_call(self, **kwargs):
        self._write_file(file=FILE.SUCCESS_API, **kwargs)

    def set_failed_api_call(self,
                            **kwargs):
        self._write_file(file=FILE.FAILED_API, **kwargs)

    def set_success_router_call(self,
                                **kwargs):
        self._write_file(file=FILE.SUCCESS_ROUTER, **kwargs)

    def set_failed_router_call(self, **kwargs):
        self._write_file(file=FILE.FAILED_ROUTER, **kwargs)

    def get_last_success_api_call(self, **kwargs) -> Optional[datetime.datetime]:
        return self._read_last_time(file=FILE.SUCCESS_API)

    def get_last_failed_api_call(self, **kwargs) -> Optional[datetime.datetime]:
        return self._read_last_time(file=FILE.FAILED_API)

    def get_last_success_router_call(self, **kwargs) -> Optional[datetime.datetime]:
        return self._read_last_time(file=FILE.SUCCESS_ROUTER)

    def get_last_failed_router_call(self, **kwargs) -> Optional[datetime.datetime]:
        return self._read_last_time(file=FILE.FAILED_ROUTER)

    def get_flows_from_router(self,
                              command_worker: ICommandWorker,
                              resource: Optional = None,
                              credentials: Optional[Dict[str, Any]] = None,
                              flow_number: Optional[bool] = False,
                              *args, **kwargs) -> Optional[List[Dict[str, Any]]]:
        try:
            flows = command_worker.get_flows_from_router(credentials=credentials,
                                                         resource=resource,
                                                         filter_by_prefix=True,
                                                         flow_number=flow_number,
                                                         vrf=kwargs.get('vrf'))
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to get flows from the router - {logged}error: {str(ex)}')
            self.set_failed_router_call()
            return None

        self.set_success_router_call()
        return flows

    def remove_flow(self,
                    flow: Dict[str, Any],
                    command_worker: Optional[TCommandWorker] = None,
                    resource: Optional[Any] = None,
                    credentials: Optional[Dict] = None,
                    **kwargs) -> Union[bool]:
        if not credentials:
            credentials = get_ssh_credentials_from_config(self._args)
        if not command_worker:
            command_worker = init_command_worker(vendor=self.vendor,
                                                 credentials=credentials)
        flow_id = flow['id']
        try:
            result = command_worker.remove_flow(flow=flow,
                                                credentials=credentials,
                                                resource=resource)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to get stats from router - {logged}error: "{str(ex)}"')
            self.set_failed_router_call()
            return False
        self.set_success_router_call()

        try:
            result = command_worker.set_flow_status_api(identifier=self._identifier,
                                                        flow_id=flow_id,
                                                        status='removed')
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to set flow status (api call) - {logged}error: "{str(ex)}"')
            self.set_failed_api_call()
            return False

        self.set_success_api_call()
        Log.debug(f'flow ({flow_id}) status was updated to backend')
        return True

    def apply_flow(self,
                   flow: Dict[str, Any],
                   command_worker: Optional[TCommandWorker] = None,
                   credentials: Optional[Dict] = None,
                   resource: Optional[Any] = None,
                   **kwargs) -> bool:
        flow_id = flow.get('id')
        if not command_worker:
            command_worker = init_command_worker(vendor=self.vendor,
                                                 credentials=credentials)
        try:
            success = command_worker.apply_flow(flow=flow,
                                                credentials=credentials,
                                                resource=resource)
            self.set_success_router_call()
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to get stats from router - {logged}error: "{str(ex)}"')
            self.set_failed_router_call()
            return False

        try:
            result = command_worker.set_flow_status_api(identifier=self._identifier,
                                                        flow_id=flow_id,
                                                        status='applied')
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to set flow status (api call) - {logged}error: "{str(ex)}"')
            self.set_failed_api_call()
            return False

        self.set_success_api_call()
        Log.debug(f'flow ({flow_id}) status was updated to backend')
        return True


def get_debug_config(filename: Optional[str] = None) -> Optional[str]:
    if not filename:
        filename = 'secret-secunity.conf'

    if '/' not in filename:
        from pathlib import Path

        path = Path(__file__)
        filename = os.path.join(path.parent.parent.absolute(), filename)
    if not os.path.isfile(filename):
        return None

    from common.configs import set_conf
    set_conf(filename, replace=True)
    return filename
