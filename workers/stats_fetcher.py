import datetime
from typing import List, Optional, Dict, Any

from common.api_secunity import send_request, REQUEST_TYPE
from common.consts import PROGRAM
from common.logs import Log
from common.utils import is_bool
from workers.bases import BaseWorker


class StatsFetcher(BaseWorker):

    @classmethod
    def module_name(cls) -> str:
        return PROGRAM.STATS_FETCHER

    _argparse_params = ('host', 'port', 'username', 'password', 'key_filename',
                        'vendor', 'command_prefix', 'log', 'url', 'dump')
    _argparse_title: str = 'Secunity\'s On-Prem Statistics Fetcher'

    _seconds_interval = 60

    def work(self,
             credentials: Optional[Dict[str, Any]] = None,
             *args, **kwargs):
        Log.debug('starting new iteration')
        start_time = datetime.datetime.utcnow()

        if not self._pre_validate_work_params(**kwargs):
            return self.report_task_failure()

        success, command_worker, ex = self.wrap_call_with_try(f=self.init_command_worker,
                                                              credentials=credentials)
        if not success:
            if ex:
                Log.exception(f'failed to initialize command_worker - vendor: "{self.vendor}"', ex=ex)
            return self.report_task_failure()

        router_flows = self.get_flows_from_router(command_worker=command_worker,
                                                  credentials=credentials,
                                                  flow_number=True)
        if router_flows is None:
            Log.warning(f'an error occurred while trying to get flows from the router: "{str(ex)}"')
            return self.report_task_failure()

        success, result, ex = self.wrap_call_with_try(f=self.wrap_result,
                                                      success=success,
                                                      payload=router_flows,
                                                      cur_time=True)
        if not success:
            if ex:
                Log.exception('failed to build response for API', ex=ex)
            return self.report_task_failure()

        params = dict(request_type=REQUEST_TYPE.SEND_STATS,
                      identifier=self._identifier,
                      payload=result)
        params.update({k: v for k, v in self.args.items() if k not in params})

        success, result, ex = self.wrap_call_with_try(f=send_request,
                                                      config=self.args,
                                                      **params)
        if not success or not result:
            if ex:
                Log.exception('failed to send stats to BE API', ex=ex)
            self.set_failed_api_call()
            return self.report_task_failure()
        self.set_success_api_call()

        end_time = datetime.datetime.utcnow()
        Log.debug('finished iteration successfully')
        return self.report_task_success()

    @staticmethod
    def wrap_result(success: bool,
                    payload: Optional[List[str]] = None,
                    cur_time: Optional[bool] = True,
                    **kwargs) -> Dict[str, Any]:
        if not is_bool(success):
            Log.error_raise(f'success is not of type bool')
        result = dict(success=success)
        if payload:
            result['data'] = payload
        if cur_time:
            result['local_time'] = datetime.datetime.utcnow()
        return result
