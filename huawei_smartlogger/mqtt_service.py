"""MQTT broker settings supplied by Home Assistant Supervisor."""

import json
import os
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class MQTTServiceConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    ssl: bool


def get_mqtt_service_config() -> MQTTServiceConfig:
    """Read and validate the MQTT service configuration from Supervisor."""
    supervisor_token = os.getenv("SUPERVISOR_TOKEN")
    if not supervisor_token:
        raise RuntimeError(
            "SUPERVISOR_TOKEN is unavailable. Run this add-on inside Home Assistant "
            "or provide MQTT credentials in the add-on options."
        )

    request = Request(
        "http://supervisor/services/mqtt",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
    except URLError as error:
        raise RuntimeError(
            "Could not retrieve MQTT settings from Home Assistant Supervisor. "
            "Make sure the MQTT integration and broker are configured."
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Home Assistant Supervisor returned invalid MQTT service data."
        ) from error

    if not isinstance(payload, dict) or payload.get("result") != "ok":
        message = payload.get("message") if isinstance(payload, dict) else None
        detail = f" ({message})" if isinstance(message, str) and message else ""
        raise RuntimeError(
            "Home Assistant Supervisor could not provide MQTT settings. "
            "Make sure the MQTT integration and broker are configured."
            f"{detail}"
        )

    config = payload.get("data")
    if not isinstance(config, dict):
        raise RuntimeError("Home Assistant Supervisor returned no MQTT broker settings.")

    broker_host = config.get("host")
    broker_port = config.get("port")
    username = config.get("username")
    password = config.get("password")
    use_tls = config.get("ssl", False)
    if not isinstance(broker_host, str) or not broker_host.strip():
        raise RuntimeError("The Home Assistant MQTT service returned an empty broker host.")
    if (
        isinstance(broker_port, bool)
        or not isinstance(broker_port, int)
        or not 1 <= broker_port <= 65535
    ):
        raise RuntimeError("The Home Assistant MQTT service returned an invalid broker port.")
    if username is not None and not isinstance(username, str):
        raise RuntimeError("The Home Assistant MQTT service returned an invalid username.")
    if password is not None and not isinstance(password, str):
        raise RuntimeError("The Home Assistant MQTT service returned an invalid password.")
    if bool(username) != bool(password):
        raise RuntimeError(
            "The Home Assistant MQTT service must provide both a username and password."
        )
    if not isinstance(use_tls, bool):
        raise RuntimeError("The Home Assistant MQTT service returned an invalid TLS setting.")

    return MQTTServiceConfig(
        host=broker_host.strip(),
        port=broker_port,
        username=username,
        password=password,
        ssl=use_tls,
    )
