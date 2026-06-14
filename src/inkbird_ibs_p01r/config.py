from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Callable, Mapping

import yaml


class ConfigWarning(UserWarning):
    pass


@dataclass(frozen=True)
class DeviceConfig:
    name: str = "pool"
    model: str = "Inkbird IBS-P01R"
    id: str = "pool"


@dataclass(frozen=True)
class SDRConfig:
    mode: str = "rtl433_cu8"
    start_rtl433: bool = True
    rtl433_path: str = "rtl_433"
    device: str = "00000001"
    frequency: str = "434.097M"
    sample_rate: str = "1000k"
    gain: str = "30"
    capture_dir: str = "/run/inkbird-ibs-p01r/captures"
    min_long_file_size: int = 3_000_000
    cleanup_after_decode: bool = True
    keep_cu8: bool = False
    keep_cs16: bool = False
    keep_successful_files: bool = False
    keep_no_hit_files: bool = False
    keep_error_files: bool = True
    keep_failed_files: bool | None = None
    file_stable_seconds: float = 0.5
    poll_interval_seconds: float = 1.0
    max_capture_age_seconds: int | None = 3600
    max_capture_dir_size_mb: int | None = 256
    capture_stats_interval_seconds: int | None = 300
    no_successful_decode_warning_seconds: int | None = 3600
    rtl433_restart_interval_seconds: int = 10


@dataclass(frozen=True)
class DecoderConfig:
    fs: int = 1_000_000
    sps: int = 100
    tone_min_hz: int = -215_000
    tone_max_hz: int = -150_000
    bit_threshold_hz: int = -182_500
    min_valid_symbols: int = 500
    min_confidence_count: int = 1


@dataclass(frozen=True)
class MQTTConfig:
    host: str = "localhost"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    client_id: str = "inkbird-ibs-p01r"
    topic: str = "sensors/inkbird_ibs_p01r/pool"
    state_topic: str | None = "sensors/inkbird_ibs_p01r/pool/state"
    field_topic: str | None = "sensors/inkbird_ibs_p01r/pool/field"
    raw13_topic: str | None = "sensors/inkbird_ibs_p01r/pool/raw13"
    confidence_topic: str | None = "sensors/inkbird_ibs_p01r/pool/confidence"
    last_seen_topic: str | None = "sensors/inkbird_ibs_p01r/pool/last_seen"
    availability_topic: str | None = "sensors/inkbird_ibs_p01r/pool/availability"
    qos: int = 0
    retain: bool = False
    tls_enabled: bool = False
    tls_ca_cert: str | None = None
    tls_insecure: bool = False
    tls_client_cert: str | None = None
    tls_client_key: str | None = None
    connect_timeout_seconds: float = 10.0
    reconnect_interval_seconds: float = 30.0


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(frozen=True)
class AppConfig:
    device: DeviceConfig = DeviceConfig()
    sdr: SDRConfig = SDRConfig()
    decoder: DecoderConfig = DecoderConfig()
    mqtt: MQTTConfig = MQTTConfig()
    logging: LoggingConfig = LoggingConfig()


CONFIG_SECTIONS: dict[str, type] = {
    "device": DeviceConfig,
    "sdr": SDRConfig,
    "decoder": DecoderConfig,
    "mqtt": MQTTConfig,
    "logging": LoggingConfig,
}

EnvCast = Callable[[str], Any]
EnvOverride = tuple[str, str, EnvCast]


def find_unknown_config_keys(raw: Mapping[str, Any]) -> list[str]:
    unknown: list[str] = []
    for key, value in raw.items():
        section_cls = CONFIG_SECTIONS.get(key)
        if section_cls is None:
            unknown.append(str(key))
            continue
        if value is None or not isinstance(value, Mapping):
            continue

        allowed = {field.name for field in fields(section_cls)}
        for section_key in value:
            if section_key not in allowed:
                unknown.append(f"{key}.{section_key}")
    return unknown


def warn_unknown_config_keys(raw: Mapping[str, Any], config_path: Path) -> None:
    for key in find_unknown_config_keys(raw):
        warnings.warn(
            f"unknown config key ignored in {config_path}: {key}",
            ConfigWarning,
            stacklevel=3,
        )


