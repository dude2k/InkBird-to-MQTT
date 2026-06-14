from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from inkbird_ibs_p01r.iq import convert_cu8_to_cs16, cu8_to_cs16


class IQConversionTests(unittest.TestCase):
    def test_cu8_bytes_convert_to_signed_16_bit_iq(self) -> None:
        converted = cu8_to_cs16(bytes([0, 128, 255, 129, 127]))

        self.assertEqual(converted.tolist(), [-32768, 0, 32512, 256])

    def test_convert_cu8_file_writes_cs16_file(self) -> None:
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "g001_434.097M_1000k.cu8"
            target = Path(tmp) / "g001_434.097M_1000k.cs16"
            source.write_bytes(bytes([0, 128, 255, 129]))

            returned = convert_cu8_to_cs16(source)

            self.assertEqual(returned, target)
            self.assertEqual(target.read_bytes(), b"\x00\x80\x00\x00\x00\x7f\x00\x01")


if __name__ == "__main__":
    unittest.main()
