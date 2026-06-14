from __future__ import annotations

import os
import time
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from inkbird_ibs_p01r.config import AppConfig, SDRConfig, load_config
from inkbird_ibs_p01r.decoder import DecodeResult
from inkbird_ibs_p01r.service import (
    DirectoryWatcher,
    cleanup_capture_file,
    cleanup_old_captures,
    enforce_capture_dir_size,
)


def make_result(decode_ok: bool, reason: str | None = None) -> DecodeResult:
    if not decode_ok:
        return DecodeResult(False, "sample.cs16", reason=reason)
    return DecodeResult(
        decode_ok=True,
        file="sample.cs16",
        temperature_C=24.2,
        temperature_C_exact=24.2,
        field="fe40",
        flags=7,
        raw13=-448,
        confidence_count=3,
        marker="0280a280",
    )


def make_config(capture_dir: Path, **overrides: object) -> AppConfig:
    sdr = SDRConfig(
        capture_dir=str(capture_dir),
        min_long_file_size=10,
        file_stable_seconds=0,
        cleanup_after_decode=True,
        keep_successful_files=False,
        keep_no_hit_files=False,
        keep_error_files=True,
        max_capture_age_seconds=None,
        max_capture_dir_size_mb=None,
    )
    return AppConfig(sdr=replace(sdr, **overrides))


