import re
import time
from typing import Dict, Any

import paramiko

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


def read_and_wait(shell: paramiko.Channel, prompt: re.Pattern) -> str:
    full_output = []

    while True:
        if shell.recv_ready():
            output = shell.recv(1024).decode("utf-8")
            full_output.append(output)

            if prompt.search(output):
                break

        if shell.exit_status_ready():
            break

        if shell.closed or shell.eof_received or not shell.active:
            break

        time.sleep(0.1)

    return "".join(full_output)
