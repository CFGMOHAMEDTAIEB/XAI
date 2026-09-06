import gzip
import hashlib
import json
import math
import random

import pytest

from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.hybrid.codecs import Strategy, available_registry
from xai_compress.hybrid.container import (
    CHUNK,
    PREFIX,
    HybridFormatError,
    compress_hybrid_bytes,
    decompress_hybrid_bytes,
)
from xai_compress.hybrid.features import MAX_FEATURE_SCAN_BYTES, extract_features, extract_file_features
from xai_compress.hybrid.ml import SelectorArtifact
from xai_compress.hybrid.profiles import label_measurements, load_profiles
from xai_compress.hybrid.selector import HybridSelector, measure_strategy
from xai_compress.hybrid.transforms import TRANSFORMS


def digest(data):
    return hashlib.sha256(data).digest()


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"x",
        bytes(range(256)),
        b"repeat" * 1000,
        bytes(random.Random(7).randrange(256) for _ in range(4096)),
        b"plain text\n" * 300,
        b'{"x":1,"values":[1,2,3]}\n' * 100,
        b"a,b,c\n1,2,3\n" * 100,
        b"%PDF-1.4\nstream\ncompressed document\nendstream\n" * 50,
        gzip.compress(b"already compressed" * 100),
    ],
)
def test_hybrid_v5_sha_matrix(data):
    artifact = compress_hybrid_bytes(
        data, profile="balanced", selector_mode="rules", chunk_size=1024
    )
    restored = decompress_hybrid_bytes(artifact)
    assert restored == data
    assert digest(restored) == digest(data)
    assert artifact[:5] == b"XAIC\x05"


def test_hybrid_v5_one_mib_random_and_multichunk():
    data = bytes(random.Random(9).randrange(256) for _ in range(1 << 20))
    artifact = compress_hybrid_bytes(
        data, profile="fastest", selector_mode="rules", chunk_size=64 << 10
    )
    assert decompress_hybrid_bytes(artifact) == data


def test_every_transform_exact_and_deterministic():
    samples = [b"", bytes(range(256)), b"\0" * 400, b'{"value": true}\n' * 40]
    for transform in TRANSFORMS.values():
        for data in samples:
            encoded_a, metadata_a = transform.forward(data)
            encoded_b, metadata_b = transform.forward(data)
            assert (encoded_a, metadata_a) == (encoded_b, metadata_b)
            assert transform.inverse(encoded_a, metadata_a) == data


def test_every_classical_adapter_and_transform_combination():
    registry = available_registry()
    data = (b'{"value":123,"zeros":"\0\0\0","text":"codec"}\n' * 4)
    for codec_id in ("raw", "zstd", "brotli", "deflate", "lzma2", "bzip2", "xai-static"):
        adapter = registry[codec_id]
        level = adapter.available_levels()[0]
        for transform_id in TRANSFORMS:
            measured = measure_strategy(data, Strategy(codec_id, level, transform_id), registry)
            assert measured["sha_pass"]


@pytest.mark.parametrize("codec_id", ["xai-gru", "xai-transformer"])
def test_neural_adapters_lazy_roundtrip(codec_id):
    registry = available_registry()
    if codec_id not in registry:
        pytest.skip(f"{codec_id} checkpoint unavailable")
    measured = measure_strategy(b"neural", Strategy(codec_id), registry)
    assert measured["sha_pass"]


def test_feature_vector_is_bounded_finite_deterministic(tmp_path):
    path = tmp_path / "large.bin"
    path.write_bytes(bytes(range(256)) * 2048)
    first = extract_file_features(path)
    second = extract_file_features(path)
    assert first == second
    assert first["sample_size"] == MAX_FEATURE_SCAN_BYTES
    assert all(not isinstance(value, float) or math.isfinite(value) for value in first.values())
    assert extract_features(b"\x89PNG\r\n\x1a\nrest", extension=".wrong")["is_already_compressed"] == 1.0
    assert extract_features(b"unknown", extension="")["extension"] == "<none>"


