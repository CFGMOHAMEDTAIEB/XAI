import hashlib
import os
import random
import struct
import zlib
import importlib.util
from pathlib import Path

import pytest

from xai_compress.compression import compress_file, decompress_file
from xai_compress.hybrid.codecs import Strategy, available_registry
from xai_compress.hybrid.container_v2 import (
    CompactFormatError,
    adaptive_plan,
    compress_hybrid_v2_file,
    decompress_hybrid_v2_file,
    inspect_hybrid_v2,
)
from xai_compress.hybrid.selector_v2 import HybridSelectorV2


def _load_benchmark_hybrid_v2_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_hybrid_v2.py"
    spec = importlib.util.spec_from_file_location("benchmark_hybrid_v2", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_select_held_out_keeps_valid_real_files(tmp_path, monkeypatch):
    module = _load_benchmark_hybrid_v2_module()
    manifest = tmp_path / "corpus_manifest.csv"

    def write_file(name: str, payload: bytes):
        path = tmp_path / name
        path.write_bytes(payload)
        return str(path)

    valid_one = write_file("first.bin", b"abc")
    valid_two = write_file("second.bin", b"defgh")
    valid_three = write_file("third.bin", b"ijklmnop")
    invalid = write_file("invalid.bin", b"bad")

    rows = [
        {"source_id": "a", "category": "binary", "size_bucket": "lt_16KiB", "split": "test", "origin": "real", "source_path": valid_one, "original_bytes": "3", "sha256": hashlib.sha256(b"abc").hexdigest()},
        {"source_id": "b", "category": "binary", "size_bucket": "lt_16KiB", "split": "test", "origin": "real", "source_path": valid_two, "original_bytes": "5", "sha256": hashlib.sha256(b"defgh").hexdigest()},
        {"source_id": "c", "category": "logs", "size_bucket": "lt_16KiB", "split": "test", "origin": "real", "source_path": valid_three, "original_bytes": "8", "sha256": hashlib.sha256(b"ijklmnop").hexdigest()},
        {"source_id": "bad", "category": "binary", "size_bucket": "lt_16KiB", "split": "test", "origin": "real", "source_path": invalid, "original_bytes": "3", "sha256": hashlib.sha256(b"zzz").hexdigest()},
    ]
    manifest.write_text("source_id,category,size_bucket,split,origin,source_path,original_bytes,sha256\n" + "\n".join(
        ",".join(str(row[col]) for col in ("source_id", "category", "size_bucket", "split", "origin", "source_path", "original_bytes", "sha256")) for row in rows
    ) + "\n", encoding="utf-8")

    monkeypatch.setattr(module, "MANIFEST", manifest)
    monkeypatch.setattr(module, "RESULTS", tmp_path / "results")

    selected = module.select_held_out()

    assert [row["source_id"] for row in selected] == ["a", "b", "c"]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"x",
        bytes(range(256)),
        b"A" * 8192,
        b"hybrid v2 compact text\n" * 400,
        b'{"key":123,"ok":true}\n' * 300,
        bytes(random.Random(42).randrange(256) for _ in range(8192)),
        b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 16,
    ],
)
def test_compact_v6_exact_sha_roundtrip(tmp_path, data):
    source = tmp_path / "input.bin"
    artifact = tmp_path / "output.xaic"
    restored = tmp_path / "restored.bin"
    source.write_bytes(data)
    info = compress_hybrid_v2_file(source, artifact)
    decoded = decompress_hybrid_v2_file(artifact, restored)
    assert restored.read_bytes() == data
    assert hashlib.sha256(restored.read_bytes()).digest() == hashlib.sha256(data).digest()
    assert info["format_version"] == decoded["format_version"] == 6
    assert info["total_metadata_bytes"] == artifact.stat().st_size - info["codec_payload_bytes"]


def test_compact_single_chunk_and_homogeneous_metadata(tmp_path):
    source = tmp_path / "data.txt"
    source.write_bytes(b"compact metadata\n" * 400)
    artifact = tmp_path / "data.xaic"
    info = compress_hybrid_v2_file(source, artifact)
    inspected = inspect_hybrid_v2(artifact)
    assert info["plan_mode"] == "whole_file"
    assert info["chunks"] == 1
    assert info["homogeneous"] is True
    assert info["XAIC_chunk_metadata_bytes"] == 0
    assert inspected["homogeneous"] is True


