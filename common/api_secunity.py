from typing import Optional, Tuple, Union, Dict, Any, List, Callable

import requests

from common.configs import get_url_params
from common.utils import parse_identifier, remove_unserializable_types
from common.logs import Log


class URL_SETTING_KEY:
    SCHEME = 'url_scheme'
    HOST = 'url_host'
    PORT = 'url_port'
    METHOD = 'url_method'
    USERNAME = 'url_username'
    PASSWORD = 'url_password'

    ALL = (SCHEME, HOST, PORT, METHOD, USERNAME, PASSWORD)


URL_SETTING_DEFAULTS = {
    URL_SETTING_KEY.SCHEME: 'https',
    URL_SETTING_KEY.HOST: 'api.secunity.io',
    URL_SETTING_KEY.PORT: 443,
    URL_SETTING_KEY.METHOD: 'POST',
    URL_SETTING_KEY.USERNAME: None,
    URL_SETTING_KEY.PASSWORD: None,
}


class REQUEST_TYPE:
    SEND_STATS = 'send_stats'
    GET_FLOWS = 'get_flows'
    SET_FLOW = 'set_flow'

    ALL = (SEND_STATS, GET_FLOWS, SET_FLOW)


class KEYS:
    PATH = 'path'
    METHOD = 'method'


class FORMAT_KEYS:
    IDENTIFIER = 'identifier'
    FLOW_TYPE = 'flow_type'
    FLOW_ID = 'flow_id'
    STATUS = 'status'

    ALL = (IDENTIFIER, FLOW_TYPE, FLOW_ID, STATUS)


REQUEST_TYPE_DEFAULT = {
    REQUEST_TYPE.SEND_STATS:  {
        KEYS.PATH: f'/fstats/{{{FORMAT_KEYS.IDENTIFIER}}}/flows/stat',
        KEYS.METHOD: 'PUT',
    },
    REQUEST_TYPE.GET_FLOWS: {
        KEYS.PATH: f'/fstats/{{{FORMAT_KEYS.IDENTIFIER}}}/flows/{{{FORMAT_KEYS.FLOW_TYPE}}}',
        KEYS.METHOD: 'GET',
    },
    REQUEST_TYPE.SET_FLOW: {
        KEYS.PATH: f'/fstats/{{{FORMAT_KEYS.IDENTIFIER}}}/flows/{{{FORMAT_KEYS.FLOW_ID}}}/status/{{{FORMAT_KEYS.STATUS}}}',
        KEYS.METHOD: 'POST'
    },
}


def get_url_path_and_method(request_type: Union[REQUEST_TYPE, str],
                            **kwargs) -> Tuple[str, str]:  #  path, http-method
    if request_type not in REQUEST_TYPE.ALL:
        Log.error_raise(f'unsupported request type: "{request_type}"')
    defaults = REQUEST_TYPE_DEFAULT.get(request_type)
    if not defaults:
        Log.error_raise(f'request type "{request_type}" does not have defaults')
    path_unformatted = defaults.get(KEYS.PATH)
    params = {
        key: kwargs[key]
        for key in FORMAT_KEYS.ALL
        if kwargs.get(key) is not None
    }
    path_formatted = path_unformatted.format(**params)
    return path_formatted, defaults[KEYS.METHOD].upper()


def get_url_scheme_and_host(config: Optional[Dict[str, Any]] = None,
                            **kwargs) -> str:
    config_url_params = get_url_params(config=config)
    params = {
        key: kwargs[key] if kwargs.get(key) is not None else
             config_url_params[key] if config_url_params.get(key) is not None else
             URL_SETTING_DEFAULTS[key]
        for key in URL_SETTING_KEY.ALL
    }
    result = []
    result.append('http' if params[URL_SETTING_KEY.SCHEME] == 'http' else 'https')
    result.append('://')
    if params.get(URL_SETTING_KEY.USERNAME) and params.get(URL_SETTING_KEY.PASSWORD):
        result.append(f'{params[URL_SETTING_KEY.USERNAME]}:{params[URL_SETTING_KEY.PASSWORD]}@')
    result.append(params[URL_SETTING_KEY.HOST])
    port = params.get(URL_SETTING_KEY.PORT)
    if port:
        result.append(f':{port}')
    return ''.join(result)


def get_url(request_type: Union[REQUEST_TYPE, str],
            method: Optional[bool] = True,
            config: Optional[Dict[str, Any]] = None,
            **kwargs) -> Union[str,                # url
                               Tuple[str, str]]:   # url, http-method
    path, _method = get_url_path_and_method(request_type=request_type, **kwargs)
    kwargs['config'] = config
    scheme_and_host = get_url_scheme_and_host(**kwargs)

    url = f'{scheme_and_host.rstrip("/")}/{path.lstrip("/")}'
    if method:
        return url, _method
    return url


def send_request(request_type: Union[REQUEST_TYPE, str],
                 identifier: str,
                 payload: Optional[Dict[str, Any]] = None,
                 config: Optional[Dict[str, Any]] = None,
                 **kwargs) -> Optional[Union[str, Dict[str, Any], List[Dict[str, Any]]]]:
    identifier = parse_identifier(identifier=identifier, **kwargs)
    if not identifier:
        Log.error(f'invalid identifier: "{identifier}"')
        return None

    url, method = get_url(request_type=request_type,
                          identifier=identifier,
                          method=True,
                          config=config, **kwargs)
    request_str = f'for identifier "{identifier}" to "{url}" using "{method}"'
    Log.debug(f'sending message {request_str}')

    func_params = dict(url=url)
    if payload:
        try:
            payload = remove_unserializable_types(payload)
        except Exception as ex:
            Log.exception_raise(f'failed to serialize payload - ex: "{str(ex)}"')
        func_params['json'] = payload
    try:
        func: Callable = getattr(requests, method.lower())
    except Exception as ex:
        Log.exception_raise(f'failed to generate API request, invalid http method: "{method}"')
    try:
        response: requests.Response = func(**func_params)
        success = 200 <= response.status_code <= 210
    except Exception as ex:
        Log.error(f'failed to send message {request_str}. ex: "{str(ex)}"')
        Log.exception(f'AAAAAAA: {str(type(ex))}')
        # raise
        return None
    if not success:
        Log.error("API function was not successfully performed")
        return None
    try:
        result = response.json() if success and 'application/json' in response.headers.get('Content-Type') else \
                 response.text
    except Exception as ex:
        Log.exception(f'failed to read data from the API. error: "{str(ex)}"')
        return None
    return result