def test_profile_weights_and_labels_are_deterministic():
    profiles = load_profiles()
    rows = [
        {"strategy_id": "small", "compressed_bytes": 10, "compression_seconds": 2, "decompression_seconds": 2, "peak_rss": 2},
        {"strategy_id": "fast", "compressed_bytes": 20, "compression_seconds": 1, "decompression_seconds": 1, "peak_rss": 1},
    ]
    assert label_measurements(rows, "smallest", profiles)[0]["strategy_id"] == "small"
    assert label_measurements(rows, "fastest", profiles)[0]["strategy_id"] == "fast"
    assert label_measurements(rows, "balanced", profiles) == label_measurements(rows, "balanced", profiles)


def test_selector_prediction_and_fallback_are_deterministic():
    model = SelectorArtifact.load("checkpoints/selector/best.json")
    features = extract_features(b"selector text\n" * 100, extension=".txt")
    assert model.predict_top_k(features, "balanced", 3) == model.predict_top_k(features, "balanced", 3)
    selector = HybridSelector(
        mode="ai", profile="balanced", model_path="missing-selector.json", registry={"raw": available_registry()["raw"]}
    )
    selected = selector.select(b"fallback")
    assert selected.strategy.codec == "raw"
    assert selected.fallback_reason


def test_selector_reuses_only_exact_consecutive_bounded_chunks():
    registry = available_registry()
    selector = HybridSelector(mode="rules", profile="balanced", registry=registry)
    data = b"identical bounded chunk\n" * 128
    first = selector.select(data, extension=".txt")
    cached = selector.select(data, extension=".txt")
    assert cached.strategy == first.strategy
    assert cached.feature_scan_ms == 0.0
    assert cached.model_inference_ms == 0.0
    assert cached.microbenchmark_ms == 0.0
    changed = selector.select(data + b"x", extension=".txt")
    assert changed.feature_scan_ms > 0.0
    changed_extension = selector.select(data + b"x", extension=".bin")
    assert changed_extension.feature_scan_ms > 0.0


def _first_chunk_metadata(blob):
    _, _, header_len = PREFIX.unpack_from(blob)
    position = PREFIX.size + header_len + 32
    values = CHUNK.unpack_from(blob, position)
    metadata_len = values[-2]
    metadata_position = position + CHUNK.size
    metadata = json.loads(blob[metadata_position : metadata_position + metadata_len])
    return position, metadata_position, metadata_len, values, metadata


def _replace_chunk_metadata(blob, update):
    mutable = bytearray(blob)
    position, metadata_position, old_len, values, metadata = _first_chunk_metadata(blob)
    update(metadata)
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    assert len(encoded) == old_len
    mutable[metadata_position : metadata_position + old_len] = encoded
    fields = list(values)
    fields[-1] = digest(encoded)
    mutable[position : position + CHUNK.size] = CHUNK.pack(*fields)
    return bytes(mutable)


def test_hybrid_corruption_rejections():
    data = b"metadata corruption" * 100
    artifact = compress_hybrid_bytes(data, selector_mode="rules", chunk_size=512)
    with pytest.raises(HybridFormatError):
        decompress_hybrid_bytes(artifact[:-3])
    with pytest.raises(HybridFormatError):
        decompress_hybrid_bytes(artifact + b"trailing")
    position, _, _, values, _ = _first_chunk_metadata(artifact)
    bad_id = bytearray(artifact)
    fields = list(values)
    fields[1] = 7
    bad_id[position : position + CHUNK.size] = CHUNK.pack(*fields)
    with pytest.raises(HybridFormatError, match="non-sequential"):
        decompress_hybrid_bytes(bytes(bad_id))
    bad_codec = _replace_chunk_metadata(
        artifact, lambda md: md.update(codec_id="q" * len(md["codec_id"]))
    )
    with pytest.raises(HybridFormatError, match="invalid codec"):
        decompress_hybrid_bytes(bad_codec)
    bad_transform = _replace_chunk_metadata(
        artifact, lambda md: md.update(transform_id="q" * len(md["transform_id"]))
    )
    with pytest.raises(HybridFormatError, match="invalid transform"):
        decompress_hybrid_bytes(bad_transform)


def test_legacy_v1_v2_still_decode():
    data = b"legacy compatibility" * 100
    for mode in ("static", "hybrid"):
        artifact = compress_bytes(data, mode, chunk_size=64)
        assert decompress_bytes(artifact) == data
