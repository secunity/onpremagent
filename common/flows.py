from typing import List, Dict, Any, Optional, Callable

__STATUS_KEY__ = 'status'
__ID_KEY__ = 'id'
__COMMENT_KEY__ = 'comment'

from common.consts import BOOL_VALUES
from common.logs import Log


def default_callback__get_flow_status(flow: Dict[str, Any],
                                      pop_status: bool) -> str:
    status = getattr(flow, 'pop' if pop_status else 'get')(__STATUS_KEY__)
    return status


def get_flows_by_status(flows: List[Dict[str, Any]],
                        pop_status: Optional[bool] = False,
                        get_flow_status: Optional[Callable[[Dict[str, Any], bool], str]] = None,
                        ) -> Dict[str, List[Dict[str, Any]]]:
    if not get_flow_status:
        get_flow_status = default_callback__get_flow_status
    elif not isinstance(get_flow_status, Callable):
        Log.error_raise(f'get_flow_status must be a callable, got "{type(get_flow_status)}"')
    if pop_status is None:
        pop_status = False
    elif pop_status not in BOOL_VALUES:
        Log.error_raise(f'pop status must be of type bool, got "{type(pop_status)}"')

    flows_by_status = {}
    for flow in flows:
        status = get_flow_status(flow=flow, pop_status=pop_status)
        if not status:
            Log.error_raise(f'flow without status. key: "{__STATUS_KEY__}"')
        lst = flows_by_status.get(status)
        if lst:
            lst.append(flow)
        else:
            flows_by_status[status] = [flow]
    return flows_by_status
