from typing import ClassVar, Literal

from pydantic import BaseModel, Field, SecretStr


class MikrotikRouterOsApiSettings(BaseModel):
    name: ClassVar[str] = "mikrotik_routeros_api"

    type: Literal["mikrotik_routeros_api"]

    host: str = Field(
        description="Hostname or IP address of the MikroTik RouterOS device"
    )
    port: int = Field(
        default=8728,
        description="TCP port for the RouterOS API (8728 for plaintext, 8729 for SSL)",
    )
    username: str = Field(
        description="Username for authenticating to the RouterOS device"
    )
    password: SecretStr = Field(
        description="Password for authenticating to the RouterOS device"
    )
    plaintext_login: bool = Field(
        default=True,
        description="Use plaintext login method, required for RouterOS 6.43 and newer",
    )
    encoding: str = Field(
        default="utf-8",
        description="Character encoding used to decode responses from the device",
    )

    firewall_rule_prefix: str = Field(
        default="FlowSec_",
        description="Prefix added to firewall rule comments to identify rules managed by this connector",
    )
