# Inkbird IBS-P01R MQTT Decoder

Python service for decoding Inkbird IBS-P01R pool thermometer RF captures and publishing the temperature to MQTT.

The decoder is intended for Raspberry Pi installations that use `rtl_433 -S all` with an SDRplay RSPdx-R2. It reads `.cs16` IQ files, extracts the currently reverse-engineered Inkbird packet, decodes the temperature field, and publishes successful readings to MQTT as JSON plus plain scalar state topics.

## Status

Initial implementation based on verified capture analysis. The temperature field, prefix, marker variants, and IQ demodulation path are implemented. CRC/checksum, sensor ID, battery status, and channel data are not yet known.

## Features

- Decode a single `.cs16` file to JSON.
- Watch an `rtl_433 -S all` capture directory for long `.cs16` files.
- Optionally start and supervise `rtl_433`.
- Publish successful decodes to MQTT as JSON plus plain scalar state topics.
- Optionally connect to MQTT over TLS/MQTTS.
- Log periodic capture statistics and warn when no successful decode is seen for a configured time.
- Restart `rtl_433` automatically if the capture process exits.
- Provide `status` and `doctor` commands for installation diagnostics.
- Provide a systemd unit for always-on Raspberry Pi operation.
- Include tests for confirmed protocol vectors and marker validation.

## Raspberry Pi Installation

