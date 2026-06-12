from __future__ import annotations

import logging
import signal
import time
from pathlib import Path
from threading import Event
from typing import Callable

from .config import AppConfig
from .decoder import DecodeResult, decode_cs16_file
from .mqtt_client import MQTTPublisher
from .rtl433_capture import Rtl433Capture

LOG = logging.getLogger(__name__)
ResultCallback = Callable[[DecodeResult], None]


def is_file_stable(path: Path, stable_seconds: float) -> bool:
    try:
        first_size = path.stat().st_size
    except FileNotFoundError:
        return False
    time.sleep(max(0.0, stable_seconds))
    try:
        return path.stat().st_size == first_size
    except FileNotFoundError:
        return False


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


class DirectoryWatcher:
    def __init__(self, config: AppConfig, on_result: ResultCallback | None = None) -> None:
        self.config = config
        self.on_result = on_result
        self.seen: set[Path] = set()

    def scan_once(self) -> list[DecodeResult]:
        results: list[DecodeResult] = []
        capture_dir = Path(self.config.sdr.capture_dir)
        capture_dir.mkdir(parents=True, exist_ok=True)

        for path in capture_files(capture_dir):
            resolved = path.resolve()
            if resolved in self.seen:
                continue
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                continue

            if size < self.config.sdr.min_long_file_size:
                continue
            if not is_file_stable(path, self.config.sdr.file_stable_seconds):
                continue

            result = decode_cs16_file(
                path,
                decoder_config=self.config.decoder,
                min_file_size=self.config.sdr.min_long_file_size,
            )
            self.seen.add(resolved)
            self._log_result(result)
            results.append(result)

            if self.on_result is not None:
                self.on_result(result)

            self._cleanup(path, result)

        return results

    def _cleanup(self, path: Path, result: DecodeResult) -> None:
        if not self.config.sdr.cleanup_after_decode:
            return
        if not result.decode_ok and self.config.sdr.keep_failed_files:
            return
        try:
            path.unlink()
            LOG.debug("removed_capture file=%s", path.name)
        except FileNotFoundError:
            return
        except OSError as exc:
            LOG.warning("remove_capture_failed file=%s error=%s", path.name, exc)

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

    def install_signal_handlers(self) -> None:
        def handle_signal(signum: int, _frame: object) -> None:
            LOG.info("signal_received signum=%s", signum)
            self.stop()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def run(self) -> None:
        self.install_signal_handlers()
        self.publisher.connect()
        if self.capture is not None:
            self.capture.start()

        try:
            while not self.stop_event.is_set():
                if self.capture is not None:
                    code = self.capture.poll()
                    if code is not None:
                        LOG.error("rtl433_exited code=%s", code)
                        self.stop_event.set()
                        break
                self.watcher.scan_once()
                self.stop_event.wait(self.config.sdr.poll_interval_seconds)
        finally:
            self.close()

    def _publish_result(self, result: DecodeResult) -> None:
        if not result.decode_ok:
            return
        try:
            payload = self.publisher.publish_decode(result)
            LOG.info("mqtt_publish topic=%s temperature_C=%s", self.config.mqtt.topic, payload["temperature_C"])
        except Exception as exc:
            LOG.error("mqtt_publish_failed error=%r", exc)

    def stop(self) -> None:
        self.stop_event.set()

    def close(self) -> None:
        if self.capture is not None:
            self.capture.stop()
        self.publisher.close()
