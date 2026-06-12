# Inkbird IBS-P01R Decoder Documentation

## Overview

This document describes the currently reverse-engineered RF packet decoding for the Inkbird IBS-P01R floating pool thermometer.

The decoder is based on IQ recordings captured with `rtl_433 -S all` and SDRplay hardware. It does not depend on rtl_433 having a native decoder for this device.

The current implementation decodes temperature reliably from `.cs16` IQ captures.

## Capture Parameters

Verified SDR setup:

```text
Receiver: SDRplay RSPdx-R2
rtl_433 device: driver=sdrplay,antenna=Antenna A
Frequency: 434.097 MHz
Sample rate: 1,000,000 samples/s
Capture format: cs16
```

Working capture command:

```bash
rtl_433 \
  -d "driver=sdrplay,antenna=Antenna A" \
  -f 434.097M \
  -s 1000k \
  -S all
```

The `-S all` option writes IQ captures as `.cs16` files. The useful files are usually long captures of approximately:

```text
3,145,728 bytes
```

Short files may contain only preamble or unusable fragments.

## Modulation

The signal is FSK-like and can be decoded from FM-demodulated IQ phase differences.

Observed tone centers:

```text
low tone:  approximately -192.7 kHz
high tone: approximately -172.2 kHz
tone spacing: approximately 20.5 kHz
```

Symbol timing:

```text
Sample rate: 1,000,000 samples/s
Samples per symbol: 100
Symbol duration: 100 µs
Symbol rate: approximately 10 kBd
```

Bit threshold:

```text
threshold: approximately -182.5 kHz
```

Valid symbol tone range:

```text
-215,000 Hz <= median symbol frequency <= -150,000 Hz
```

## IQ Demodulation

Input format:

```text
little-endian signed int16
interleaved IQ
I0, Q0, I1, Q1, ...
```

Python loading:

```python
import numpy as np

x = np.fromfile(path, dtype="<i2")

if len(x) % 2:
    x = x[:-1]

z = x[0::2].astype(np.float32) + 1j * x[1::2].astype(np.float32)
```

FM demodulation:

```python
FS = 1_000_000

d = z[1:] * np.conj(z[:-1])
freq = np.angle(d).astype(np.float32) * (FS / (2*np.pi))
```

Symbol slicing:

```python
SPS = 100
```

For each possible phase offset, take the median of 100 frequency samples:

```python
median_frequency = median(freq[phase + n*SPS : phase + (n+1)*SPS])
```

Bit decision:

```text
if median_frequency > -182500 Hz:
    bit = 1
else:
    bit = 0
```

Only symbols whose median frequency lies in the valid tone band are used.

Recommended phase search order:

```text
0, 5, 10, 15,
40, 45, 50, 55, 60, 65,
90, 95,
20, 25, 30, 35, 70, 75, 80, 85
```

## Packet Structure

A decoded usable packet contains a long alternating preamble followed by a canonical payload tail.

Known preamble pattern:

```text
55 / aa alternating sequence
```

Known canonical payload prefix:

```text
45ba9a7221f00060200c86a8
```

After this prefix comes a 16-bit field container:

```text
field16
```

After the field comes a marker/trailer word sequence:

```text
0280a280
```

or:

```text
2280a280
```

Observed payload layout:

```text
[preamble] [prefix] [field16] [marker] [remaining trailer]
```

Concrete examples:

```text
25.2 °C:
45ba9a7221f00060200c86a8 ff80 0280a280 ab9e20

26.2 °C:
45ba9a7221f00060200c86a8 e0c0 2280a280 aead60

26.1 °C:
45ba9a7221f00060200c86a8 e0a0 2280a280 aeab04
```

## Marker Validation

The marker is not always byte-identical. Known variants:

```text
0280a280
2280a280
```

The first marker word differs by bit `0x2000`.

Validation rule:

```python
def marker_ok(marker_hex: str) -> bool:
    if len(marker_hex) < 8:
        return False

    w1 = int(marker_hex[:4], 16)
    w2 = int(marker_hex[4:8], 16)

    return (w1 & 0xdfff) == 0x0280 and w2 == 0xa280
```

This accepts:

```text
0280a280
2280a280
```

and rejects unrelated false hits.

## Temperature Field

The 16-bit field immediately following the prefix is not a signed 16-bit temperature value.

Correct interpretation:

```text
field16: 16-bit container
bits 15..13: flags
bits 12..0: signed 13-bit temperature raw value
```

Extraction:

```python
container = int(field_hex, 16)

flags = (container >> 13) & 0x7

raw13 = container & 0x1fff
if raw13 >= 0x1000:
    raw13 -= 0x2000
```

Temperature formula:

```python
temperature_C = (raw13 + 8192) / 320
```

Resolution:

```text
32 raw counts = 0.1 °C
1 raw count = 0.003125 °C
```

The decoded display temperature appears to be on a 0.1 °C grid.

## Why signed16 Is Wrong

An early decoder interpreted the field as signed 16-bit:

```python
raw = signed16(field)
temperature_C = (raw + 8192) / 320
```

This worked below approximately 25.6 °C for some fields, but failed above the zero crossing.

Example:

```text
field=e0c0
signed16(e0c0) = -8000
temperature = 0.6 °C
```

But the real measured value was:

```text
26.2 °C
```

Correct raw13 interpretation:

```text
e0c0 & 1fff = 00c0
raw13 = 192
temperature = (192 + 8192) / 320 = 26.2 °C
```

Therefore the correct temperature field is signed 13-bit, not signed 16-bit.

## Confirmed Test Vectors

