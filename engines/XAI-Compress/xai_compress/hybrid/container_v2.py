"""Compact XAIC v6 container and adaptive Hybrid AI V2 pipeline."""
from __future__ import annotations

import hashlib
import os
import struct
import time
import zlib
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from ..format import MAGIC
from ..streaming import atomic_target
from .codecs import CodecAdapter, Strategy, available_registry, build_registry
from .features import bounded_file_sample, extract_features
from .selector_v2 import HybridSelectorV2, V2Selection
from .transforms import get_transform

if TYPE_CHECKING:
    from .context import CompressionContext

COMPACT_VERSION = 6
FOOTER_MAGIC = b"V6ND"
FLAG_HOMOGENEOUS = 1
FLAG_WHOLE_FILE = 2
FLAG_CHUNK_CRC32 = 4
MAX_CHUNK_SIZE = 64 << 20
MAX_OUTPUT_SIZE = 8 << 30

CODECS = {"raw": 0, "zstd": 1, "brotli": 2, "deflate": 3, "lzma2": 4, "bzip2": 5, "xai-static": 6}
CODEC_NAMES = {value: key for key, value in CODECS.items()}
TRANSFORMS = {"identity": 0, "rle": 1, "delta": 2, "byte-shuffle": 3, "zero-run": 4, "dictionary": 5}
TRANSFORM_NAMES = {value: key for key, value in TRANSFORMS.items()}
PROFILES = {"fastest": 0, "balanced": 1, "smallest": 2}
PROFILE_NAMES = {value: key for key, value in PROFILES.items()}


class CompactFormatError(ValueError):
    pass


def encode_varint(value: int) -> bytes:
    if not isinstance(value, int) or value < 0:
        raise ValueError("varint requires a non-negative integer")
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        output.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(output)


def read_varint(handle: BinaryIO, capture: bytearray | None = None, maximum: int = MAX_OUTPUT_SIZE) -> int:
    value = 0
    for shift in range(0, 70, 7):
        raw = handle.read(1)
        if len(raw) != 1:
            raise CompactFormatError("truncated XAIC v6 varint")
        if capture is not None:
            capture.extend(raw)
        value |= (raw[0] & 0x7F) << shift
        if not raw[0] & 0x80:
            if value > maximum:
                raise CompactFormatError("unsafe XAIC v6 varint value")
            return value
    raise CompactFormatError("oversized XAIC v6 varint")


def _level_code(level: int | None) -> int:
    return 0 if level is None else int(level) + 1


def _decode_level(value: int) -> int | None:
    return None if value == 0 else value - 1


def _strategy_bytes(strategy: Strategy) -> bytes:
    if strategy.codec not in CODECS or strategy.transform not in TRANSFORMS:
        raise CompactFormatError(f"strategy is not compact-v6 compatible: {strategy.strategy_id}")
    return bytes((CODECS[strategy.codec], TRANSFORMS[strategy.transform])) + encode_varint(_level_code(strategy.level))


def _read_strategy(handle: BinaryIO, capture: bytearray) -> Strategy:
    raw = handle.read(2)
    if len(raw) != 2:
        raise CompactFormatError("truncated XAIC v6 strategy table")
    capture.extend(raw)
    codec = CODEC_NAMES.get(raw[0])
    transform = TRANSFORM_NAMES.get(raw[1])
    if codec is None:
        raise CompactFormatError("invalid XAIC v6 codec id")
    if transform is None:
        raise CompactFormatError("invalid XAIC v6 transform id")
    return Strategy(codec, _decode_level(read_varint(handle, capture, 255)), transform)


def _codec_metadata(strategy: Strategy, transformed_size: int) -> dict:
    if strategy.codec == "raw":
        return {"level": None}
    if strategy.codec in {"zstd", "brotli", "bzip2"}:
        return {"level": strategy.level}
    if strategy.codec == "deflate":
        return {"level": strategy.level, "wrapper": "zlib"}
    if strategy.codec == "lzma2":
        return {"level": strategy.level, "container": "xz", "filter": "lzma2"}
    if strategy.codec == "xai-static":
        return {"level": None, "coder": "adaptive-arithmetic32-v1", "original_size": transformed_size}
    raise CompactFormatError("unsupported compact codec")


