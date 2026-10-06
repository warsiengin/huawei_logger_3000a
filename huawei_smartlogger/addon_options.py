"""Validated configuration loaded from Home Assistant add-on options."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core import validate_slave_id


def stable_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return key or "smartlogger"


@dataclass(frozen=True)
class AddonOptions:
    modbus_host: str
    modbus_port: int
    modbus_slave_id: int
    scan_interval: int
    mqtt_host: str
    mqtt_port: int
    mqtt_username: str
    mqtt_password: str
    mqtt_ssl: bool
    mqtt_topic_prefix: str
    instance_id: str

    @property
    def key(self) -> str:
        return stable_key(self.instance_id)

    @property
    def availability_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/{self.instance_id}/availability"

    @property
    def state_prefix(self) -> str:
        return f"{self.mqtt_topic_prefix}/{self.instance_id}/state"


def load_options(path: str | Path = "/data/options.json") -> AddonOptions:
    with Path(path).open(encoding="utf-8") as options_file:
        options = json.load(options_file)

    host = options.get("modbus_host")
    port = options.get("modbus_port")
    slave_id = validate_slave_id(options.get("modbus_slave_id", 0))
    scan_interval = options.get("scan_interval")
    mqtt_host = options.get("mqtt_host", "core-mosquitto")
    mqtt_port = options.get("mqtt_port", 1883)
    mqtt_username = options.get("mqtt_username", "")
    mqtt_password = options.get("mqtt_password", "")
    mqtt_ssl = options.get("mqtt_ssl", False)
    mqtt_topic_prefix = options.get("mqtt_topic_prefix", "smartlogger")
    instance_id = options.get("instance_id", "")

    if not isinstance(host, str) or not host.strip():
        raise ValueError("Set modbus_host to the SmartLogger's IP address or hostname.")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("modbus_port must be between 1 and 65535.")
    if (
        isinstance(scan_interval, bool)
        or not isinstance(scan_interval, int)
        or not 5 <= scan_interval <= 3600
    ):
        raise ValueError("scan_interval must be between 5 and 3600 seconds.")
    if not isinstance(mqtt_host, str) or not mqtt_host.strip():
        raise ValueError("Set mqtt_host to the MQTT broker's IP address or hostname.")
    if (
        isinstance(mqtt_port, bool)
        or not isinstance(mqtt_port, int)
        or not 1 <= mqtt_port <= 65535
    ):
        raise ValueError("mqtt_port must be between 1 and 65535.")
    if not isinstance(mqtt_username, str) or not isinstance(mqtt_password, str):
        raise ValueError("MQTT username and password must be strings.")
    if bool(mqtt_username) != bool(mqtt_password):
        raise ValueError("Set both MQTT username and password, or leave both blank.")
    if not isinstance(mqtt_ssl, bool):
        raise ValueError("mqtt_ssl must be true or false.")
    if not isinstance(mqtt_topic_prefix, str):
        raise ValueError("mqtt_topic_prefix must be a string.")

    mqtt_topic_prefix = mqtt_topic_prefix.strip("/")
    if not mqtt_topic_prefix or any(
        not re.fullmatch(r"[A-Za-z0-9_-]+", segment)
        for segment in mqtt_topic_prefix.split("/")
    ):
        raise ValueError(
            "mqtt_topic_prefix must contain non-empty topic segments using only "
            "letters, numbers, underscores, and hyphens."
        )

    if not isinstance(instance_id, str):
        raise ValueError("instance_id must be a string.")
    instance_id = instance_id.strip() or stable_key(host.strip())
    if not re.fullmatch(r"[A-Za-z0-9_-]+", instance_id):
        raise ValueError(
            "instance_id must use only letters, numbers, underscores, and hyphens."
        )

    return AddonOptions(
        modbus_host=host.strip(),
        modbus_port=port,
        modbus_slave_id=slave_id,
        scan_interval=scan_interval,
        mqtt_host=mqtt_host.strip(),
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        mqtt_ssl=mqtt_ssl,
        mqtt_topic_prefix=mqtt_topic_prefix,
        instance_id=instance_id,
    )
