import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from mqtt_service import get_mqtt_service_config
from core import (
    ALARMS,
    PLANT_STATUS,
    REGISTERS,
    Register,
    alarm_is_active,
    decode_register,
    register_groups,
    validate_slave_id,
)


LOGGER = logging.getLogger("smartlogger")
MODEL = "SmartLogger V300R024C10SPC161"
MODBUS_TIMEOUT = 5
DISCOVERY_PREFIX = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant")


def load_options() -> tuple[str, int, int, int]:
    with Path("/data/options.json").open(encoding="utf-8") as options_file:
        options = json.load(options_file)

    host = options.get("modbus_host")
    port = options.get("modbus_port")
    slave_id = validate_slave_id(options.get("modbus_slave_id", 0))
    scan_interval = options.get("scan_interval")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("Set modbus_host to the SmartLogger's IP address or hostname.")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("modbus_port must be between 1 and 65535.")
    if not isinstance(scan_interval, int) or not 5 <= scan_interval <= 3600:
        raise ValueError("scan_interval must be between 5 and 3600 seconds.")
    return host.strip(), port, slave_id, scan_interval


def stable_key(host: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_")
    return key or "smartlogger"


def mqtt_client(host: str) -> mqtt.Client:
    config = get_mqtt_service_config()

    key = stable_key(host)
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"smartlogger_{key}",
        protocol=mqtt.MQTTv311,
    )
    if config.username:
        client.username_pw_set(config.username, config.password)
    if config.ssl:
        client.tls_set()

    availability_topic = f"smartlogger/{key}/availability"
    client.will_set(availability_topic, payload="offline", qos=1, retain=True)
    client.on_connect = lambda connected_client, userdata, flags, reason, properties: (
        on_connect(
            connected_client,
            host,
            key,
            availability_topic,
            reason,
        )
    )
    client.connect_async(config.host, config.port, keepalive=60)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.loop_start()
    return client


def discovery_entities(host: str, key: str, availability_topic: str) -> list[dict[str, Any]]:
    device = {
        "identifiers": [f"huawei_smartlogger_{key}"],
        "name": f"Huawei SmartLogger ({host})",
        "manufacturer": "Huawei",
        "model": MODEL,
    }
    state_prefix = f"smartlogger/{key}/state"
    entities: list[dict[str, Any]] = []

    for register in REGISTERS:
        entity: dict[str, Any] = {
            "name": register.name,
            "unique_id": f"huawei_smartlogger_{key}_{register.key}",
            "state_topic": f"{state_prefix}/{register.key}",
            "availability_topic": availability_topic,
            "device": device,
            "entity_category": "diagnostic"
            if register.key.startswith("alarm_info_")
            else None,
        }
        if register.unit:
            entity["unit_of_measurement"] = register.unit
        if register.device_class:
            entity["device_class"] = register.device_class
        if register.state_class:
            entity["state_class"] = register.state_class
        if register.key == "plant_status":
            entity["options"] = list(PLANT_STATUS.values())
        entities.append(
            {
                "component": "sensor",
                "key": register.key,
                "config": {name: value for name, value in entity.items() if value is not None},
            }
        )

    for alarm in ALARMS:
        entities.append(
            {
                "component": "binary_sensor",
                "key": alarm.key,
                "config": {
                    "name": alarm.name,
                    "unique_id": f"huawei_smartlogger_{key}_{alarm.key}",
                    "state_topic": f"{state_prefix}/{alarm.key}",
                    "availability_topic": availability_topic,
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device_class": "problem",
                    "entity_category": "diagnostic",
                    "device": device,
                },
            }
        )
    return entities


def publish_discovery(
    client: mqtt.Client,
    host: str,
    key: str,
    availability_topic: str,
) -> None:
    for entity in discovery_entities(host, key, availability_topic):
        topic = (
            f"{DISCOVERY_PREFIX}/{entity['component']}/{key}/"
            f"{entity['key']}/config"
        )
        client.publish(topic, json.dumps(entity["config"]), qos=1, retain=True)


def read_registers(host: str, port: int, slave_id: int) -> dict[int, int]:
    client = ModbusTcpClient(host, port=port, timeout=MODBUS_TIMEOUT)
    try:
        if not client.connect():
            raise OSError(f"Could not connect to Modbus TCP endpoint {host}:{port}.")

        values: dict[int, int] = {}
        for address, count in register_groups():
            response = client.read_holding_registers(
                address=address,
                count=count,
                device_id=slave_id,
            )
            if response.isError():
                raise ModbusException(
                    f"Modbus exception while reading holding registers "
                    f"{address}-{address + count - 1}: {response}"
                )
            if len(response.registers) != count:
                raise ModbusException(
                    f"Expected {count} registers at {address}, got "
                    f"{len(response.registers)}."
                )
            values.update(
                (address + offset, value)
                for offset, value in enumerate(response.registers)
            )
        return values
    finally:
        client.close()


def publish_states(
    client: mqtt.Client,
    host: str,
    key: str,
    availability_topic: str,
    values: dict[int, int],
) -> None:
    raw_by_key = {register.key: decode_register(register, values) for register in REGISTERS}
    state_prefix = f"smartlogger/{key}/state"

    for register in REGISTERS:
        value = raw_by_key[register.key]
        if register.key == "plant_status":
            state = PLANT_STATUS.get(int(value), f"Unknown ({int(value)})")
        elif isinstance(value, float):
            state = format(value, ".10g")
        else:
            state = str(value)
        client.publish(
            f"{state_prefix}/{register.key}",
            payload=state,
            qos=1,
            retain=True,
        )

    for alarm in ALARMS:
        alarm_value = int(raw_by_key[alarm.register_key])
        state = "ON" if alarm_is_active(alarm, {alarm.register_key: alarm_value}) else "OFF"
        client.publish(
            f"{state_prefix}/{alarm.key}",
            payload=state,
            qos=1,
            retain=True,
        )

    client.publish(availability_topic, payload="online", qos=1, retain=True)


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host, port, slave_id, scan_interval = load_options()
    key = stable_key(host)
    availability_topic = f"smartlogger/{key}/availability"
    client = mqtt_client(host)

    try:
        while True:
            if not client.is_connected():
                time.sleep(1)
                continue
            try:
                values = read_registers(host, port, slave_id)
                publish_states(client, host, key, availability_topic, values)
                LOGGER.debug(
                    "Published telemetry from %s:%s (Modbus slave ID %s)",
                    host,
                    port,
                    slave_id,
                )
            except (OSError, TimeoutError, ModbusException, ValueError) as error:
                LOGGER.warning("SmartLogger read failed: %s", error)
                client.publish(availability_topic, payload="offline", qos=1, retain=True)
            time.sleep(scan_interval)
    except KeyboardInterrupt:
        LOGGER.info("Stopping SmartLogger MQTT add-on.")
    finally:
        client.loop_stop()
        client.disconnect()


def on_connect(
    client: mqtt.Client,
    host: str,
    key: str,
    availability_topic: str,
    reason_code: mqtt.ReasonCode,
) -> None:
    if reason_code.is_failure:
        LOGGER.warning("Could not connect to MQTT broker: %s", reason_code)
        return
    LOGGER.info("Connected to MQTT broker; publishing Home Assistant discovery.")
    client.publish(availability_topic, payload="offline", qos=1, retain=True)
    publish_discovery(client, host, key, availability_topic)


if __name__ == "__main__":
    run()
