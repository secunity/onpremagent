import datetime
from typing import Optional, Dict, List, Any

from command_workers.mikrotik import MikrotikCommandWorker
from common.enums import FLOW_TYPE
from common.flows import default_callback__get_flow_status
from common.logs import Log, LException
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

        try:
            current_flows = self.get_flows_from_router(command_worker=command_worker,
                                                       resource=resource,
                                                       credentials=credentials)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to get flows from the router - {logged}error: {str(ex)}')
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

            try:
                result = self.apply_flow(flow=flow,
                                         command_worker=command_worker,
                                         resource=resource,
                                         credentials=credentials)
                self.set_success_router_call()
                success_apply.append(flow)
            except Exception as ex:
                logged = f'logged - ' if isinstance(ex, LException) else ''
                Log.exception(f'failed to apply flow with id "{flow_id}" - {logged}error: "{str(ex)}"')
                self.set_failed_router_call()
                failed_apply.append(flow)

        Log.debug(f'finished applying {len(success_apply)} flows, {len(failed_apply)} flows failed')

        success_remove, failed_remove = [], []
        status = 'remove'
        for flow_id, flow in current_flows_by_ids.items():
            try:
                result = self.remove_flow(flow=flow,
                                          command_worker=command_worker,
                                          resource=resource,
                                          credentials=credentials)
                self.set_success_router_call()
                success_remove.append(flow)
            except Exception as ex:
                logged = f'logged - ' if isinstance(ex, LException) else ''
                Log.exception(f'failed to remove flow with id "{flow_id}" - {logged}error: "{str(ex)}"')
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
    import uuid as _uuid
    import json as _json
    import os
    _identifier = "62447c7549b5bf207dfe4064"
    _host = '172.20.1.10'
    _username = 'admin'
    _password = 'admin'
    _vendor = 'mikrotik'

    _url_host = '127.0.0.1'
    _url_scheme = 'http'
    _url_port = 5000

    _config = dict(identifier=_identifier,
                   host=_host,
                   username=_username,
                   password=_password,
                   vendor=_vendor,
                   verbose=True,
                   url_host=_url_host,
                   url_scheme=_url_scheme,
                   url_port=_url_port
                   )
    _filename = os.path.join('/tmp', f'{_uuid.uuid4()}.json')

    with open(_filename, 'w') as _f:
        _json.dump(_config, _f)
    _worker = FlowsSync(config=_filename)
    _worker.work()