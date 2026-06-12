from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from .config import DecoderConfig
from .iq import fm_demodulate, load_cs16

PREFIX_HEX = "45ba9a7221f00060200c86a8"
PREFIX_BITS = "".join(f"{int(ch, 16):04b}" for ch in PREFIX_HEX)
PHASE_OFFSETS = (
    0,
    5,
    10,
    15,
    40,
    45,
    50,
    55,
    60,
    65,
    90,
    95,
    20,
    25,
    30,
    35,
    70,
    75,
    80,
    85,
)


@dataclass(frozen=True)
class TemperatureDecode:
    field: str
    flags: int
    raw13: int
    temperature_C: float
    temperature_C_exact: float

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "field": self.field,
            "flags": self.flags,
            "raw13": self.raw13,
            "temperature_C": self.temperature_C,
            "temperature_C_exact": self.temperature_C_exact,
        }


@dataclass(frozen=True)
class PacketCandidate:
    temperature: TemperatureDecode
    marker: str
    phase: int
    bit_index: int


@dataclass(frozen=True)
class DecodeResult:
    decode_ok: bool
    file: str
    reason: str | None = None
    temperature_C: float | None = None
    temperature_C_exact: float | None = None
    field: str | None = None
    flags: int | None = None
    raw13: int | None = None
    confidence_count: int | None = None
    marker: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"decode_ok": self.decode_ok}
        if self.decode_ok:
            data.update(
                {
                    "temperature_C": self.temperature_C,
                    "temperature_C_exact": self.temperature_C_exact,
                    "field": self.field,
                    "flags": self.flags,
                    "raw13": self.raw13,
                    "confidence_count": self.confidence_count,
                    "marker": self.marker,
                }
            )
        else:
            data["reason"] = self.reason or "decode_error"
        data["file"] = self.file
        return data


def raw13_from_field(field_hex: str) -> int:
    value = int(field_hex, 16) & 0x1FFF
    if value >= 0x1000:
        value -= 0x2000
    return value


def flags_from_field(field_hex: str) -> int:
    return (int(field_hex, 16) >> 13) & 0x7


def temperature_from_raw13(raw13: int) -> float:
    return (raw13 + 8192) / 320.0


def decode_temperature_field(field_hex: str) -> TemperatureDecode:
    normalized = field_hex.lower()
    if len(normalized) != 4:
        raise ValueError(f"field must contain exactly 16 bits as hex: {field_hex!r}")

    raw13 = raw13_from_field(normalized)
    exact = temperature_from_raw13(raw13)
    return TemperatureDecode(
        field=normalized,
        flags=flags_from_field(normalized),
        raw13=raw13,
        temperature_C=round(exact, 1),
        temperature_C_exact=exact,
    )


def marker_ok(marker_hex: str) -> bool:
    if len(marker_hex) < 8:
        return False
    try:
        w1 = int(marker_hex[:4], 16)
        w2 = int(marker_hex[4:8], 16)
    except ValueError:
        return False
    return (w1 & 0xDFFF) == 0x0280 and w2 == 0xA280


def bits_to_int(bits: Sequence[int] | str) -> int:
    if isinstance(bits, str):
        return int(bits, 2)
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def bits_to_hex(bits: Sequence[int] | str) -> str:
    width = len(bits)
    return f"{bits_to_int(bits):0{(width + 3) // 4}x}"


def hex_to_bit_string(payload_hex: str) -> str:
    clean = "".join(payload_hex.split()).lower()
    if len(clean) % 2:
        raise ValueError("hex payload must contain complete bytes")
    return "".join(f"{int(ch, 16):04b}" for ch in clean)


def plausible_temperature(decoded: TemperatureDecode) -> bool:
    if decoded.raw13 % 32 != 0:
        return False
    return -20.0 <= decoded.temperature_C_exact <= 60.0


def decode_payload_hex(payload_hex: str) -> TemperatureDecode:
    bits = hex_to_bit_string(payload_hex)
    candidates = list(find_packet_candidates_in_bits(bits, phase=0))
    if not candidates:
        raise ValueError("payload does not contain a valid Inkbird packet")
    return candidates[0].temperature


