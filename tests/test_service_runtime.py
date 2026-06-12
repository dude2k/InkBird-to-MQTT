from __future__ import annotations

import time
import unittest

from inkbird_ibs_p01r.config import AppConfig, SDRConfig
from inkbird_ibs_p01r.service import InkbirdService


class FakeCapture:
    def __init__(self) -> None:
        self.process = object()
        self.start_count = 0
        self.stop_count = 0
        self.exit_code: int | None = 7

    def poll(self) -> int | None:
        return self.exit_code

    def stop(self) -> None:
        self.stop_count += 1
        self.process = None
        self.exit_code = None

    def start(self) -> None:
        self.start_count += 1
        self.process = object()
        self.exit_code = None


class ServiceRuntimeTests(unittest.TestCase):
    def test_rtl433_exit_is_restarted_internally(self) -> None:
        config = AppConfig(sdr=SDRConfig(rtl433_restart_interval_seconds=0))
        service = InkbirdService(config)
        capture = FakeCapture()
        service.capture = capture  # type: ignore[assignment]

        service._ensure_capture_running()
        self.assertEqual(capture.stop_count, 1)
        self.assertIsNone(capture.process)

        service._ensure_capture_running()
        self.assertEqual(capture.start_count, 1)

    def test_no_successful_decode_health_warning(self) -> None:
        config = AppConfig(sdr=SDRConfig(no_successful_decode_warning_seconds=1))
        service = InkbirdService(config)
        service._last_successful_decode_at = time.monotonic() - 10

        with self.assertLogs("inkbird_ibs_p01r.service", level="WARNING") as logs:
            service._maybe_log_decode_health()

        self.assertIn("no_successful_decode_for", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()

