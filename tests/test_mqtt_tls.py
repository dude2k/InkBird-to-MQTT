from __future__ import annotations

import ssl
import unittest

from inkbird_ibs_p01r.config import AppConfig, MQTTConfig
from inkbird_ibs_p01r.diagnostics import effective_config_lines
from inkbird_ibs_p01r.mqtt_client import build_tls_context


class MQTTTLSTests(unittest.TestCase):
    def test_default_tls_is_disabled(self) -> None:
        config = AppConfig()

        self.assertFalse(config.mqtt.tls_enabled)
        self.assertIn("mqtt.tls_enabled=False", effective_config_lines(config))

    def test_insecure_tls_context_disables_certificate_verification(self) -> None:
        config = AppConfig(mqtt=MQTTConfig(tls_enabled=True, tls_insecure=True))

        context = build_tls_context(config)

        self.assertFalse(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)

    def test_insecure_tls_context_does_not_require_ca_file(self) -> None:
        config = AppConfig(
            mqtt=MQTTConfig(
                tls_enabled=True,
                tls_ca_cert="/does/not/exist/ca.pem",
                tls_insecure=True,
            )
        )

        context = build_tls_context(config)

        self.assertEqual(context.verify_mode, ssl.CERT_NONE)

    def test_effective_config_masks_client_key_path(self) -> None:
        config = AppConfig(
            mqtt=MQTTConfig(
                tls_enabled=True,
                tls_client_cert="/etc/mqtt/client.crt",
                tls_client_key="/etc/mqtt/client.key",
            )
        )

        lines = effective_config_lines(config)

        self.assertIn("mqtt.tls_client_key_set=True", lines)
        self.assertNotIn("mqtt.tls_client_key=/etc/mqtt/client.key", lines)


if __name__ == "__main__":
    unittest.main()
