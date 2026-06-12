from __future__ import annotations

import unittest

from inkbird_ibs_p01r.decoder import marker_ok


class MarkerValidationTests(unittest.TestCase):
    def test_known_marker_variants_are_valid(self) -> None:
        self.assertTrue(marker_ok("0280a280"))
        self.assertTrue(marker_ok("2280a280"))

    def test_unrelated_markers_are_rejected(self) -> None:
        self.assertFalse(marker_ok("0280a281"))
        self.assertFalse(marker_ok("4280a280"))
        self.assertFalse(marker_ok("0280"))
        self.assertFalse(marker_ok("not-hex"))


if __name__ == "__main__":
    unittest.main()

