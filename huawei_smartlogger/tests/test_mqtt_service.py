import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError

from mqtt_service import get_mqtt_service_config


class MQTTServiceTests(unittest.TestCase):
    @patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-supervisor-token"})
    @patch("mqtt_service.urlopen")
    def test_reads_credentials_and_tls_from_supervisor(self, urlopen) -> None:
        response = BytesIO(
            json.dumps(
                {
                    "result": "ok",
                    "data": {
                        "host": "core-mosquitto",
                        "port": 8883,
                        "username": "addon",
                        "password": "secret",
                        "ssl": True,
                    },
                }
            ).encode()
        )
        urlopen.return_value.__enter__.return_value = response

        config = get_mqtt_service_config()

        self.assertEqual(config.host, "core-mosquitto")
        self.assertEqual(config.port, 8883)
        self.assertEqual(config.username, "addon")
        self.assertEqual(config.password, "secret")
        self.assertTrue(config.ssl)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://supervisor/services/mqtt")
        self.assertEqual(
            request.get_header("Authorization"),
            "Bearer test-supervisor-token",
        )

    @patch.dict(os.environ, {}, clear=True)
    def test_requires_supervisor_token(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "SUPERVISOR_TOKEN"):
            get_mqtt_service_config()

    @patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"})
    @patch("mqtt_service.urlopen", side_effect=URLError("Supervisor unavailable"))
    def test_reports_unavailable_mqtt_service(self, urlopen) -> None:
        with self.assertRaisesRegex(RuntimeError, "MQTT integration and broker"):
            get_mqtt_service_config()

    @patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"})
    @patch("mqtt_service.urlopen")
    def test_rejects_unavailable_mqtt_service(self, urlopen) -> None:
        response = BytesIO(
            json.dumps(
                {
                    "result": "error",
                    "message": "Service not enabled",
                }
            ).encode()
        )
        urlopen.return_value.__enter__.return_value = response

        with self.assertRaisesRegex(RuntimeError, "Service not enabled"):
            get_mqtt_service_config()


if __name__ == "__main__":
    unittest.main()
