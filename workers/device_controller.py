import datetime
import decimal
from typing import Optional, Union, Dict, List, Any

from command_workers.bases import ICommandWorker
from common.consts import PROGRAM, BOOL_VALUES
from common.logs import Log, LException
from common.utils import get_float, strftime
from workers.bases import BaseWorker


class DeviceController(BaseWorker):

    @classmethod
    def module_name(cls) -> str:
        return PROGRAM.DEVICE_CONTROLLER

    _argparse_params = ('host', 'port', 'username', 'password', 'key_filename',
                        'vendor', 'command_prefix', 'log', 'url', 'dump')
    _argparse_title: str = 'Secunity\'s On-Prem Device Controller'
    _seconds_interval = int(datetime.timedelta(seconds=10).total_seconds())

    _seconds_limit: datetime.timedelta = datetime.timedelta(minutes=1)

    def work(self,
             credentials: Optional[Dict[str, Any]] = None,
             seconds_limit: Optional[Union[int, float, decimal.Decimal, datetime.timedelta]] = None,
             remove_only_if_failed_requests: Optional[bool] = False,
             *args, **kwargs):
        Log.debug('starting')

        if not self._pre_validate_work_params(**kwargs):
            return self.report_task_failure()

        if not seconds_limit:
            seconds_limit = self._seconds_limit
        elif isinstance(seconds_limit, (int, float, decimal.Decimal)):
            seconds_limit = datetime.timedelta(seconds=get_float(seconds_limit))
        elif not isinstance(seconds_limit, datetime.timedelta):
            Log.error(f'invalid seconds limit, got "{type(seconds_limit)}"')

        if remove_only_if_failed_requests is None:
            remove_only_if_failed_requests = False
        elif remove_only_if_failed_requests not in BOOL_VALUES:
            Log.error_raise(f'remove_only_if_failed_requests must be of type bool, got '
                            f'"{type(remove_only_if_failed_requests)}"')

        now = datetime.datetime.utcnow()
        min_time = now - seconds_limit
        min_time_str = strftime(min_time)

        last_success_router = self.get_last_success_router_call() or datetime.datetime.min
        if last_success_router < min_time:
            last_success_router_str = strftime(last_success_router) \
                if last_success_router > datetime.datetime.min else ''
            Log.debug(f'last_success_router is lower than min_time - '
                      f'last_success_router: "{last_success_router_str}", min_time: "{min_time_str}"')
            if remove_only_if_failed_requests:
                last_failed_router = self.get_last_failed_router_call() or datetime.datetime.min
                last_failed_router_str = strftime(last_failed_router) if last_failed_router > datetime.date.min else ''
                if last_failed_router >= min_time:
                    Log.debug(f'last_failed_router is greater than min_time, removing all flows on the router - '
                              f'last_failed_router "{last_failed_router_str}", min_time: "{min_time_str}"')
                    self.remove_all_flows()
                    return self.report_task_success()
                else:
                    Log.debug(f'last_failed_router is lower than min_time, not removing all flows on the router - '
                              f'last_failed_router "{last_failed_router_str}", min_time: "{min_time_str}"')
            else:
                Log.debug(f'removing all flows on the router')
                self.remove_all_flows()
                return self.report_task_success()
        Log.debug('router connectivity is valid - no need to remove flows')

        last_success_api = self.get_last_success_api_call() or datetime.datetime.min
        if last_success_api < min_time:
            last_success_api_str = strftime(last_success_api) if last_success_api > datetime.datetime.min else ''
            Log.debug(f'last_success_api is lower than min_time - '
                      f'last_success_api: "{last_success_api_str}", min_time: "{min_time_str}"')
            if remove_only_if_failed_requests:
                last_failed_api = self.get_last_failed_api_call() or datetime.datetime.min
                last_failed_api_str = strftime(last_failed_api) if last_failed_api > datetime.date.min else ''
                if last_failed_api >= min_time:
                    Log.debug(f'last_failed_api is greater than min_time, removing all flows on the router - '
                              f'last_failed_api "{last_failed_api_str}", min_time: "{min_time_str}"')
                    self.remove_all_flows()
                    return self.report_task_success()
                else:
                    Log.debug(f'last_failed_api is lower than min_time, not removing all flows on the router - '
                              f'last_failed_api "{last_failed_api_str}", min_time: "{min_time_str}"')
            else:
                Log.debug(f'removing all flows on the router')
                self.remove_all_flows()
                return self.report_task_success()
        Log.debug('api connectivity is valid - no need to remove flows')

        return self.report_task_success()

    def remove_all_flows(self,
                         command_worker: ICommandWorker = None,
                         credentials: Optional[Dict[str, Any]] = None,
                         flows: Optional[List[Dict[str, Any]]] = None,
                         *args, **kwargs) -> bool:
        Log.debug('starting to remove all flows')

        if not command_worker:
            try:
                command_worker = self.init_command_worker(credentials=credentials)
            except Exception as ex:
                logged = f'logged - ' if isinstance(ex, LException) else ''
                Log.exception(f'failed to initialize command_worker - vendor: "{self.vendor}" - {logged}error: {str(ex)}')
                return False

        if not flows:
            flows = self.get_flows_from_router(command_worker=command_worker,
                                               credentials=credentials,
                                               flow_number=True)
            if flows is None:
                Log.error('failed to get flows from router - cannot continue')
                return False

        success_flows, failed_flows = [], []
        for flow in flows:
            flow_id = command_worker.flow_id(flow)
            try:
                result = self.remove_flow(flow=flow,
                                          command_worker=command_worker,
                                          credentials=credentials)
                Log.debug(f'flow with id "{flow_id}" was removed successfully')
                success_flows.append(flow)
                self.set_success_router_call()
            except Exception as ex:
                logged = f'logged - ' if isinstance(ex, LException) else ''
                Log.exception(f'failde to remove flow with id "{flow_id}" - {logged}error: "{str(ex)}"')
                failed_flows.append(flow)
                self.set_failed_router_call()

        return len(failed_flows) == 0
