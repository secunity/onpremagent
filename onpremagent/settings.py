from pydantic import BaseModel, Field

from onpremagent.connectors.fortigate.settings import FortiGateSettings


class Settings(BaseModel):
    """Top-level configuration for the firewall management tool."""

    connector: FortiGateSettings = Field(..., discriminator="type")

    identifier: str = Field(
        description="Unique identifier for the agent",
    )

    dry_run: bool = Field(
        default=False,
        description="If true, the connector will not make any changes to the device and will only log the intended actions",
    )
