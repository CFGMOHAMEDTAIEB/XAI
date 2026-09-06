import hashlib
import importlib.util
import json
from pathlib import Path

from xai_compress.hybrid.selector_v2 import HybridSelectorV2, quick_bypass
from xai_compress.hybrid.codecs import available_registry


def _load_v3():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_hybrid_v3.py"
    spec = importlib.util.spec_from_file_location("benchmark_hybrid_v3", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _pass_row(module, source_id="src", method="hybrid_v3_top3", repetition=0, sha="abc"):
    return {
        "benchmark_version": module.BENCHMARK_VERSION,
        "source_id": source_id,
        "source_sha256": sha,
        "method": method,
        "routing_mode": module.routing_for(method),
        "original_bytes": 100,
        "compressed_bytes": 80,
        "compression_ms": 12.5,
        "decompression_ms": 3.0,
        "roundtrip_sha_pass": True,
        "status": "PASS",
        "repetition": repetition,
    }


def test_incomplete_rows_are_never_pass(tmp_path, monkeypatch):
    module = _load_v3()
    monkeypatch.setattr(module, "RESULTS", tmp_path)
    monkeypatch.setattr(module, "CHECKPOINT", tmp_path / "checkpoint.jsonl")
    incomplete = _pass_row(module)
    del incomplete["compressed_bytes"]
    failed = _pass_row(module, method="hybrid_v1")
    failed["status"] = "FAIL"
    failed["roundtrip_sha_pass"] = False
    failed["compressed_bytes"] = 0
    complete = _pass_row(module, method="brotli-11")
    (tmp_path / "checkpoint.jsonl").write_text(
        json.dumps(incomplete) + "\n" + json.dumps(failed) + "\nnot json\n" + json.dumps(complete) + "\n",
        encoding="utf-8",
    )
    loaded = module.load_checkpoint()
    assert len(loaded) == 1
    kept = next(iter(loaded.values()))
    assert kept["method"] == "brotli-11"
    assert module.row_complete(incomplete) is False
    assert module.row_complete(failed) is False


def test_resume_skips_only_matching_identity(tmp_path, monkeypatch):
    module = _load_v3()
    monkeypatch.setattr(module, "RESULTS", tmp_path)
    monkeypatch.setattr(module, "CHECKPOINT", tmp_path / "checkpoint.jsonl")
    row = _pass_row(module, sha="deadbeef")
    module.append_checkpoint(row)
    completed = module.load_checkpoint()
    same = module.measurement_key(row)
    stale = dict(row)
    stale["source_sha256"] = "ffff"
    assert same in completed
    assert module.measurement_key(stale) not in completed
    assert module.measurement_key({**row, "repetition": 1}) not in completed


def test_bpb_tracks_compressed_bytes_with_shared_denominator():
    module = _load_v3()
    aggregates = {
        "a": {"compressed_bytes": 10, "weighted_bpb": 8 * 10 / 100},
        "b": {"compressed_bytes": 20, "weighted_bpb": 8 * 20 / 100},
    }
    assert module.assert_bpb_consistency(aggregates) is True
    aggregates["b"]["weighted_bpb"] = 0.1
    assert module.assert_bpb_consistency(aggregates) is False


def test_transient_test_artifacts_are_not_authoritative_corpus():
    module = _load_v3()
    path = Path(r"C:\repo\engines\XAI-Compress\.test-tmp\final-all\case\out")
    assert module.is_transient_source_path(path) is True
    stable = Path(r"C:\repo\apps\public_nextjs\.next\cache\webpack\server\0.pack.gz")
    assert module.is_transient_source_path(stable) is False


def test_frozen_v2_bypass_keeps_original_tiny_threshold():
    payload = b"x" * 100
    v3, reason_v3 = quick_bypass(payload, "v3")
    v2, reason_v2 = quick_bypass(payload, "v2")
    assert v3 is None
    assert v2 is not None and reason_v2 == "tiny_input"
    selector = HybridSelectorV2(profile="balanced", registry=available_registry(), runtime_generation="v2")
    selected = selector.select(payload)
    assert selected.direct_reason == "tiny_input"
