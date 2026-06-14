from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

from .config import SDRConfig

LOG = logging.getLogger(__name__)


class Rtl433Capture:
    def __init__(self, config: SDRConfig) -> None:
        self.config = config
        self.process: subprocess.Popen[str] | None = None
        self._log_thread: threading.Thread | None = None

    def command(self) -> list[str]:
        return [
            self.config.rtl433_path,
            "-d",
            self.config.device,
            "-f",
            self.config.frequency,
            "-s",
            self.config.sample_rate,
            "-R",
            "0",
            "-Y",
            "minmax",
            "-g",
            str(self.config.gain),
            "-S",
            "all",
            "-F",
            "log",
        ]

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return

        capture_dir = Path(self.config.capture_dir)
        capture_dir.mkdir(parents=True, exist_ok=True)
        cmd = self.command()
        LOG.info("starting rtl_433 command=%s cwd=%s", " ".join(cmd), capture_dir)
        self.process = subprocess.Popen(
            cmd,
            cwd=capture_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._log_thread = threading.Thread(target=self._log_output, daemon=True)
        self._log_thread.start()

    def _log_output(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        for line in self.process.stdout:
            LOG.debug("rtl_433 %s", line.rstrip())

    def poll(self) -> int | None:
        if self.process is None:
            return None
        return self.process.poll()

    def stop(self, timeout: float = 5.0) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            LOG.info("stopping rtl_433")
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                LOG.warning("rtl_433 did not stop in time, killing")
                self.process.kill()
                self.process.wait(timeout=timeout)
        self.process = None
