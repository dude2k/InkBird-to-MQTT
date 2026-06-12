from __future__ import annotations

import logging
import signal
import time
from collections import Counter
from pathlib import Path
from threading import Event
from typing import Callable

from . import __version__
from .config import AppConfig
from .decoder import DecodeResult, decode_cs16_file
from .mqtt_client import MQTTPublisher
from .rtl433_capture import Rtl433Capture

LOG = logging.getLogger(__name__)
ResultCallback = Callable[[DecodeResult], bool | None]
SHORT_CAPTURE_REASONS = {"no_hit", "too_short", "not_long_file"}


def log_effective_config(config: AppConfig) -> None:
    LOG.info(
        (
            "effective_config version=%s device_id=%s device_name=%s "
            "mqtt_host=%s mqtt_port=%s mqtt_topic=%s mqtt_state_topic=%s "
            "mqtt_field_topic=%s mqtt_raw13_topic=%s mqtt_confidence_topic=%s "
            "mqtt_last_seen_topic=%s mqtt_availability_topic=%s mqtt_username_set=%s mqtt_password_set=%s "
            "sdr_start_rtl433=%s sdr_rtl433_path=%s sdr_device=%s sdr_frequency=%s sdr_sample_rate=%s "
            "sdr_capture_dir=%s sdr_cleanup_after_decode=%s sdr_keep_successful_files=%s "
            "sdr_keep_no_hit_files=%s sdr_keep_error_files=%s"
        ),
        __version__,
        config.device.id,
        config.device.name,
        config.mqtt.host,
        config.mqtt.port,
        config.mqtt.topic,
        config.mqtt.state_topic,
        config.mqtt.field_topic,
        config.mqtt.raw13_topic,
        config.mqtt.confidence_topic,
        config.mqtt.last_seen_topic,
        config.mqtt.availability_topic,
        config.mqtt.username is not None,
        config.mqtt.password is not None,
        config.sdr.start_rtl433,
        config.sdr.rtl433_path,
        config.sdr.device,
        config.sdr.frequency,
        config.sdr.sample_rate,
        config.sdr.capture_dir,
        config.sdr.cleanup_after_decode,
        config.sdr.keep_successful_files,
        config.sdr.keep_no_hit_files,
        config.sdr.keep_error_files,
    )


def is_file_stable(path: Path, stable_seconds: float) -> bool:
    try:
        first_stat = path.stat()
    except FileNotFoundError:
        return False
    time.sleep(max(0.0, stable_seconds))
    try:
        second_stat = path.stat()
    except FileNotFoundError:
        return False
    return first_stat.st_size == second_stat.st_size and first_stat.st_mtime_ns == second_stat.st_mtime_ns


def capture_files(capture_dir: Path) -> list[Path]:
    if not capture_dir.exists():
        return []
    files = []
    for item in capture_dir.glob("*.cs16"):
        try:
            files.append((item.stat().st_mtime, item))
        except FileNotFoundError:
            continue
    return [item for _, item in sorted(files)]


def cleanup_capture_file(path: Path, result: DecodeResult, config: AppConfig) -> bool:
    if not config.sdr.cleanup_after_decode:
        LOG.debug("capture_kept cleanup_disabled file=%s", path.name)
        return False

    if result.decode_ok and config.sdr.keep_successful_files:
        LOG.debug("capture_kept successful file=%s", path.name)
        return False

    reason = result.reason or "success"
    if not result.decode_ok and reason in SHORT_CAPTURE_REASONS and config.sdr.keep_no_hit_files:
        LOG.debug("capture_kept reason=%s file=%s", reason, path.name)
        return False

    if not result.decode_ok and reason not in SHORT_CAPTURE_REASONS and config.sdr.keep_error_files:
        LOG.debug("capture_kept error reason=%s file=%s", reason, path.name)
        return False

    try:
        path.unlink()
        LOG.debug("capture_deleted file=%s reason=%s decode_ok=%s", path.name, reason, result.decode_ok)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        LOG.warning("capture_delete_failed file=%s error=%s", path, exc)
        return False


def cleanup_old_captures(capture_dir: Path, max_age_seconds: int | None) -> int:
    if not max_age_seconds or max_age_seconds <= 0 or not capture_dir.exists():
        return 0

    deleted = 0
    now = time.time()
    for path in capture_dir.glob("*.cs16"):
        try:
            age = now - path.stat().st_mtime
            if age <= max_age_seconds:
                continue
            path.unlink()
            deleted += 1
            LOG.debug("capture_deleted_old file=%s age_seconds=%.1f", path.name, age)
        except FileNotFoundError:
            continue
        except OSError as exc:
            LOG.warning("capture_delete_old_failed file=%s error=%s", path, exc)
    return deleted


