import datetime
from typing import Optional, Dict, List, Any

from command_workers.mikrotik import MikrotikCommandWorker
from common.enums import FLOW_TYPE
from common.logs import Log
from workers.flows_applier import BaseFlowsApplier


class FlowsSync(BaseFlowsApplier):

    _seconds_interval = int(datetime.timedelta(minutes=10).total_seconds())
    _flow_type = FLOW_TYPE.APPLIED
    _filter_flows_to_handle_statuses = tuple()

    def handle_flows(self,
                     flows_by_status: Dict[str, List[Dict[str, Any]]],
                     command_worker: Optional[MikrotikCommandWorker],
                     resource: Optional = None,
                     credentials: Optional[Dict] = None) -> bool:
        flows_by_status_str = self.flows_by_status_str(flows_by_status)
        Log.debug(f'found {self.total_flows(flows_by_status)} flows: {flows_by_status_str}')
        # flows_to_apply_by_id = {
        #     command_worker.flow_id(flow): flow
        #     for status, flows in flows_by_status.items()
        #     for flow in flows
        # }
        success, current_flows, ex = self.wrap_call_with_try(self.get_flows_from_router,
                                                             command_worker=command_worker,
                                                             resource=resource,
                                                             credentials=credentials)
        if not success:
            if ex:
                Log.exception(f'failed to get flows from router - ex: "{str(ex)}"', ex=ex)
            self.set_failed_router_call()
            return False
        Log.debug(f'found {len(current_flows)} on the router')
        current_flows_by_ids = {
            command_worker.flow_id(flow): flow
            for flow in current_flows
        }

        success_apply, failed_apply = [], []
        status = 'apply'
        flows_to_apply = flows_by_status.get(status) or []
        for flow in flows_to_apply:
            flow_id = command_worker.flow_id(flow)
            if flow_id in current_flows_by_ids:
                current_flows_by_ids.pop(flow_id, None)
                continue
            success, result, ex = self.wrap_call_with_try(f=self.apply_flow,
                                                          flow=flow,
                                                          command_worker=command_worker,
                                                          credentials=credentials)
            if success:
                self.set_success_router_call()
                success_apply.append(flow)
            else:
                if ex:
                    Log.exception(f'failed to apply flow: "{flow.get("id")}"', ex=ex)
                self.set_failed_router_call()
                failed_apply.append(flow)

        Log.debug(f'finished applying {len(success_apply)} flows, {len(failed_apply)} flows failed')

        success_remove, failed_remove = [], []
        status = 'remove'
        for flow_id, flow in current_flows_by_ids.items():
            success, result, ex = self.wrap_call_with_try(f=self.remove_flow,
                                                          flow=flow,
                                                          command_worker=command_worker,
                                                          credentials=credentials)
            if success:
                self.set_success_router_call()
                success_remove.append(flow)
            else:
                if ex:
                    Log.exception(f'failed to apply flow: "{flow.get("id")}"', ex=ex)
                self.set_failed_router_call()
                failed_remove.append(flow)

        Log.debug(f'finished removing {len(success_remove)} flows, {len(failed_remove)} failed')

        return len(failed_apply) == 0 and len(failed_remove) == 0

    def get_flow_status(self,
                        flow: Dict[str, Any],
                        pop_status: bool) -> str:
        status = default_callback__get_flow_status(flow, pop_status=True)
        if status in ('apply', 'applied', 'moderation_approved'):
            return 'apply'
        elif status in ('remove', 'removed', 'removed_moderation_approved'):
            return 'remove'
        Log .error_raise(f'invalid flow status: "{status}"')


if __name__ == '__main__':
    _config = ''
    _worker = FlowsSync(config=_config)
    _command_worker = _worker.init_command_worker()
    _worker.work(command_worker=_command_worker)
    # _worker.start()
