# Inkbird IBS-P01R MQTT Decoder

Python service for decoding Inkbird IBS-P01R pool thermometer RF captures and publishing the temperature to MQTT.

The decoder is intended for Raspberry Pi installations that use `rtl_433 -S all` with an SDRplay RSPdx-R2. It reads `.cs16` IQ files, extracts the currently reverse-engineered Inkbird packet, decodes the temperature field, and publishes successful readings as JSON.

## Status

Initial implementation based on verified capture analysis. The temperature field, prefix, marker variants, and IQ demodulation path are implemented. CRC/checksum, sensor ID, battery status, and channel data are not yet known.

## Features

- Decode a single `.cs16` file to JSON.
- Watch an `rtl_433 -S all` capture directory for long `.cs16` files.
- Optionally start and supervise `rtl_433`.
- Publish successful decodes to MQTT.
- Provide a systemd unit for always-on Raspberry Pi operation.
- Include tests for confirmed protocol vectors and marker validation.

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
```

Decode one file:

```bash
inkbird-ibs-p01r-mqtt decode-file ./captures/g005_434.097M_1000k.cs16
```

Watch a directory:

```bash
inkbird-ibs-p01r-mqtt watch-dir ./captures --config ./config.yaml
```

Run the MQTT service:

```bash
inkbird-ibs-p01r-mqtt run --config ./config.yaml
```

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