def _transform_metadata(strategy: Strategy, raw_size: int) -> dict:
    if strategy.transform == "byte-shuffle":
        return {"original_size": raw_size}
    if strategy.transform == "dictionary":
        return {"dictionary": "structured-v1"}
    return {}


def adaptive_plan(path: Path, requested_chunk_size: int | None = None, context: "CompressionContext | None" = None) -> dict:
    size = path.stat().st_size
    if requested_chunk_size is not None:
        if not 0 < requested_chunk_size <= MAX_CHUNK_SIZE:
            raise ValueError("invalid compact chunk size")
        return {"mode": "requested_chunking", "chunk_size": requested_chunk_size, "global_strategy": False, "reason": "explicit_chunk_size"}
    if size <= 10 << 20:
        return {"mode": "whole_file", "chunk_size": max(1, size), "global_strategy": True, "reason": "whole_file_within_10MiB_memory_bound"}
    sample = bounded_file_sample(path)
    # Phase 4 optimization: Use context feature cache if available
    if context is not None:
        features = context.extract_and_cache_features(sample, path.suffix, size)
    else:
        features = extract_features(sample, file_size=size, extension=path.suffix)
    homogeneous = float(features["local_entropy_std"]) < 0.35 and float(features["entropy_gradient"]) < 1.0
    if homogeneous:
        return {"mode": "homogeneous_chunks", "chunk_size": 4 << 20, "global_strategy": True, "reason": "bounded_entropy_regions_homogeneous"}
    chunk_size = 256 << 10 if float(features["entropy_gradient"]) >= 2.0 else 1 << 20
    return {"mode": "adaptive_chunks", "chunk_size": chunk_size, "global_strategy": False, "reason": "bounded_entropy_regions_heterogeneous"}


