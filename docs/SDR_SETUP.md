# SDR Setup

This project is now tuned for a Nooelec/RTL-SDR receiver driven by `rtl_433 -S all`.
With RTL-SDR hardware, `rtl_433` writes unsigned 8-bit IQ captures as `.cu8` files.
The service converts those files to `.cs16` before running the existing Inkbird decoder.

## Verified Hardware

```text
Host: rpi-adsb
Receiver: RTL-SDR / Nooelec
Tuner: RTL2838/E4000
RTL-SDR serial: 00000001
Frequency: 434.097 MHz
Sample rate: 1 Msps
Gain: 30
Capture format from rtl_433: cu8
Decoder input after conversion: cs16
```

The receiver is selected by serial with `-d 00000001`. Do not hardcode
`/dev/bus/usb/...` paths; those can change after reboot or USB re-enumeration.
On `rpi-adsb`, ADS-B uses a different stick, so selecting the Inkbird receiver by
serial keeps the ADS-B receiver untouched.

## Capture Command

The known-good capture command is:

```bash
rtl_433 \
  -d 00000001 \
  -f 434.097M \
  -s 1000k \
  -R 0 \
  -Y minmax \
  -g 30 \
  -S all \
  -F log
```

The sensor is nominally around 433.92 MHz. The center frequency is intentionally
`434.097M` because the current decoder expects the FSK tones relative to the SDR
center around -177 kHz.

`rtl_433` writes capture files into the current working directory. For service
use, configure `sdr.capture_dir` and set `sdr.start_rtl433: true`.

Recommended service capture directory:

```text
/run/inkbird-ibs-p01r/captures
```

`/run` is normally RAM-backed tmpfs on Linux and is preferred for continuous
Raspberry Pi operation because it reduces SD-card writes. The systemd unit
creates `/run/inkbird-ibs-p01r`, and the Python service creates the `captures`
subdirectory.

For debugging, a persistent directory can be used instead:

```text
/var/lib/inkbird-ibs-p01r/captures
```

## Configuration

YAML configuration and environment variables can be combined. Environment values
override YAML values.

```yaml
sdr:
  mode: "rtl433_cu8"
  start_rtl433: true
  rtl433_path: "rtl_433"
  device: "00000001"
  frequency: "434.097M"
  sample_rate: "1000k"
  gain: "30"
  capture_dir: "/run/inkbird-ibs-p01r/captures"
  keep_cu8: false
  keep_cs16: false
```

Equivalent systemd environment file entries:

```dotenv
SDR_DEVICE=00000001
FREQ=434.097M
SAMPLE_RATE=1000k
GAIN=30
KEEP_CU8=false
KEEP_CS16=false
MQTT_HOST=192.168.1.10
MQTT_TOPIC=sensors/inkbird_ibs_p01r/pool
```

## Long Files

Not every capture contains a full usable packet. Short files often contain
fragments only. The default long-file threshold is:

```text
3,000,000 bytes
```

The confirmed RTL-SDR test capture was:

```text
g001_434.097M_1000k.cu8
3,014,656 bytes
about 1.507 s
```

Stable files below this threshold are treated as `too_short` and cleaned up
according to `keep_cu8`.

## Runtime Monitoring

The service logs periodic aggregate capture statistics when
`sdr.capture_stats_interval_seconds` is enabled. This keeps normal cleanup quiet
while still showing whether captures are arriving and being deleted.

If `rtl_433` exits, the Python service logs `rtl433_exited` and starts it again
after `sdr.rtl433_restart_interval_seconds`. This avoids a full systemd restart
for transient capture-process failures.

If no successful decode is published for `sdr.no_successful_decode_warning_seconds`,
the service logs `no_successful_decode_for`. That usually means no sensor packet
was received, the receiver is tuned incorrectly, the antenna path is bad, or
captures are being produced but not decoding.

## Troubleshooting

- `captures=0`: antenna, receiver placement, permissions, serial selection, or sensor range problem.
- `FAIL:no_hit`: a long capture was present, but it was likely a foreign signal or an incomplete fragment.
- `decode_ok=true`: a valid Inkbird frame was decoded and can be published.
- `clip_pct > 0`: reduce `GAIN`.

## Diagnostics

Show the effective config and lightweight checks:

```bash
inkbird-ibs-p01r-mqtt status --config /etc/inkbird-ibs-p01r/config.yaml
```

Run deeper checks for MQTT TCP reachability, capture directory access, and the
`rtl_433` command:

```bash
inkbird-ibs-p01r-mqtt doctor --config /etc/inkbird-ibs-p01r/config.yaml
```

Both commands can also run without `--config` when values are supplied by the
environment or `/etc/inkbird-to-mqtt.env` through systemd.

Unknown config keys are reported as warnings to make configuration typos visible.

## Raspberry Pi Notes

Install `rtl_433` with RTL-SDR support before enabling the systemd service. The
service user must be able to access the RTL-SDR stick and write to the capture
directory.
