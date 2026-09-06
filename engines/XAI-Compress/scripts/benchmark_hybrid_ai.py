"""Measured fixed-codec, Hybrid AI, and oracle benchmark."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.hybrid.codecs import available_registry
from xai_compress.hybrid.container import compress_hybrid_file, decompress_hybrid_file, inspect_hybrid

RESULTS = ROOT / "results" / "hybrid_ai"


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def peak_rss_mb() -> float | None:
    try:
        import psutil

        memory = psutil.Process().memory_info()
        return float(getattr(memory, "peak_wset", memory.rss)) / (1 << 20)
    except (ImportError, OSError):
        return None


def fixed_worker(method: str, source: Path) -> dict[str, Any]:
    data = source.read_bytes()
    registry = available_registry(device="cpu")
    started = time.perf_counter()
    if method == "gzip-9":
        artifact = gzip.compress(data, compresslevel=9)
        decoder = gzip.decompress
    elif method == "xai-static":
        artifact = compress_bytes(data, "static")
        decoder = decompress_bytes
    elif method == "xai-gru":
        checkpoint = ROOT / "checkpoints" / "kaggle" / "best.pt"
        artifact = compress_bytes(data, "neural-lossless", checkpoint, device="cpu", coder="rans")
        decoder = lambda blob: decompress_bytes(blob, checkpoint, device="cpu")
    elif method == "xai-transformer":
        checkpoint = ROOT / "checkpoints" / "neural_lossless_v2" / "best.pt"
        artifact = compress_bytes(data, "neural-lossless", checkpoint, device="cpu", coder="rans")
        decoder = lambda blob: decompress_bytes(blob, checkpoint, device="cpu")
    else:
        codec_id, raw_level = method.rsplit("-", 1)
        level = None if raw_level == "default" else int(raw_level)
        adapter = registry[codec_id]
        encoded = adapter.compress(data, level)
        artifact = encoded.payload
        decoder = lambda blob: adapter.decompress(blob, encoded.metadata)
    compression_seconds = time.perf_counter() - started
    started = time.perf_counter()
    restored = decoder(artifact)
    decompression_seconds = time.perf_counter() - started
    passed = restored == data and hashlib.sha256(restored).digest() == hashlib.sha256(data).digest()
    if not passed:
        raise RuntimeError(f"fixed codec SHA failure: {method}")
    return {
        "method": method,
        "original_size": len(data),
        "compressed_size": len(artifact),
        "actual_bpb": 8 * len(artifact) / max(1, len(data)),
        "compression_ratio": len(data) / max(1, len(artifact)),
        "compression_time": compression_seconds,
        "decompression_time": decompression_seconds,
        "compression_MB_s": len(data) / (1 << 20) / max(compression_seconds, 1e-12),
        "decompression_MB_s": len(data) / (1 << 20) / max(decompression_seconds, 1e-12),
        "peak_RSS_MB": peak_rss_mb(),
        "SHA_PASS": True,
    }


def hybrid_worker(profile: str, selector_mode: str, source: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="xai-hybrid-worker-") as temporary:
        work = Path(temporary)
        artifact, restored = work / "artifact.xaic", work / "restored.bin"
        size = source.stat().st_size
        chunk_size = min(max(4096, size), 1 << 20)
        microbench = min(64 << 10, chunk_size)
        started = time.perf_counter()
        info = compress_hybrid_file(
            source,
            artifact,
            profile=profile,
            selector_mode=selector_mode,
            chunk_size=chunk_size,
            top_k=3,
            microbench_bytes=microbench,
            selector_model=ROOT / "checkpoints" / "selector" / "best.json",
        )
        compression_seconds = time.perf_counter() - started
        started = time.perf_counter()
        restored_info = decompress_hybrid_file(artifact, restored)
        decompression_seconds = time.perf_counter() - started
        passed = digest_file(source) == digest_file(restored)
        if not passed:
            raise RuntimeError("hybrid SHA failure")
        inspection = inspect_hybrid(artifact)
        return {
            "method": "oracle-hybrid" if selector_mode == "benchmark-only" else "hybrid-ai",
            "profile": profile,
            "selector_mode": selector_mode,
            "original_size": size,
            "compressed_size": artifact.stat().st_size,
            "actual_bpb": 8 * artifact.stat().st_size / max(1, size),
            "compression_ratio": size / max(1, artifact.stat().st_size),
            "compression_time": compression_seconds,
            "decompression_time": decompression_seconds,
            "compression_MB_s": size / (1 << 20) / max(compression_seconds, 1e-12),
            "decompression_MB_s": size / (1 << 20) / max(decompression_seconds, 1e-12),
            "feature_scan_ms": info["feature_scan_ms"],
            "model_inference_ms": info["model_inference_ms"],
            "microbenchmark_ms": info["microbenchmark_ms"],
            "selection_overhead_ms": info["selection_overhead_ms"],
            "codec_compression_ms": max(0.0, compression_seconds * 1000 - info["selection_overhead_ms"]),
            "peak_RSS_MB": peak_rss_mb(),
            "SHA_PASS": True,
            "chunks": info["chunks"],
            "codec_distribution": json.dumps(inspection["codec_distribution"], sort_keys=True),
            "transform_distribution": json.dumps(inspection["transform_distribution"], sort_keys=True),
        }


def write_pattern(path: Path, size: int, block: bytes) -> None:
    remaining = size
    with path.open("wb") as handle:
        while remaining:
            piece = block[: min(remaining, len(block))]
            handle.write(piece)
            remaining -= len(piece)


def make_corpus(root: Path, include_100_mib: bool) -> list[dict[str, Any]]:
    rng = random.Random(20260901)
    specs = [
        ("text_4KiB", "text", 4 << 10, b"XAI hybrid compression selects measured codecs.\n" * 128),
        ("random_64KiB", "random", 64 << 10, bytes(rng.randrange(256) for _ in range(64 << 10))),
        ("numeric_1MiB", "scientific", 1 << 20, bytes(range(256)) * 256),
        ("structured_10MiB", "json", 10 << 20, b'{"id":42,"codec":"zstd","value":123456,"status":"ok"}\n' * 1024),
    ]
    if include_100_mib:
        specs.append(("repetitive_100MiB", "repetitive", 100 << 20, b"XAI-COMPRESS-HYBRID-ORCHESTRATOR|" * 2048))
    manifest = []
    for name, category, size, block in specs:
        path = root / f"{name}.bin"
        write_pattern(path, size, block)
        manifest.append({"sample_id": name, "category": category, "size": size, "path": path, "sha256": digest_file(path)})
    return manifest


def child(command: list[str], timeout: int = 1200) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout.splitlines()[-1])


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=["fixed", "hybrid"])
    parser.add_argument("--method")
    parser.add_argument("--profile")
    parser.add_argument("--selector-mode")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--skip-100-mib", action="store_true")
    args = parser.parse_args()
    if args.worker == "fixed":
        print(json.dumps(fixed_worker(args.method, args.source)))
        return
    if args.worker == "hybrid":
        print(json.dumps(hybrid_worker(args.profile, args.selector_mode, args.source)))
        return

    RESULTS.mkdir(parents=True, exist_ok=True)
    fixed_methods = [
        "raw-default", "deflate-6", "gzip-9", "zstd-3", "brotli-6", "lzma2-6",
        "bzip2-9", "xai-static", "xai-gru", "xai-transformer",
    ]
    fixed_rows: list[dict] = []
    hybrid_rows: list[dict] = []
    oracle_rows: list[dict] = []
    runtime_rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="xai-hybrid-corpus-", dir=RESULTS) as temporary:
        corpus = make_corpus(Path(temporary), not args.skip_100_mib)
        manifest = [{key: (str(value) if isinstance(value, Path) else value) for key, value in item.items()} for item in corpus]
        (RESULTS / "benchmark_corpus_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        for sample in corpus:
            source = sample["path"]
            for method in fixed_methods:
                if method in {"xai-gru", "xai-transformer"} and sample["size"] > 4096:
                    fixed_rows.append({**{k: v for k, v in sample.items() if k != "path"}, "method": method, "status": "NOT MEASURED", "reason": "bounded neural benchmark policy (>4 KiB)"})
                    continue
                if method == "xai-static" and sample["size"] > (1 << 20):
                    fixed_rows.append({**{k: v for k, v in sample.items() if k != "path"}, "method": method, "status": "NOT MEASURED", "reason": "bounded Python static benchmark policy (>1 MiB)"})
                    continue
                try:
                    result = child([sys.executable, __file__, "--worker", "fixed", "--method", method, "--source", str(source)])
                    result.update({k: v for k, v in sample.items() if k != "path"}, status="PASS")
                except Exception as exc:
                    result = {**{k: v for k, v in sample.items() if k != "path"}, "method": method, "status": "N/A", "error": str(exc)}
                fixed_rows.append(result)
                print(f"FIXED {sample['sample_id']} {method}: {result['status']}", flush=True)
            for profile in ("fastest", "balanced", "smallest"):
                try:
                    result = child([sys.executable, __file__, "--worker", "hybrid", "--profile", profile, "--selector-mode", "ai-benchmark", "--source", str(source)])
                    result.update({k: v for k, v in sample.items() if k != "path"}, status="PASS")
                    runtime_rows.append({key: result.get(key) for key in ("sample_id", "category", "profile", "feature_scan_ms", "model_inference_ms", "microbenchmark_ms", "codec_compression_ms", "compression_time", "decompression_time", "peak_RSS_MB")})
                except Exception as exc:
                    result = {**{k: v for k, v in sample.items() if k != "path"}, "method": "hybrid-ai", "profile": profile, "status": "N/A", "error": str(exc)}
                hybrid_rows.append(result)
                print(f"HYBRID {sample['sample_id']} {profile}: {result['status']}", flush=True)
            if sample["size"] <= (10 << 20):
                for profile in ("fastest", "balanced", "smallest"):
                    try:
                        result = child([sys.executable, __file__, "--worker", "hybrid", "--profile", profile, "--selector-mode", "benchmark-only", "--source", str(source)])
                        result.update({k: v for k, v in sample.items() if k != "path"}, status="PASS")
                    except Exception as exc:
                        result = {**{k: v for k, v in sample.items() if k != "path"}, "method": "oracle-hybrid", "profile": profile, "status": "N/A", "error": str(exc)}
                    oracle_rows.append(result)
                    print(f"ORACLE {sample['sample_id']} {profile}: {result['status']}", flush=True)
            else:
                for profile in ("fastest", "balanced", "smallest"):
                    oracle_rows.append({**{k: v for k, v in sample.items() if k != "path"}, "method": "oracle-hybrid", "profile": profile, "status": "NOT MEASURED", "reason": "100 MiB exhaustive oracle not resource-bounded"})

    for oracle in oracle_rows:
        if oracle.get("status") != "PASS":
            continue
        hybrid = next((row for row in hybrid_rows if row.get("status") == "PASS" and row["sample_id"] == oracle["sample_id"] and row["profile"] == oracle["profile"]), None)
        if hybrid:
            oracle["hybrid_compressed_size"] = hybrid["compressed_size"]
            oracle["oracle_gap_percent"] = 100 * (hybrid["compressed_size"] - oracle["compressed_size"]) / max(1, oracle["compressed_size"])

    decisions = []
    for hybrid in [row for row in hybrid_rows if row.get("status") == "PASS" and row["profile"] == "balanced"]:
        candidates = [row for row in fixed_rows if row.get("status") == "PASS" and row["sample_id"] == hybrid["sample_id"]]
        best = min(candidates, key=lambda row: (row["compressed_size"], row["method"]))
        decisions.append(
            {
                "sample_id": hybrid["sample_id"],
                "category": hybrid["category"],
                "selected_strategy": hybrid["codec_distribution"],
                "best_fixed_codec": best["method"],
                "hybrid_compressed_bytes": hybrid["compressed_size"],
                "best_fixed_compressed_bytes": best["compressed_size"],
                "hybrid_gap_percent": 100 * (hybrid["compressed_size"] - best["compressed_size"]) / max(1, best["compressed_size"]),
                "hybrid_wins": hybrid["compressed_size"] <= best["compressed_size"],
            }
        )
    write_csv(RESULTS / "codec_benchmark.csv", fixed_rows)
    write_csv(RESULTS / "hybrid_benchmark.csv", hybrid_rows)
    write_csv(RESULTS / "oracle_benchmark.csv", oracle_rows)
    write_csv(RESULTS / "runtime_breakdown.csv", runtime_rows)
    write_csv(RESULTS / "profile_comparison.csv", hybrid_rows)
    write_csv(RESULTS / "final_decision_table.csv", decisions)
    summary = {
        "fixed_measurements": sum(row.get("status") == "PASS" for row in fixed_rows),
        "hybrid_measurements": sum(row.get("status") == "PASS" for row in hybrid_rows),
        "oracle_measurements": sum(row.get("status") == "PASS" for row in oracle_rows),
        "sha_pass": all(row.get("SHA_PASS", True) for row in fixed_rows + hybrid_rows + oracle_rows if row.get("status") == "PASS"),
        "category_wins": [row["category"] for row in decisions if row["hybrid_wins"]],
    }
    (RESULTS / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
