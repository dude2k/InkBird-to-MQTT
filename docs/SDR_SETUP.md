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

## Raspberry Pi Notes

Install and verify the SDRplay API and `rtl_433` before enabling the systemd service. The service user must be able to access the SDR device and write to the capture directory.
