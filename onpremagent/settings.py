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

    flowsec_url: str = Field(
        default="http://localhost:8000",
        description="URL of the FlowSec API",
    )

    sync_interval: int = Field(
        default=10,
        description="Interval in seconds between syncs",
    )
    send_statistics_interval: int = Field(
        default=60,
        description="Interval in seconds between sending statistics",
    )
    connectivity_checker_interval: int = Field(
        default=30,
        description="Interval in seconds between connectivity checks",
    )

    connectivity_timeout: int = Field(
        default=60,
        description="Time in seconds after which, if no heartbeat is received, the agent is considered disconnected",
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level (e.g. DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    run_sync_worker: bool = Field(
        default=True,
        description="Whether to run the sync worker that periodically syncs firewall rules with the FlowSec API",
    )
    run_statistics_worker: bool = Field(
        default=True,
        description="Whether to run the statistics worker that periodically sends statistics to the FlowSec API",
    )
    run_connectivity_checker: bool = Field(
        default=True,
        description="Whether to run the connectivity checker that periodically checks connectivity with the FlowSec API",
    )
