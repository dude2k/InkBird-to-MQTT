from __future__ import annotations

import unittest

from inkbird_ibs_p01r.config import SDRConfig
from inkbird_ibs_p01r.rtl433_capture import Rtl433Capture


class Rtl433CaptureTests(unittest.TestCase):
    def test_default_command_uses_verified_rtl_sdr_capture_arguments(self) -> None:
        command = Rtl433Capture(SDRConfig()).command()

        self.assertEqual(
            command,
            [
                "rtl_433",
                "-d",
                "00000001",
                "-f",
                "434.097M",
                "-s",
                "1000k",
                "-R",
                "0",
                "-Y",
                "minmax",
                "-g",
                "30",
                "-S",
                "all",
                "-F",
                "log",
            ],
        )


if __name__ == "__main__":
    unittest.main()
