import datetime
from typing import List, Dict, Any, Union, Tuple, Optional, Callable
from abc import ABC

from command_workers.mikrotik import MikrotikCommandWorker
from common.consts import PROGRAM
from common.enums import FLOW_TYPE
from common.flows import default_callback__get_flow_status
from common.logs import Log
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
                                         **kwargs) -> Optional[Tuple[MikrotikCommandWorker, Any]]:
        success, command_worker, ex = self.wrap_call_with_try(f=self.init_command_worker,
                                                              credentials=credentials)
        if not success:
            if ex:
                Log.exception(f'failed to initialize command_worker - vendor: "{self.vendor}"', ex=ex)
            return None

        success, resource, ex = self.wrap_call_with_try(f=command_worker.get_resource,
                                                        credentials=credentials)
        if not success:
            if ex:
                Log.exception(f'failed to get resource - error: "{str(ex)}"')
            self.set_failed_router_call()
            return None

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
        Log.debug('starting new iteration')
        start_time = datetime.datetime.utcnow()

        if not self._pre_validate_work_params(**kwargs):
            return self.report_task_failure()

        _flow_type = self._parse_flow_type(flow_type)
        if not _flow_type:
            Log.error(f'invalid flow_type: "{flow_type}"')
            return self.report_task_failure()
        flow_type = _flow_type

        result_tuple = self.init_command_worker_and_resource(credentials=credentials)
        if not result_tuple:
            Log.error(f'failed to init command worker and resource')
            self.set_failed_router_call()
            return self.report_task_failure()
        command_worker: MikrotikCommandWorker = result_tuple[0]
        resource = result_tuple[1]

        if not get_flow_status_callback:
            get_flow_status_callback = self.get_flow_status
        success, flows_by_status, ex = self.wrap_call_with_try(f=command_worker.get_flows_from_api,
                                                               identifier=self._identifier,
                                                               flow_type=flow_type,
                                                               parse=False,
                                                               get_flow_status_callback=get_flow_status_callback,
                                                               config=self.args)
        if not success:
            if ex:
                Log.exception(f'failed to flows from api - flow_type - vendor: "{self.vendor}"', ex=ex)
            self.set_failed_api_call()
            return self.report_task_failure()
        self.set_success_api_call()

        if not flows_by_status:
            end_time = datetime.datetime.utcnow()
            return self.report_task_success()

        success, _none, ex = self.wrap_call_with_try(f=self.handle_flows,
                                                     flows_by_status=flows_by_status,
                                                     command_worker=command_worker)
        if not success:
            if ex:
                Log.exception('failed to handle flows from api', ex=ex)
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

    def apply_flows(self,
                    flows_by_status: Dict[str, List[Dict[str, Any]]],
                    command_worker: Optional[MikrotikCommandWorker],
                    status: str,
                    credentials: Optional[Dict] = None) -> bool:
        flows_to_handle = flows_by_status.get(status)
        if not flows_to_handle:
            Log.debug(f'no flows with statys "{status}" were found')
            return True

        status = True
        for flow in flows_to_handle:
            success, result, ex = self.wrap_call_with_try(self.apply_flow,
                                                          flow=flow,
                                                          command_worker=command_worker)
            if success:
                self.set_success_router_call()
            else:
                if ex:
                    Log.exception(f'failed to apply flow: "{flow.get("id")}"', ex=ex)
                self.set_failed_router_call()
                status = False

        return status

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
                func = self.get_flow_operation_func_by_status(status=status)
                success, result, ex = self.wrap_call_with_try(f=func,
                                                              flow=flow,
                                                              command_worker=command_worker)
                if success and result:
                    self.set_success_router_call()
                    success_flows.append(flow)
                else:
                    if ex:
                        Log.exception(f'failed to apply flow: "{flow.get("id")}"', ex=ex)
                    self.set_failed_router_call()
                    failed_flows.append(flow)

        Log.debug(f'finished handling {total_flows} flows - breakdown by status: {flows_by_status_str} - '
                  f'success: {len(success_flows)} - '
                  f'failed - {len(failed_flows)}')
        return len(failed_flows) == 0

    def handle_apply_flow(self,
                          flow: Dict[str, Any],
                          command_worker: MikrotikCommandWorker) -> bool:
        success, result, ex = self.wrap_call_with_try(f=self.apply_flow,
                                                      flow=flow,
                                                      command_worker=command_worker)
        if success:
            self.set_success_router_call()

            flow_id = flow.get('id')
            success, result, ex = self.wrap_call_with_try(f=command_worker.set_flow_status_api,
                                                          identifier=self._identifier,
                                                          flow_id=flow_id,
                                                          status='applied')
            if not success:
                if ex:
                    Log.exception(f'failed to inform api about applied flow', ex=ex)
                self.set_failed_api_call()
            else:
                self.set_success_api_call()
                Log.debug(f'flow ({flow_id}) status was updated to backend')
        else:
            if ex:
                Log.exception(f'failed to apply flow - ex: "{str(ex)}"', ex=ex)
            self.set_success_router_call()

        return success


class FlowsApplier(BaseFlowsApplier):

    _seconds_interval = int(datetime.timedelta(seconds=10).total_seconds())
    _flow_type = FLOW_TYPE.APPLY_REMOVE
    _filter_flows_to_handle_statuses = (FLOW_TYPE.APPLY, FLOW_TYPE.REMOVE, FLOW_TYPE.APPLY_REMOVE)


if __name__ == '__main__':
    import os
    from pathlib import Path
    path = Path(__file__)
    _conf = os.path.join(str(path.parent.parent), 'secret-secunity.conf')
    _applier = FlowsApplier(config=_conf)
    _applier.work()
