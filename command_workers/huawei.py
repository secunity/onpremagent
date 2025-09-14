import re
from typing import Optional, Dict, List, Callable

from command_workers.bases import SshCommandWorker
from common.enums import VENDOR


class HuaweiCommandWorker(SshCommandWorker):
    _default_vpn_name = 'LAB-VPN'

    _get_stats_from_router_command = 'display bgp flow vpnv4 vpn-instance {} routing-table'
    _get_stats_for_sig = 'display flowspec vpnv4 vpn-instance {} statistics {}'

    @property
    def vendor(self) -> VENDOR:
        return VENDOR.HUAWEI

    def execute_cli(self,
                    credentials: Dict[str, object],
                    command: str = None,
                    exec_command: Optional[Callable] = None,
                    **kwargs) -> List[str]:
        vpn_name = kwargs.get('vrf', self._default_vpn_name)

        connection = self.generate_connection(credentials, **kwargs)
        try:
            _, stdout, stderr = connection.exec_command(self._get_stats_from_router_command.format(vpn_name))
            result = stdout.readlines()

            connection.close()
            connection = self.generate_connection(credentials, **kwargs)

            for idx in re.findall(r"ReIndex\s*:\s*(\d+)", '\n'.join(result)):
                try:
                    stdin, stdout, stderr = connection.exec_command(self._get_stats_for_sig.format(vpn_name, idx))
                    for _ in range(10):
                        stdin.write('\n')
                    stdin.flush()
                    result_idx = stdout.readlines()
                    for s in result_idx:
                        print("line", s)
                        result.append(re.sub(r"\s*---- More ----\x1b\[16D\s*\x1b\[16D", "", s))
                except Exception as er:
                    print(f"error idx {idx}: {er}")

            output = [line.rstrip('\r\n') for line in result]

            print(output)

            return output
        finally:
            connection.close()









