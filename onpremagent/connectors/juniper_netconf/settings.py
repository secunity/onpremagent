from typing import ClassVar, Literal

from pydantic import BaseModel, Field, SecretStr


class JuniperNetconfSettings(BaseModel):
    name: ClassVar[str] = "juniper_netconf"

    type: Literal["juniper_netconf"]

    host: str = Field(description="Hostname or IP address of the device")
    port: int = Field(default=830, description="NETCONF port number")
    username: str = Field(description="Username for authentication")
    password: SecretStr = Field(description="Password for authentication")
    timeout: int | None = Field(
        default=None, description="Connection timeout in seconds"
    )

    ephemeral_instance: str = Field(
        description="Name of the ephemeral configuration instance"
    )

    filter_name: str = Field(description="Name of the firewall filter to be used")

    interface: str = Field(description="Interface name")
    interface_unit: int = Field(description="Interface unit number")