def _select_plan(path: Path, plan: dict, selector: HybridSelectorV2) -> tuple[list[V2Selection], int]:
    size = path.stat().st_size
    if plan["global_strategy"]:
        data = path.read_bytes() if plan["mode"] == "whole_file" else bounded_file_sample(path)
        selection = selector.select(data, extension=path.suffix, file_size=size)
        chunks = max(1, (size + plan["chunk_size"] - 1) // plan["chunk_size"])
        return [selection] * chunks, chunks
    selections = []
    with path.open("rb", buffering=1 << 20) as handle:
        while True:
            data = handle.read(plan["chunk_size"])
            if not data:
                break
            selections.append(selector.select(data, extension=path.suffix))
    if not selections:
        selections.append(selector.select(b"", extension=path.suffix))
    return selections, len(selections)


def _unique_strategies(selections: list[V2Selection]) -> list[Strategy]:
    result = []
    for selection in selections:
        if selection.strategy not in result:
            result.append(selection.strategy)
    return result


def compress_hybrid_v2_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    profile: str = "balanced",
    selector_model: str | Path | None = None,
    chunk_size: int | None = None,
    microbench_bytes: int = 16 << 10,
    routing_mode: str = "top3",
    forced_strategy: Strategy | str | None = None,
    overwrite: bool = False,
    context: "CompressionContext | None" = None,
    runtime_generation: str = "v3",
) -> dict:
    source, destination = Path(input_path), Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    effective_context = None if runtime_generation == "v2" else context
    registry = effective_context.codec_registry if effective_context else available_registry()
    plan = adaptive_plan(source, chunk_size, effective_context)
    selection_started = time.perf_counter()
    if forced_strategy is not None:
        strategy = Strategy.parse(forced_strategy) if isinstance(forced_strategy, str) else forced_strategy
        adapter = registry.get(strategy.codec)
        if adapter is None or not adapter.available() or strategy.level not in adapter.available_levels():
            raise CompactFormatError(f"forced strategy unavailable: {strategy.strategy_id}")
        chunks = max(1, (source.stat().st_size + plan["chunk_size"] - 1) // plan["chunk_size"])
        forced = V2Selection(strategy, 1.0, "forced_benchmark", 0, 0.0, 0.0, 0.0, 0.0, False, "benchmark_oracle", False, ((strategy.strategy_id, 1.0),))
        selections = [forced] * chunks
    else:
        # Use pre-loaded artifact from context if available (Phase 3 optimization)
        preloaded = effective_context.selector_artifact if effective_context else None
        # Build selector kwargs, only including model_path if explicitly provided
        selector_kwargs = {
            "profile": profile,
            "registry": registry,
            "microbench_bytes": microbench_bytes,
            "routing_mode": routing_mode,
            "preloaded_artifact": preloaded if runtime_generation != "v2" else None,
            "context": context if runtime_generation != "v2" else None,
            "runtime_generation": runtime_generation,
        }
        if selector_model is not None:
            selector_kwargs["model_path"] = selector_model
        selector = HybridSelectorV2(**selector_kwargs)
        selections, chunks = _select_plan(source, plan, selector)
    selection_ms = (time.perf_counter() - selection_started) * 1000
    strategies = _unique_strategies(selections)
    if any(strategy.codec not in CODECS for strategy in strategies):
        raise CompactFormatError("neural strategies require legacy v5 metadata and are excluded by Selector V2 cost policy")
    homogeneous = len(strategies) == 1
    flags = FLAG_CHUNK_CRC32 | (FLAG_HOMOGENEOUS if homogeneous else 0) | (FLAG_WHOLE_FILE if plan["mode"] == "whole_file" else 0)
    size = source.stat().st_size
    header = bytearray(MAGIC + bytes((COMPACT_VERSION, flags, PROFILES[profile], 0)))
    header.extend(encode_varint(size))
    header.extend(encode_varint(plan["chunk_size"]))
    header.extend(encode_varint(chunks))
    header.extend(encode_varint(len(strategies)))
    for strategy in strategies:
        header.extend(_strategy_bytes(strategy))
    header.extend(struct.pack(">I", zlib.crc32(header) & 0xFFFFFFFF))
    temporary = atomic_target(destination)
    digest = hashlib.sha256()
    codec_payload_bytes = 0
    chunk_framing_bytes = 0
    transform_ms = 0.0
    codec_ms = 0.0
    serialization_ms = 0.0
    routes = Counter()
    codec_distribution = Counter()
    transform_distribution = Counter()
    started_total = time.perf_counter()
    try:
        with source.open("rb", buffering=1 << 20) as input_handle, temporary.open("wb", buffering=1 << 20) as output_handle:
            output_handle.write(header)
            for chunk_id in range(chunks):
                raw = input_handle.read(plan["chunk_size"])
                if size == 0 and chunk_id == 0:
                    raw = b""
                selection = selections[chunk_id]
                strategy = selection.strategy
                routes[selection.route] += 1
                transform = get_transform(strategy.transform)
                stage = time.perf_counter()
                transformed, _ = transform.forward(raw)
                transform_ms += (time.perf_counter() - stage) * 1000
                stage = time.perf_counter()
                encoded = registry[strategy.codec].compress(transformed, strategy.level)
                codec_ms += (time.perf_counter() - stage) * 1000
                stage = time.perf_counter()
                framing = bytearray()
                if not homogeneous:
                    framing.extend(encode_varint(strategies.index(strategy)))
                framing.extend(encode_varint(len(raw)))
                framing.extend(encode_varint(len(transformed)))
                framing.extend(encode_varint(len(encoded.payload)))
                framing.extend(struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF))
                output_handle.write(framing)
                output_handle.write(encoded.payload)
                serialization_ms += (time.perf_counter() - stage) * 1000
                chunk_framing_bytes += len(framing)
                codec_payload_bytes += len(encoded.payload)
                digest.update(raw)
                codec_distribution[strategy.codec] += 1
                transform_distribution[strategy.transform] += 1
            output_handle.write(FOOTER_MAGIC + digest.digest())
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    total_ms = (time.perf_counter() - started_total) * 1000 + selection_ms
    artifact_bytes = destination.stat().st_size
    metadata_bytes = artifact_bytes - codec_payload_bytes
    # A global decision is evaluated once and reused for every output chunk.
    # ``selections`` intentionally repeats that immutable decision to simplify
    # encoding, but selector timings must not be multiplied by chunk count.
    measured_selections = selections[:1] if plan["global_strategy"] else selections
    return {
        "format_version": COMPACT_VERSION,
        "mode": "hybrid-ai-v2",
        "profile": profile,
        "routing_mode": routing_mode,
        "forced_strategy": forced_strategy.strategy_id if isinstance(forced_strategy, Strategy) else forced_strategy,
        "plan_mode": plan["mode"],
        "plan_reason": plan["reason"],
        "original_size": size,
        "artifact_size": artifact_bytes,
        "chunks": chunks,
        "homogeneous": homogeneous,
        "strategies": [strategy.strategy_id for strategy in strategies],
        "codec_distribution": dict(sorted(codec_distribution.items())),
        "transform_distribution": dict(sorted(transform_distribution.items())),
        "route_distribution": dict(sorted(routes.items())),
        "selector_confidence_mean": sum(selection.confidence or 0.0 for selection in selections) / len(selections),
        "feature_scan_ms": sum(selection.feature_scan_ms for selection in measured_selections),
        "inference_ms": sum(selection.inference_ms for selection in measured_selections),
        "candidate_generation_ms": sum(selection.candidate_generation_ms for selection in measured_selections),
        "microbenchmark_ms": sum(selection.microbenchmark_ms for selection in measured_selections),
        "selection_ms": selection_ms,
        "transform_ms": transform_ms,
        "codec_compression_ms": codec_ms,
        "container_serialization_ms": serialization_ms,
        "total_compression_ms": total_ms,
        "codec_payload_bytes": codec_payload_bytes,
        "XAIC_header_bytes": len(header),
        "XAIC_chunk_metadata_bytes": 0,
        "chunk_framing_bytes": chunk_framing_bytes,
        "checksum_bytes": 4 + 4 * chunks + 32,
        "footer_bytes": 36,
        "total_metadata_bytes": metadata_bytes,
        "metadata_overhead_percent": 100 * metadata_bytes / max(1, artifact_bytes),
        "container_penalty_bytes": metadata_bytes,
    }


