from typing import Dict, Any

from common.configs import CONFIG_KEY
from common.consts import SSH_PORT


class SSH_DEFAULTS_KEYS:
    PORT = 'port'
    WARN = 'warn'
    PTY = 'pty'
    TIMEOUT = 'timeout'

    ALL_KEYS = (PORT, WARN, PTY, TIMEOUT)


SSH_DEFAULTS = {
    SSH_DEFAULTS_KEYS.PORT: SSH_PORT,
    SSH_DEFAULTS_KEYS.WARN: False,
    SSH_DEFAULTS_KEYS.PTY: True,
    SSH_DEFAULTS_KEYS.TIMEOUT: 30
}


def get_ssh_credentials_from_config(config: Dict[str, Any]) -> Dict[str, Any]:
    result = {
        k: v for k, v in config.items()
        if k in CONFIG_KEY.SSH_CONFIG_KEYS
        and v is not None
    }
    if result.get('username') and not result.get('user'):
        result['user'] = result['username']
    elif result.get('user') and not result.get('username'):
        result['username'] = result['user']
    return result

