import os.path
import time
from typing import Optional, Union, Iterable, Tuple, List

from common.logs import Log


class FILE:
    SUCCESS_API = 'success-api'
    FAILED_API = 'failed-api'
    SUCCESS_ROUTER = 'success-router'
    FAILED_ROUTER = 'failed-router'

    ALL = (SUCCESS_API, FAILED_API, SUCCESS_ROUTER, FAILED_ROUTER)


_LOCK_FILES = {
    _: f'/tmp/secunity-{_}.lock'
    for _ in FILE.ALL
}


class MODE:
    READ = 'r'
    WRITE = 'w'
    APPEND = 'a'


_FILE_FILES = {
    _: os.path.join('/var/log/secunity', f'{_}.log')
    for _ in FILE.ALL
}


def _write_line(handle,
                line: str,
                newline: Optional[bool] = True):
    handle.write(line)
    if newline:
        handle.write('\n')


def _get_file_path_and_mode(file: Union[FILE, str],
                            mode: Optional[Union[MODE, str]] = None) -> Tuple[str, Union[MODE, str]]:
    file_path = _FILE_FILES.get(file)
    if not file_path:
        Log.error_raise(f'invalid file: "{file}"')
    if not mode:
        mode = MODE.APPEND
    return file_path, mode


def read_file(file: Union[FILE, str],
              lock: Optional[bool] = False) -> Optional[List[str]]:
    file_path, mode = _get_file_path_and_mode(file=file, mode=MODE.READ)
    if not os.path.isfile(file_path):
        Log.warning(f'the file "{file_path}" does not exist')
        return None

    def _read() -> List[str]:
        with open(file_path, mode=mode) as f:
            data = f.read()
        lines = [_.strip('\r') for _ in data.split('\n')]
        return lines

    if lock:
        lock_file = _LOCK_FILES.get(file)
        if not lock_file:
            Log.error_raise(f'invalid lock: "{lock}"')
        with FileLock(filename=lock_file, mode='w'):
            return _read()
    else:
        return _read()


def write_line(file: Union[FILE, str],
               line: Union[str, Iterable[str]],
               lock: Optional[bool] = False,
               mode: Optional[Union[MODE, str]] = None):
    if not line:
        return
    file_path, mode = _get_file_path_and_mode(file=file, mode=mode)
    lines = [line] if isinstance(line, str) else list(line)
    if lock:
        lock_file = _LOCK_FILES.get(file)
        if not lock_file:
            Log.error_raise(f'invalid lock: "{lock}"')
        with FileLock(filename=lock_file, mode='w', retries=5, sleep=0.1):
            with open(file_path, mode=mode) as f:
                for line in lines:
                    _write_line(handle=f, line=line, newline=True)
    else:
        with open(file_path, mode=mode) as f:
            for line in lines:
                _write_line(handle=f, line=line, newline=True)


class FileLock:

    __DEFAULTS__ = {
        'retries': 3,
        'sleep': 0.1,
        'mode': 'w'
    }

    def __init__(self,
                 filename: str,
                 retries: Optional[int] = None,
                 sleep: Optional[Union[int, float]] = None,
                 mode: Optional[Union[str, MODE]] = None):
        """
        Perform file lock. Performs several attempts to lock the file
        """
        self._filename = filename
        if not retries:
            retries = self.__DEFAULTS__['retries']
        self._retries = retries
        if not sleep:
            sleep = self.__DEFAULTS__['sleep']
        self._sleep = sleep
        if not mode:
            mode = self.__DEFAULTS__['mode']
        self._mode = mode
        self._handle = None

    def __enter__(self):
        for attempt in range(self._retries):
            try:
                self._handle = open(self._filename, self._mode)
                return self._handle
            except Exception as ex:
                if attempt < self._retries:
                    time.sleep(self._sleep)
                else:
                    raise ex

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._handle and not self._handle.closed:
            self._handle.close()
