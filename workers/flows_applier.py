import datetime
from typing import List, Dict, Any, Union, Tuple, Optional, Callable
from abc import ABC

from command_workers.mikrotik import MikrotikCommandWorker
from common.consts import PROGRAM
from common.enums import FLOW_TYPE, VENDOR
from common.flows import default_callback__get_flow_status
from common.logs import Log, LException
from workers.bases import BaseWorker


class BaseFlowsApplier(BaseWorker, ABC):

    @classmethod
    def module_name(cls) -> str:
        return PROGRAM.FLOWS_APPLIER

    _argparse_params = ('vendor', 'command_prefix', 'log', 'url', 'dump')
    _argparse_title: str = 'Secunity\'s On-Prem Flows Applier'

    _flow_type = None

    _filter_flows_to_handle_statuses = tuple()

    def _parse_flow_type(self,
                         flow_type: Optional[Union[FLOW_TYPE, str]] = None,
                         **kwargs) -> Union[FLOW_TYPE, str]:
        if not flow_type:
            flow_type = self._flow_type
        return flow_type if flow_type in FLOW_TYPE.ALL else None

    def init_command_worker_and_resource(self,
                                         credentials: Optional[Dict[str, Any]] = None,
                                         **kwargs) -> Tuple[Optional[MikrotikCommandWorker], Optional[Any]]:
        try:
            command_worker: MikrotikCommandWorker = self.init_command_worker(credentials=credentials)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to init command worker - {logged}error: "{str(ex)}"')
            return None, None

        if self.vendor != VENDOR.MIKROTIK:
            Log.error(f'Current process not running with vendor "{self.vendor}"')
            return None, None

        try:
            resource = command_worker.get_resource(credentials=credentials)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to init command worker resource - {logged}error: "{str(ex)}"')
            return None, None

        return command_worker, resource

    def get_flow_status(self,
                        flow: Dict[str, Any],
                        pop_status: bool) -> str:
        status = default_callback__get_flow_status(flow, pop_status=True)
        return status

    def work(self,
             credentials: Optional[Dict[str, Any]] = None,
             flow_type: Optional[Union[FLOW_TYPE, str]] = None,
             get_flow_status_callback: Optional[Callable[[Dict[str, Any], bool], str]] = None,
             *args, **kwargs):
        Log.debug('starting a new iteration')

        if not self._pre_validate_work_params(**kwargs):
            return self.report_task_failure()

        _flow_type = self._parse_flow_type(flow_type)
        if not _flow_type:
            Log.error(f'invalid flow_type: "{flow_type}"')
            return self.report_task_failure()
        flow_type = _flow_type

        command_worker, resource = self.init_command_worker_and_resource(credentials=credentials)
        if not command_worker:
            Log.error(f'failed to init command worker and resource')
            self.set_failed_router_call()
            return self.report_task_failure()

        if not get_flow_status_callback:
            get_flow_status_callback = self.get_flow_status
        try:
            flows_by_status = command_worker.get_flows_from_api(identifier=self._identifier,
                                                                flow_type=flow_type,
                                                                parse=False,
                                                                get_flow_status_callback=get_flow_status_callback,
                                                                config=self.args)

        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to get flows from api - flow_type: "{flow_type}" - {logged}error: "{str(ex)}"')
            self.set_failed_api_call()
            return self.report_task_failure()
        self.set_success_api_call()

        if not flows_by_status:
            return self.report_task_success()

        try:
            success = self.handle_flows(flows_by_status=flows_by_status,
                                        command_worker=command_worker,
                                        resource=resource,
                                        credentials=command_worker.credentials)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to apply/remove flows  - flow_type: "{flow_type}" - {logged}error: "{str(ex)}"')
            self.set_failed_router_call()
            return self.report_task_failure()
        self.set_success_router_call()

        end_time = datetime.datetime.utcnow()
        return self.report_task_success()

    def filter_flows_to_handle(self,
                               flows_by_status: Dict[str, List[Dict[str, Any]]],
                               **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        result = {
            k: v for k, v in flows_by_status.items()
            if k in self._filter_flows_to_handle_statuses
        }
        return result

    @staticmethod
    def flows_by_status_str(flows_by_status: Dict[str, List[Dict[str, Any]]],
                            **kwargs) -> str:
        result = ', '.join([
            f'{status}: {len(_flows)}'
            for status, _flows in flows_by_status.items()
            if _flows
        ])
        return result

    @staticmethod
    def total_flows(flows_by_status: Dict[str, List[Dict[str, Any]]],
                    **kwargs) -> int:
        total_flows = [v for k, v in flows_by_status.items() if v]
        total_flows = sum([len(_) for _ in total_flows]) if total_flows else 0
        return total_flows

    def get_flow_operation_func_by_status(self,
                                          status: str) -> \
            Callable[[Dict[str, Any], MikrotikCommandWorker, Optional[Dict]], bool]:
        if status in ('apply', 'applied'):
            return self.apply_flow
        elif status in ('remove', 'removed'):
            return self.remove_flow
        else:
            Log.exception_raise(f'invalid flow status: "{status}"')

    def handle_flows(self,
                     flows_by_status: Dict[str, List[Dict[str, Any]]],
                     command_worker: Optional[MikrotikCommandWorker],
                     resource: Optional = None,
                     credentials: Optional[Dict] = None) -> bool:
        flows_by_status_str = self.flows_by_status_str(flows_by_status)
        Log.debug(f'found {self.total_flows(flows_by_status)} flows by status: {flows_by_status_str}')

        flows_by_status = self.filter_flows_to_handle(flows_by_status)
        total_flows = self.total_flows(flows_by_status)
        flows_by_status_str = self.flows_by_status_str(flows_by_status)
        Log.debug(f'after filter, {total_flows} flows remain. breakdown by status: {flows_by_status_str}')

        success_flows, failed_flows = [], []
        for status, flows in flows_by_status.items():
            Log.debug(f'starting to handle {len(flows)} flows of status "{status}"')
            for flow in flows:
                if status in ('apply', 'applied'):
                    func = self.apply_flow
                elif status in ('remove', 'removed'):
                    func = self.remove_flow
                else:
                    Log.error(f'invalid flow status: "{status}"')
                    continue
                try:
                    result = func(flow=flow,
                                  command_worker=command_worker,
                                  resource=resource,
                                  credentials=credentials)
                except Exception as ex:
                    logged = f'logged - ' if isinstance(ex, LException) else ''
                    Log.exception(f'failed to handle flow - action: "{func.__name__}" - {logged}error: "{str(ex)}"')
                    result = None
                if result:
                    self.set_success_router_call()
                    success_flows.append(flow)
                else:
                    self.set_failed_router_call()
                    failed_flows.append(flow)

        Log.debug(f'finished handling {total_flows} flows - breakdown by status: {flows_by_status_str} - '
                  f'success: {len(success_flows)} - '
                  f'failed - {len(failed_flows)}')
        return len(failed_flows) == 0


class FlowsApplier(BaseFlowsApplier):

    _seconds_interval = int(datetime.timedelta(seconds=10).total_seconds())
    _flow_type = FLOW_TYPE.APPLY_REMOVE
    _filter_flows_to_handle_statuses = (FLOW_TYPE.APPLY, FLOW_TYPE.REMOVE, FLOW_TYPE.APPLY_REMOVE)