def _read_header(handle: BinaryIO, max_output_size: int) -> tuple[dict, list[Strategy], int]:
    fixed = handle.read(8)
    if len(fixed) != 8 or fixed[:4] != MAGIC or fixed[4] != COMPACT_VERSION:
        raise CompactFormatError("not an XAIC v6 compact artifact")
    capture = bytearray(fixed)
    flags, profile_id, selector_id = fixed[5], fixed[6], fixed[7]
    if flags & ~(FLAG_HOMOGENEOUS | FLAG_WHOLE_FILE | FLAG_CHUNK_CRC32):
        raise CompactFormatError("invalid XAIC v6 flags")
    if profile_id not in PROFILE_NAMES or selector_id != 0:
        raise CompactFormatError("invalid XAIC v6 profile/selector id")
    original_size = read_varint(handle, capture, max_output_size)
    chunk_size = read_varint(handle, capture, MAX_CHUNK_SIZE)
    chunks = read_varint(handle, capture, max(1, original_size + 1))
    strategy_count = read_varint(handle, capture, 256)
    if chunk_size <= 0 or chunks <= 0 or strategy_count <= 0:
        raise CompactFormatError("invalid XAIC v6 header counts")
    strategies = [_read_strategy(handle, capture) for _ in range(strategy_count)]
    checksum = handle.read(4)
    if len(checksum) != 4 or struct.unpack(">I", checksum)[0] != zlib.crc32(capture) & 0xFFFFFFFF:
        raise CompactFormatError("XAIC v6 header checksum failure")
    if bool(flags & FLAG_HOMOGENEOUS) != (strategy_count == 1):
        raise CompactFormatError("inconsistent XAIC v6 homogeneous flag")
    return {"flags": flags, "profile": PROFILE_NAMES[profile_id], "original_size": original_size, "chunk_size": chunk_size, "chunks": chunks}, strategies, len(capture) + 4


