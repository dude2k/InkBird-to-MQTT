from __future__ import annotations

from pathlib import Path

import numpy as np


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

