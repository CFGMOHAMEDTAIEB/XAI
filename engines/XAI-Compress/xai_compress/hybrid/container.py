"""XAIC v5 chunk-level hybrid container.

Version 5 stores the selected codec and reversible transform in each chunk.
The decoder uses only this metadata; it never loads the selector model.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import time
from collections import Counter
from pathlib import Path
from typing import BinaryIO

from ..format import MAGIC, MAX_METADATA
from ..streaming import atomic_target
from .codecs import CodecAdapter, Strategy, available_registry, build_registry
from .selector import HybridSelector, SelectionResult
from .transforms import get_transform

HYBRID_VERSION = 5
PREFIX = struct.Struct(">4sBI")
CHUNK_MAGIC = b"HCHK"
FOOTER_MAGIC = b"HEND"
CHUNK = struct.Struct(">4sQIII32sI32s")
FOOTER = struct.Struct(">4sQQ32s")
MAX_CHUNK_SIZE = 64 << 20
MAX_CHUNK_METADATA = 1 << 16


class HybridFormatError(ValueError):
    pass


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write_header(handle: BinaryIO, metadata: dict) -> int:
    value = dict(metadata, format_version=HYBRID_VERSION, mode="hybrid-ai")
    raw = _canonical(value)
    if not raw or len(raw) > MAX_METADATA:
        raise HybridFormatError("invalid XAIC v5 metadata length")
    handle.write(PREFIX.pack(MAGIC, HYBRID_VERSION, len(raw)))
    handle.write(raw)
    handle.write(hashlib.sha256(raw).digest())
    return PREFIX.size + len(raw) + 32


def _read_header(handle: BinaryIO, max_output_size: int) -> dict:
    prefix = handle.read(PREFIX.size)
    if len(prefix) != PREFIX.size:
        raise HybridFormatError("truncated XAIC v5 header")
    magic, version, length = PREFIX.unpack(prefix)
    if magic != MAGIC or version != HYBRID_VERSION:
        raise HybridFormatError("not an XAIC v5 hybrid container")
    if not 0 < length <= MAX_METADATA:
        raise HybridFormatError("invalid XAIC v5 metadata length")
    raw = handle.read(length)
    digest = handle.read(32)
    if len(raw) != length or len(digest) != 32:
        raise HybridFormatError("truncated XAIC v5 metadata")
    if hashlib.sha256(raw).digest() != digest:
        raise HybridFormatError("XAIC v5 header checksum failure")
    try:
        metadata = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HybridFormatError("invalid XAIC v5 metadata JSON") from exc
    required = {"format_version", "mode", "profile", "selector_mode", "chunk_size", "original_size"}
    if not required.issubset(metadata):
        raise HybridFormatError("missing XAIC v5 metadata field")
    if metadata["format_version"] != HYBRID_VERSION or metadata["mode"] != "hybrid-ai":
        raise HybridFormatError("inconsistent XAIC v5 metadata")
    if not isinstance(metadata["original_size"], int) or not 0 <= metadata["original_size"] <= max_output_size:
        raise HybridFormatError("unsafe XAIC v5 original size")
    if not isinstance(metadata["chunk_size"], int) or not 0 < metadata["chunk_size"] <= MAX_CHUNK_SIZE:
        raise HybridFormatError("invalid XAIC v5 chunk size")
    return metadata


def _encode_chunk(
    raw: bytes,
    chunk_id: int,
    selection: SelectionResult,
    registry: dict[str, CodecAdapter],
) -> tuple[bytes, dict, dict]:
    strategy = selection.strategy
    if strategy.codec not in registry:
        raise HybridFormatError(f"selected codec unavailable: {strategy.codec}")
    transform = get_transform(strategy.transform)
    transform_started = time.perf_counter()
    transformed, transform_metadata = transform.forward(raw)
    transform_ms = (time.perf_counter() - transform_started) * 1000
    adapter = registry[strategy.codec]
    codec_started = time.perf_counter()
    result = adapter.compress(transformed, strategy.level)
    codec_ms = (time.perf_counter() - codec_started) * 1000
    serialization_started = time.perf_counter()
    selection_metadata = selection.metadata()
    # Candidate rankings are retained in optional local observation logs, not
    # repeated inside every chunk.  Decoding needs only the selected strategy;
    # omitting rankings materially reduces small-chunk container overhead.
    selection_metadata.pop("ranked_candidates", None)
    metadata = {
        "codec_id": strategy.codec,
        "codec_level": strategy.level,
        "transform_id": strategy.transform,
        "transform_metadata": transform_metadata,
        "codec_metadata": result.metadata,
        "selection": selection_metadata,
    }
    encoded_metadata = _canonical(metadata)
    if not encoded_metadata or len(encoded_metadata) > MAX_CHUNK_METADATA:
        raise HybridFormatError("invalid hybrid chunk metadata length")
    header = CHUNK.pack(
        CHUNK_MAGIC,
        chunk_id,
        len(raw),
        len(transformed),
        len(result.payload),
        hashlib.sha256(raw).digest(),
        len(encoded_metadata),
        hashlib.sha256(encoded_metadata).digest(),
    )
    encoded = header + encoded_metadata + result.payload
    serialization_ms = (time.perf_counter() - serialization_started) * 1000
    return encoded, metadata, {
        "transform_ms": transform_ms,
        "codec_compression_ms": codec_ms,
        "container_serialization_ms": serialization_ms,
        "codec_payload_bytes": len(result.payload),
        "chunk_framing_bytes": len(header),
        "chunk_metadata_bytes": len(encoded_metadata),
    }


def _read_record(handle: BinaryIO, expected_id: int, chunk_size: int, max_output_size: int):
    magic = handle.read(4)
    if not magic:
        raise HybridFormatError("missing XAIC v5 footer")
    if magic == FOOTER_MAGIC:
        rest = handle.read(FOOTER.size - 4)
        if len(rest) != FOOTER.size - 4:
            raise HybridFormatError("truncated XAIC v5 footer")
        _, chunks, size, digest = FOOTER.unpack(magic + rest)
        if handle.read(1):
            raise HybridFormatError("unexpected bytes after XAIC v5 footer")
        return "footer", (chunks, size, digest)
    if magic != CHUNK_MAGIC:
        raise HybridFormatError("invalid XAIC v5 chunk marker")
    rest = handle.read(CHUNK.size - 4)
    if len(rest) != CHUNK.size - 4:
        raise HybridFormatError("truncated XAIC v5 chunk header")
    _, chunk_id, raw_len, transformed_len, payload_len, raw_digest, metadata_len, metadata_digest = CHUNK.unpack(magic + rest)
    if chunk_id != expected_id:
        raise HybridFormatError("non-sequential XAIC v5 chunk id")
    if raw_len > chunk_size or raw_len > max_output_size:
        raise HybridFormatError("unsafe XAIC v5 raw chunk length")
    if transformed_len > raw_len * 2 + 16:
        raise HybridFormatError("unsafe XAIC v5 transformed length")
    if payload_len > transformed_len * 4 + (1 << 20):
        raise HybridFormatError("unsafe XAIC v5 payload length")
    if not 0 < metadata_len <= MAX_CHUNK_METADATA:
        raise HybridFormatError("invalid XAIC v5 chunk metadata length")
    encoded_metadata = handle.read(metadata_len)
    if len(encoded_metadata) != metadata_len or hashlib.sha256(encoded_metadata).digest() != metadata_digest:
        raise HybridFormatError("XAIC v5 chunk metadata integrity failure")
    try:
        metadata = json.loads(encoded_metadata.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HybridFormatError("invalid XAIC v5 chunk metadata JSON") from exc
    required = {"codec_id", "codec_level", "transform_id", "transform_metadata", "codec_metadata"}
    if not required.issubset(metadata):
        raise HybridFormatError("missing XAIC v5 chunk metadata field")
    payload = handle.read(payload_len)
    if len(payload) != payload_len:
        raise HybridFormatError("truncated XAIC v5 chunk payload")
    return "chunk", (raw_len, transformed_len, raw_digest, metadata, payload)


def _decode_chunk(record, registry: dict[str, CodecAdapter]) -> tuple[bytes, dict]:
    raw_len, transformed_len, raw_digest, metadata, payload = record
    codec_id = metadata["codec_id"]
    transform_id = metadata["transform_id"]
    if not isinstance(codec_id, str) or codec_id not in registry:
        raise HybridFormatError(f"invalid codec id: {codec_id!r}")
    try:
        transform = get_transform(transform_id)
    except Exception as exc:
        raise HybridFormatError(f"invalid transform id: {transform_id!r}") from exc
    try:
        transformed = registry[codec_id].decompress(payload, metadata["codec_metadata"])
    except Exception as exc:
        raise HybridFormatError(f"codec decompression failed: {codec_id}") from exc
    if len(transformed) != transformed_len:
        raise HybridFormatError("transformed chunk length mismatch")
    try:
        raw = transform.inverse(transformed, metadata["transform_metadata"])
    except Exception as exc:
        raise HybridFormatError(f"transform inversion failed: {transform_id}") from exc
    if len(raw) != raw_len:
        raise HybridFormatError("decoded hybrid chunk length mismatch")
    if hashlib.sha256(raw).digest() != raw_digest:
        raise HybridFormatError("hybrid chunk checksum failure")
    return raw, metadata


def _selector(
    profile: str,
    selector_mode: str,
    top_k: int,
    microbench_bytes: int,
    selector_model: str | Path | None,
    registry: dict[str, CodecAdapter],
    collect_path: str | Path | None,
) -> HybridSelector:
    return HybridSelector(
        profile=profile,
        mode=selector_mode,
        top_k=top_k,
        microbench_bytes=microbench_bytes,
        model_path=selector_model,
        registry=registry,
        collect_path=collect_path,
    )


def compress_hybrid_bytes(
    data: bytes,
    *,
    profile: str = "balanced",
    selector_mode: str = "ai-benchmark",
    chunk_size: int = 1 << 20,
    top_k: int = 3,
    microbench_bytes: int = 64 << 10,
    selector_model: str | Path | None = None,
    gru_checkpoint: str | Path | None = None,
    transformer_checkpoint: str | Path | None = None,
    device: str = "cpu",
    extension: str = "",
    collect_path: str | Path | None = None,
) -> bytes:
    raw_data = bytes(data)
    if not 0 < chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("invalid hybrid chunk size")
    registry = available_registry(
        gru_checkpoint=gru_checkpoint,
        transformer_checkpoint=transformer_checkpoint,
        device=device,
    )
    selector = _selector(profile, selector_mode, top_k, microbench_bytes, selector_model, registry, collect_path)
    output = io.BytesIO()
    _write_header(
        output,
        {
            "profile": profile,
            "selector_mode": selector_mode,
            "chunk_size": chunk_size,
            "original_size": len(raw_data),
            "top_k": top_k,
            "microbench_bytes": microbench_bytes,
            "flags": {"per_chunk_sha256": True, "whole_file_sha256": True},
        },
    )
    chunks = 0
    for offset in range(0, len(raw_data), chunk_size):
        raw = raw_data[offset : offset + chunk_size]
        selection = selector.select(raw, extension=extension)
        encoded, _, _ = _encode_chunk(raw, chunks, selection, registry)
        output.write(encoded)
        chunks += 1
    output.write(FOOTER.pack(FOOTER_MAGIC, chunks, len(raw_data), hashlib.sha256(raw_data).digest()))
    return output.getvalue()


def decompress_hybrid_bytes(
    blob: bytes,
    *,
    max_output_size: int = 8 << 30,
    gru_checkpoint: str | Path | None = None,
    transformer_checkpoint: str | Path | None = None,
    device: str = "cpu",
) -> bytes:
    handle = io.BytesIO(blob)
    metadata = _read_header(handle, max_output_size)
    registry = build_registry(
        gru_checkpoint=gru_checkpoint,
        transformer_checkpoint=transformer_checkpoint,
        device=device,
    )
    output = bytearray()
    chunks = 0
    digest = hashlib.sha256()
    while True:
        kind, record = _read_record(handle, chunks, metadata["chunk_size"], max_output_size - len(output))
        if kind == "footer":
            footer_chunks, footer_size, footer_digest = record
            break
        raw, _ = _decode_chunk(record, registry)
        output.extend(raw)
        digest.update(raw)
        chunks += 1
    if footer_chunks != chunks or footer_size != len(output) or footer_size != metadata["original_size"]:
        raise HybridFormatError("XAIC v5 footer size/count mismatch")
    if digest.digest() != footer_digest:
        raise HybridFormatError("XAIC v5 whole-file checksum failure")
    return bytes(output)


def compress_hybrid_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    profile: str = "balanced",
    selector_mode: str = "ai-benchmark",
    chunk_size: int = 1 << 20,
    top_k: int = 3,
    microbench_bytes: int = 64 << 10,
    selector_model: str | Path | None = None,
    gru_checkpoint: str | Path | None = None,
    transformer_checkpoint: str | Path | None = None,
    device: str = "cpu",
    overwrite: bool = False,
    collect_path: str | Path | None = None,
) -> dict:
    source, destination = Path(input_path), Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    if not 0 < chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("invalid hybrid chunk size")
    registry = available_registry(
        gru_checkpoint=gru_checkpoint,
        transformer_checkpoint=transformer_checkpoint,
        device=device,
    )
    selector = _selector(profile, selector_mode, top_k, microbench_bytes, selector_model, registry, collect_path)
    temporary = atomic_target(destination)
    whole = hashlib.sha256()
    distribution: Counter[str] = Counter()
    transform_distribution: Counter[str] = Counter()
    feature_scan_ms = 0.0
    model_inference_ms = 0.0
    microbenchmark_ms = 0.0
    candidate_generation_ms = 0.0
    transform_ms = 0.0
    codec_compression_ms = 0.0
    container_serialization_ms = 0.0
    codec_payload_bytes = 0
    chunk_framing_bytes = 0
    chunk_metadata_bytes = 0
    size = source.stat().st_size
    chunks = 0
    try:
        with source.open("rb", buffering=1 << 20) as input_handle, temporary.open("wb", buffering=1 << 20) as output_handle:
            header_bytes = _write_header(
                output_handle,
                {
                    "profile": profile,
                    "selector_mode": selector_mode,
                    "chunk_size": chunk_size,
                    "original_size": size,
                    "top_k": top_k,
                    "microbench_bytes": microbench_bytes,
                    "flags": {"per_chunk_sha256": True, "whole_file_sha256": True},
                },
            )
            while True:
                raw = input_handle.read(chunk_size)
                if not raw:
                    break
                whole.update(raw)
                selection = selector.select(raw, extension=source.suffix)
                feature_scan_ms += selection.feature_scan_ms
                model_inference_ms += selection.model_inference_ms
                microbenchmark_ms += selection.microbenchmark_ms
                candidate_generation_ms += selection.candidate_generation_ms
                encoded, chunk_metadata, chunk_stats = _encode_chunk(raw, chunks, selection, registry)
                transform_ms += chunk_stats["transform_ms"]
                codec_compression_ms += chunk_stats["codec_compression_ms"]
                container_serialization_ms += chunk_stats["container_serialization_ms"]
                codec_payload_bytes += chunk_stats["codec_payload_bytes"]
                chunk_framing_bytes += chunk_stats["chunk_framing_bytes"]
                chunk_metadata_bytes += chunk_stats["chunk_metadata_bytes"]
                output_handle.write(encoded)
                distribution[chunk_metadata["codec_id"]] += 1
                transform_distribution[chunk_metadata["transform_id"]] += 1
                chunks += 1
            output_handle.write(FOOTER.pack(FOOTER_MAGIC, chunks, size, whole.digest()))
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "original_size": size,
        "artifact_size": destination.stat().st_size,
        "mode": "hybrid-ai",
        "format_version": HYBRID_VERSION,
        "profile": profile,
        "selector_mode": selector_mode,
        "chunks": chunks,
        "codec_distribution": dict(sorted(distribution.items())),
        "transform_distribution": dict(sorted(transform_distribution.items())),
        "feature_scan_ms": feature_scan_ms,
        "model_inference_ms": model_inference_ms,
        "microbenchmark_ms": microbenchmark_ms,
        "candidate_generation_ms": candidate_generation_ms,
        "transform_ms": transform_ms,
        "codec_compression_ms": codec_compression_ms,
        "container_serialization_ms": container_serialization_ms,
        "raw_payload_bytes": size,
        "codec_payload_bytes": codec_payload_bytes,
        "XAIC_header_bytes": header_bytes,
        "XAIC_chunk_metadata_bytes": chunk_metadata_bytes,
        "chunk_framing_bytes": chunk_framing_bytes,
        "checksum_bytes": 64 * chunks + 64,
        "footer_bytes": FOOTER.size,
        "total_metadata_bytes": destination.stat().st_size - codec_payload_bytes,
        "container_penalty_bytes": destination.stat().st_size - codec_payload_bytes,
        "selection_overhead_ms": feature_scan_ms + model_inference_ms + microbenchmark_ms,
    }


def decompress_hybrid_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    max_output_size: int = 8 << 30,
    gru_checkpoint: str | Path | None = None,
    transformer_checkpoint: str | Path | None = None,
    device: str = "cpu",
    overwrite: bool = False,
) -> dict:
    source, destination = Path(input_path), Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    temporary = atomic_target(destination)
    registry = build_registry(
        gru_checkpoint=gru_checkpoint,
        transformer_checkpoint=transformer_checkpoint,
        device=device,
    )
    chunks = 0
    total = 0
    whole = hashlib.sha256()
    distribution: Counter[str] = Counter()
    try:
        with source.open("rb", buffering=1 << 20) as input_handle, temporary.open("wb", buffering=1 << 20) as output_handle:
            metadata = _read_header(input_handle, max_output_size)
            while True:
                kind, record = _read_record(input_handle, chunks, metadata["chunk_size"], max_output_size - total)
                if kind == "footer":
                    footer_chunks, footer_size, footer_digest = record
                    break
                raw, chunk_metadata = _decode_chunk(record, registry)
                output_handle.write(raw)
                whole.update(raw)
                total += len(raw)
                distribution[chunk_metadata["codec_id"]] += 1
                chunks += 1
            if footer_chunks != chunks or footer_size != total or total != metadata["original_size"]:
                raise HybridFormatError("XAIC v5 footer size/count mismatch")
            if whole.digest() != footer_digest:
                raise HybridFormatError("XAIC v5 whole-file checksum failure")
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "restored_size": total,
        "sha256": whole.hexdigest(),
        "format_version": HYBRID_VERSION,
        "chunks": chunks,
        "codec_distribution": dict(sorted(distribution.items())),
    }


def inspect_hybrid(path: str | Path) -> dict:
    source = Path(path)
    distribution: Counter[str] = Counter()
    transforms: Counter[str] = Counter()
    chunks = 0
    with source.open("rb") as handle:
        metadata = _read_header(handle, 8 << 30)
        while True:
            kind, record = _read_record(handle, chunks, metadata["chunk_size"], 8 << 30)
            if kind == "footer":
                footer_chunks, footer_size, footer_digest = record
                break
            _, _, _, chunk_metadata, _ = record
            codec = chunk_metadata["codec_id"]
            transform = chunk_metadata["transform_id"]
            if not isinstance(codec, str) or not isinstance(transform, str):
                raise HybridFormatError("invalid XAIC v5 strategy metadata")
            distribution[codec] += 1
            transforms[transform] += 1
            chunks += 1
    if footer_chunks != chunks or footer_size != metadata["original_size"]:
        raise HybridFormatError("XAIC v5 inspection footer mismatch")
    return {
        **metadata,
        "chunks": chunks,
        "codec_distribution": dict(sorted(distribution.items())),
        "transform_distribution": dict(sorted(transforms.items())),
        "whole_file_sha256": footer_digest.hex(),
    }
