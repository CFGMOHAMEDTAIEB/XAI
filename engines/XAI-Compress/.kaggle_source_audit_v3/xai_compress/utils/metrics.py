from __future__ import annotations


def bits_per_byte(compressed_size: int, original_size: int) -> float:
    if original_size <= 0:
        return 0.0
    return 8.0 * compressed_size / original_size


def compression_ratio(original_size: int, compressed_size: int) -> float:
    if compressed_size <= 0:
        return 0.0
    return original_size / compressed_size


def throughput_mbs(nbytes: int, seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    return (nbytes / (1024 * 1024)) / seconds
