import enum
from ipaddress import IPv4Network, IPv6Network
from typing import Annotated, Any, Literal

from annotated_types import Ge, Le
from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
)

from onpremagent.utils.tcp_flags import tcp_flags_parser

type OneOrMany[T] = T | list[T]


def parse_range(value: str) -> str:
    try:
        start, end = value.split("-", maxsplit=1)
        start, end = int(start), int(end)
        if start < 0 or end < 0:
            raise ValueError(f"Range values must be non-negative, got {start}-{end}")
        if start > end:
            raise ValueError(f"Range start must be <= end, got {start}-{end}")
        return f"{start}-{end}"
    except Exception as err:
        raise ValueError(f"Invalid Range: {value}") from err


type RangeAnnotated[T] = Annotated[str, BeforeValidator(parse_range)]


type PortNumber = Annotated[int, Ge(0), Le(65535)]

type PortValue = PortNumber | RangeAnnotated[PortNumber]


def parse_tcp_flags(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    try:
        return tcp_flags_parser.parse(value)
    except Exception as err:
        raise ValueError(f"Invalid TCP flags: {value}") from err


type TcpNumber = Annotated[int, Ge(0), Le(255)]

type TcpValue = Annotated[TcpNumber, BeforeValidator(parse_tcp_flags)]


type ProtocolString = Literal["tcp", "udp", "icmp", "gre", "esp"]

type ProtocolNumber = Annotated[int, Ge(0), Le(255)]

type ProtocolValue = ProtocolString | ProtocolNumber


type PacketLengthNumber = Annotated[int, Ge(0), Le(65_535)]

type PacketLengthValue = PacketLengthNumber | RangeAnnotated[PacketLengthNumber]


def parse_bps(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    if value.startswith("k"):
        factor = 1_000
        value = value[1:]
    elif value.startswith("m"):
        factor = 1_000_000
        value = value[1:]
    elif value.startswith("g"):
        factor = 1_000_000_000
        value = value[1:]
    else:
        raise ValueError(f"Invalid bps value: {value}")

    return value * factor


type BpsNumber = Annotated[int, Ge(0)]

type BpsValue = Annotated[BpsNumber, BeforeValidator(parse_bps)]


def parse_pps(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    if value.startswith("k"):
        factor = 1_000
        value = value[1:]
    elif value.startswith("m"):
        factor = 1_000_000
        value = value[1:]
    else:
        raise ValueError(f"Invalid pps value: {value}")

    return value * factor


type PpsNumber = Annotated[int, Ge(0)]

type PpsValue = Annotated[PpsNumber, BeforeValidator(parse_pps)]


class Family(enum.StrEnum):
    INET = "inet"
    INET6 = "inet6"


class FirewallRuleActionDiscard(BaseModel):
    type: Literal["discard"] = Field(description="Action to discard matching packets")


class FirewallRuleActionBpsLimit(BaseModel):
    type: Literal["bps-limit"] = Field(
        description="Action to rate-limit matching packets based on bits per second"
    )
    bps: BpsValue = Field(description="Maximum bits per second")


class FirewallRuleActionPpsLimit(BaseModel):
    type: Literal["pps-limit"] = Field(
        description="Action to rate-limit matching packets based on packets per second"
    )
    pps: PpsValue = Field(description="Maximum packets per second")


class FirewallRuleActionAccept(BaseModel):
    type: Literal["accept"] = Field(description="Action to accept matching packets")


class BaseFirewallRule[T](BaseModel):
    id: str = Field(description="Unique ID of the firewall rule")
    source_address: T | None = Field(
        default=None, description="Source IP address or subnet"
    )
    destination_address: T | None = Field(
        default=None, description="Destination IP address or subnet"
    )
    protocol: ProtocolValue | None = Field(
        default=None, description="Protocol (e.g., tcp, udp, icmp, or protocol number)"
    )
    source_port: OneOrMany[PortValue] | None = Field(
        default=None, description="Source port number or range (e.g., 80, 1000-2000)"
    )
    destination_port: OneOrMany[PortValue] | None = Field(
        default=None,
        description="Destination port number or range (e.g., 80, 1000-2000)",
    )
    tcp_flags: TcpValue | None = Field(
        default=None,
        description="List of TCP flags (e.g., syn, ack, or number representing flags)",
    )
    packet_length: PacketLengthValue | None = Field(
        default=None,
        description="Packet length or range in bytes (e.g., 100, 500-1000)",
    )
    action: (
        FirewallRuleActionDiscard
        | FirewallRuleActionBpsLimit
        | FirewallRuleActionPpsLimit
        | FirewallRuleActionAccept
    ) = Field(
        description="Action(s) to apply to matching packets",
        discriminator="type",
    )

    dropped_bytes: int | None = Field(
        default=None,
        description="Dropped bytes",
    )
    dropped_packets: int | None = Field(
        default=None,
        description="Dropped packets",
    )
    matched_bytes: int | None = Field(
        default=None,
        description="Matched bytes",
    )
    matched_packets: int | None = Field(
        default=None,
        description="Matched packets",
    )

    @property
    def family(self) -> Family:
        if isinstance(self.source_address, IPv6Network) or isinstance(
            self.destination_address, IPv6Network
        ):
            return Family.INET6
        return Family.INET


class FirewallRule(BaseFirewallRule[IPv4Network | IPv6Network]):
    pass
