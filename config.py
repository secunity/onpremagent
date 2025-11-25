import json
import os
from dataclasses import dataclass
from pathlib import Path

SECUNITY_API_URL = f"{os.getenv('SECUNITY_API_URL', default='https://api.secunity.io')}/fstats"


@dataclass
class MongoDBConfig:
    username: str | None = None
    password: str | None = None
    host: str | None = None
    port: int = 27017


@dataclass
class Config:
    identifier: str
    vendor: str
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    vrf: str | None = None

    # MikroTik specific settings
    plaintext_login: bool = True
    encoding: str = "utf-8"

    enable_ipv6: bool = True


def read_config_file(path: Path) -> Config:
    with open(path) as file:
        data = json.load(file)

        if data.get("cloud"):
            pass

        vendor = data.get("vendor")

        port = data.get("port")
        if port is None:
            if vendor == "mikrotik":
                port = 8728  # Default MikroTik API port
            else:
                port = 22  # Default SSH port for other vendors

        enable_ipv6 = data.get("enable_ipv6", True)

        return Config(
            identifier=data["identifier"],
            host=data.get("host"),
            port=port,
            vendor=data.get("vendor"),
            vrf=data.get("vrf"),
            username=data.get("username"),
            password=data.get("password"),
            plaintext_login=data.get("plaintext_login", True),
            encoding=data.get("encoding", "utf-8"),
            enable_ipv6=enable_ipv6,
        )