Install basic system packages first:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
```

Install and verify these external runtime dependencies before starting the service:

- SDRplay API for your SDRplay receiver.
- `rtl_433` with SDRplay support.
- An MQTT broker, for example Mosquitto or Home Assistant MQTT.

Clone the project to the target installation directory:

```bash
sudo mkdir -p /opt
cd /opt
sudo git clone https://github.com/dude2k/InkBird-to-MQTT.git inkbird-ibs-p01r-mqtt
sudo chown -R "$USER:$USER" /opt/inkbird-ibs-p01r-mqtt
cd /opt/inkbird-ibs-p01r-mqtt
```

Create a virtual environment and install the package into it:

```bash
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install .
```

Create the runtime directories and configuration:

```bash
sudo useradd --system --home /var/lib/inkbird-ibs-p01r --shell /usr/sbin/nologin inkbird
sudo mkdir -p /etc/inkbird-ibs-p01r /var/lib/inkbird-ibs-p01r
sudo cp config.example.yaml /etc/inkbird-ibs-p01r/config.yaml
sudo chown -R inkbird:inkbird /var/lib/inkbird-ibs-p01r
sudo chown root:root /etc/inkbird-ibs-p01r/config.yaml
```

Edit `/etc/inkbird-ibs-p01r/config.yaml` and set at least:

- `mqtt.host`
- `mqtt.topic`
- `sdr.device`
- `sdr.capture_dir`, default `/run/inkbird-ibs-p01r/captures`
- `sdr.start_rtl433: true`, if the service should start `rtl_433` itself

Install and start the systemd service:

```bash
sudo cp systemd/inkbird-ibs-p01r-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now inkbird-ibs-p01r-mqtt.service
sudo systemctl status inkbird-ibs-p01r-mqtt.service
```

Follow logs:

```bash
journalctl -u inkbird-ibs-p01r-mqtt.service -f
```

## Updating On The Raspberry Pi

When the service was installed with `pip install .`, pull updates and reinstall the package into the virtual environment:

```bash
cd /opt/inkbird-ibs-p01r-mqtt
git pull
. .venv/bin/activate
pip install .
sudo cp systemd/inkbird-ibs-p01r-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart inkbird-ibs-p01r-mqtt.service
```

Check the installed version:

```bash
inkbird-ibs-p01r-mqtt --version
```

Check the effective config and run installation diagnostics:

```bash
inkbird-ibs-p01r-mqtt status --config /etc/inkbird-ibs-p01r/config.yaml
inkbird-ibs-p01r-mqtt doctor --config /etc/inkbird-ibs-p01r/config.yaml
```

## Local Quick Start

For testing or development on a cloned checkout:

```bash
git clone https://github.com/dude2k/InkBird-to-MQTT.git
cd InkBird-to-MQTT
python -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e .
cp config.example.yaml config.yaml
```

`pip install -e .` is an editable developer install. For a Raspberry Pi service install, prefer `pip install .` and rerun it after `git pull` updates.

Decode one file:

```bash
inkbird-ibs-p01r-mqtt decode-file ./captures/g005_434.097M_1000k.cs16
```

Add `--delete-after` if a manual decode should remove the input file after the decode attempt.

Watch a directory:

```bash
inkbird-ibs-p01r-mqtt watch-dir ./captures --config ./config.yaml
```

Run the MQTT service:

```bash
inkbird-ibs-p01r-mqtt run --config ./config.yaml
```

## MQTT Troubleshooting

If the service logs `TimeoutError: timed out` while connecting to MQTT, the configured broker address or port is not reachable from the Raspberry Pi.

Check the effective service config:

```bash
sudo grep -A20 '^mqtt:' /etc/inkbird-ibs-p01r/config.yaml
```

Check TCP reachability from the Pi:

```bash
nc -vz MQTT_BROKER_IP 1883
```

If `nc` is not installed:

```bash
sudo apt install -y netcat-openbsd
```

If Mosquitto client tools are installed, test a publish without this service:

```bash
mosquitto_pub -h MQTT_BROKER_IP -p 1883 -t sensors/inkbird_ibs_p01r/test -m test
```

Common causes:

- The broker only listens on `localhost` instead of the LAN address.
- Firewall rules block port `1883`.
- The IP address in `mqtt.host` is wrong or not reachable from the Pi network.
- Username/password are required but missing in `config.yaml`.

When MQTT is unavailable, the service now logs `mqtt_connect_failed` and retries instead of exiting.

## MQTTS / TLS

MQTT over TLS is disabled by default. Enable it when your broker listens on an encrypted MQTT port, usually `8883`:

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

`tls_ca_cert: null` uses the system trust store. For a private CA, set `tls_ca_cert` to the CA certificate path. For mutual TLS, set `tls_client_cert` and `tls_client_key`.

For temporary self-signed test setups, `tls_insecure: true` disables certificate verification. Leave it `false` for normal operation.

`doctor` performs a TLS handshake when `tls_enabled: true`:

```bash
inkbird-ibs-p01r-mqtt doctor --config /etc/inkbird-ibs-p01r/config.yaml
```

## MQTT Topics

By default, every successful decode is published to these measurement topics:

```text
sensors/inkbird_ibs_p01r/pool
sensors/inkbird_ibs_p01r/pool/state
sensors/inkbird_ibs_p01r/pool/field
sensors/inkbird_ibs_p01r/pool/raw13
sensors/inkbird_ibs_p01r/pool/confidence
sensors/inkbird_ibs_p01r/pool/last_seen
```

The first topic contains the full JSON payload. The other topics contain plain values for ioBroker, Home Assistant, charts, and automations.

The `/state` topic contains only the temperature value, for example:

```text
24.1
```

Set any optional topic to `null` in `config.yaml` to disable it.

## ioBroker

The ioBroker MQTT adapter usually creates one object per topic. Use these plain values for states, charts, and automations:

```text
mqtt.0.sensors.inkbird_ibs_p01r.pool.state
mqtt.0.sensors.inkbird_ibs_p01r.pool.field
mqtt.0.sensors.inkbird_ibs_p01r.pool.raw13
mqtt.0.sensors.inkbird_ibs_p01r.pool.confidence
mqtt.0.sensors.inkbird_ibs_p01r.pool.last_seen
```

The JSON topic:

```text
mqtt.0.sensors.inkbird_ibs_p01r.pool
```

is still useful for diagnostics because it includes `field`, `raw13`, `marker`, `confidence_count`, and the source file.

If ioBroker creates `/state` as a string, delete the object once or change its object type to `number`; the next publish will carry a plain value such as `24.1`.

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

The `/state` topic is the numeric sensor value. The JSON topic is attached as attributes for debugging.

## Capture Cleanup

For Raspberry Pi 24/7 operation, the recommended capture directory is:

```yaml
sdr:
  capture_dir: "/run/inkbird-ibs-p01r/captures"
  cleanup_after_decode: true
  keep_successful_files: false
  keep_no_hit_files: false
  keep_error_files: true
  max_capture_age_seconds: 3600
  max_capture_dir_size_mb: 256
  capture_stats_interval_seconds: 300
  no_successful_decode_warning_seconds: 3600
  rtl433_restart_interval_seconds: 10
