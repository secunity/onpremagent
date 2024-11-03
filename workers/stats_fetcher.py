import argparse
import datetime
from typing import List, Optional, Dict, Any

from common.api_secunity import send_request, REQUEST_TYPE
from common.consts import PROGRAM
from common.logs import Log, LException
from common.utils import is_bool
from workers.bases import BaseWorker


def decrypt_symetric(db, word, key=None):
    from Crypto.Cipher import AES
    import base64
    if isinstance(word, str):
        word = word.encode('utf-8')
    if key is None:
        key = db.SecunitySettings.find_one('cipher-symetric_default')['value']

    word = base64.b64decode(word)
    iv = word[0:AES.block_size]
    cipher = AES.new(base64.b64decode(key), AES.MODE_CFB, iv)
    return cipher.decrypt(word[16:]).decode('utf-8')


def decrypt(db, word):
    try:
        return decrypt_symetric(db, word=word)
    except Exception as ex:
        return word

class StatsFetcher(BaseWorker):

    @classmethod
    def module_name(cls) -> str:
        return PROGRAM.STATS_FETCHER

    _argparse_params = ('host', 'port', 'username', 'password', 'key_filename',
                        'vendor', 'command_prefix', 'log', 'url', 'dump')
    _argparse_title: str = 'Secunity\'s On-Prem Statistics Fetcher'

    _seconds_interval = 60

    def report_task_failure(self, *args, **kwargs):
        try:
            result = self.wrap_result(success=False, payload=list(args), cur_time=True)
            params = dict(request_type=REQUEST_TYPE.SEND_STATS, identifier=self._identifier, payload=result)
            params.update({k: v for k, v in self.args.items() if k not in params})

            result = send_request(config=self.args, **params)

            return result
        except Exception as e:
            err_msg = f'failed report_task_failure - "{str(e)}"'
            Log.exception(err_msg)
            return None

    def work(self, credentials: Optional[Dict[str, Any]] = None, *args, **kwargs):
        Log.debug('starting a new iteration')
        start_time = datetime.datetime.utcnow()

        if not self._pre_validate_work_params(**kwargs):
            return self.report_task_failure()

        vrf = kwargs.get('vrf')
        if kwargs.get('cloud'):
            db_credentials = self._get_credentials_from_db(kwargs.get('mongodb'))
            if db_credentials:
                dvrf = db_credentials.pop('vrf', None)
                vrf = dvrf if dvrf else vrf
                credentials = db_credentials
            else:
                err_msg = f'failed to get credentials from db'
                Log.error(err_msg)
                # return self.report_task_failure(err_msg)

        command_worker = self.init_command_worker(credentials=credentials)
        if not command_worker:
            err_msg = f'failed to initialize command_worker - vendor: "{self.vendor}"'
            Log.error(err_msg)
            return self.report_task_failure(err_msg)

        Log.debug(f'Get flows: vendor: "{self.vendor}", IPv4 vrf: "{vrf}"')
        pres = self._perform_flows(command_worker, credentials, vrf, 'IPv4', **kwargs)
        if not pres:
            Log.error(f'Failed to get flows for IPv4: {pres}')
            return self.report_task_failure()

        Log.debug(f'Get flows: vendor: "{self.vendor}", IPv6 vrf: "{vrf}"')
        pres = self._perform_flows(command_worker, credentials, vrf, 'IPv6', **kwargs)
        if not pres:
            Log.error(f'Failed to get flows for IPv6: {pres}')
            return self.report_task_failure()

        end_time = datetime.datetime.utcnow()
        Log.debug(f'finished iteration successfully - duration: "{(end_time-start_time).total_seconds():.2f}" seconds')

        return self.report_task_success()

    def _perform_flows(self, command_worker, credentials, vrf, stats_type, **kwargs):
        Log.debug(f'Perform for {stats_type}, {credentials.get("user")}@{credentials.get("host")}')

        router_flows = self.get_flows_from_router(command_worker=command_worker,
                                                  credentials=credentials,
                                                  flow_number=True,
                                                  vrf=vrf,
                                                  stats_type=stats_type,
                                                  **kwargs)
        if router_flows is None:
            err_msg = f'an error occurred while trying to get flows from the router'
            Log.warning(err_msg)
            return self.report_task_failure(err_msg)
        try:
            result = self.wrap_result(success=True,
                                      payload=router_flows,
                                      cur_time=True)
            Log.debug(f'Flows res for {stats_type}: {result}')
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            err_msg = f'failed to wrap result to api - {logged}error: "{str(ex)}"'
            Log.exception(err_msg)
            return self.report_task_failure(err_msg)
        params = dict(request_type=REQUEST_TYPE.SEND_STATS,
                      identifier=self._identifier,
                      payload=result)
        params.update({k: v for k, v in self.args.items() if k not in params})
        try:
            result = send_request(config=self.args, **params)
        except Exception as ex:
            logged = f'logged - ' if isinstance(ex, LException) else ''
            err_msg = f'failed to send stats to BE api - {logged}error: "{str(ex)}"'
            Log.exception(err_msg)
            self.set_failed_api_call()
            return self.report_task_failure(err_msg)

        self.set_success_api_call()

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


    def _get_credentials_from_db(self, mongodb_params: Any):
        try:
            from pymongo import MongoClient
            from bson import ObjectId

            usr = mongodb_params.get('username') or mongodb_params.get('user')
            passwd = mongodb_params.get('password')
            host = mongodb_params.get('host')
            port = mongodb_params.get('port', 27017)
            auth = mongodb_params.get('authSource') or 'admin'

            Log.debug(f'get credentials from db - "{usr}@{host}:{port}/{auth}"')

            uri = f"mongodb://{usr}:{passwd}@{host}:{port}/{auth}"
            client = MongoClient(uri)

            db = client[mongodb_params.get('db_name', 'secunity')]
            acc_device = db.AccountNetworkDevices.find_one({
                "client.flowspec.stats_settings.use_agent": True,
                'client.flowspec.stats_settings.agent_id': ObjectId(self.identifier)
            })
            if not acc_device:
                Log.error(f'failed to get account network device from db')
                return None
            ssh_usr = acc_device.get('client', {}).get('flowspec', {}).get('ssh_settings', {}).get('username')
            password = acc_device.get('client', {}).get('flowspec', {}).get('ssh_settings', {}).get('password')
            ssh_pass = decrypt(db, password)
            ssh_host = acc_device.get('client', {}).get('flowspec', {}).get('ssh_settings', {}).get('ip')
            ssh_port = acc_device.get('client', {}).get('flowspec', {}).get('ssh_settings', {}).get('port', 22)

            vrf = acc_device.get('default_stats_interface_name')

            self._vendor = acc_device.get('vendor')

            Log.debug(f'Credentials from DB - "{ssh_usr}@{ssh_host}:{ssh_port}", vrf: "{vrf}", vendor: "{self.vendor}"')

            return dict(host=ssh_host, port=ssh_port, username=ssh_usr, password=ssh_pass, vrf=vrf) \
                if ssh_usr and ssh_pass and ssh_host else None
        except Exception as ex:
            Log.exception(f'failed to get credentials from db - "{str(ex)}"')
            return None

