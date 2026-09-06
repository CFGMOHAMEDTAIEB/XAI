from __future__ import annotations

import bz2
import lzma
import zlib
from typing import Callable

from ..transforms import TransformError
from .base import CodecAdapter, CodecError, CodecResult


class RawCodec(CodecAdapter):
    codec_id = "raw"

    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        return CodecResult(bytes(data), {"level": None})

    def decompress(self, data: bytes, metadata: dict) -> bytes:
        return bytes(data)

    def available_levels(self) -> tuple[None, ...]:
        return (None,)


class ZstdCodec(CodecAdapter):
    codec_id = "zstd"

    def available(self) -> bool:
        try:
            import zstandard  # noqa: F401

            return True
        except ImportError:
            return False

    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise CodecError("zstandard dependency unavailable") from exc
        chosen = 3 if level is None else int(level)
        if chosen not in self.available_levels():
            raise CodecError(f"unsupported zstd level: {chosen}")
        return CodecResult(zstd.ZstdCompressor(level=chosen).compress(data), {"level": chosen})

    def decompress(self, data: bytes, metadata: dict) -> bytes:
        import zstandard as zstd

        return zstd.ZstdDecompressor().decompress(data)

    def available_levels(self) -> tuple[int, ...]:
        return (1, 3, 6, 9, 19)


class BrotliCodec(CodecAdapter):
    codec_id = "brotli"

    def available(self) -> bool:
        try:
            import brotli  # noqa: F401

            return True
        except ImportError:
            return False

    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        try:
            import brotli
        except ImportError as exc:
            raise CodecError("brotli dependency unavailable") from exc
        chosen = 6 if level is None else int(level)
        if chosen not in self.available_levels():
            raise CodecError(f"unsupported brotli level: {chosen}")
        return CodecResult(brotli.compress(data, quality=chosen), {"level": chosen})

    def decompress(self, data: bytes, metadata: dict) -> bytes:
        import brotli

        return brotli.decompress(data)

    def available_levels(self) -> tuple[int, ...]:
        return (1, 4, 6, 9, 11)


class DeflateCodec(CodecAdapter):
    """Zlib-wrapped Deflate; interoperable with standard Deflate tooling."""

    codec_id = "deflate"

    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        chosen = 6 if level is None else int(level)
        if chosen not in self.available_levels():
            raise CodecError(f"unsupported deflate level: {chosen}")
        return CodecResult(zlib.compress(data, chosen), {"level": chosen, "wrapper": "zlib"})

    def decompress(self, data: bytes, metadata: dict) -> bytes:
        return zlib.decompress(data)

    def available_levels(self) -> tuple[int, ...]:
        return (1, 6, 9)


class Lzma2Codec(CodecAdapter):
    codec_id = "lzma2"

    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        chosen = 6 if level is None else int(level)
        if chosen not in self.available_levels():
            raise CodecError(f"unsupported LZMA2 preset: {chosen}")
        return CodecResult(
            lzma.compress(data, format=lzma.FORMAT_XZ, preset=chosen),
            {"level": chosen, "container": "xz", "filter": "lzma2"},
        )

    def decompress(self, data: bytes, metadata: dict) -> bytes:
        return lzma.decompress(data, format=lzma.FORMAT_XZ)

    def available_levels(self) -> tuple[int, ...]:
        return (0, 3, 6, 9)


class Bzip2Codec(CodecAdapter):
    codec_id = "bzip2"

    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        chosen = 9 if level is None else int(level)
        if chosen not in self.available_levels():
            raise CodecError(f"unsupported bzip2 level: {chosen}")
        return CodecResult(bz2.compress(data, compresslevel=chosen), {"level": chosen})

    def decompress(self, data: bytes, metadata: dict) -> bytes:
        return bz2.decompress(data)

    def available_levels(self) -> tuple[int, ...]:
        return (1, 6, 9)


class XaiStaticCodec(CodecAdapter):
    codec_id = "xai-static"

    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        from ...compression import _encode_static

        return CodecResult(_encode_static(data), {"level": None, "coder": "adaptive-arithmetic32-v1", "original_size": len(data)})

    def decompress(self, data: bytes, metadata: dict) -> bytes:
        from ...compression import _decode_static

        size = metadata.get("original_size")
        if not isinstance(size, int) or size < 0:
            raise CodecError("xai-static missing original_size")
        return _decode_static(data, size)

    def available_levels(self) -> tuple[None, ...]:
        return (None,)
