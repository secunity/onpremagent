import collections
from typing import override

import routeros_api
from routeros_api.api import RouterOsApi
from routeros_api.api_structure import StringField
from routeros_api.exceptions import RouterOsApiError
from routeros_api.resource import RouterOsResource

from onpremagent.connectors.base import BaseConnector
from onpremagent.connectors.mikrotik_routeros_api.settings import (
    MikrotikRouterOsApiSettings,
)


class MikrotikRouterOsApiConnector(BaseConnector[MikrotikRouterOsApiSettings]):
    def __init__(self, settings: MikrotikRouterOsApiSettings) -> None:
        super().__init__(settings)

        self.connection = routeros_api.RouterOsApiPool(
            host=self.settings.host,
            port=self.settings.port,
            username=self.settings.username,
            password=self.settings.password.get_secret_value(),
            plaintext_login=self.settings.plaintext_login,
        )

        self.api: RouterOsApi = self.connection.get_api()

        self.resource_ipv4 = self.api.get_resource(
            "/ip/firewall/raw",
            structure=collections.defaultdict(
                lambda: StringField(encoding=self.settings.encoding)
            ),
        )
        self.resource_ipv6 = self.api.get_resource(
            "/ipv6/firewall/raw",
            structure=collections.defaultdict(
                lambda: StringField(encoding=self.settings.encoding)
            ),
        )

    @override
    def connect(self) -> None:
        pass

    @override
    def disconnect(self) -> None:
        pass

    @override
    def setup(self) -> None:
        pass

    @override
    def cleanup(self) -> None:
        pass
