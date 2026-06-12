from __future__ import annotations

import warnings
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Mapping

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
    mode: str = "rtl433_cs16"
    start_rtl433: bool = False
    rtl433_path: str = "rtl_433"
    device: str = "driver=sdrplay,antenna=Antenna A"
    frequency: str = "434.097M"
    sample_rate: str = "1000k"
    capture_dir: str = "/run/inkbird-ibs-p01r/captures"
    min_long_file_size: int = 3_000_000
    cleanup_after_decode: bool = True
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
        return config

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

    return AppConfig(
        device=_merge_dataclass(config.device, _section_values(raw, "device", config_path)),
        sdr=_merge_dataclass(config.sdr, sdr_values),
        decoder=_merge_dataclass(config.decoder, _section_values(raw, "decoder", config_path)),
        mqtt=_merge_dataclass(config.mqtt, _section_values(raw, "mqtt", config_path)),
        logging=_merge_dataclass(config.logging, _section_values(raw, "logging", config_path)),
    )


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
