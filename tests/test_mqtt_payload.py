from __future__ import annotations

import unittest

from inkbird_ibs_p01r.decoder import DecodeResult
from inkbird_ibs_p01r.mqtt_client import build_auxiliary_state_payloads, build_state_payload


class MQTTPayloadTests(unittest.TestCase):
    def test_state_payload_is_plain_temperature(self) -> None:
        result = DecodeResult(
            decode_ok=True,
            file="sample.cs16",
            temperature_C=24.1,
            temperature_C_exact=24.1,
            field="fe20",
            flags=7,
            raw13=-480,
            confidence_count=20,
            marker="0280a280",
        )

        self.assertEqual(build_state_payload(result), "24.1")

    def test_auxiliary_payloads_are_plain_values(self) -> None:
        result = DecodeResult(
            decode_ok=True,
            file="sample.cs16",
            temperature_C=24.1,
            temperature_C_exact=24.1,
            field="fe20",
            flags=7,
            raw13=-480,
            confidence_count=20,
            marker="0280a280",
        )

        self.assertEqual(
            build_auxiliary_state_payloads(result, "2026-06-12T13:14:35+02:00"),
            {
                "field": "fe20",
                "raw13": "-480",
                "confidence": "20",
                "last_seen": "2026-06-12T13:14:35+02:00",
            },
        )


if __name__ == "__main__":
    unittest.main()
