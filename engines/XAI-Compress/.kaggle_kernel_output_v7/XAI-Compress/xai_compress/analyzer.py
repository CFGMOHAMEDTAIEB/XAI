from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

Strategy = Literal["store", "static", "zlib", "neural"]


@dataclass(frozen=True)
class BlockAnalysis:
    size: int
    entropy: float
    unique_bytes: int
    ascii_ratio: float
    null_ratio: float
    max_run: int
    zlib_size: int | None
    compressibility: float
    suggested: Strategy
    reason: str


def byte_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    p = counts[counts > 0] / len(data)
    return float(-(p * np.log2(p)).sum())


def max_run_length(data: bytes) -> int:
    if not data:
        return 0
    best = cur = 1
    prev = data[0]
    for b in data[1:]:
        if b == prev:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 1
            prev = b
    return best


def ascii_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    arr = np.frombuffer(data, dtype=np.uint8)
    printable = ((arr >= 9) & (arr <= 13)) | ((arr >= 32) & (arr < 127))
    return float(printable.mean())


def classify_kind(data: bytes) -> str:
    if not data:
        return "empty"
    h = byte_entropy(data)
    ascii_r = ascii_ratio(data)
    if h >= 7.85:
        return "high_entropy"
    if ascii_r > 0.92:
        head = data[: min(64, len(data))].lstrip()
        if head.startswith((b"{", b"[")):
            return "json"
        if head.startswith(b"<"):
            return "xml"
        if b"\n" in data[:4096] and (b"," in data[:256] or b";" in data[:256]):
            return "tabular"
        return "text"
    if ascii_r > 0.7:
        return "mixed"
    return "binary"


def analyze_block(data: bytes, probe_zlib: bool = True) -> BlockAnalysis:
    size = len(data)
    if size == 0:
        return BlockAnalysis(0, 0.0, 0, 0.0, 0.0, 0, 0, 1.0, "store", "empty")
    arr = np.frombuffer(data, dtype=np.uint8)
    entropy = byte_entropy(data)
    unique = int(np.count_nonzero(np.bincount(arr, minlength=256)))
    ascii_r = ascii_ratio(data)
    null_r = float((arr == 0).mean())
    run = max_run_length(data if size <= 1_000_000 else data[:1_000_000])
    zlib_size = None
    if probe_zlib:
        import zlib

        sample = data if size <= 1 << 20 else data[: 1 << 20]
        z = zlib.compress(sample, 6)
        scale = size / max(1, len(sample))
        zlib_size = int(math.ceil(len(z) * scale))
    if entropy >= 7.9:
        suggested: Strategy = "store"
        reason = "near-incompressible entropy"
    elif zlib_size is not None and zlib_size >= size * 0.98 and entropy > 7.2:
        suggested = "store"
        reason = "zlib cannot shrink the block"
    elif ascii_r > 0.85 and entropy < 6.2:
        suggested = "neural"
        reason = "structured/text-like distribution"
    elif zlib_size is not None and zlib_size < size * 0.85:
        suggested = "zlib"
        reason = "classical LZ match wins on this block"
    else:
        suggested = "static"
        reason = "order-0 adaptive coding is competitive"
    comp = 1.0 if zlib_size is None else min(1.0, zlib_size / max(1, size))
    return BlockAnalysis(
        size=size,
        entropy=entropy,
        unique_bytes=unique,
        ascii_ratio=ascii_r,
        null_ratio=null_r,
        max_run=run,
        zlib_size=zlib_size,
        compressibility=float(comp),
        suggested=suggested,
        reason=reason,
    )


def choose_strategy(data: bytes, neural_available: bool) -> Strategy:
    analysis = analyze_block(data)
    if analysis.suggested == "neural" and not neural_available:
        return "zlib" if (analysis.zlib_size or analysis.size) < analysis.size else "static"
    if analysis.suggested == "neural" and neural_available:
        return "neural"
    return analysis.suggested