The following vectors have been confirmed from live captures:

```text
Temperature  Field  Flags  Raw13  Marker
22.6 °C      fc40   7      -960   not always printed, expected valid
24.9 °C      ff20   7      -224   0280a280
25.1 °C      ff60   7      -160   0280a280
25.2 °C      ff80   7      -128   0280a280
25.4 °C      ffc0   7       -64   0280a280
25.5 °C      ffe0   7       -32   0280a280
26.0 °C      e080   7       128   2280a280
26.1 °C      e0a0   7       160   2280a280
26.2 °C      e0c0   7       192   2280a280
26.4 °C      e100   7       256   2280a280
```

Unit tests should assert both directions:

```text
field -> temperature
temperature -> expected raw13
```

Example:

```python
def test_26_2():
    assert decode_temperature_field("e0c0") == {
        "flags": 7,
        "raw13": 192,
        "temperature_C": 26.2,
    }
```

## Recommended Decoder Logic

High-level algorithm:

```text
1. Load cs16 IQ file.
2. FM-demodulate via z[n+1] * conj(z[n]).
3. Convert instantaneous phase to frequency.
4. Slice into 100-sample symbols.
5. Try multiple phase offsets.
6. Convert valid FSK symbols to bitstream.
7. Split valid contiguous symbol regions.
8. Search bitstream for prefix:
   45ba9a7221f00060200c86a8
9. Read next 16 bits as field16.
10. Read next 32 bits as marker.
11. Validate marker with 0x2000 mask in first marker word.
12. Extract flags and signed raw13.
13. Convert raw13 to temperature.
14. Accept only plausible results.
```

Plausibility checks:

```text
temperature range: e.g. -20 °C to 60 °C
raw13 % 32 == 0
marker_ok == true
prefix exact match
```

`raw13 % 32 == 0` is useful because confirmed 0.1 °C values are spaced by 32 counts.

## Reference Python Functions

```python
def raw13_from_field(field_hex: str) -> int:
    v = int(field_hex, 16) & 0x1fff

    if v >= 0x1000:
        v -= 0x2000

    return v


def flags_from_field(field_hex: str) -> int:
    return (int(field_hex, 16) >> 13) & 0x7


def temperature_from_raw13(raw13: int) -> float:
    return (raw13 + 8192) / 320.0


def decode_temperature_field(field_hex: str) -> dict:
    raw13 = raw13_from_field(field_hex)
    flags = flags_from_field(field_hex)
    temp = temperature_from_raw13(raw13)

    return {
        "field": field_hex.lower(),
        "flags": flags,
        "raw13": raw13,
        "temperature_C": round(temp, 1),
        "temperature_C_exact": temp,
    }
```

Marker validation:

```python
def marker_ok(marker_hex: str) -> bool:
    if len(marker_hex) < 8:
        return False

    w1 = int(marker_hex[:4], 16)
    w2 = int(marker_hex[4:8], 16)

    return (w1 & 0xdfff) == 0x0280 and w2 == 0xa280
```

## Confidence Count

The current decoder tries multiple symbol phase offsets. If multiple phase offsets produce the same field value, this increases confidence.

Typical good result:

```text
confidence_count=2
```

Guidance:

```text
confidence_count >= 3: strong
confidence_count = 2: good
confidence_count = 1: usable but lower confidence
decode_ok=false: no usable packet
```

Do not treat `no_decode` as a fatal error. Some captured files are not complete or not aligned enough to decode.

## Known Limitations

Not yet reverse-engineered:

```text
CRC or checksum
sensor ID
battery status
channel
meaning of flags
full trailer structure
packet repeat count
```

Currently observed:

```text
flags often equals 7
```

But the meaning is not yet known.

Known trailing examples:

```text
25.2:
... ff80 0280a280 ab9e20

26.2:
... e0c0 2280a280 aead60

26.1:
... e0a0 2280a280 aeab04
```

The trailing bytes may contain checksum, status, or other information.

## MQTT Integration Recommendation

A successful decode should be published as JSON.

Example MQTT topic:

```text
sensors/inkbird_ibs_p01r/pool
```

Example payload:

```json
{
  "device": "inkbird_ibs_p01r",
  "temperature_C": 26.2,
  "temperature_C_exact": 26.2,
  "field": "e0c0",
  "flags": 7,
  "raw13": 192,
  "marker": "2280a280",
  "confidence_count": 2,
  "source": "rtl_433_cs16",
  "frequency_Hz": 434097000,
  "sample_rate": 1000000
}
```

## Example CLI Output

Human-readable live mode:

```text
2026-06-12T12:20:00+0200 temperature_C=26.2 temperature_C_exact=26.200 field=e0c0 flags=7 raw13=192 confidence_count=2 file=g008_434.097M_1000k.cs16
```

Machine-readable JSON mode:

```json
{
  "decode_ok": true,
  "temperature_C": 26.2,
  "temperature_C_exact": 26.2,
  "field": "e0c0",
  "flags": 7,
  "raw13": 192,
  "confidence_count": 2,
  "marker": "2280a280"
}
```

## Summary

The temperature decoder is considered robust for the tested range.

Core facts:

```text
Prefix: 45ba9a7221f00060200c86a8
Temperature container: next 16 bits
Temperature raw: signed 13-bit from lower 13 bits
Flags: upper 3 bits
Formula: temperature_C = (raw13 + 8192) / 320
Marker: 0280a280 or 2280a280
Symbol rate: approximately 10 kBd
Sample rate: 1 Msps
Samples per symbol: 100
```

Do not use signed16 decoding. Use signed13 from the lower 13 bits.
