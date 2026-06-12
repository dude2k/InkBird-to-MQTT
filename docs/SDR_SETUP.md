# SDR Setup

This project expects `.cs16` IQ captures written by `rtl_433 -S all`.

## Verified Hardware

```text
Receiver: SDRplay RSPdx-R2
SDRplay API: 3.15
rtl_433: v25.02
Frequency: 434.097 MHz
Sample rate: 1 Msps
Capture format: cs16
```

## Capture Command

```bash
rtl_433 \
  -d "driver=sdrplay,antenna=Antenna A" \
  -f 434.097M \
  -s 1000k \
  -S all
```

`rtl_433` writes capture files into the current working directory. For service use, configure `sdr.capture_dir` and either run `rtl_433` externally in that directory or set `sdr.start_rtl433: true`.

Recommended service capture directory:

```text
/run/inkbird-ibs-p01r/captures
```

`/run` is normally RAM-backed tmpfs on Linux and is preferred for continuous Raspberry Pi operation because it reduces SD-card writes. The systemd unit creates `/run/inkbird-ibs-p01r`, and the Python service creates the `captures` subdirectory.

For debugging, a persistent directory can be used instead:

```text
/var/lib/inkbird-ibs-p01r/captures
```

## Long Files

Not every capture contains a full usable packet. Short files often contain fragments only. The default long-file threshold is:

```text
3,000,000 bytes
```

Typical useful files are around:

```text
3,145,728 bytes
```

The service waits until a file is at least this size and stable before decoding it.

Stable files below this threshold are treated as `too_short` and cleaned up according to the same retention settings as `no_hit` captures.

## Runtime Monitoring

The service logs periodic aggregate capture statistics when `sdr.capture_stats_interval_seconds` is enabled. This keeps normal cleanup quiet while still showing whether captures are arriving and being deleted.

If `rtl_433` exits, the Python service logs `rtl433_exited` and starts it again after `sdr.rtl433_restart_interval_seconds`. This avoids a full systemd restart for transient capture-process failures.

If no successful decode is published for `sdr.no_successful_decode_warning_seconds`, the service logs `no_successful_decode_for`. That usually means no sensor packet was received, the receiver is tuned incorrectly, the antenna path is bad, or captures are being produced but not decoding.

## Diagnostics

Show the effective config and lightweight checks:

```bash
inkbird-ibs-p01r-mqtt status --config /etc/inkbird-ibs-p01r/config.yaml
```

Run deeper checks for MQTT TCP reachability, capture directory access, and the `rtl_433` command:

```bash
inkbird-ibs-p01r-mqtt doctor --config /etc/inkbird-ibs-p01r/config.yaml
```

`doctor` uses `--service-user inkbird` by default when it suggests a permission-check command. If your systemd unit uses a different `User=`, pass it explicitly:

```bash
inkbird-ibs-p01r-mqtt doctor --config /etc/inkbird-ibs-p01r/config.yaml --service-user YOUR_USER
```

Unknown config keys are reported as warnings to make configuration typos visible.

## Raspberry Pi Notes

Install and verify the SDRplay API and `rtl_433` before enabling the systemd service. The service user must be able to access the SDR device and write to the capture directory.
