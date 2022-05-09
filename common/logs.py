import os.path
import sys
import logging
import traceback
from typing import Optional, Union, Type, TypeVar

from common.utils import is_bool, parse_bool


class LOG_DEFAULTS_KEYS:
    ENABLED = 'enabled'
    FOLDER = 'folder'
    MODULE = 'module'
    VERBOSE = 'verbose'
    FORMATTER = 'formatter'


LOG_DEFAULTS = {
    LOG_DEFAULTS_KEYS.ENABLED: False,
    LOG_DEFAULTS_KEYS.FOLDER: '/var/log/secunity',
    LOG_DEFAULTS_KEYS.MODULE: 'secunity',
    LOG_DEFAULTS_KEYS.VERBOSE: False,
    LOG_DEFAULTS_KEYS.FORMATTER: '%(asctime)s - %(levelname)s - %(funcName)s - %(lineno)s - %(message)s',
}


class LOG_LEVEL:
    CRITICAL = 'CRITICAL'
    ERROR = 'ERROR'
    EXCEPTION = 'EXCEPTION'
    WARNING = 'WARNING'
    INFO = 'INFO'
    DEBUG = 'DEBUG'

    @classmethod
    def parse(cls,
              value: str):
        return next(_ for _ in cls.ALL if value == _)

    ALL = (CRITICAL, ERROR, EXCEPTION, WARNING, INFO, DEBUG)


class LException(Exception):

    pass


TException = TypeVar('TException', bound=Union[LException, ValueError, Exception])


class LogMeta(type):

    def __getattr__(cls, item):
        if item.upper() in LOG_LEVEL.ALL:
            func = getattr(cls.logger(), item.lower())
            return func


