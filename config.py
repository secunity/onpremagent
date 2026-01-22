import base64
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cachetools.func
from bson import ObjectId
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pymongo import MongoClient

type CallableConfig = Callable[[], Config]

SECUNITY_API_URL = (
    f"{os.getenv('SECUNITY_API_URL', default='https://api.secunity.io')}/fstats"
)

logger = logging.getLogger("config")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)8s - %(lineno)s - %(message)s"
    )
)

logger.addHandler(console_handler)

client: MongoClient | None = None


@dataclass
class MongoDBConfig:
    username: str
    password: str
    host: str
    port: int
    db_name: str


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

    cloud: bool = False
    mongodb: MongoDBConfig | None = None


def decrypt_symmetric(data: bytes, key: str) -> bytes:
    key = base64.b64decode(key.encode())
    data = base64.b64decode(data)
    iv = data[:16]
    cipher = Cipher(algorithms.AES(key), modes.CFB8(iv))
    decryptor = cipher.decryptor()
    return decryptor.update(data[16:]) + decryptor.finalize()


def get_credentials_from_db(db_config: MongoDBConfig, identifier: str):
    global client

    logger.debug("Get credentials from db: %s", db_config)

    if client is None:
        client = MongoClient(
            host=db_config.host,
            port=db_config.port,
            username=db_config.username,
            password=db_config.password,
        )

    db = client[db_config.db_name]

    key = db.SecunitySettings.find_one("cipher-symetric_default")["value"]

    account_network_devices = db.AccountNetworkDevices.find_one(
        {
            "client.flowspec.stats_settings.use_agent": True,
            "client.flowspec.stats_settings.agent_id": ObjectId(identifier),
        }
    )

    if not account_network_devices:
        logger.error("Failed to get account network device from db")
        return None

    ssh_settings = (
        account_network_devices.get("client", {})
        .get("flowspec", {})
        .get("ssh_settings", {})
    )

    username = ssh_settings.get("username")
    password = decrypt_symmetric(ssh_settings.get("password"), key)
    host = ssh_settings.get("ip")

    vendor = account_network_devices.get("vendor")

    port = ssh_settings.get("port")
    if port is None:
        if vendor == "mikrotik":
            port = 8728
        else:
            port = 22

    vrf = account_network_devices.get("default_stats_interface_name")

    enable_ipv6 = account_network_devices.get("enable_ipv6", True)
    plaintext_login = account_network_devices.get("plaintext_login", True)
    encoding = account_network_devices.get("encoding", "utf-8")

    config = Config(
        identifier=identifier,
        host=host,
        port=port,
        vendor=vendor,
        vrf=vrf,
        username=username,
        password=password,
        plaintext_login=plaintext_login,
        encoding=encoding,
        enable_ipv6=enable_ipv6,
    )

    logger.debug("Credentials from DB: %s", config)

    return config


@cachetools.func.ttl_cache(ttl=60)
def read_config_file(path: Path) -> Config:
    with open(path) as file:
        data = json.load(file)

        cloud = data.get("cloud", False)

        mongodb = data.get("mongodb")
        if mongodb and cloud:
            mongodb_config = MongoDBConfig(
                host=mongodb.get("host"),
                port=mongodb.get("port", 27017),
                username=mongodb.get("username"),
                password=mongodb.get("password"),
                db_name=mongodb.get("db_name", "secunity"),
            )

            return get_credentials_from_db(mongodb_config, data["identifier"])

        vendor = data.get("vendor")

        port = data.get("port")
        if port is None:
            if vendor == "mikrotik":
                port = 8728  # Default MikroTik API port
            else:
                port = 22  # Default SSH port for other vendors

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
            enable_ipv6=data.get("enable_ipv6", True),
        )
