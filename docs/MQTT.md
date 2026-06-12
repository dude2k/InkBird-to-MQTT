# MQTT

Every successful decode is published as JSON and, by default, as plain scalar state topics.

Default JSON topic:

```text
sensors/inkbird_ibs_p01r/pool
```

Example payload:

```json
{
  "device": "inkbird_ibs_p01r",
  "device_name": "pool",
  "device_id": "pool",
  "model": "Inkbird IBS-P01R",
  "temperature_C": 26.2,
  "temperature_C_exact": 26.2,
  "field": "e0c0",
  "flags": 7,
  "raw13": 192,
  "marker": "2280a280",
  "confidence_count": 2,
  "frequency_Hz": 434097000,
  "sample_rate": 1000000,
  "source": "rtl_433_cs16",
  "source_file": "g005_434.097M_1000k.cs16",
  "timestamp": "2026-06-12T12:20:00+02:00"
}
```

The plain temperature value is published when `mqtt.state_topic` is set:

```text
sensors/inkbird_ibs_p01r/pool/state
```

Example payload:

```text
26.2
```

Set `mqtt.state_topic: null` to disable the plain state topic.

Additional scalar topics are enabled by default:

```text
sensors/inkbird_ibs_p01r/pool/field
sensors/inkbird_ibs_p01r/pool/raw13
sensors/inkbird_ibs_p01r/pool/confidence
sensors/inkbird_ibs_p01r/pool/last_seen
```

Example payloads:

```text
fe20
-480
20
2026-06-12T13:14:35+02:00
```

Set `mqtt.field_topic`, `mqtt.raw13_topic`, `mqtt.confidence_topic`, or `mqtt.last_seen_topic` to `null` to disable individual scalar topics.

Availability is published when `mqtt.availability_topic` is set:

```text
sensors/inkbird_ibs_p01r/pool/availability
```

Payloads:

```text
online
offline
```

## Test Publish

```bash
inkbird-ibs-p01r-mqtt test-mqtt --config ./config.yaml
```

## Connection Retries

The service retries MQTT connections instead of exiting when the broker is temporarily unreachable.

Relevant configuration:

```yaml
mqtt:
  host: "192.168.1.10"
  port: 1883
  topic: "sensors/inkbird_ibs_p01r/pool"
  state_topic: "sensors/inkbird_ibs_p01r/pool/state"
  field_topic: "sensors/inkbird_ibs_p01r/pool/field"
  raw13_topic: "sensors/inkbird_ibs_p01r/pool/raw13"
  confidence_topic: "sensors/inkbird_ibs_p01r/pool/confidence"
  last_seen_topic: "sensors/inkbird_ibs_p01r/pool/last_seen"
  tls_enabled: false
  tls_ca_cert: null
  tls_insecure: false
  tls_client_cert: null
  tls_client_key: null
  connect_timeout_seconds: 10
  reconnect_interval_seconds: 30
```

If the broker is on another machine, verify from the Raspberry Pi that TCP port `1883` is reachable:

```bash
nc -vz 192.168.1.10 1883
```

## MQTTS / TLS

For MQTT over TLS, enable TLS and use your broker's encrypted port, usually `8883`:

```yaml
mqtt:
  host: "mqtt.example.local"
  port: 8883
  tls_enabled: true
  tls_ca_cert: null
  tls_insecure: false
  tls_client_cert: null
  tls_client_key: null
```

`tls_ca_cert: null` uses the system trust store. Set `tls_ca_cert` for a private CA. Set `tls_client_cert` and `tls_client_key` when the broker requires client certificates.

`tls_insecure: true` disables certificate verification and should only be used temporarily while testing a self-signed setup.

When TLS is enabled, `doctor` performs a TLS handshake:

```bash
inkbird-ibs-p01r-mqtt doctor --config /etc/inkbird-ibs-p01r/config.yaml
```

## Home Assistant

Manual MQTT sensor example:

```yaml
mqtt:
  sensor:
    - name: "Pool Temperature"
      unique_id: inkbird_ibs_p01r_pool_temperature
      state_topic: "sensors/inkbird_ibs_p01r/pool/state"
      availability_topic: "sensors/inkbird_ibs_p01r/pool/availability"
      json_attributes_topic: "sensors/inkbird_ibs_p01r/pool"
      unit_of_measurement: "°C"
      device_class: temperature
      state_class: measurement
    - name: "Pool Inkbird Confidence"
      unique_id: inkbird_ibs_p01r_pool_confidence
      state_topic: "sensors/inkbird_ibs_p01r/pool/confidence"
      availability_topic: "sensors/inkbird_ibs_p01r/pool/availability"
      state_class: measurement
    - name: "Pool Inkbird Raw13"
      unique_id: inkbird_ibs_p01r_pool_raw13
      state_topic: "sensors/inkbird_ibs_p01r/pool/raw13"
      availability_topic: "sensors/inkbird_ibs_p01r/pool/availability"
    - name: "Pool Inkbird Last Seen"
      unique_id: inkbird_ibs_p01r_pool_last_seen
      state_topic: "sensors/inkbird_ibs_p01r/pool/last_seen"
      availability_topic: "sensors/inkbird_ibs_p01r/pool/availability"
      device_class: timestamp
```

## ioBroker

Use the scalar topics as direct ioBroker states:

```text
mqtt.0.sensors.inkbird_ibs_p01r.pool.state
mqtt.0.sensors.inkbird_ibs_p01r.pool.field
mqtt.0.sensors.inkbird_ibs_p01r.pool.raw13
mqtt.0.sensors.inkbird_ibs_p01r.pool.confidence
mqtt.0.sensors.inkbird_ibs_p01r.pool.last_seen
```

Keep the JSON topic for diagnostics:

```text
mqtt.0.sensors.inkbird_ibs_p01r.pool
```
