"""XAIC v3 bounded-memory streaming container.

Legacy v1/v2 parsing remains in :mod:`xai_compress.format`.  V3 is a file
format (rather than a bytes API) so neither compressed nor restored content
needs to exist as one Python object.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import BinaryIO

from .format import MAGIC, MAX_METADATA

STREAM_VERSION = 3
PREFIX = struct.Struct(">4sBI")
CHUNK_MAGIC = b"XCHK"
FOOTER_MAGIC = b"XEND"
CHUNK = struct.Struct(">4sQBI I32s".replace(" ", ""))  # magic, id, codec, raw, encoded, raw sha256
FOOTER = struct.Struct(">4sQQ32s")  # magic, chunks, original bytes, whole-file sha256


class StreamingFormatError(ValueError):
    pass


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_header(handle: BinaryIO, metadata: dict) -> int:
    value = dict(metadata)
    value["format_version"] = STREAM_VERSION
    raw = _canonical(value)
    if not raw or len(raw) > MAX_METADATA:
        raise StreamingFormatError("invalid streaming metadata length")
    handle.write(PREFIX.pack(MAGIC, STREAM_VERSION, len(raw)))
    handle.write(raw)
    handle.write(hashlib.sha256(raw).digest())
    return PREFIX.size + len(raw) + 32


def read_header(handle: BinaryIO) -> dict:
    prefix = handle.read(PREFIX.size)
    if len(prefix) != PREFIX.size:
        raise StreamingFormatError("truncated global header")
    magic, version, length = PREFIX.unpack(prefix)
    if magic != MAGIC:
        raise StreamingFormatError("invalid magic")
    if version != STREAM_VERSION:
        raise StreamingFormatError(f"not a streaming v{STREAM_VERSION} container")
    if not 0 < length <= MAX_METADATA:
        raise StreamingFormatError("invalid metadata length")
    raw = handle.read(length)
    digest = handle.read(32)
    if len(raw) != length or len(digest) != 32:
        raise StreamingFormatError("truncated global metadata")
    if hashlib.sha256(raw).digest() != digest:
        raise StreamingFormatError("global header checksum failure")
    try:
        metadata = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StreamingFormatError("invalid metadata JSON") from exc
    required = {"format_version", "mode", "coder_version", "original_size", "chunk_size"}
    if not required.issubset(metadata) or metadata["format_version"] != STREAM_VERSION:
        raise StreamingFormatError("missing or inconsistent streaming metadata")
    if not isinstance(metadata["original_size"], int) or metadata["original_size"] < 0:
        raise StreamingFormatError("invalid original size")
    if not isinstance(metadata["chunk_size"], int) or metadata["chunk_size"] <= 0:
        raise StreamingFormatError("invalid chunk size")
    return metadata


def write_chunk(handle: BinaryIO, chunk_id: int, codec: int, raw: bytes, payload: bytes) -> int:
    digest = hashlib.sha256(raw).digest()
    handle.write(CHUNK.pack(CHUNK_MAGIC, chunk_id, codec, len(raw), len(payload), digest))
    handle.write(payload)
    return CHUNK.size + len(payload)


def write_footer(handle: BinaryIO, chunks: int, size: int, digest: bytes) -> int:
    handle.write(FOOTER.pack(FOOTER_MAGIC, chunks, size, digest))
    return FOOTER.size


def read_record_header(handle: BinaryIO):
    magic = handle.read(4)
    if not magic:
        raise StreamingFormatError("missing stream footer")
    if magic == FOOTER_MAGIC:
        rest = handle.read(FOOTER.size - 4)
        if len(rest) != FOOTER.size - 4:
            raise StreamingFormatError("truncated stream footer")
        _, chunks, size, digest = FOOTER.unpack(magic + rest)
        if handle.read(1):
            raise StreamingFormatError("unexpected bytes after footer")
        return "footer", (chunks, size, digest)
    if magic != CHUNK_MAGIC:
        raise StreamingFormatError("invalid chunk marker")
    rest = handle.read(CHUNK.size - 4)
    if len(rest) != CHUNK.size - 4:
        raise StreamingFormatError("truncated chunk header")
    _, chunk_id, codec, raw_len, encoded_len, digest = CHUNK.unpack(magic + rest)
    return "chunk", (chunk_id, codec, raw_len, encoded_len, digest)


def atomic_target(destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=str(destination.parent))
    os.close(fd)
    return Path(name)