def main():
    # Set the default values
    MDB_HOST = '172.17.1.153'
    MDB_PORT = 27017
    MDB_USER = 'admin'
    MDB_AUTH_SOURCE = 'admin'

    # Parse the command line arguments
    args = argparse.ArgumentParser()
    args.add_argument('--host', dest='host', default=MDB_HOST)
    args.add_argument('--port', dest='port', default=MDB_PORT)
    args.add_argument('--user', dest='user', default=MDB_USER)
    args.add_argument('--authSource', dest='authSource', default=MDB_AUTH_SOURCE)
    args.add_argument('--password', dest='password', required=True, default=None)
    # args identifier
    args.add_argument('-i', '--identifier', dest='identifier', required=True, default=None)
    # args VRF
    args.add_argument('--vrf', dest='vrf', default=None)
    # args cloud
    args.add_argument('-c', '--cloud', dest='cloud', default=True)
    # args verbose
    args.add_argument('-v', '--verbose', dest='verbose', default=True)

    args = args.parse_args()
    # convert args to dict
    args_dict = vars(args)
    args_dict['mongodb'] = dict(
        host=args_dict.pop('host'),
        port=args_dict.pop('port'),
        username=args_dict.pop('user'),
        authSource=args_dict.pop('authSource'),
        password=args_dict.pop('password')
    )

    try:
        worker = StatsFetcher()
        worker.work(credentials=None, **args_dict)
    except Exception as ex:
        Log.exception(f'failed to run the worker - "{str(ex)}"')

# main
if __name__ == '__main__':
    main()