class CaptureCleanupTests(unittest.TestCase):
    def test_successful_decode_deletes_file_after_callback_success(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.cs16"
            path.write_bytes(b"x" * 20)
            config = make_config(Path(tmp))

            with patch("inkbird_ibs_p01r.service.decode_cs16_file", return_value=make_result(True)):
                DirectoryWatcher(config, on_result=lambda _result: True).scan_once()

            self.assertFalse(path.exists())

    def test_no_hit_deletes_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.cs16"
            path.write_bytes(b"x" * 20)
            config = make_config(Path(tmp))

            with patch("inkbird_ibs_p01r.service.decode_cs16_file", return_value=make_result(False, "no_hit")):
                DirectoryWatcher(config).scan_once()

            self.assertFalse(path.exists())

    def test_too_short_deletes_file_without_decode_attempt(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.cs16"
            path.write_bytes(b"x")
            config = make_config(Path(tmp), min_long_file_size=10)

            with patch("inkbird_ibs_p01r.service.decode_cs16_file") as decode:
                results = DirectoryWatcher(config).scan_once()

            decode.assert_not_called()
            self.assertEqual(results[0].reason, "too_short")
            self.assertFalse(path.exists())

    def test_cu8_capture_is_converted_decoded_and_deleted(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "g001_434.097M_1000k.cu8"
            cs16_path = path.with_suffix(".cs16")
            path.write_bytes(bytes([128, 128]) * 10)
            config = make_config(Path(tmp), min_long_file_size=10, keep_cu8=False, keep_cs16=False)

            with patch("inkbird_ibs_p01r.service.decode_cs16_file", return_value=make_result(True)) as decode:
                results = DirectoryWatcher(config).scan_once()

            self.assertEqual(results[0].file, path.name)
            self.assertEqual(decode.call_args.args[0], cs16_path)
            self.assertFalse(path.exists())
            self.assertFalse(cs16_path.exists())

    def test_kept_cu8_and_cs16_are_not_reprocessed(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "g001_434.097M_1000k.cu8"
            cs16_path = path.with_suffix(".cs16")
            path.write_bytes(bytes([128, 128]) * 10)
            config = make_config(
                Path(tmp),
                min_long_file_size=10,
                keep_cu8=True,
                keep_cs16=True,
            )
            watcher = DirectoryWatcher(config)

            with patch("inkbird_ibs_p01r.service.decode_cs16_file", return_value=make_result(True)) as decode:
                first = watcher.scan_once()
                second = watcher.scan_once()

            self.assertEqual(len(first), 1)
            self.assertEqual(second, [])
            self.assertEqual(decode.call_count, 1)
            self.assertTrue(path.exists())
            self.assertTrue(cs16_path.exists())

    def test_matching_cs16_is_skipped_when_cu8_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "g001_434.097M_1000k.cu8"
            cs16_path = path.with_suffix(".cs16")
            path.write_bytes(bytes([128, 128]) * 10)
            cs16_path.write_bytes(b"x" * 20)
            config = make_config(
                Path(tmp),
                min_long_file_size=10,
                keep_cu8=True,
                keep_cs16=True,
            )

            with patch("inkbird_ibs_p01r.service.decode_cs16_file", return_value=make_result(False, "no_hit")) as decode:
                results = DirectoryWatcher(config).scan_once()

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].file, path.name)
            self.assertEqual(decode.call_count, 1)

    def test_decode_exception_can_be_retained(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.cs16"
            path.write_bytes(b"x" * 20)
            config = make_config(Path(tmp), keep_error_files=True)

            with self.assertLogs("inkbird_ibs_p01r.service", level="ERROR") as logs:
                with patch("inkbird_ibs_p01r.service.decode_cs16_file", side_effect=RuntimeError("broken")):
                    results = DirectoryWatcher(config).scan_once()

            self.assertEqual(results[0].reason, "decode_error")
            self.assertTrue(path.exists())
            self.assertIn("decode_exception file=sample.cs16", "\n".join(logs.output))

    def test_cleanup_disabled_keeps_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.cs16"
            path.write_bytes(b"x")
            result = make_result(False, "no_hit")

            cleanup_capture_file(path, result, make_config(Path(tmp), cleanup_after_decode=False))

            self.assertTrue(path.exists())

    def test_capture_dir_is_created_if_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            capture_dir = Path(tmp) / "run" / "inkbird-ibs-p01r" / "captures"
            config = make_config(capture_dir)

            DirectoryWatcher(config).scan_once()

            self.assertTrue(capture_dir.is_dir())

    def test_reused_file_path_with_new_signature_is_processed_again(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.cs16"
            path.write_bytes(b"x" * 20)
            config = make_config(Path(tmp), cleanup_after_decode=False)
            watcher = DirectoryWatcher(config)

            with patch("inkbird_ibs_p01r.service.decode_cs16_file", return_value=make_result(False, "no_hit")) as decode:
                first = watcher.scan_once()
                path.write_bytes(b"y" * 21)
                second = watcher.scan_once()

            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)
            self.assertEqual(decode.call_count, 2)

    def test_old_keep_failed_files_config_maps_to_new_flags(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text('sdr:\n  keep_failed_files: "false"\n', encoding="utf-8")

            config = load_config(config_path)

            self.assertFalse(config.sdr.keep_no_hit_files)
            self.assertFalse(config.sdr.keep_error_files)

    def test_old_capture_cleanup_deletes_stale_file(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.cs16"
            path.write_bytes(b"x")
            old_time = path.stat().st_mtime - 7200
            os.utime(path, (old_time, old_time))

            deleted = cleanup_old_captures(Path(tmp), max_age_seconds=3600)

            self.assertEqual(deleted, 1)
            self.assertFalse(path.exists())

    def test_capture_dir_size_cleanup_deletes_oldest_file(self) -> None:
        with TemporaryDirectory() as tmp:
            older = Path(tmp) / "older.cs16"
            newer = Path(tmp) / "newer.cs16"
            older.write_bytes(b"x" * 1024 * 1024)
            newer.write_bytes(b"x" * 1024 * 1024)

            now = time.time()
            os.utime(older, (now - 10, now - 10))
            os.utime(newer, (now - 5, now - 5))

            deleted = enforce_capture_dir_size(Path(tmp), max_size_mb=1)

            self.assertEqual(deleted, 1)
            self.assertFalse(older.exists())
            self.assertTrue(newer.exists())


if __name__ == "__main__":
    unittest.main()