class Log(metaclass=LogMeta):

    _logger = None

    @classmethod
    def initialize(cls, **kwargs) -> logging.Logger:
        return cls.logger(**kwargs)

    @classmethod
    def logger(cls,
               enabled: Optional[bool] = None,
               folder: Optional[str] = None,
               module: Optional[str] = None,
               verbose: Optional[bool] = None,
               to_stdout: Optional[bool] = True,
               to_stderr: Optional[bool] = False,
               **kwargs) -> logging.Logger:
        if cls._logger:
            return cls._logger
        logger = logging.getLogger(__name__)
        if enabled is not True:
            cls._logger = logger
            return cls._logger

        if not module:
            module = LOG_DEFAULTS[LOG_DEFAULTS_KEYS.MODULE]
        if not folder:
            folder = LOG_DEFAULTS[LOG_DEFAULTS_KEYS.FOLDER]
        try:
            verbose = parse_bool(verbose, parse_str=True) or LOG_DEFAULTS[LOG_DEFAULTS_KEYS.VERBOSE]
        except:
            verbose = LOG_DEFAULTS[LOG_DEFAULTS_KEYS.VERBOSE]

        log_level = logging.DEBUG if verbose else logging.WARNING
        logger.setLevel(log_level)
        print(f'log_level set to {log_level}, verbose: {verbose}')

        handlers = []
        if to_stdout:
            handlers.append(logging.StreamHandler(sys.stdout))
        if to_stderr:
            handlers.append(logging.StreamHandler(sys.stderr))
        logfile = os.path.join(folder, f'{module}.log')
        handlers.append(logging.FileHandler(logfile))

        for handler in handlers:
            handler.setLevel(log_level)
            formatter = logging.Formatter(LOG_DEFAULTS[LOG_DEFAULTS_KEYS.FORMATTER])
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        cls._logger = logger
        return logger

    @staticmethod
    def ex_cls(log: Optional[bool] = False) -> Type[TException]:  # Union[LException, ValueError]:
        return LException if log else ValueError

    @classmethod
    def _raise(cls,
               _raise: Optional[Union[bool, str]] = False,
               **kwargs) -> Optional[TException]:
        if not _raise:
            return None
        if isinstance(_raise, Exception):
            pass
        elif isinstance(_raise, str):
            _raise = cls.ex_cls(log=True)
        elif is_bool(_raise):
            _raise = cls.ex_cls(log=True)
        else:
            return
        raise _raise

    @classmethod
    def critical(cls,
                 msg: str,
                 _raise: Optional[Union[bool, str]] = False,
                 *args, **kwargs):
        cls.logger().critical(msg, *args, **kwargs)
        cls._raise(_raise)

    @classmethod
    def critical_raise(cls,
                       msg: str,
                       ex: Optional[Exception] = None,
                       *args, **kwargs):
        if not ex:
            ex = kwargs.get('exception')
        if ex:
            msg = f'{msg}\n{traceback.format_exc()}'
            _raise = ex
        else:
            _raise = True
        return cls.critical(msg=msg, _raise=_raise, *args, **kwargs)

    @classmethod
    def error(cls,
              msg: str,
              _raise: Optional[Union[bool, str]] = False,
              *args, **kwargs):
        cls.logger().error(msg, *args, **kwargs)
        cls._raise(_raise)

    @classmethod
    def error_raise(cls,
                    msg: str,
                    ex: Optional[Exception] = None,
                    *args, **kwargs):
        if not ex:
            ex = kwargs.get('exception')
        if ex:
            msg = f'{msg}\n{traceback.format_exc()}'
            _raise = ex
        else:
            _raise = True
        return cls.error(msg=msg, _raise=_raise, *args, **kwargs)

    @classmethod
    def exception(cls,
                  msg: str,
                  _raise: Optional[Union[bool, str, Exception]] = False,
                  ex: Optional[Exception] = None,
                  *args, **kwargs):
        if not ex:
            ex = _raise if isinstance(_raise, Exception) else kwargs.get('exception')
        if ex:
            # try:
            #     exc, tb = sys.exc_info()[1:]
            #     trace_str = f'{str(exc)}\n{traceback.format_tb(tb)}'
            # except Exception as AAA:
            #     trace_str = traceback.format_exec()
            msg = f'{traceback.format_exc()}\n{msg}'
        cls.logger().exception(msg, *args, **kwargs)
        cls._raise(_raise)

    @classmethod
    def exception_raise(cls,
                        msg: str,
                        ex: Optional[Exception] = None,
                        *args, **kwargs):
        if not ex:
            ex = kwargs.get('exception')
        if ex:
            msg = f'{msg}\n{traceback.format_exc()}'
            _raise = ex
        else:
            _raise = True
        return cls.exception(msg=msg, _raise=_raise, *args, **kwargs)

    @classmethod
    def info(cls,
             msg: str,
             _raise: Optional[Union[bool, str]] = False,
             *args, **kwargs):
        cls.logger().info(msg, *args, **kwargs)
        cls._raise(_raise)

    @classmethod
    def info_raise(cls,
                   msg: str,
                   ex: Optional[Exception] = None,
                   *args, **kwargs):
        if not ex:
            ex = kwargs.get('exception')
        if ex:
            msg = f'{msg}\n{traceback.format_exc()}'
            _raise = ex
        else:
            _raise = True
        return cls.info(msg=msg, _raise=_raise, *args, **kwargs)

    @classmethod
    def warning(cls,
                msg: str,
                _raise: Optional[Union[bool, str]] = False,
                *args, **kwargs):
        cls.logger().warning(msg, *args, **kwargs)
        cls._raise(_raise)

    @classmethod
    def warning_raise(cls,
                      msg: str,
                      ex: Optional[Exception] = None,
                      *args, **kwargs):
        if not ex:
            ex = kwargs.get('exception')
        if ex:
            msg = f'{msg}\n{traceback.format_exc()}'
            _raise = ex
        else:
            _raise = True
        return cls.warning(msg=msg, _raise=_raise, *args, **kwargs)

    @classmethod
    def debug(cls,
              msg: str,
              _raise: Optional[Union[bool, str]] = False,
              *args, **kwargs):
        cls.logger().debug(msg, *args, **kwargs)
        cls._raise(_raise)

    @classmethod
    def debug_raise(cls,
                    msg: str,
                    ex: Optional[Exception] = None,
                    *args, **kwargs):
        if not ex:
            ex = kwargs.get('exception')
        if ex:
            msg = f'{msg}\n{traceback.format_exc()}'
            _raise = ex
        else:
            _raise = True
        return cls.debug(msg=msg, _raise=_raise, *args, **kwargs)
