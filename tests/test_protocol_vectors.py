from __future__ import annotations

import unittest

from inkbird_ibs_p01r.decoder import PREFIX_HEX, decode_payload_hex, find_packet_candidates_in_bits, hex_to_bit_string


class ProtocolVectorTests(unittest.TestCase):
    def test_payload_with_0280_marker_decodes(self) -> None:
        decoded = decode_payload_hex(PREFIX_HEX + "ff80" + "0280a280" + "ab9e20")
        self.assertEqual(decoded.field, "ff80")
        self.assertEqual(decoded.raw13, -128)
        self.assertEqual(decoded.temperature_C, 25.2)

    def test_observed_24_2_payload_decodes(self) -> None:
        decoded = decode_payload_hex(PREFIX_HEX + "fe40" + "0280a280")
        self.assertEqual(decoded.field, "fe40")
        self.assertEqual(decoded.raw13, -448)
        self.assertEqual(decoded.temperature_C, 24.2)

    def test_payload_with_2280_marker_decodes(self) -> None:
        decoded = decode_payload_hex(PREFIX_HEX + "e0c0" + "2280a280" + "aead60")
        self.assertEqual(decoded.field, "e0c0")
        self.assertEqual(decoded.raw13, 192)
        self.assertEqual(decoded.temperature_C, 26.2)

    def test_invalid_marker_rejects_candidate(self) -> None:
        bits = hex_to_bit_string(PREFIX_HEX + "e0c0" + "4280a280" + "aead60")
        self.assertEqual(list(find_packet_candidates_in_bits(bits)), [])


if __name__ == "__main__":
    unittest.main()
