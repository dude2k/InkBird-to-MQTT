from __future__ import annotations

import getpass
import os
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .mqtt_client import build_tls_context


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    ok: bool
    detail: str
    required: bool = True
    hint: str | None = None

    @property
    def status(self) -> str:
        if self.ok:
            return "OK"
        if self.required:
            return "FAIL"
        return "WARN"


def effective_config_lines(config: AppConfig) -> list[str]:
    topic_lines = [
        f"mqtt.topic={config.mqtt.topic}",
        f"mqtt.state_topic={config.mqtt.state_topic}",
        f"mqtt.field_topic={config.mqtt.field_topic}",
        f"mqtt.raw13_topic={config.mqtt.raw13_topic}",
        f"mqtt.confidence_topic={config.mqtt.confidence_topic}",
        f"mqtt.last_seen_topic={config.mqtt.last_seen_topic}",
        f"mqtt.availability_topic={config.mqtt.availability_topic}",
    ]
    return [
        f"device.name={config.device.name}",
        f"device.id={config.device.id}",
        f"sdr.start_rtl433={config.sdr.start_rtl433}",
        f"sdr.rtl433_path={config.sdr.rtl433_path}",
        f"sdr.device={config.sdr.device}",
        f"sdr.frequency={config.sdr.frequency}",
        f"sdr.sample_rate={config.sdr.sample_rate}",
        f"sdr.gain={config.sdr.gain}",
        f"sdr.capture_dir={config.sdr.capture_dir}",
        f"sdr.cleanup_after_decode={config.sdr.cleanup_after_decode}",
        f"sdr.keep_cu8={config.sdr.keep_cu8}",
        f"sdr.keep_cs16={config.sdr.keep_cs16}",
        f"sdr.keep_successful_files={config.sdr.keep_successful_files}",
        f"sdr.keep_no_hit_files={config.sdr.keep_no_hit_files}",
        f"sdr.keep_error_files={config.sdr.keep_error_files}",
        f"mqtt.host={config.mqtt.host}",
        f"mqtt.port={config.mqtt.port}",
        f"mqtt.username_set={config.mqtt.username is not None}",
        f"mqtt.password_set={config.mqtt.password is not None}",
        *topic_lines,
        f"mqtt.qos={config.mqtt.qos}",
        f"mqtt.retain={config.mqtt.retain}",
        f"mqtt.tls_enabled={config.mqtt.tls_enabled}",
        f"mqtt.tls_ca_cert={config.mqtt.tls_ca_cert}",
        f"mqtt.tls_insecure={config.mqtt.tls_insecure}",
        f"mqtt.tls_client_cert={config.mqtt.tls_client_cert}",
        f"mqtt.tls_client_key_set={config.mqtt.tls_client_key is not None}",
        f"logging.level={config.logging.level}",
    ]


def run_status_checks(config: AppConfig) -> list[DiagnosticResult]:
    return [
        _python_check(),
        _mqtt_config_check(config),
        _capture_dir_check(config),
        _rtl433_path_check(config),
    ]


def run_doctor_checks(
    config: AppConfig,
    service_user: str | None = "inkbird",
    config_path: str | Path | None = None,
    executable: str | None = None,
) -> list[DiagnosticResult]:
    results = [
        *run_status_checks(config),
        _capture_dir_writable_check(config, service_user=service_user, config_path=config_path, executable=executable),
    ]
    if config.mqtt.tls_enabled:
        results.append(_mqtt_tls_files_check(config))
    results.extend(
        [
            _mqtt_network_check(config),
            _rtl433_version_check(config),
        ]
    )
    return results


def format_results(results: list[DiagnosticResult]) -> str:
    lines: list[str] = []
    for result in results:
        lines.append(f"[{result.status}] {result.name}: {result.detail}")
        if result.hint:
            lines.append(f"  hint: {result.hint}")
    return "\n".join(lines)


def exit_code_for_results(results: list[DiagnosticResult]) -> int:
    return 1 if any(not result.ok and result.required for result in results) else 0


def _python_check() -> DiagnosticResult:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = sys.version_info >= (3, 10)
    return DiagnosticResult("python", ok, version)


def _mqtt_config_check(config: AppConfig) -> DiagnosticResult:
    if not config.mqtt.host:
        return DiagnosticResult("mqtt_config", False, "mqtt.host is empty")
    if not 1 <= int(config.mqtt.port) <= 65535:
        return DiagnosticResult("mqtt_config", False, f"invalid port {config.mqtt.port}")
    if config.mqtt.tls_client_key and not config.mqtt.tls_client_cert:
        return DiagnosticResult("mqtt_config", False, "tls_client_key requires tls_client_cert")
    return DiagnosticResult("mqtt_config", True, f"{config.mqtt.host}:{config.mqtt.port}")


def _capture_dir_check(config: AppConfig) -> DiagnosticResult:
    path = Path(config.sdr.capture_dir)
    if path.exists():
        if not path.is_dir():
            return DiagnosticResult("capture_dir", False, f"{path} exists but is not a directory")
        return DiagnosticResult("capture_dir", True, str(path))

    parent = _nearest_existing_parent(path)
    detail = f"{path} does not exist yet; nearest existing parent is {parent}"
    return DiagnosticResult("capture_dir", False, detail, required=False)


