try:
    import paramiko
    SSH_PORT = paramiko.config.SSH_PORT
except:
    SSH_PORT = 22

BOOL_VALUES = (True, False)


class DEFAULT_KEYS:
    CONFIG = 'config'
    DATETIME_FORMAT = 'datetime_format'
    SUPERVISOR_PATH = 'supervisor_path'
    LAST_SUCCESS_FILE = '/etc/secunity/last.log'
    FAILED_FILE = '/etc/secunity/failed.log'


DEFAULTS = {
    DEFAULT_KEYS.CONFIG: '/etc/secunity/secunity.conf',
    DEFAULT_KEYS.DATETIME_FORMAT: '%Y-%m-%d %H:%M:%S',
    DEFAULT_KEYS.SUPERVISOR_PATH: "/etc/supervisor/conf.d/secunity.conf",
}


class PROGRAM:
    STATS_FETCHER = 'stats_fetcher'
    FLOWS_APPLIER = 'flows_applier'
    FLOWS_SYNC = 'flows_sync'
    DEVICE_CONTROLLER = 'device_controller'

    ALL = (STATS_FETCHER, FLOWS_APPLIER, FLOWS_SYNC, DEVICE_CONTROLLER)

