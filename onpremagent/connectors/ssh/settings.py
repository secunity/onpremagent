from typing import ClassVar, Literal

from pydantic import BaseModel, Field, SecretStr


class SSHSettings(BaseModel):
    name: ClassVar[str] = "ssh"

    type: Literal["ssh"]

    host: str = Field(
        description="Hostname or IP address of the SSH device",
    )
    port: int = Field(
        default=22,
        description="TCP port for the SSH connection (default is 22)",
    )
    username: str = Field(
        description="Username for authenticating to the SSH device",
    )
    password: SecretStr = Field(
        description="Password for authenticating to the SSH device"
    )
    timeout: int = Field(
        default=10,
        description="Connection timeout in seconds (default is 10)",
    )

    vendor: str = Field(
        description="Vendor of the SSH device",
    )
    model: str = Field(
        default="",
        description="Model of the SSH device",
    )
    vrf: str = Field(
        default="",
        description="VRF name",
    )