```

`/run` is usually a RAM-backed tmpfs. This avoids keeping the frequent `rtl_433 -S all` `.cs16` writes on the SD card. The systemd unit creates `/run/inkbird-ibs-p01r`, and the Python service creates the `captures` subdirectory.

The service deletes stable `.cs16` files after processing:

- successful decodes are deleted after MQTT publish unless `keep_successful_files: true`
- `no_hit` captures are deleted unless `keep_no_hit_files: true`
- short stable captures below `min_long_file_size` are treated as `too_short` and deleted unless `keep_no_hit_files: true`
- `decode_error` captures are kept by default with `keep_error_files: true`

For debugging, use a persistent directory and enable retention:

```yaml
sdr:
  capture_dir: "/var/lib/inkbird-ibs-p01r/captures"
  keep_successful_files: true
  keep_no_hit_files: true
  keep_error_files: true
```

The service also removes stale captures older than `max_capture_age_seconds` and enforces `max_capture_dir_size_mb` by deleting the oldest `.cs16` files first.

Older configs with `keep_failed_files` are still accepted. If the new `keep_no_hit_files` and `keep_error_files` settings are absent, `keep_failed_files` is mapped to both of them.

At `INFO` level, the service periodically logs aggregate capture statistics:

```text
capture_stats seen=120 decoded=2 no_hit=8 too_short=110 errors=0 unstable=0 deleted=118 kept=2 deferred=0
```

It also warns when no successful decode has been published for `no_successful_decode_warning_seconds`. This helps catch antenna, SDR, or sensor problems while keeping normal `too_short` cleanup quiet.

## Example Decode Output

```json
{
  "decode_ok": true,
  "temperature_C": 26.2,
  "temperature_C_exact": 26.2,
  "field": "e0c0",
  "flags": 7,
  "raw13": 192,
  "confidence_count": 2,
  "marker": "2280a280",
  "file": "g005_434.097M_1000k.cs16"
}
```

Non-decodable long captures are expected with this capture method:

```json
{
  "decode_ok": false,
  "reason": "no_hit",
  "file": "g006_434.097M_1000k.cs16"
}
```

## Capture Command

The known-good capture command is:

```bash
rtl_433 \
  -d "driver=sdrplay,antenna=Antenna A" \
  -f 434.097M \
  -s 1000k \
  -S all
```

Useful long captures are usually around `3,145,728` bytes. The default long-file threshold is `3,000,000` bytes.

## Tests

```bash
python -m unittest discover -s tests
```

## Documentation

- [Decoder details](docs/DECODER.md)
- [SDR setup](docs/SDR_SETUP.md)
- [MQTT payloads](docs/MQTT.md)

## Changelog

- `0.4.0`: Add optional MQTT over TLS/MQTTS support and TLS checks in `doctor`.
- `0.3.0`: Add scalar MQTT topics, `status`/`doctor`, startup effective-config logging, and GitHub Actions CI.
- `0.2.0`: Improve capture cleanup, service observability, and internal `rtl_433` restart handling.
