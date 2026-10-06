import json
import logging
import os
import time
from typing import Any

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from addon_options import AddonOptions, load_options
from mqtt_service import get_mqtt_service_config
from core import (
    ALARMS,
    PLANT_STATUS,
    REGISTERS,
    Register,
    alarm_is_active,
    decode_register,
    register_groups,
)


LOGGER = logging.getLogger("smartlogger")
MODEL = "SmartLogger V300R024C10SPC161"
MODBUS_TIMEOUT = 5
DISCOVERY_PREFIX = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant")


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


def mqtt_client(options: AddonOptions) -> mqtt.Client:
    username = options.mqtt_username
    password = options.mqtt_password
    use_tls = options.mqtt_ssl
    if not username:
        service_config = get_mqtt_service_config()
        username = service_config.username or ""
        password = service_config.password or ""
        use_tls = service_config.ssl

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"smartlogger_{options.key}",
        protocol=mqtt.MQTTv311,
    )
    if username:
        client.username_pw_set(username, password)
    if use_tls:
        client.tls_set()

    client.will_set(
        options.availability_topic,
        payload="offline",
        qos=1,
        retain=True,
    )
    client.on_connect = lambda connected_client, userdata, flags, reason, properties: (
        on_connect(
            connected_client,
            options,
            reason,
        )
    )
    client.connect_async(options.mqtt_host, options.mqtt_port, keepalive=60)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.loop_start()
    return client


def discovery_entities(options: AddonOptions) -> list[dict[str, Any]]:
    device = {
        "identifiers": [f"huawei_smartlogger_{options.key}"],
        "name": f"Huawei SmartLogger ({options.modbus_host})",
        "manufacturer": "Huawei",
        "model": MODEL,
    }
    entities: list[dict[str, Any]] = []

    for register in REGISTERS:
        entity: dict[str, Any] = {
            "name": register.name,
            "unique_id": f"huawei_smartlogger_{options.key}_{register.key}",
            "state_topic": f"{options.state_prefix}/{register.key}",
            "availability_topic": options.availability_topic,
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
                    "unique_id": f"huawei_smartlogger_{options.key}_{alarm.key}",
                    "state_topic": f"{options.state_prefix}/{alarm.key}",
                    "availability_topic": options.availability_topic,
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
    options: AddonOptions,
) -> None:
    for entity in discovery_entities(options):
        topic = (
            f"{DISCOVERY_PREFIX}/{entity['component']}/{options.key}/"
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
    options: AddonOptions,
    values: dict[int, int],
) -> None:
    raw_by_key = {register.key: decode_register(register, values) for register in REGISTERS}

    for register in REGISTERS:
        value = raw_by_key[register.key]
        if register.key == "plant_status":
            state = PLANT_STATUS.get(int(value), f"Unknown ({int(value)})")
        elif isinstance(value, float):
            state = format(value, ".10g")
        else:
            state = str(value)
        client.publish(
            f"{options.state_prefix}/{register.key}",
            payload=state,
            qos=1,
            retain=True,
        )

    for alarm in ALARMS:
        alarm_value = int(raw_by_key[alarm.register_key])
        state = "ON" if alarm_is_active(alarm, {alarm.register_key: alarm_value}) else "OFF"
        client.publish(
            f"{options.state_prefix}/{alarm.key}",
            payload=state,
            qos=1,
            retain=True,
        )

    client.publish(options.availability_topic, payload="online", qos=1, retain=True)


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    options = load_options()
    client = mqtt_client(options)

    try:
        while True:
            if not client.is_connected():
                time.sleep(1)
                continue
            try:
                values = read_registers(
                    options.modbus_host,
                    options.modbus_port,
                    options.modbus_slave_id,
                )
                publish_states(client, options, values)
                LOGGER.debug(
                    "Published telemetry from %s:%s (Modbus slave ID %s)",
                    options.modbus_host,
                    options.modbus_port,
                    options.modbus_slave_id,
                )
            except (OSError, TimeoutError, ModbusException, ValueError) as error:
                LOGGER.warning("SmartLogger read failed: %s", error)
                client.publish(
                    options.availability_topic,
                    payload="offline",
                    qos=1,
                    retain=True,
                )
            time.sleep(options.scan_interval)
    except KeyboardInterrupt:
        LOGGER.info("Stopping SmartLogger MQTT add-on.")
    finally:
        client.loop_stop()
        client.disconnect()


def on_connect(
    client: mqtt.Client,
    options: AddonOptions,
    reason_code: mqtt.ReasonCode,
) -> None:
    if reason_code.is_failure:
        LOGGER.warning("Could not connect to MQTT broker: %s", reason_code)
        return
    LOGGER.info("Connected to MQTT broker; publishing Home Assistant discovery.")
    client.publish(
        options.availability_topic,
        payload="offline",
        qos=1,
        retain=True,
    )
    publish_discovery(client, options)


if __name__ == "__main__":
    run()
