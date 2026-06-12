from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .config import AppConfig, frequency_hz, sample_rate_hz
from .decoder import DecodeResult

LOG = logging.getLogger(__name__)


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


def build_state_payload(result: DecodeResult) -> str:
    if not result.decode_ok or result.temperature_C is None:
        raise ValueError("only successful decode results can be published")
    return f"{result.temperature_C:.1f}"


class MQTTPublisher:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._connected

    def connect(self) -> None:
        if self.is_connected:
            return
        if self._client is not None:
            self.close(publish_offline=False)

        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("paho-mqtt is required for MQTT publishing") from exc

        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.config.mqtt.client_id)
        except (AttributeError, TypeError):
            client = mqtt.Client(client_id=self.config.mqtt.client_id)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        try:
            if hasattr(client, "connect_timeout"):
                client.connect_timeout = self.config.mqtt.connect_timeout_seconds
            elif hasattr(client, "_connect_timeout"):
                client._connect_timeout = self.config.mqtt.connect_timeout_seconds
        except Exception as exc:
            LOG.debug("mqtt_connect_timeout_config_ignored error=%r", exc)

        if self.config.mqtt.username is not None:
            client.username_pw_set(self.config.mqtt.username, self.config.mqtt.password)

        client.connect(self.config.mqtt.host, self.config.mqtt.port, keepalive=60)
        self._client = client
        self._connected = True
        client.loop_start()
        self.publish_availability("online", retain=True)

    def _on_connect(self, _client: object, _userdata: object, _flags: object, reason_code: object, *_args: object) -> None:
        self._connected = str(reason_code) in {"0", "Success"}
        if not self._connected:
            LOG.error("mqtt_connack_failed reason=%s", reason_code)

    def _on_disconnect(self, _client: object, _userdata: object, *args: object) -> None:
        self._connected = False
        reason = args[-2] if len(args) >= 2 else args[0] if args else "unknown"
        LOG.warning("mqtt_disconnected reason=%s", reason)

    def publish_availability(self, state: str, retain: bool | None = None) -> None:
        if not self.is_connected or not self.config.mqtt.availability_topic:
            return
        info = self._client.publish(
            self.config.mqtt.availability_topic,
            state,
            qos=self.config.mqtt.qos,
            retain=self.config.mqtt.retain if retain is None else retain,
        )
        info.wait_for_publish()

    def publish_decode(self, result: DecodeResult) -> dict[str, Any]:
        if not self.is_connected:
            raise RuntimeError("MQTT client is not connected")

        payload = build_mqtt_payload(result, self.config)
        info = self._client.publish(
            self.config.mqtt.topic,
            json.dumps(payload, separators=(",", ":")),
            qos=self.config.mqtt.qos,
            retain=self.config.mqtt.retain,
        )
        info.wait_for_publish()

        if self.config.mqtt.state_topic:
            state_info = self._client.publish(
                self.config.mqtt.state_topic,
                build_state_payload(result),
                qos=self.config.mqtt.qos,
                retain=self.config.mqtt.retain,
            )
            state_info.wait_for_publish()
        return payload

    def close(self, publish_offline: bool = True) -> None:
        if self._client is None:
            return
        try:
            if publish_offline:
                self.publish_availability("offline", retain=True)
        finally:
            self._client.disconnect()
            self._client.loop_stop()
            self._client = None
            self._connected = False
