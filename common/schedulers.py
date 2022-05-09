import datetime
from typing import Optional, Union, Iterable

from apscheduler.job import Job
from apscheduler.schedulers.background import BackgroundScheduler, BaseScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from common.consts import BOOL_VALUES
from common.logs import Log


_scheduler: Optional[BackgroundScheduler] = None


class SCHEDULER_SETTINGS_KEYS:
    START = 'start'
    EXECUTOR_THREADPOOL_SIZE = 'executor_threadpool_size'
    TIMEZONE = 'timezone'


SCHEDULER_SETTINGS = {
    SCHEDULER_SETTINGS_KEYS.START: True,
    SCHEDULER_SETTINGS_KEYS.EXECUTOR_THREADPOOL_SIZE: 30,
    SCHEDULER_SETTINGS_KEYS.TIMEZONE: 'UTC',
}


def start_scheduler(start: Optional[bool] = None,
                    threadpool_size: Optional[int] = None,
                    timezone: Optional[Union[datetime.tzinfo, str]] = None,
                    **kwargs) -> BaseScheduler:
    if start not in BOOL_VALUES:
        start = SCHEDULER_SETTINGS[SCHEDULER_SETTINGS_KEYS.START]
    if not isinstance(threadpool_size, int) or threadpool_size <= 0:
        threadpool_size = SCHEDULER_SETTINGS[SCHEDULER_SETTINGS_KEYS.EXECUTOR_THREADPOOL_SIZE]
    if not timezone:
        timezone = pytz.timezone(SCHEDULER_SETTINGS[SCHEDULER_SETTINGS_KEYS.TIMEZONE])
    elif isinstance(timezone, str):
        timezone = pytz.timezone(timezone)
    elif not isinstance(timezone, datetime.tzinfo):
        Log.error_raise(f'invalid timezone: "{str(timezone)}"')

    global _scheduler
    _scheduler = BackgroundScheduler(executors={'default': ThreadPoolExecutor(threadpool_size)},
                                     job_defaults={'max_instances': 1},
                                     timezone=timezone)
    if start:
        _scheduler.start()
        Log.debug('scheduler initialized and started')
    else:
        Log.debug('scheduler initialized')

    return _scheduler


def shutdown_scheduler(wait: bool = True):
    _scheduler.shutdown(wait=wait)


def add_job(func: callable,
            interval: Union[BaseTrigger, int, float],
            func_args: Optional[Iterable] = None,
            func_kwargs: Optional[dict] = None,
            next_run_time: Optional[Union[datetime.timedelta, datetime.datetime, int, float]] = None,
            **kwargs) -> Job:
    if isinstance(interval, (int, float)):
        trigger = IntervalTrigger(seconds=interval)
    elif isinstance(interval, BaseTrigger):
        trigger = interval
    elif interval:
        Log.error_raise(f'invalid interval: "{interval}"')
    else:
        Log.error_raise(f'trigger was not specified')

    if func_args:
        if isinstance(func_args, str) or not isinstance(func_args, Iterable):
            Log.error_raise('func_args must be Iterable')
        func_args = [_ for _ in func_args]

    if func_kwargs and not isinstance(func_kwargs, dict):
        Log.error_raise('func_kwargs must be of type dict')

    if next_run_time is not None:
        if isinstance(next_run_time, (int, float)):
            next_run_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=next_run_time)
        elif isinstance(next_run_time, datetime.timedelta):
            next_run_time = datetime.datetime.utcnow() + next_run_time
        elif not isinstance(next_run_time, datetime.datetime):
            Log.error_raise('next_run_time ust be of type datetime.datetime')

    job = _scheduler.add_job(func=func,
                             trigger=trigger,
                             args=func_args,
                             kwargs=func_kwargs,
                             next_run_time=next_run_time)
    return job


def get_scheduler():
    return _scheduler