def test_compression_api_and_automatic_v6_decode(tmp_path):
    source = tmp_path / "input.txt"
    artifact = tmp_path / "artifact.xaic"
    restored = tmp_path / "restored.txt"
    source.write_bytes(b"API hybrid V2\n" * 100)
    encoded = compress_file(source, artifact, mode="hybrid-v2", profile="balanced", overwrite=True)
    decoded = decompress_file(artifact, restored, overwrite=True)
    assert encoded["format_version"] == decoded["format_version"] == 6
    assert restored.read_bytes() == source.read_bytes()


class _FakeArtifact:
    def __init__(self, predictions, low=0.5, high=0.8):
        self.predictions = predictions
        self.metrics = {"confidence_thresholds": {"balanced": {"low": low, "high": high}}}

    def predict_top_k(self, features, profile, top_k):
        return self.predictions[:top_k]


def test_confidence_routes_top2_top3_and_high(monkeypatch):
    registry = available_registry()
    data = b"confidence routing data\n" * 100
    selector = HybridSelectorV2(profile="balanced", registry=registry, routing_mode="confidence")
    selector._artifact = _FakeArtifact([("zstd|1|identity", 0.90), ("brotli|1|identity", 0.08), ("raw|default|identity", 0.02)])
    assert selector.select(data).route == "high_confidence_direct"
    selector._cache.clear()
    selector._artifact = _FakeArtifact([("zstd|1|identity", 0.65), ("brotli|1|identity", 0.30), ("raw|default|identity", 0.05)])
    assert selector.select(data).candidates_benchmarked == 2
    selector._cache.clear()
    selector._artifact = _FakeArtifact([("zstd|1|identity", 0.40), ("brotli|1|identity", 0.35), ("raw|default|identity", 0.25)])
    assert selector.select(data).candidates_benchmarked == 3


@pytest.mark.parametrize("routing_mode,count", [("top1", 0), ("top2", 2), ("top3", 3)])
def test_explicit_ablation_routing(monkeypatch, routing_mode, count):
    registry = available_registry()
    selector = HybridSelectorV2(profile="balanced", registry=registry, routing_mode=routing_mode)
    selector._artifact = _FakeArtifact([("zstd|1|identity", 0.90), ("brotli|1|identity", 0.08), ("raw|default|identity", 0.02)])
    selected = selector.select(b"explicit routing data\n" * 100)
    assert selected.candidates_benchmarked == count


def test_forced_strategy_is_lossless_and_model_independent(tmp_path):
    source = tmp_path / "forced.txt"
    artifact = tmp_path / "forced.xaic"
    restored = tmp_path / "forced.out"
    source.write_bytes(b"forced oracle measurement\n" * 100)
    info = compress_hybrid_v2_file(source, artifact, forced_strategy="zstd|3|identity")
    decompress_hybrid_v2_file(artifact, restored)
    assert info["strategies"] == ["zstd|3|identity"]
    assert restored.read_bytes() == source.read_bytes()


def test_direct_bypass_and_exact_cache():
    selector = HybridSelectorV2(profile="balanced", registry=available_registry())
    first = selector.select(b"tiny")
    second = selector.select(b"tiny")
    assert first.route == "direct_bypass"
    assert first.direct_reason == "tiny_input"
    assert second.cache_hit is True
    assert second.feature_scan_ms == second.microbenchmark_ms == 0.0


def test_default_routing_uses_bounded_top3_for_speed():
    selector = HybridSelectorV2(profile="balanced", registry=available_registry())
    assert selector.routing_mode == "top3"


def test_minimum_gain_rule(monkeypatch):
    import xai_compress.hybrid.selector_v2 as module

    selector = HybridSelectorV2(profile="balanced", registry=available_registry())
    selector._artifact = _FakeArtifact([("brotli|6|identity", 0.65), ("zstd|1|identity", 0.30), ("raw|default|identity", 0.05)])

    def measured(data, strategy, registry):
        size = 95 if strategy.codec == "brotli" else 100
        return {
            "strategy_id": strategy.strategy_id,
            "codec": strategy.codec,
            "level": strategy.level,
            "transform": strategy.transform,
            "compressed_bytes": size,
            "compression_seconds": 0.01,
            "decompression_seconds": 0.01,
            "peak_rss": 1.0,
        }

    monkeypatch.setattr(module, "measure_strategy", measured)
    selected = selector.select(b"minimum gain policy data\n" * 100)
    assert selected.strategy == Strategy("zstd", 1)
    assert selected.minimum_gain_applied is True