def _capture_dir_writable_check(
    config: AppConfig,
    service_user: str | None = None,
    config_path: str | Path | None = None,
    executable: str | None = None,
) -> DiagnosticResult:
    path = Path(config.sdr.capture_dir)
    if not path.exists():
        return DiagnosticResult(
            "capture_dir_writable",
            False,
            f"{path} does not exist yet; start the service or create it with matching permissions",
            required=False,
            hint=_service_user_doctor_hint(service_user, config_path, executable),
        )
    if not os.access(path, os.R_OK | os.W_OK | os.X_OK):
        return DiagnosticResult(
            "capture_dir_writable",
            False,
            f"{path} is not readable/writable by this user",
            hint=_service_user_doctor_hint(service_user, config_path, executable),
        )
    return DiagnosticResult("capture_dir_writable", True, str(path))


def _rtl433_path_check(config: AppConfig) -> DiagnosticResult:
    resolved = shutil.which(config.sdr.rtl433_path)
    if resolved:
        return DiagnosticResult("rtl_433_path", True, resolved)

    required = bool(config.sdr.start_rtl433)
    detail = f"{config.sdr.rtl433_path!r} was not found in PATH"
    return DiagnosticResult("rtl_433_path", False, detail, required=required)


def _rtl433_version_check(config: AppConfig) -> DiagnosticResult:
    resolved = shutil.which(config.sdr.rtl433_path)
    if not resolved:
        required = bool(config.sdr.start_rtl433)
        return DiagnosticResult("rtl_433_version", False, "rtl_433 command not available", required=required)

    try:
        completed = subprocess.run(
            [resolved, "-V"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return DiagnosticResult("rtl_433_version", False, repr(exc), required=bool(config.sdr.start_rtl433))

    output = (completed.stdout or completed.stderr).strip().splitlines()
    detail = output[0] if output else f"exit_code={completed.returncode}"
    return DiagnosticResult("rtl_433_version", completed.returncode == 0, detail, required=bool(config.sdr.start_rtl433))


def _mqtt_tls_files_check(config: AppConfig) -> DiagnosticResult:
    paths = [
        ("tls_client_cert", config.mqtt.tls_client_cert),
        ("tls_client_key", config.mqtt.tls_client_key),
    ]
    if not config.mqtt.tls_insecure:
        paths.append(("tls_ca_cert", config.mqtt.tls_ca_cert))
    missing = [f"{name}={path}" for name, path in paths if path and not Path(path).is_file()]
    if missing:
        return DiagnosticResult("mqtt_tls_files", False, "missing files: " + ", ".join(missing))
    return DiagnosticResult("mqtt_tls_files", True, "configured certificate files are readable or not required")


def _mqtt_network_check(config: AppConfig) -> DiagnosticResult:
    if config.mqtt.tls_enabled:
        return _mqtt_tls_check(config)
    return _mqtt_tcp_check(config)


def _mqtt_tcp_check(config: AppConfig) -> DiagnosticResult:
    try:
        with socket.create_connection(
            (config.mqtt.host, int(config.mqtt.port)),
            timeout=float(config.mqtt.connect_timeout_seconds),
        ):
            pass
    except OSError as exc:
        return DiagnosticResult("mqtt_tcp", False, f"{config.mqtt.host}:{config.mqtt.port} {exc!r}")

    return DiagnosticResult("mqtt_tcp", True, f"{config.mqtt.host}:{config.mqtt.port}")


def _mqtt_tls_check(config: AppConfig) -> DiagnosticResult:
    try:
        context = build_tls_context(config)
        with socket.create_connection(
            (config.mqtt.host, int(config.mqtt.port)),
            timeout=float(config.mqtt.connect_timeout_seconds),
        ) as sock:
            with context.wrap_socket(sock, server_hostname=config.mqtt.host):
                pass
    except ssl.SSLError as exc:
        return DiagnosticResult("mqtt_tls", False, f"{config.mqtt.host}:{config.mqtt.port} {exc!r}")
    except OSError as exc:
        return DiagnosticResult("mqtt_tls", False, f"{config.mqtt.host}:{config.mqtt.port} {exc!r}")

    detail = f"{config.mqtt.host}:{config.mqtt.port}"
    if config.mqtt.tls_insecure:
        detail += " insecure_verification=true"
    return DiagnosticResult("mqtt_tls", True, detail)


def _service_user_doctor_hint(
    service_user: str | None,
    config_path: str | Path | None,
    executable: str | None,
) -> str | None:
    if not service_user:
        return None
    try:
        if getpass.getuser() == service_user:
            return None
    except Exception:
        pass

    command = ["sudo", "-u", service_user, executable or "inkbird-ibs-p01r-mqtt", "doctor"]
    if config_path is not None:
        command.extend(["--config", str(config_path)])
    return "The systemd unit usually runs as the service user. Re-run this check with: " + " ".join(
        shlex.quote(part) for part in command
    )


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current
