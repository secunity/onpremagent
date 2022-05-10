import datetime
from typing import List, Optional, Dict, Any

from common.api_secunity import send_request, REQUEST_TYPE
from common.consts import PROGRAM
from common.logs import Log, LException
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
        Log.debug('starting a new iteration')
        start_time = datetime.datetime.utcnow()

        if not self._pre_validate_work_params(**kwargs):
            return self.report_task_failure()

        command_worker = self.init_command_worker(credentials=credentials)
        if not command_worker:
            Log.error(f'failed to initialize command_worker - vendor: "{self.vendor}"')
            return self.report_task_failure()

        router_flows = self.get_flows_from_router(command_worker=command_worker,
                                                  credentials=credentials,
                                                  flow_number=True)
        if router_flows is None:
            Log.warning(f'an error occurred while trying to get flows from the router')
            return self.report_task_failure()

        try:
            result = self.wrap_result(success=True,
                                      payload=router_flows,
                                      cur_time=True)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to wrap result to api - {logged}error: "{str(ex)}"')
            return self.report_task_failure()

        params = dict(request_type=REQUEST_TYPE.SEND_STATS,
                      identifier=self._identifier,
                      payload=result)
        params.update({k: v for k, v in self.args.items() if k not in params})

        try:
            result = send_request(config=self.args, **params)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            Log.exception(f'failed to send stats to BE api - {logged}error: "{str(ex)}"')
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
