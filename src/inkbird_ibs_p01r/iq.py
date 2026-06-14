from __future__ import annotations

from pathlib import Path

import numpy as np


def cu8_to_cs16(raw: bytes | np.ndarray) -> np.ndarray:
    values = np.frombuffer(raw, dtype=np.uint8) if isinstance(raw, bytes) else raw.astype(np.uint8, copy=False)
    if values.size % 2:
        values = values[:-1]
    return ((values.astype(np.int16) - 128) << 8).astype("<i2", copy=False)


def convert_cu8_to_cs16(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    source = Path(input_path)
    target = Path(output_path) if output_path is not None else source.with_suffix(".cs16")
    converted = cu8_to_cs16(np.fromfile(source, dtype=np.uint8))
    target.write_bytes(converted.tobytes())
    return target


def load_cs16(path: str | Path) -> np.ndarray:
    raw = np.fromfile(Path(path), dtype="<i2")
    if raw.size % 2:
        raw = raw[:-1]
    i = raw[0::2].astype(np.float32)
    q = raw[1::2].astype(np.float32)
    return i + 1j * q


def fm_demodulate(iq: np.ndarray, fs: int) -> np.ndarray:
    if iq.size < 2:
        return np.array([], dtype=np.float32)
    delta = iq[1:] * np.conj(iq[:-1])
    return (np.angle(delta).astype(np.float32) * (fs / (2.0 * np.pi))).astype(np.float32)