def test_small_file_rule_path_avoids_microbenchmark(monkeypatch):
    selector = HybridSelectorV2(profile="balanced", registry=available_registry())
    selector._artifact = _FakeArtifact([("brotli|6|identity", 0.75), ("zstd|1|identity", 0.20), ("raw|default|identity", 0.05)])

    def fail_if_called(data, strategy, registry):
        raise AssertionError("small-file fast path should skip microbenchmark")

    monkeypatch.setattr("xai_compress.hybrid.selector_v2.measure_strategy", fail_if_called)
    selected = selector.select(b"tiny text payload\n" * 12)
    assert selected.route == "small_file_rule_direct"
    assert selected.microbenchmark_ms == 0.0
    assert selected.strategy in {Strategy("raw"), Strategy("zstd", 1), Strategy("brotli", 1)}


def _strategy_offset_and_crc_position(blob: bytearray):
    position = 8
    for _ in range(4):
        while blob[position] & 0x80:
            position += 1
        position += 1
    strategy_offset = position
    position += 2
    while blob[position] & 0x80:
        position += 1
    position += 1
    return strategy_offset, position


def test_compact_corruption_rejections(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"corruption test\n" * 300)
    artifact = tmp_path / "artifact.xaic"
    restored = tmp_path / "restored.bin"
    compress_hybrid_v2_file(source, artifact)
    blob = bytearray(artifact.read_bytes())
    with pytest.raises(CompactFormatError):
        bad = tmp_path / "truncated.xaic"
        bad.write_bytes(blob[:-2])
        decompress_hybrid_v2_file(bad, restored, overwrite=True)
    with pytest.raises(CompactFormatError, match="trailing"):
        bad = tmp_path / "trailing.xaic"
        bad.write_bytes(blob + b"garbage")
        decompress_hybrid_v2_file(bad, restored, overwrite=True)
    strategy_offset, crc_position = _strategy_offset_and_crc_position(blob)
    for offset, match in ((strategy_offset, "codec"), (strategy_offset + 1, "transform")):
        damaged = bytearray(blob)
        damaged[offset] = 255
        damaged[crc_position : crc_position + 4] = struct.pack(">I", zlib.crc32(damaged[:crc_position]) & 0xFFFFFFFF)
        bad = tmp_path / f"bad-{match}.xaic"
        bad.write_bytes(damaged)
        with pytest.raises(CompactFormatError, match=match):
            decompress_hybrid_v2_file(bad, restored, overwrite=True)


def test_adaptive_chunk_plan_is_measured_from_regions(tmp_path):
    homogeneous = tmp_path / "homogeneous.bin"
    heterogeneous = tmp_path / "heterogeneous.bin"
    homogeneous.write_bytes(b"ABCD" * ((11 << 20) // 4))
    rng = random.Random(99)
    with heterogeneous.open("wb") as handle:
        handle.write(b"\0" * (4 << 20))
        handle.write(rng.randbytes(4 << 20))
        handle.write(b"structured text\n" * ((3 << 20) // 16))
    first = adaptive_plan(homogeneous)
    second = adaptive_plan(heterogeneous)
    assert first["mode"] == "homogeneous_chunks"
    assert first["chunk_size"] == 4 << 20
    assert second["mode"] == "adaptive_chunks"
    assert second["chunk_size"] in {256 << 10, 1 << 20}


@pytest.mark.parametrize(
    "data",
    [
        bytes(range(256)) * 128,
        b"ABCD" * 8192,
        bytes(random.Random(7).randrange(256) for _ in range(32768)),
    ],
    ids=["alphabet", "repetitive", "seeded-random"],
)
def test_rust_python_feature_parity(monkeypatch, data):
    import xai_compress.hybrid.features as feature_module

    native = feature_module.extract_features(data, file_size=len(data), extension=".bin")
    monkeypatch.setattr(feature_module, "_native_byte_stats", lambda _: None)
    python = feature_module.extract_features(data, file_size=len(data), extension=".bin")
    assert native.keys() == python.keys()
    for key in native:
        if isinstance(native[key], float):
            assert native[key] == pytest.approx(python[key], abs=1e-12), key
        else:
            assert native[key] == python[key], key
