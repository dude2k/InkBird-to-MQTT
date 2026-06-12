# MQTT

Every successful decode is published as JSON and, by default, as a plain numeric temperature state.

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
  connect_timeout_seconds: 10
  reconnect_interval_seconds: 30
```

If the broker is on another machine, verify from the Raspberry Pi that TCP port `1883` is reachable:

```bash
nc -vz 192.168.1.10 1883
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
```

## ioBroker

Use the `/state` topic as the numeric value:

```text
mqtt.0.sensors.inkbird_ibs_p01r.pool.state
```

Keep the JSON topic for diagnostics:

```text
mqtt.0.sensors.inkbird_ibs_p01r.pool
```
