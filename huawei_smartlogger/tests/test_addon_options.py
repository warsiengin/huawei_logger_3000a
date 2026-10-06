import json
import tempfile
import unittest
from pathlib import Path

from addon_options import load_options


class AddonOptionsTests(unittest.TestCase):
    def load(self, values: dict[str, object]):
        file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        path = Path(file.name)
        try:
            with file:
                json.dump(values, file)
            return load_options(path)
        finally:
            path.unlink(missing_ok=True)

    def base_options(self) -> dict[str, object]:
        return {
            "modbus_host": "192.168.1.10",
            "modbus_port": 502,
            "modbus_slave_id": 3,
            "scan_interval": 10,
        }

    def test_default_mqtt_settings_keep_existing_host_based_instance_topics(self) -> None:
        options = self.load(self.base_options())

        self.assertEqual(options.mqtt_host, "core-mosquitto")
        self.assertEqual(options.mqtt_port, 1883)
        self.assertEqual(options.mqtt_username, "")
        self.assertEqual(options.mqtt_password, "")
        self.assertFalse(options.mqtt_ssl)
        self.assertEqual(options.modbus_slave_id, 3)
        self.assertEqual(options.instance_id, "192_168_1_10")
        self.assertEqual(
            options.state_prefix,
            "smartlogger/192_168_1_10/state",
        )

    def test_custom_mqtt_settings_generate_configurable_instance_topics(self) -> None:
        options = self.load(
            {
                **self.base_options(),
                "mqtt_host": "broker.example",
                "mqtt_port": 1884,
                "mqtt_username": "logger",
                "mqtt_password": "password",
                "mqtt_ssl": True,
                "mqtt_topic_prefix": "solar/site_1/",
                "instance_id": "inv_1",
            }
        )

        self.assertEqual(options.mqtt_host, "broker.example")
        self.assertEqual(options.mqtt_port, 1884)
        self.assertEqual(options.state_prefix, "solar/site_1/inv_1/state")
        self.assertEqual(
            options.availability_topic,
            "solar/site_1/inv_1/availability",
        )
        self.assertEqual(options.key, "inv_1")

    def test_requires_mqtt_username_and_password_as_a_pair(self) -> None:
        for partial_credentials in (
            {"mqtt_username": "logger"},
            {"mqtt_password": "password"},
        ):
            with self.subTest(partial_credentials=partial_credentials):
                with self.assertRaisesRegex(ValueError, "both MQTT username and password"):
                    self.load({**self.base_options(), **partial_credentials})

    def test_rejects_invalid_mqtt_topics_and_instance_ids(self) -> None:
        for overrides in (
            {"mqtt_topic_prefix": "solar/#"},
            {"mqtt_topic_prefix": "solar//site"},
            {"instance_id": "inverter 1"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.load({**self.base_options(), **overrides})

    def test_rejects_invalid_mqtt_port(self) -> None:
        with self.assertRaisesRegex(ValueError, "mqtt_port"):
            self.load({**self.base_options(), "mqtt_port": 65536})


if __name__ == "__main__":
    unittest.main()
