from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import AppConfig, frequency_hz, sample_rate_hz
from .decoder import DecodeResult


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_mqtt_payload(result: DecodeResult, config: AppConfig, timestamp: str | None = None) -> dict[str, Any]:
    if not result.decode_ok:
        raise ValueError("only successful decode results can be published")

    return {
        "device": "inkbird_ibs_p01r",
        "device_name": config.device.name,
        "device_id": config.device.id,
        "model": config.device.model,
        "temperature_C": result.temperature_C,
        "temperature_C_exact": result.temperature_C_exact,
        "field": result.field,
        "flags": result.flags,
        "raw13": result.raw13,
        "marker": result.marker,
        "confidence_count": result.confidence_count,
        "frequency_Hz": frequency_hz(config.sdr.frequency),
        "sample_rate": sample_rate_hz(config.sdr.sample_rate),
        "source": config.sdr.mode,
        "source_file": result.file,
        "timestamp": timestamp or utc_timestamp(),
    }


class MQTTPublisher:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = None

    def connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("paho-mqtt is required for MQTT publishing") from exc

        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.config.mqtt.client_id)
        except (AttributeError, TypeError):
            client = mqtt.Client(client_id=self.config.mqtt.client_id)

        if self.config.mqtt.username is not None:
            client.username_pw_set(self.config.mqtt.username, self.config.mqtt.password)

        client.connect(self.config.mqtt.host, self.config.mqtt.port, keepalive=60)
        client.loop_start()
        self._client = client
        self.publish_availability("online", retain=True)

    def publish_availability(self, state: str, retain: bool | None = None) -> None:
        if self._client is None or not self.config.mqtt.availability_topic:
            return
        info = self._client.publish(
            self.config.mqtt.availability_topic,
            state,
            qos=self.config.mqtt.qos,
            retain=self.config.mqtt.retain if retain is None else retain,
        )
        info.wait_for_publish()

    def publish_decode(self, result: DecodeResult) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("MQTT client is not connected")

        payload = build_mqtt_payload(result, self.config)
        info = self._client.publish(
            self.config.mqtt.topic,
            json.dumps(payload, separators=(",", ":")),
            qos=self.config.mqtt.qos,
            retain=self.config.mqtt.retain,
        )
        info.wait_for_publish()
        return payload

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self.publish_availability("offline", retain=True)
        finally:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