def enforce_capture_dir_size(capture_dir: Path, max_size_mb: int | None, active_grace_seconds: float = 2.0) -> int:
    if not max_size_mb or max_size_mb <= 0 or not capture_dir.exists():
        return 0

    files: list[tuple[float, int, Path]] = []
    now = time.time()
    for path in capture_dir.glob("*.cs16"):
        try:
            stat = path.stat()
            files.append((stat.st_mtime, stat.st_size, path))
        except FileNotFoundError:
            continue
        except OSError as exc:
            LOG.warning("capture_stat_failed file=%s error=%s", path, exc)

    limit = max_size_mb * 1024 * 1024
    total = sum(size for _, size, _ in files)
    if total <= limit:
        return 0

    deleted = 0
    for mtime, size, path in sorted(files):
        if total <= limit:
            break
        if now - mtime < active_grace_seconds:
            continue
        try:
            path.unlink()
            total -= size
            deleted += 1
            LOG.debug("capture_deleted_size_limit file=%s size=%s remaining_bytes=%s", path.name, size, total)
        except FileNotFoundError:
            total -= size
        except OSError as exc:
            LOG.warning("capture_delete_size_limit_failed file=%s error=%s", path, exc)
    return deleted


class DirectoryWatcher:
    def __init__(self, config: AppConfig, on_result: ResultCallback | None = None) -> None:
        self.config = config
        self.on_result = on_result
        self.seen: set[tuple[Path, int, int]] = set()
        self.stats: Counter[str] = Counter()
        self._last_stats_log_at = time.monotonic()

    def scan_once(self) -> list[DecodeResult]:
        results: list[DecodeResult] = []
        capture_dir = Path(self.config.sdr.capture_dir)
        capture_dir.mkdir(parents=True, exist_ok=True)
        self._run_safety_cleanup(capture_dir)

        for path in capture_files(capture_dir):
            resolved = path.resolve()
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                continue

            self.stats["seen"] += 1
            LOG.debug("capture_seen file=%s size=%s", path.name, size)
            if not is_file_stable(path, self.config.sdr.file_stable_seconds):
                self.stats["unstable"] += 1
                continue

            try:
                stable_stat = path.stat()
            except FileNotFoundError:
                continue
            signature = (resolved, stable_stat.st_mtime_ns, stable_stat.st_size)
            if signature in self.seen:
                continue
            size = stable_stat.st_size

            if size < self.config.sdr.min_long_file_size:
                LOG.debug(
                    "capture_skipped_short file=%s size=%s min_long_file_size=%s",
                    path.name,
                    size,
                    self.config.sdr.min_long_file_size,
                )
                result = DecodeResult(False, path.name, reason="too_short")
            else:
                try:
                    result = decode_cs16_file(
                        path,
                        decoder_config=self.config.decoder,
                        min_file_size=self.config.sdr.min_long_file_size,
                    )
                except Exception:
                    LOG.exception("decode_exception file=%s", path.name)
                    result = DecodeResult(False, path.name, reason="decode_error")
            self._log_result(result)
            results.append(result)
            self._record_result(result)

            callback_ok = True
            if self.on_result is not None:
                callback_result = self.on_result(result)
                callback_ok = callback_result is not False

            if result.decode_ok and not callback_ok:
                self.stats["deferred"] += 1
                LOG.warning("decode_delivery_deferred file=%s", result.file)
                continue

            if cleanup_capture_file(path, result, self.config):
                self.stats["deleted"] += 1
            else:
                self.seen.add(signature)
                self.stats["kept"] += 1

        self._maybe_log_stats()
        return results

    def _record_result(self, result: DecodeResult) -> None:
        if result.decode_ok:
            self.stats["decoded"] += 1
            return

        reason = result.reason or "decode_error"
        if reason == "too_short":
            self.stats["too_short"] += 1
        elif reason == "no_hit":
            self.stats["no_hit"] += 1
        else:
            self.stats["errors"] += 1

    def _maybe_log_stats(self) -> None:
        interval = self.config.sdr.capture_stats_interval_seconds
        if not interval or interval <= 0 or not self.stats:
            return

        now = time.monotonic()
        if now - self._last_stats_log_at < interval:
            return

        LOG.info(
            "capture_stats seen=%s decoded=%s no_hit=%s too_short=%s errors=%s unstable=%s deleted=%s kept=%s deferred=%s",
            self.stats["seen"],
            self.stats["decoded"],
            self.stats["no_hit"],
            self.stats["too_short"],
            self.stats["errors"],
            self.stats["unstable"],
            self.stats["deleted"],
            self.stats["kept"],
            self.stats["deferred"],
        )
        self.stats.clear()
        self._last_stats_log_at = now

    def _run_safety_cleanup(self, capture_dir: Path) -> None:
        deleted_old = cleanup_old_captures(capture_dir, self.config.sdr.max_capture_age_seconds)
        deleted_size = enforce_capture_dir_size(
            capture_dir,
            self.config.sdr.max_capture_dir_size_mb,
            active_grace_seconds=max(2.0, self.config.sdr.file_stable_seconds * 2.0),
        )
        if deleted_old or deleted_size:
            LOG.info("capture_safety_cleanup deleted_old=%s deleted_size_limit=%s", deleted_old, deleted_size)

    @staticmethod
    def _log_result(result: DecodeResult) -> None:
        if result.decode_ok:
            LOG.info(
                "decoded temperature_C=%s field=%s flags=%s raw13=%s confidence_count=%s file=%s",
                result.temperature_C,
                result.field,
                result.flags,
                result.raw13,
                result.confidence_count,
                result.file,
            )
        elif result.reason == "too_short":
            LOG.debug("capture_skipped_short file=%s", result.file)
        else:
            LOG.debug("no_decode reason=%s file=%s", result.reason, result.file)

    def run(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            self.scan_once()
            stop_event.wait(self.config.sdr.poll_interval_seconds)


class InkbirdService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.stop_event = Event()
        self.publisher = MQTTPublisher(config)
        self.capture = Rtl433Capture(config.sdr) if config.sdr.start_rtl433 else None
        self.watcher = DirectoryWatcher(config, on_result=self._publish_result)
        self._next_mqtt_connect_attempt = 0.0
        self._next_rtl433_start_attempt = 0.0
        self._last_successful_decode_at = time.monotonic()
        self._last_no_decode_warning_at = 0.0

    def install_signal_handlers(self) -> None:
        def handle_signal(signum: int, _frame: object) -> None:
            LOG.info("signal_received signum=%s", signum)
            self.stop()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def run(self) -> None:
        self.install_signal_handlers()
        log_effective_config(self.config)

        try:
            while not self.stop_event.is_set():
                if not self._ensure_mqtt_connected():
                    self.stop_event.wait(self.config.mqtt.reconnect_interval_seconds)
                    continue

                self._ensure_capture_running()
                self.watcher.scan_once()
                self._maybe_log_decode_health()
                self.stop_event.wait(self.config.sdr.poll_interval_seconds)
        finally:
            self.close()

    def _ensure_capture_running(self) -> None:
        if self.capture is None:
            return

        now = time.monotonic()
        if self.capture.process is not None:
            code = self.capture.poll()
            if code is None:
                return
            LOG.error(
                "rtl433_exited code=%s restart_in=%ss",
                code,
                self.config.sdr.rtl433_restart_interval_seconds,
            )
            self.capture.stop()
            self._next_rtl433_start_attempt = now + self.config.sdr.rtl433_restart_interval_seconds
            return

        if now < self._next_rtl433_start_attempt:
            return

        try:
            self.capture.start()
        except Exception as exc:
            self._next_rtl433_start_attempt = now + self.config.sdr.rtl433_restart_interval_seconds
            LOG.error(
                "rtl433_start_failed retry_in=%ss error=%r",
                self.config.sdr.rtl433_restart_interval_seconds,
                exc,
            )

    def _ensure_mqtt_connected(self) -> bool:
        if self.publisher.is_connected:
            return True

        now = time.monotonic()
        if now < self._next_mqtt_connect_attempt:
            return False

        try:
            self.publisher.connect()
            LOG.info(
                "mqtt_connected host=%s port=%s topic=%s",
                self.config.mqtt.host,
                self.config.mqtt.port,
                self.config.mqtt.topic,
            )
            return True
        except Exception as exc:
            self._next_mqtt_connect_attempt = now + self.config.mqtt.reconnect_interval_seconds
            LOG.error(
                "mqtt_connect_failed host=%s port=%s retry_in=%ss error=%r",
                self.config.mqtt.host,
                self.config.mqtt.port,
                self.config.mqtt.reconnect_interval_seconds,
                exc,
            )
            return False

    def _publish_result(self, result: DecodeResult) -> bool:
        if not result.decode_ok:
            return True
        try:
            if not self._ensure_mqtt_connected():
                return False
            payload = self.publisher.publish_decode(result)
            LOG.info(
                "mqtt_publish topic=%s state_topic=%s temperature_C=%s",
                self.config.mqtt.topic,
                self.config.mqtt.state_topic,
                payload["temperature_C"],
            )
            self._last_successful_decode_at = time.monotonic()
            return True
        except Exception as exc:
            LOG.error("mqtt_publish_failed error=%r", exc)
            return False

    def _maybe_log_decode_health(self) -> None:
        interval = self.config.sdr.no_successful_decode_warning_seconds
        if not interval or interval <= 0:
            return

        now = time.monotonic()
        silence = now - self._last_successful_decode_at
        if silence < interval:
            return
        if now - self._last_no_decode_warning_at < interval:
            return

        LOG.warning(
            "no_successful_decode_for seconds=%.0f capture_dir=%s",
            silence,
            self.config.sdr.capture_dir,
        )
        self._last_no_decode_warning_at = now

    def stop(self) -> None:
        self.stop_event.set()

    def close(self) -> None:
        if self.capture is not None:
            self.capture.stop()
        self.publisher.close()
