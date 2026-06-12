from __future__ import annotations

import unittest

from inkbird_ibs_p01r.decoder import decode_temperature_field


class TemperatureDecodeTests(unittest.TestCase):
    def test_confirmed_temperature_vectors(self) -> None:
        vectors = [
            ("fc40", 7, -960, 22.6),
            ("ff20", 7, -224, 24.9),
            ("ff60", 7, -160, 25.1),
            ("ff80", 7, -128, 25.2),
            ("ffc0", 7, -64, 25.4),
            ("ffe0", 7, -32, 25.5),
            ("e080", 7, 128, 26.0),
            ("e0a0", 7, 160, 26.1),
            ("e0c0", 7, 192, 26.2),
            ("e100", 7, 256, 26.4),
        ]

        for field, flags, raw13, temp in vectors:
            with self.subTest(field=field):
                decoded = decode_temperature_field(field)
                self.assertEqual(decoded.field, field)
                self.assertEqual(decoded.flags, flags)
                self.assertEqual(decoded.raw13, raw13)
                self.assertEqual(decoded.temperature_C, temp)
                self.assertAlmostEqual(decoded.temperature_C_exact, temp, places=4)


if __name__ == "__main__":
    unittest.main()