def _filter_dataclass_values(cls: type, values: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {field.name for field in fields(cls)}
    return {key: value for key, value in values.items() if key in allowed}


def _merge_dataclass(instance: Any, values: Mapping[str, Any]) -> Any:
    return replace(instance, **_filter_dataclass_values(type(instance), values))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_optional_str(value: str) -> str | None:
    text = value.strip()
    if text.lower() in {"", "none", "null"}:
        return None
    return text


ENV_CONFIG_MAP: tuple[tuple[str, EnvOverride], ...] = (
    ("INKBIRD_CONFIG", ("_meta", "config_path", str)),
    ("DEVICE_NAME", ("device", "name", str)),
    ("DEVICE_ID", ("device", "id", str)),
    ("DEVICE_MODEL", ("device", "model", str)),
    ("START_RTL433", ("sdr", "start_rtl433", _as_bool)),
    ("SDR_START_RTL433", ("sdr", "start_rtl433", _as_bool)),
    ("RTL433_PATH", ("sdr", "rtl433_path", str)),
    ("SDR_DEVICE", ("sdr", "device", str)),
    ("FREQ", ("sdr", "frequency", str)),
    ("FREQUENCY", ("sdr", "frequency", str)),
    ("SDR_FREQUENCY", ("sdr", "frequency", str)),
    ("SAMPLE_RATE", ("sdr", "sample_rate", str)),
    ("SDR_SAMPLE_RATE", ("sdr", "sample_rate", str)),
    ("GAIN", ("sdr", "gain", str)),
    ("SDR_GAIN", ("sdr", "gain", str)),
    ("CAPTURE_DIR", ("sdr", "capture_dir", str)),
    ("SDR_CAPTURE_DIR", ("sdr", "capture_dir", str)),
    ("MIN_LONG_FILE_SIZE", ("sdr", "min_long_file_size", int)),
    ("KEEP_CU8", ("sdr", "keep_cu8", _as_bool)),
    ("KEEP_CS16", ("sdr", "keep_cs16", _as_bool)),
    ("CLEANUP_AFTER_DECODE", ("sdr", "cleanup_after_decode", _as_bool)),
    ("POLL_INTERVAL_SECONDS", ("sdr", "poll_interval_seconds", float)),
    ("FILE_STABLE_SECONDS", ("sdr", "file_stable_seconds", float)),
    ("MQTT_HOST", ("mqtt", "host", str)),
    ("MQTT_PORT", ("mqtt", "port", int)),
    ("MQTT_USERNAME", ("mqtt", "username", _as_optional_str)),
    ("MQTT_PASSWORD", ("mqtt", "password", _as_optional_str)),
    ("MQTT_CLIENT_ID", ("mqtt", "client_id", str)),
    ("MQTT_TOPIC", ("mqtt", "topic", str)),
    ("MQTT_STATE_TOPIC", ("mqtt", "state_topic", _as_optional_str)),
    ("MQTT_FIELD_TOPIC", ("mqtt", "field_topic", _as_optional_str)),
    ("MQTT_RAW13_TOPIC", ("mqtt", "raw13_topic", _as_optional_str)),
    ("MQTT_CONFIDENCE_TOPIC", ("mqtt", "confidence_topic", _as_optional_str)),
    ("MQTT_LAST_SEEN_TOPIC", ("mqtt", "last_seen_topic", _as_optional_str)),
    ("MQTT_AVAILABILITY_TOPIC", ("mqtt", "availability_topic", _as_optional_str)),
    ("MQTT_QOS", ("mqtt", "qos", int)),
    ("MQTT_RETAIN", ("mqtt", "retain", _as_bool)),
    ("MQTT_TLS_ENABLED", ("mqtt", "tls_enabled", _as_bool)),
    ("MQTT_TLS_CA_CERT", ("mqtt", "tls_ca_cert", _as_optional_str)),
    ("MQTT_TLS_INSECURE", ("mqtt", "tls_insecure", _as_bool)),
    ("MQTT_TLS_CLIENT_CERT", ("mqtt", "tls_client_cert", _as_optional_str)),
    ("MQTT_TLS_CLIENT_KEY", ("mqtt", "tls_client_key", _as_optional_str)),
    ("LOG_LEVEL", ("logging", "level", str)),
    ("INKBIRD_LOG_LEVEL", ("logging", "level", str)),
)


def _environment_values(environ: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for env_name, (section, key, cast) in ENV_CONFIG_MAP:
        if section == "_meta" or env_name not in environ:
            continue
        values.setdefault(section, {})[key] = cast(environ[env_name])
    return values


def apply_environment_overrides(config: AppConfig, environ: Mapping[str, str] | None = None) -> AppConfig:
    values = _environment_values(os.environ if environ is None else environ)
    if not values:
        return config

    return AppConfig(
        device=_merge_dataclass(config.device, values.get("device", {})),
        sdr=_merge_dataclass(config.sdr, values.get("sdr", {})),
        decoder=_merge_dataclass(config.decoder, values.get("decoder", {})),
        mqtt=_merge_dataclass(config.mqtt, values.get("mqtt", {})),
        logging=_merge_dataclass(config.logging, values.get("logging", {})),
    )


def _section_values(raw: Mapping[str, Any], section: str, config_path: Path) -> Mapping[str, Any]:
    values = raw.get(section, {})
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise ValueError(f"config section {section!r} must be a mapping: {config_path}")
    return values


def load_config(path: str | Path | None = None) -> AppConfig:
    config = AppConfig()
    if path is None:
        path = os.environ.get("INKBIRD_CONFIG")
    if path is None:
        return apply_environment_overrides(config)

    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    if not isinstance(raw, Mapping):
        raise ValueError(f"config root must be a mapping: {config_path}")

    warn_unknown_config_keys(raw, config_path)

    sdr_values = dict(_section_values(raw, "sdr", config_path))
    if "keep_failed_files" in sdr_values:
        keep_failed = _as_bool(sdr_values["keep_failed_files"])
        sdr_values.setdefault("keep_no_hit_files", keep_failed)
        sdr_values.setdefault("keep_error_files", keep_failed)

    config = AppConfig(
        device=_merge_dataclass(config.device, _section_values(raw, "device", config_path)),
        sdr=_merge_dataclass(config.sdr, sdr_values),
        decoder=_merge_dataclass(config.decoder, _section_values(raw, "decoder", config_path)),
        mqtt=_merge_dataclass(config.mqtt, _section_values(raw, "mqtt", config_path)),
        logging=_merge_dataclass(config.logging, _section_values(raw, "logging", config_path)),
    )
    return apply_environment_overrides(config)


def parse_scaled_number(value: str | int | float) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = str(value).strip().lower().replace("_", "")
    if text.endswith("hz"):
        text = text[:-2]

    multiplier = 1.0
    if text.endswith("k"):
        multiplier = 1_000.0
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000.0
        text = text[:-1]

    return int(round(float(text) * multiplier))


def frequency_hz(value: str | int | float) -> int:
    return parse_scaled_number(value)


def sample_rate_hz(value: str | int | float) -> int:
    return parse_scaled_number(value)