def decompress_hybrid_v2_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    max_output_size: int = MAX_OUTPUT_SIZE,
) -> dict:
    source, destination = Path(input_path), Path(output_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    registry = build_registry()
    temporary = atomic_target(destination)
    digest = hashlib.sha256()
    total = 0
    distribution = Counter()
    started = time.perf_counter()
    try:
        with source.open("rb", buffering=1 << 20) as input_handle, temporary.open("wb", buffering=1 << 20) as output_handle:
            metadata, strategies, _ = _read_header(input_handle, max_output_size)
            homogeneous = bool(metadata["flags"] & FLAG_HOMOGENEOUS)
            for _ in range(metadata["chunks"]):
                strategy_index = 0 if homogeneous else read_varint(input_handle, maximum=len(strategies) - 1)
                if strategy_index >= len(strategies):
                    raise CompactFormatError("invalid XAIC v6 strategy index")
                raw_size = read_varint(input_handle, maximum=min(metadata["chunk_size"], max_output_size - total))
                transformed_size = read_varint(input_handle, maximum=raw_size * 2 + 16)
                payload_size = read_varint(input_handle, maximum=transformed_size * 4 + (1 << 20))
                raw_crc = input_handle.read(4)
                payload = input_handle.read(payload_size)
                if len(raw_crc) != 4 or len(payload) != payload_size:
                    raise CompactFormatError("truncated XAIC v6 chunk")
                strategy = strategies[strategy_index]
                adapter = registry.get(strategy.codec)
                if adapter is None:
                    raise CompactFormatError("XAIC v6 codec unavailable")
                try:
                    transformed = adapter.decompress(payload, _codec_metadata(strategy, transformed_size))
                    raw = get_transform(strategy.transform).inverse(transformed, _transform_metadata(strategy, raw_size))
                except Exception as exc:
                    raise CompactFormatError("XAIC v6 chunk decode failure") from exc
                if len(transformed) != transformed_size or len(raw) != raw_size:
                    raise CompactFormatError("XAIC v6 decoded length mismatch")
                if zlib.crc32(raw) & 0xFFFFFFFF != struct.unpack(">I", raw_crc)[0]:
                    raise CompactFormatError("XAIC v6 chunk checksum failure")
                output_handle.write(raw)
                digest.update(raw)
                total += len(raw)
                distribution[strategy.codec] += 1
            footer = input_handle.read(36)
            if len(footer) != 36 or footer[:4] != FOOTER_MAGIC:
                raise CompactFormatError("truncated or invalid XAIC v6 footer")
            if footer[4:] != digest.digest() or total != metadata["original_size"]:
                raise CompactFormatError("XAIC v6 whole-file SHA/size failure")
            if input_handle.read(1):
                raise CompactFormatError("trailing bytes after XAIC v6 footer")
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {"format_version": COMPACT_VERSION, "restored_size": total, "sha256": digest.hexdigest(), "chunks": metadata["chunks"], "codec_distribution": dict(sorted(distribution.items())), "decompression_ms": (time.perf_counter() - started) * 1000}


def inspect_hybrid_v2(path: str | Path) -> dict:
    source = Path(path)
    with source.open("rb") as handle:
        metadata, strategies, header_bytes = _read_header(handle, MAX_OUTPUT_SIZE)
    return dict(metadata, format_version=COMPACT_VERSION, mode="hybrid-ai-v2", strategies=[strategy.strategy_id for strategy in strategies], homogeneous=bool(metadata["flags"] & FLAG_HOMOGENEOUS), header_bytes=header_bytes, artifact_bytes=source.stat().st_size)
