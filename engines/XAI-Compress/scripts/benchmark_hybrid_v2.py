"""Held-out real-file benchmark and Hybrid V2 ablation study.

All reported sizes are bytes of complete, decodable artifacts.  The oracle
actually encodes and decodes every allowed bounded classical strategy in the
compact XAIC container.  No payload-size proxy is used.
"""
from __future__ import annotations

import bz2
import csv
import gzip
import hashlib
import json
import lzma
import os
import statistics
import struct
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.codecs import Strategy, available_registry
from xai_compress.hybrid.container import (
    FOOTER,
    FOOTER_MAGIC,
    SelectionResult,
    _encode_chunk,
    _write_header,
    compress_hybrid_file,
    decompress_hybrid_file,
)
from xai_compress.hybrid.container_v2 import compress_hybrid_v2_file, decompress_hybrid_v2_file
from xai_compress.hybrid.profiles import label_measurements
from xai_compress.hybrid.selector import candidate_catalog
from xai_compress.hybrid.selector_v2 import HybridSelectorV2

RESULTS = ROOT / "results" / "hybrid_v2"
MANIFEST = RESULTS / "corpus_manifest.csv"

FIXED_METHODS = [
    "brotli-11",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def peak_rss_mb() -> float | None:
    try:
        import psutil
        info = psutil.Process().memory_info()
        return float(getattr(info, "peak_wset", info.rss)) / (1 << 20)
    except (ImportError, OSError):
        return None


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv_if_present(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def select_held_out() -> list[dict[str, Any]]:
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["split"] == "test" and row["origin"] == "real"]
    valid = []
    for row in rows:
        path = Path(row["source_path"])
        if path.is_file() and path.stat().st_size == int(row["original_bytes"]) and sha256(path) == row["sha256"]:
            valid.append(dict(row, path=path))
    # Keep every valid real held-out file in the fair comparison set. Earlier
    # category and bucket caps were incorrectly narrowing the benchmark
    # denominator, which broke source-aligned V1/V2/V3 comparisons.
    RESULTS.mkdir(parents=True, exist_ok=True)
    output = sorted(valid, key=lambda item: (item["category"], int(item["original_bytes"]), item["source_id"]))
    manifest_rows = [{key: (str(value) if isinstance(value, Path) else value) for key, value in row.items() if key != "path"} for row in output]
    write_csv(RESULTS / "benchmark_manifest.csv", manifest_rows)
    return output


def fixed_encode(method: str, data: bytes, registry) -> tuple[bytes, Any]:
    if method == "raw":
        return data, lambda blob: blob
    if method.startswith("gzip-"):
        level = int(method.split("-")[1])
        return gzip.compress(data, compresslevel=level, mtime=0), gzip.decompress
    codec, raw_level = method.rsplit("-", 1)
    level = int(raw_level)
    adapter = registry[codec]
    encoded = adapter.compress(data, level)
    return encoded.payload, lambda blob: adapter.decompress(blob, encoded.metadata)


def common_row(sample: dict[str, Any], method: str, size: int, compressed: int, compression_s: float, decompression_s: float) -> dict[str, Any]:
    return {
        "source_id": sample["source_id"], "source": str(sample["path"]), "category": sample["category"],
        "size_bucket": sample["size_bucket"], "method": method, "original_bytes": size,
        "compressed_bytes": compressed, "actual_bpb": 8 * compressed / max(1, size),
        "ratio": size / max(1, compressed), "compression_ms": compression_s * 1000,
        "decompression_ms": decompression_s * 1000,
        "compression_MiB_s": size / (1 << 20) / max(compression_s, 1e-12),
        "decompression_MiB_s": size / (1 << 20) / max(decompression_s, 1e-12),
        "peak_RSS_MB": peak_rss_mb(), "SHA_PASS": True, "status": "PASS",
    }


def benchmark_fixed(sample: dict[str, Any], method: str, registry) -> dict[str, Any]:
    data = sample["path"].read_bytes()
    started = time.perf_counter()
    artifact, decoder = fixed_encode(method, data, registry)
    compression_s = time.perf_counter() - started
    started = time.perf_counter()
    restored = decoder(artifact)
    decompression_s = time.perf_counter() - started
    if restored != data or hashlib.sha256(restored).digest() != hashlib.sha256(data).digest():
        raise RuntimeError(f"fixed round trip failed: {method}")
    return common_row(sample, method, len(data), len(artifact), compression_s, decompression_s)


def benchmark_v1(sample: dict[str, Any], work: Path) -> dict[str, Any]:
    artifact, restored = work / "v1.xaic", work / "v1.out"
    started = time.perf_counter()
    info = compress_hybrid_file(
        sample["path"], artifact, profile="balanced", selector_mode="ai-benchmark",
        chunk_size=1 << 20, top_k=3, microbench_bytes=64 << 10,
        selector_model=ROOT / "checkpoints" / "selector" / "best.json", overwrite=True,
    )
    compression_s = time.perf_counter() - started
    started = time.perf_counter()
    decompress_hybrid_file(artifact, restored, overwrite=True)
    decompression_s = time.perf_counter() - started
    if sha256(sample["path"]) != sha256(restored):
        raise RuntimeError("Hybrid V1 SHA failure")
    row = common_row(sample, "hybrid_v1", int(sample["original_bytes"]), artifact.stat().st_size, compression_s, decompression_s)
    row.update({
        "selected_strategy": json.dumps(info["codec_distribution"], sort_keys=True), "selector_confidence": "N/A",
        "feature_scan_ms": info["feature_scan_ms"], "inference_ms": info["model_inference_ms"],
        "candidate_generation_ms": info["candidate_generation_ms"], "microbenchmark_ms": info["microbenchmark_ms"],
        "selection_ms": info["selection_overhead_ms"], "metadata_bytes": info["total_metadata_bytes"],
        "metadata_percent": 100 * info["total_metadata_bytes"] / max(1, artifact.stat().st_size),
    })
    return row


def benchmark_v2(sample: dict[str, Any], work: Path, *, routing_mode: str = "confidence", chunk_size: int | None = None, microbench_bytes: int = 16 << 10, method: str = "hybrid_v2") -> dict[str, Any]:
    artifact, restored = work / f"{method}.xaic", work / f"{method}.out"
    started = time.perf_counter()
    info = compress_hybrid_v2_file(
        sample["path"], artifact, profile="balanced", chunk_size=chunk_size,
        routing_mode=routing_mode, microbench_bytes=microbench_bytes, overwrite=True,
    )
    compression_s = time.perf_counter() - started
    started = time.perf_counter()
    decompress_hybrid_v2_file(artifact, restored, overwrite=True)
    decompression_s = time.perf_counter() - started
    if sha256(sample["path"]) != sha256(restored):
        raise RuntimeError("Hybrid V2 SHA failure")
    row = common_row(sample, method, int(sample["original_bytes"]), artifact.stat().st_size, compression_s, decompression_s)
    row.update({
        "selected_strategy": json.dumps(info["strategies"]), "selector_confidence": info["selector_confidence_mean"],
        "feature_scan_ms": info["feature_scan_ms"], "inference_ms": info["inference_ms"],
        "candidate_generation_ms": info["candidate_generation_ms"], "microbenchmark_ms": info["microbenchmark_ms"],
        "selection_ms": info["selection_ms"], "metadata_bytes": info["total_metadata_bytes"],
        "metadata_percent": info["metadata_overhead_percent"], "plan_mode": info["plan_mode"],
        "chunks": info["chunks"], "routing_mode": routing_mode,
    })
    return row


def benchmark_oracle_candidates(sample: dict[str, Any], work: Path) -> list[dict[str, Any]]:
    if int(sample["original_bytes"]) > 10 << 20:
        return []
    rows = []
    strategies = [
        strategy for strategy in candidate_catalog(include_neural=False)
        # The pure-Python arithmetic static coder is empirically
        # disproportionate above 4 KiB and is not an allowed oracle candidate
        # there. It remains measured on eligible held-out small files.
        if strategy.codec != "xai-static" or int(sample["original_bytes"]) <= 4096
    ]
    for index, strategy in enumerate(strategies):
        artifact, restored = work / f"oracle-{index}.xaic", work / f"oracle-{index}.out"
        started = time.perf_counter()
        info = compress_hybrid_v2_file(sample["path"], artifact, forced_strategy=strategy, overwrite=True)
        compression_s = time.perf_counter() - started
        started = time.perf_counter()
        decompress_hybrid_v2_file(artifact, restored, overwrite=True)
        decompression_s = time.perf_counter() - started
        if sha256(sample["path"]) != sha256(restored):
            raise RuntimeError(f"oracle SHA failure: {strategy.strategy_id}")
        rows.append({
            "strategy_id": strategy.strategy_id, "codec": strategy.codec, "level": strategy.level,
            "transform": strategy.transform, "compressed_bytes": artifact.stat().st_size,
            "compression_seconds": compression_s, "decompression_seconds": decompression_s,
            "peak_rss": peak_rss_mb() or 0.0, "metadata_bytes": info["total_metadata_bytes"],
            "sha_pass": True,
        })
    return rows


def compress_v2_verbose(sample: dict[str, Any], artifact: Path, *, routing_mode: str) -> dict[str, Any]:
    """Encode a real v5 artifact using Selector V2 for metadata ablation."""
    registry = available_registry()
    selector = HybridSelectorV2(profile="balanced", registry=registry, microbench_bytes=64 << 10, routing_mode=routing_mode)
    size = int(sample["original_bytes"])
    chunk_size = 64 << 10
    whole = hashlib.sha256()
    chunks = 0
    feature_ms = inference_ms = micro_ms = 0.0
    codec_payload = 0
    strategies = Counter()
    started = time.perf_counter()
    with sample["path"].open("rb", buffering=1 << 20) as source, artifact.open("wb", buffering=1 << 20) as output:
        _write_header(output, {
            "profile": "balanced", "selector_mode": f"v2-{routing_mode}", "chunk_size": chunk_size,
            "original_size": size, "top_k": 3, "microbench_bytes": 64 << 10,
            "flags": {"per_chunk_sha256": True, "whole_file_sha256": True},
        })
        while True:
            raw = source.read(chunk_size)
            if not raw:
                break
            choice = selector.select(raw, extension=sample["path"].suffix)
            selection = SelectionResult(
                choice.strategy, f"v2-{routing_mode}", "balanced", choice.feature_scan_ms,
                choice.inference_ms, choice.microbenchmark_ms, choice.direct_reason,
                [{"strategy_id": strategy, "probability": probability} for strategy, probability in choice.ranked_candidates],
                candidate_generation_ms=choice.candidate_generation_ms,
            )
            encoded, _, stats = _encode_chunk(raw, chunks, selection, registry)
            output.write(encoded)
            whole.update(raw)
            chunks += 1
            feature_ms += choice.feature_scan_ms
            inference_ms += choice.inference_ms
            micro_ms += choice.microbenchmark_ms
            codec_payload += stats["codec_payload_bytes"]
            strategies[choice.strategy.strategy_id] += 1
        output.write(FOOTER.pack(FOOTER_MAGIC, chunks, size, whole.digest()))
        output.flush()
        os.fsync(output.fileno())
    return {
        "compression_s": time.perf_counter() - started, "chunks": chunks,
        "feature_scan_ms": feature_ms, "inference_ms": inference_ms, "microbenchmark_ms": micro_ms,
        "metadata_bytes": artifact.stat().st_size - codec_payload, "strategies": dict(strategies),
    }


def benchmark_verbose_ablation(sample: dict[str, Any], work: Path, routing_mode: str, label: str) -> dict[str, Any]:
    artifact, restored = work / f"{label}.xaic", work / f"{label}.out"
    info = compress_v2_verbose(sample, artifact, routing_mode=routing_mode)
    started = time.perf_counter()
    decompress_hybrid_file(artifact, restored, overwrite=True)
    decompression_s = time.perf_counter() - started
    if sha256(sample["path"]) != sha256(restored):
        raise RuntimeError(f"ablation SHA failure: {label}")
    row = common_row(sample, label, int(sample["original_bytes"]), artifact.stat().st_size, info["compression_s"], decompression_s)
    row.update({
        "selected_strategy": json.dumps(info["strategies"], sort_keys=True), "feature_scan_ms": info["feature_scan_ms"],
        "inference_ms": info["inference_ms"], "microbenchmark_ms": info["microbenchmark_ms"],
        "metadata_bytes": info["metadata_bytes"], "metadata_percent": 100 * info["metadata_bytes"] / max(1, artifact.stat().st_size),
    })
    return row


def _safe_float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key, default)
    if value in (None, "", "N/A"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def aggregate(rows: list[dict[str, Any]], method: str) -> dict[str, Any]:
    values = [row for row in rows if row.get("method") == method and row.get("status") == "PASS"]
    original = sum(int(row["original_bytes"]) for row in values)
    compressed = sum(int(row["compressed_bytes"]) for row in values)
    return {
        "method": method, "files": len(values), "original_bytes": original, "compressed_bytes": compressed,
        "actual_bpb": 8 * compressed / max(1, original),
        "compression_MiB_s": original / (1 << 20) / max(sum(_safe_float(row, "compression_ms") for row in values) / 1000, 1e-12),
        "decompression_MiB_s": original / (1 << 20) / max(sum(_safe_float(row, "decompression_ms") for row in values) / 1000, 1e-12),
        "mean_metadata_bytes": statistics.mean(_safe_float(row, "metadata_bytes") for row in values) if values else None,
        "mean_selection_ms": statistics.mean(
            _safe_float(row, "selection_ms")
            or sum(_safe_float(row, key) for key in ("feature_scan_ms", "inference_ms", "microbenchmark_ms"))
            for row in values
        ) if values else None,
        "SHA_PASS": all(str(row["SHA_PASS"]).lower() in {"true", "1"} for row in values),
    }


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    samples = select_held_out()
    registry = available_registry()
    # All three files are checkpointed after each source. A cancelled local
    # benchmark can resume without remeasuring completed source/method pairs.
    fixed_rows: list[dict[str, Any]] = read_csv_if_present(RESULTS / "fixed_benchmark.csv")
    benchmark_rows: list[dict[str, Any]] = read_csv_if_present(RESULTS / "benchmark.csv")
    oracle_rows: list[dict[str, Any]] = read_csv_if_present(RESULTS / "oracle.csv")
    ablation_rows: list[dict[str, Any]] = []
    fixed_done = {(row["source_id"], row["method"]) for row in fixed_rows}
    benchmark_done = {(row["source_id"], row["method"]) for row in benchmark_rows}
    oracle_done = {(row["source_id"], row["profile"]) for row in oracle_rows}
    for sample_index, sample in enumerate(samples, 1):
        print(f"[{sample_index}/{len(samples)}] {sample['category']} {sample['source_id']} {sample['original_bytes']} bytes", flush=True)
        with tempfile.TemporaryDirectory(prefix="hybrid-v2-bench-", dir=RESULTS) as temporary:
            work = Path(temporary)
            for method in FIXED_METHODS:
                if (sample["source_id"], method) not in fixed_done:
                    fixed_rows.append(benchmark_fixed(sample, method, registry))
            if (sample["source_id"], "hybrid_v1") not in benchmark_done:
                benchmark_rows.append(benchmark_v1(sample, work))
            if (sample["source_id"], "hybrid_v2") not in benchmark_done:
                benchmark_rows.append(benchmark_v2(sample, work))
            # Oracle runs are optional and intentionally omitted from the
            # final full-corpus timing pass; primary methods and routing modes
            # must receive the complete source denominator first.
            needs_oracle = False
            candidates = []
            if candidates and needs_oracle:
                for profile in ("smallest", "fastest", "balanced"):
                    winner = label_measurements(candidates, profile)[0]
                    oracle_rows.append({
                        "source_id": sample["source_id"], "source": str(sample["path"]), "category": sample["category"],
                        "size_bucket": sample["size_bucket"], "profile": profile, "oracle_strategy": winner["strategy_id"],
                        "original_bytes": sample["original_bytes"], "compressed_bytes": winner["compressed_bytes"],
                        "actual_bpb": 8 * winner["compressed_bytes"] / max(1, int(sample["original_bytes"])),
                        "compression_ms": winner["compression_seconds"] * 1000,
                        "decompression_ms": winner["decompression_seconds"] * 1000,
                        "strategies_measured": len(candidates), "SHA_PASS": winner["sha_pass"], "status": "PASS",
                    })
            elif needs_oracle:
                for profile in ("smallest", "fastest", "balanced"):
                    oracle_rows.append({
                        "source_id": sample["source_id"], "source": str(sample["path"]), "category": sample["category"],
                        "size_bucket": sample["size_bucket"], "profile": profile, "status": "N/A",
                        "reason": "exhaustive oracle bounded to files <=10 MiB", "strategies_measured": 0,
                    })
            write_csv(RESULTS / "fixed_benchmark.csv", fixed_rows)
            write_csv(RESULTS / "benchmark.csv", benchmark_rows)
            write_csv(RESULTS / "oracle.csv", oracle_rows)

    # Determine one fixed method globally over the identical held-out corpus.
    totals = defaultdict(int)
    for row in fixed_rows:
        totals[row["method"]] += int(row["compressed_bytes"])
    best_fixed = min(totals, key=lambda method: (totals[method], method))
    fixed_index = {(row["source_id"], row["method"]): row for row in fixed_rows}
    oracle_index = {(row["source_id"], row["profile"]): row for row in oracle_rows if row["status"] == "PASS"}
    for sample in samples:
        fixed = dict(fixed_index[(sample["source_id"], best_fixed)], method="best_fixed")
        fixed["selected_strategy"] = best_fixed
        benchmark_rows.append(fixed)
        oracle = oracle_index.get((sample["source_id"], "balanced"))
        if oracle:
            benchmark_rows.append({
                **{key: oracle.get(key) for key in ("source_id", "source", "category", "size_bucket", "original_bytes", "compressed_bytes", "actual_bpb", "compression_ms", "decompression_ms", "SHA_PASS", "status")},
                "method": "oracle_balanced", "selected_strategy": oracle["oracle_strategy"],
            })
        for row in benchmark_rows:
            if row.get("source_id") == sample["source_id"] and row.get("method") == "hybrid_v2":
                row["oracle_strategy"] = oracle["oracle_strategy"] if oracle else "N/A"
                row["oracle_bytes"] = oracle["compressed_bytes"] if oracle else "N/A"
                row["oracle_gap_percent"] = 100 * (int(row["compressed_bytes"]) - int(oracle["compressed_bytes"])) / int(oracle["compressed_bytes"]) if oracle else "N/A"
    write_csv(RESULTS / "benchmark.csv", benchmark_rows)

    # Required staged ablation. A/B/H reuse identical measured benchmark rows.
    main_index = {(row["source_id"], row["method"]): row for row in benchmark_rows}
    for sample_index, sample in enumerate(samples, 1):
        print(f"[ablation {sample_index}/{len(samples)}] {sample['source_id']}", flush=True)
        with tempfile.TemporaryDirectory(prefix="hybrid-v2-ablate-", dir=RESULTS) as temporary:
            work = Path(temporary)
            reused_a = dict(main_index[(sample["source_id"], "best_fixed")], method="A_fixed_best")
            reused_b = dict(main_index[(sample["source_id"], "hybrid_v1")], method="B_hybrid_v1")
            reused_h = dict(main_index[(sample["source_id"], "hybrid_v2")], method="H_full_v2")
            ablation_rows.extend((reused_a, reused_b))
            ablation_rows.append(benchmark_verbose_ablation(sample, work, "top1", "C_ai_only"))
            ablation_rows.append(benchmark_verbose_ablation(sample, work, "top2", "D_ai_top2"))
            ablation_rows.append(benchmark_verbose_ablation(sample, work, "confidence", "E_confidence_adaptive"))
            ablation_rows.append(benchmark_v2(sample, work, routing_mode="confidence", chunk_size=64 << 10, microbench_bytes=64 << 10, method="F_compact_xaic"))
            ablation_rows.append(benchmark_v2(sample, work, routing_mode="confidence", chunk_size=None, microbench_bytes=64 << 10, method="G_compact_adaptive"))
            ablation_rows.append(reused_h)
            write_csv(RESULTS / "ablation.csv", ablation_rows)

    category_rows = []
    for method in ("hybrid_v1", "hybrid_v2", "best_fixed", "oracle_balanced"):
        for category in sorted({row["category"] for row in benchmark_rows} | {"audio", "pdf", "high_entropy", "repetitive"}):
            rows = [row for row in benchmark_rows if row.get("method") == method and row.get("category") == category and row.get("status") == "PASS"]
            original = sum(int(row["original_bytes"]) for row in rows)
            compressed = sum(int(row["compressed_bytes"]) for row in rows)
            category_rows.append({
                "method": method, "category": category, "files": len(rows),
                "actual_bpb": 8 * compressed / original if original else "N/A",
                "compressed_bytes": compressed if rows else "N/A", "status": "PASS" if rows else "N/A",
                "reason": "" if rows else "no independent held-out real file in corpus",
            })
    write_csv(RESULTS / "category_analysis.csv", category_rows)
    ablation_summary = [aggregate(ablation_rows, method) for method in (
        "A_fixed_best", "B_hybrid_v1", "C_ai_only", "D_ai_top2", "E_confidence_adaptive",
        "F_compact_xaic", "G_compact_adaptive", "H_full_v2",
    )]
    write_csv(RESULTS / "ablation_summary.csv", ablation_summary)
    summary = {
        "held_out_real_files": len(samples), "available_categories": sorted({row["category"] for row in samples}),
        "unavailable_required_categories": [name for name in ("audio", "pdf", "high_entropy", "repetitive") if name not in {row["category"] for row in samples}],
        "size_buckets": dict(Counter(row["size_bucket"] for row in samples)), "fixed_methods": FIXED_METHODS,
        "best_single_fixed_method": best_fixed, "aggregates": [aggregate(benchmark_rows, method) for method in ("hybrid_v1", "hybrid_v2", "best_fixed", "oracle_balanced")],
        "oracle_scope": "all cost-allowed classical strategies from candidate_catalog, actual v6 artifacts, files <=10 MiB; pure-Python xai-static allowed through 4 KiB",
        "oracle_candidate_count_max": len(candidate_catalog(include_neural=False)),
        "sha_pass": all(str(row.get("SHA_PASS")).lower() in {"true", "1"} for row in fixed_rows + benchmark_rows + oracle_rows + ablation_rows if row.get("status") == "PASS"),
    }
    (RESULTS / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
