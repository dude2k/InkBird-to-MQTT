from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

from inkbird_ibs_p01r.config import ConfigWarning, find_unknown_config_keys, load_config


class ConfigValidationTests(unittest.TestCase):
    def test_find_unknown_config_keys_reports_top_level_and_section_keys(self) -> None:
        unknown = find_unknown_config_keys(
            {
                "mqtt": {"host": "localhost", "tls_enable": True},
                "sdr": {"start_rtl433": True},
                "unexpected": {},
            }
        )

        self.assertEqual(unknown, ["mqtt.tls_enable", "unexpected"])

    def test_load_config_warns_about_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text(
                """
mqtt:
  host: localhost
  tls_enable: true
unexpected: true
""",
                encoding="utf-8",
            )

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ConfigWarning)
                config = load_config(config_path)

        messages = [str(item.message) for item in caught]
        self.assertEqual(config.mqtt.host, "localhost")
        self.assertFalse(config.mqtt.tls_enabled)
        self.assertTrue(any("mqtt.tls_enable" in message for message in messages))
        self.assertTrue(any("unexpected" in message for message in messages))

    def test_load_config_rejects_non_mapping_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("mqtt:\n  - broken\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "config section 'mqtt' must be a mapping"):
                load_config(config_path)

    def test_legacy_keep_failed_files_is_still_known(self) -> None:
        self.assertEqual(find_unknown_config_keys({"sdr": {"keep_failed_files": True}}), [])


if __name__ == "__main__":
    unittest.main()
