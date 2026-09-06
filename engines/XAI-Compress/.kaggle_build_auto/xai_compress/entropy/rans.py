"""Byte rANS matching Fabian Giesen's 32-bit byte-renormalized coder.

Frequencies must sum to 2^14 (16384), which matches neural quantization.
"""
from __future__ import annotations

import struct
from typing import Sequence

SCALE_BITS = 14
FREQ_TOTAL = 1 << SCALE_BITS
RANS_L = 1 << 23
MASK = (1 << SCALE_BITS) - 1


class RANSError(ValueError):
    pass


def _cum_parts(cum: Sequence[int], symbol: int) -> tuple[int, int]:
    if len(cum) != 257 or int(cum[0]) != 0 or int(cum[-1]) != FREQ_TOTAL:
        raise RANSError("rANS requires a 257-entry table totaling 16384")
    if not 0 <= symbol <= 255:
        raise RANSError("symbol outside byte range")
    start = int(cum[symbol])
    freq = int(cum[symbol + 1]) - start
    if freq <= 0:
        raise RANSError("zero-frequency symbol")
    return start, freq


class RANSEncoder:
    def __init__(self) -> None:
        self._symbols: list[int] = []
        self._tables: list[Sequence[int]] = []

    def write(self, cum: Sequence[int], symbol: int) -> None:
        _cum_parts(cum, symbol)
        self._symbols.append(int(symbol))
        self._tables.append(cum)

    def write_fast(self, cum: Sequence[int], symbol: int) -> None:
        self._symbols.append(int(symbol))
        self._tables.append(cum)

    def finish(self) -> bytes:
        state = RANS_L
        emitted = bytearray()
        for symbol, cum in zip(reversed(self._symbols), reversed(self._tables)):
            start, freq = _cum_parts(cum, symbol)
            x_max = ((RANS_L >> SCALE_BITS) << 8) * freq
            x = state
            while x >= x_max:
                emitted.append(x & 0xFF)
                x >>= 8
            state = ((x // freq) << SCALE_BITS) + (x % freq) + start
        self._symbols.clear()
        self._tables.clear()
        return struct.pack("<I", state) + bytes(reversed(emitted))


class RANSDecoder:
    def __init__(self, payload: bytes) -> None:
        if not isinstance(payload, (bytes, bytearray)):
            raise RANSError("payload must be bytes")
        data = bytes(payload)
        if len(data) < 4:
            raise RANSError("truncated rANS payload")
        self._data = data
        self._pos = 4
        self._state = struct.unpack_from("<I", data, 0)[0]

    def _advance(self, start: int, freq: int) -> None:
        x = self._state
        x = freq * (x >> SCALE_BITS) + (x & MASK) - start
        while x < RANS_L:
            if self._pos >= len(self._data):
                raise RANSError("rANS underflow")
            x = (x << 8) | self._data[self._pos]
            self._pos += 1
        self._state = x

    def read(self, cum: Sequence[int]) -> int:
        slot = self._state & MASK
        lo, hi = 0, 256
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if cum[mid] > slot:
                hi = mid
            else:
                lo = mid
        symbol = lo
        start, freq = _cum_parts(cum, symbol)
        self._advance(start, freq)
        return symbol

    def read_fast(self, cum: Sequence[int]) -> int:
        return self.read(cum)