def find_packet_candidates_in_bits(bits: Sequence[int] | str, phase: int = 0) -> Iterable[PacketCandidate]:
    bit_string = bits if isinstance(bits, str) else "".join(str(int(bit)) for bit in bits)
    start = 0
    trailer_bits = len(PREFIX_BITS) + 16 + 32

    while True:
        hit = bit_string.find(PREFIX_BITS, start)
        if hit < 0:
            return
        if hit + trailer_bits > len(bit_string):
            return

        field_start = hit + len(PREFIX_BITS)
        marker_start = field_start + 16
        field_hex = bits_to_hex(bit_string[field_start:marker_start])
        marker_hex = bits_to_hex(bit_string[marker_start : marker_start + 32])

        if marker_ok(marker_hex):
            decoded = decode_temperature_field(field_hex)
            if plausible_temperature(decoded):
                yield PacketCandidate(
                    temperature=decoded,
                    marker=marker_hex,
                    phase=phase,
                    bit_index=hit,
                )

        start = hit + 1


def _valid_ranges(valid: np.ndarray, min_length: int) -> Iterable[tuple[int, int]]:
    if valid.size == 0:
        return

    start: int | None = None
    for index, is_valid in enumerate(valid):
        if bool(is_valid):
            if start is None:
                start = index
        elif start is not None:
            if index - start >= min_length:
                yield start, index
            start = None

    if start is not None and valid.size - start >= min_length:
        yield start, valid.size


def _bits_for_phase(freq: np.ndarray, phase: int, config: DecoderConfig) -> tuple[np.ndarray, np.ndarray]:
    usable_count = (freq.size - phase) // config.sps
    if usable_count <= 0:
        return np.array([], dtype=np.uint8), np.array([], dtype=bool)

    trimmed = freq[phase : phase + usable_count * config.sps]
    symbols = trimmed.reshape(usable_count, config.sps)
    medians = np.median(symbols, axis=1)
    valid = (medians >= config.tone_min_hz) & (medians <= config.tone_max_hz)
    bits = (medians > config.bit_threshold_hz).astype(np.uint8)
    return bits, valid


def find_packet_candidates_in_freq(freq: np.ndarray, config: DecoderConfig) -> list[PacketCandidate]:
    candidates: list[PacketCandidate] = []
    for phase in PHASE_OFFSETS:
        if phase >= config.sps:
            continue
        bits, valid = _bits_for_phase(freq, phase, config)
        for start, stop in _valid_ranges(valid, config.min_valid_symbols):
            segment = bits[start:stop]
            for candidate in find_packet_candidates_in_bits(segment, phase=phase):
                candidates.append(candidate)
    return candidates


def choose_best_candidate(candidates: Sequence[PacketCandidate], min_confidence_count: int) -> tuple[PacketCandidate, int] | None:
    by_field: dict[str, list[PacketCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_field[candidate.temperature.field].append(candidate)

    scored: list[tuple[int, int, str]] = []
    for field, field_candidates in by_field.items():
        phases = {candidate.phase for candidate in field_candidates}
        marker_counts = Counter(candidate.marker for candidate in field_candidates)
        scored.append((len(phases), marker_counts.most_common(1)[0][1], field))

    if not scored:
        return None

    scored.sort(reverse=True)
    confidence, _, field = scored[0]
    if confidence < min_confidence_count:
        return None

    field_candidates = by_field[field]
    marker = Counter(candidate.marker for candidate in field_candidates).most_common(1)[0][0]
    for candidate in field_candidates:
        if candidate.marker == marker:
            return candidate, confidence
    return field_candidates[0], confidence


def decode_cs16_file(
    path: str | Path,
    decoder_config: DecoderConfig | None = None,
    min_file_size: int = 0,
) -> DecodeResult:
    config = decoder_config or DecoderConfig()
    file_path = Path(path)

    if not file_path.exists():
        return DecodeResult(False, file_path.name, reason="file_missing")

    if min_file_size and file_path.stat().st_size < min_file_size:
        return DecodeResult(False, file_path.name, reason="not_long_file")

    try:
        iq = load_cs16(file_path)
        freq = fm_demodulate(iq, config.fs)
        candidates = find_packet_candidates_in_freq(freq, config)
        chosen = choose_best_candidate(candidates, config.min_confidence_count)
        if chosen is None:
            return DecodeResult(False, file_path.name, reason="no_hit")

        candidate, confidence_count = chosen
        temp = candidate.temperature
        return DecodeResult(
            decode_ok=True,
            file=file_path.name,
            temperature_C=temp.temperature_C,
            temperature_C_exact=temp.temperature_C_exact,
            field=temp.field,
            flags=temp.flags,
            raw13=temp.raw13,
            confidence_count=confidence_count,
            marker=candidate.marker,
        )
    except Exception:
        return DecodeResult(False, file_path.name, reason="decode_error")

