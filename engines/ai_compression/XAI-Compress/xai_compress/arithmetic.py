"""Deterministic integer arithmetic coder.

Based on the classic finite-precision arithmetic-coding algorithm. The coder
accepts a cumulative frequency table per symbol, making it usable with both an
adaptive static model and a causal neural model.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence

STATE_BITS = 32
FULL_RANGE = 1 << STATE_BITS
HALF_RANGE = FULL_RANGE >> 1
QUARTER_RANGE = HALF_RANGE >> 1
MASK = FULL_RANGE - 1
MAX_TOTAL = QUARTER_RANGE

class CodecError(ValueError):
    pass

class BitWriter:
    def __init__(self):
        self.data = bytearray(); self.current = 0; self.count = 0
    def write(self, bit: int) -> None:
        if bit not in (0, 1): raise CodecError("bit must be 0 or 1")
        self.current = (self.current << 1) | bit; self.count += 1
        if self.count == 8:
            self.data.append(self.current); self.current = 0; self.count = 0
    def finish(self) -> bytes:
        if self.count:
            self.data.append(self.current << (8 - self.count))
            self.current = 0; self.count = 0
        return bytes(self.data)

class BitReader:
    def __init__(self, data: bytes):
        self.data = data; self.byte_index = 0; self.bit_index = 0
    def read(self) -> int:
        # Arithmetic decoding convention: implicit zero bits after physical end.
        if self.byte_index >= len(self.data): return 0
        bit = (self.data[self.byte_index] >> (7 - self.bit_index)) & 1
        self.bit_index += 1
        if self.bit_index == 8:
            self.bit_index = 0; self.byte_index += 1
        return bit


def validate_cumulative(cum: Sequence[int]) -> None:
    if len(cum) != 257: raise CodecError("cumulative table must have 257 entries")
    if cum[0] != 0: raise CodecError("cumulative table must start at zero")
    if any(not isinstance(x, int) for x in cum): raise CodecError("frequencies must be integers")
    if any(cum[i+1] <= cum[i] for i in range(256)):
        raise CodecError("all 256 symbols must have positive frequency")
    if cum[-1] <= 0 or cum[-1] > MAX_TOTAL:
        raise CodecError("invalid cumulative total")

class ArithmeticEncoder:
    def __init__(self):
        self.low = 0; self.high = MASK; self.pending = 0; self.out = BitWriter()
    def _emit(self, bit: int) -> None:
        self.out.write(bit)
        opposite = 1 - bit
        for _ in range(self.pending): self.out.write(opposite)
        self.pending = 0
    def write(self, cum: Sequence[int], symbol: int) -> None:
        validate_cumulative(cum)
        if not 0 <= symbol <= 255: raise CodecError("symbol outside byte range")
        total = cum[-1]; width = self.high - self.low + 1
        new_low = self.low + (width * cum[symbol]) // total
        new_high = self.low + (width * cum[symbol+1]) // total - 1
        if new_low > new_high: raise CodecError("frequency precision collapsed interval")
        self.low, self.high = new_low, new_high
        while True:
            if self.high < HALF_RANGE:
                self._emit(0)
            elif self.low >= HALF_RANGE:
                self._emit(1); self.low -= HALF_RANGE; self.high -= HALF_RANGE
            elif self.low >= QUARTER_RANGE and self.high < 3 * QUARTER_RANGE:
                self.pending += 1; self.low -= QUARTER_RANGE; self.high -= QUARTER_RANGE
            else: break
            self.low = (self.low << 1) & MASK
            self.high = ((self.high << 1) & MASK) | 1
    def finish(self) -> bytes:
        self.pending += 1
        self._emit(0 if self.low < QUARTER_RANGE else 1)
        # Add state padding. Integrity and exact length are enforced by container.
        for _ in range(STATE_BITS): self.out.write(0)
        return self.out.finish()

class ArithmeticDecoder:
    def __init__(self, payload: bytes):
        if not isinstance(payload, (bytes, bytearray)): raise CodecError("payload must be bytes")
        self.reader = BitReader(bytes(payload)); self.low = 0; self.high = MASK; self.code = 0
        for _ in range(STATE_BITS): self.code = ((self.code << 1) | self.reader.read()) & MASK
    def read(self, cum: Sequence[int]) -> int:
        validate_cumulative(cum)
        total = cum[-1]; width = self.high - self.low + 1
        value = ((self.code - self.low + 1) * total - 1) // width
        lo, hi = 0, 256
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if cum[mid] > value: hi = mid
            else: lo = mid
        symbol = lo
        if not (cum[symbol] <= value < cum[symbol+1]): raise CodecError("malformed arithmetic stream")
        new_low = self.low + (width * cum[symbol]) // total
        new_high = self.low + (width * cum[symbol+1]) // total - 1
        self.low, self.high = new_low, new_high
        while True:
            if self.high < HALF_RANGE: pass
            elif self.low >= HALF_RANGE:
                self.low -= HALF_RANGE; self.high -= HALF_RANGE; self.code -= HALF_RANGE
            elif self.low >= QUARTER_RANGE and self.high < 3 * QUARTER_RANGE:
                self.low -= QUARTER_RANGE; self.high -= QUARTER_RANGE; self.code -= QUARTER_RANGE
            else: break
            self.low = (self.low << 1) & MASK
            self.high = ((self.high << 1) & MASK) | 1
            self.code = ((self.code << 1) & MASK) | self.reader.read()
        return symbol

class AdaptiveByteModel:
    """Order-0 adaptive model, initialized uniformly and rescaled safely."""
    def __init__(self): self.freq = [1] * 256
    def cumulative(self) -> list[int]:
        out = [0]; total = 0
        for f in self.freq: total += f; out.append(total)
        return out
    def update(self, symbol: int) -> None:
        self.freq[symbol] += 1
        if sum(self.freq) >= 1 << 15:
            self.freq = [max(1, (f + 1) // 2) for f in self.freq]
