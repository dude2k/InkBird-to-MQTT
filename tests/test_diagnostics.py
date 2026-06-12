from __future__ import annotations

import unittest

from inkbird_ibs_p01r.diagnostics import DiagnosticResult, format_results


class DiagnosticFormattingTests(unittest.TestCase):
    def test_format_results_includes_hints(self) -> None:
        output = format_results(
            [
                DiagnosticResult(
                    "capture_dir_writable",
                    False,
                    "/run/example is not readable/writable by this user",
                    hint="sudo -u inkbird inkbird-ibs-p01r-mqtt doctor --config /etc/example.yaml",
                )
            ]
        )

        self.assertIn("[FAIL] capture_dir_writable", output)
        self.assertIn("hint: sudo -u inkbird", output)


if __name__ == "__main__":
    unittest.main()
