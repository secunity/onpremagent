from typing import ClassVar, Literal

from pydantic import BaseModel, Field


class FortiGateSettings(BaseModel):
    name: ClassVar[str] = "fortigate"

    type: Literal["fortigate"]

    host: str = Field(
        description="Hostname or IP address of the fortigate EMS server"
    )
    token: str = Field(
        description="API token used to authenticate with the fortigate API"
    )
    prefix: str = Field(
        default="",
        description="Prefix prepended to created object and rule names",
    )
    ssl_verify: bool = Field(
        default=False,
        description="Whether to verify the server's SSL certificate",
    )
    src_if: str = Field(
        default="any",
        description="Source interface for created firewall rules",
    )
    dst_if: str = Field(
        default="any",
        description="Destination interface for created firewall rules",
    )
    comment: str = Field(
        default="Created by Flowsec Agent. Created at {timestamp}",
        description="Comment attached to objects and rules created by the agent",
    )
