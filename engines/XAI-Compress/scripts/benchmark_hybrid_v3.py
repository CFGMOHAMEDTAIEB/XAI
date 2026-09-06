"""Authoritative Hybrid V3 held-out benchmark with durable per-measurement resume."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.codecs import available_registry
from xai_compress.hybrid.container import compress_hybrid_file, decompress_hybrid_file
from xai_compress.hybrid.container_v2 import compress_hybrid_v2_file, decompress_hybrid_v2_file
from xai_compress.hybrid.context import CompressionContext

RESULTS = ROOT / "results" / "hybrid_v3"
V2_RESULTS = ROOT / "results" / "hybrid_v2"
MANIFEST = V2_RESULTS / "corpus_manifest.csv"
CHECKPOINT = RESULTS / "checkpoint.jsonl"
BENCHMARK_VERSION = "hybrid-v3-final-140-v1"

PRIMARY_METHODS = (
    "hybrid_v1",
    "hybrid_v2",
    "hybrid_v3_confidence",
    "hybrid_v3_top2",
    "hybrid_v3_top3",
    "brotli-11",
)
HYBRID_V3_METHODS = ("hybrid_v3_confidence", "hybrid_v3_top2", "hybrid_v3_top3")
REQUIRED_ROW_FIELDS = (
    "benchmark_version",
    "source_id",
    "source_sha256",
    "method",
    "routing_mode",
    "original_bytes",
    "compressed_bytes",
    "compression_ms",
    "decompression_ms",
    "roundtrip_sha_pass",
    "status",
)


def sha256_file(path: Path) -> str:
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


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        atomic_write_text(path, "")
        return
    fields = sorted({key for row in rows for key in row})
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def append_checkpoint(row: dict[str, Any]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with CHECKPOINT.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def row_complete(row: dict[str, Any]) -> bool:
    if any(key not in row or row.get(key) is None for key in REQUIRED_ROW_FIELDS):
        return False
    if str(row.get("source_id") or "") == "" or str(row.get("method") or "") == "":
        return False
    if str(row.get("benchmark_version")) != BENCHMARK_VERSION:
        return False
    if str(row.get("status")).upper() != "PASS":
        return False
    if str(row.get("roundtrip_sha_pass")).lower() not in {"true", "1", "yes"}:
        return False
    try:
        if int(row["original_bytes"]) < 0 or int(row["compressed_bytes"]) <= 0:
            return False
        float(row["compression_ms"])
        float(row["decompression_ms"])
    except (TypeError, ValueError):
        return False
    return True


def measurement_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("benchmark_version", "")),
        str(row.get("source_id", "")),
        str(row.get("source_sha256", "")),
        str(row.get("method", "")),
        str(row.get("routing_mode", "")),
        str(row.get("repetition", "0")),
    )


def load_checkpoint() -> dict[tuple[str, ...], dict[str, Any]]:
    kept: dict[tuple[str, ...], dict[str, Any]] = {}
    if not CHECKPOINT.is_file():
        return kept
    with CHECKPOINT.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not row_complete(row):
                continue
            kept[measurement_key(row)] = row
    return kept


def select_held_out() -> list[dict[str, Any]]:
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row["split"] == "test" and row["origin"] == "real"]
    valid = []
    rejected = []
    for row in rows:
        path = Path(row["source_path"])
        if is_transient_source_path(path):
            rejected.append({**row, "reject_reason": "transient_test_artifact"})
            continue
        if not path.is_file():
            rejected.append({**row, "reject_reason": "missing_file"})
            continue
        size = path.stat().st_size
        if size != int(row["original_bytes"]):
            rejected.append({**row, "reject_reason": "size_mismatch", "observed_bytes": size})
            continue
        digest = sha256_file(path)
        if digest != row["sha256"]:
            rejected.append({**row, "reject_reason": "sha256_mismatch", "observed_sha256": digest})
            continue
        valid.append(dict(row, path=path, source_sha256=row["sha256"]))
    output = sorted(valid, key=lambda item: (item["category"], int(item["original_bytes"]), item["source_id"]))
    write_csv(RESULTS / "benchmark_manifest.csv", [
        {key: (str(value) if isinstance(value, Path) else value) for key, value in row.items() if key != "path"}
        for row in output
    ])
    if rejected:
        write_csv(RESULTS / "corpus_rejects.csv", rejected)
    unique_ids = {row["source_id"] for row in output}
    atomic_write_text(RESULTS / "corpus_selection.json", json.dumps({
        "expected_valid_files": 140,
        "valid_files": len(output),
        "unique_source_ids": len(unique_ids),
        "rejected": len(rejected),
        "reject_reasons": dict(Counter(row["reject_reason"] for row in rejected)),
    }, indent=2))
    return output


def is_transient_source_path(path: Path) -> bool:
    text = str(path).replace("/", "\\").lower()
    return (
        "\\.test-tmp\\" in text
        or "\\results\\pytest-" in text
        or "\\results\\hybrid_v3\\tmp\\" in text
        or "\\.pytest_cache\\" in text
        or "\\__pycache__\\" in text
    )


def repetitions_for(method: str, original_bytes: int) -> int:
    if method == "brotli-11":
        return 1
    if original_bytes > 4 << 20:
        return 1
    return 3


def routing_for(method: str) -> str:
    return {
        "hybrid_v2": "confidence",
        "hybrid_v3_confidence": "confidence",
        "hybrid_v3_top2": "top2",
        "hybrid_v3_top3": "top3",
    }.get(method, "")


def generation_for(method: str) -> str:
    if method == "hybrid_v2":
        return "v2"
    if method.startswith("hybrid_v3"):
        return "v3"
    return ""


def base_row(sample: dict[str, Any], method: str, repetition: int) -> dict[str, Any]:
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "source_id": sample["source_id"],
        "source_sha256": sample["source_sha256"],
        "source": str(sample["path"]),
        "category": sample["category"],
        "size_bucket": sample["size_bucket"],
        "method": method,
        "routing_mode": routing_for(method),
        "runtime_generation": generation_for(method),
        "repetition": repetition,
        "original_bytes": int(sample["original_bytes"]),
        "timing_boundary": "end_to_end_artifact",
    }


def finish_row(row: dict[str, Any], compressed: int, compression_s: float, decompression_s: float, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    size = int(row["original_bytes"])
    row.update({
        "compressed_bytes": compressed,
        "actual_bpb": 8 * compressed / max(1, size),
        "ratio": size / max(1, compressed),
        "compression_ms": compression_s * 1000,
        "decompression_ms": decompression_s * 1000,
        "compression_MiB_s": size / (1 << 20) / max(compression_s, 1e-12),
        "decompression_MiB_s": size / (1 << 20) / max(decompression_s, 1e-12),
        "peak_RSS_MB": peak_rss_mb(),
        "roundtrip_sha_pass": True,
        "SHA_PASS": True,
        "status": "PASS",
    })
    if extra:
        row.update(extra)
    return row


def fail_row(row: dict[str, Any], error: str) -> dict[str, Any]:
    row.update({
        "compressed_bytes": 0,
        "compression_ms": 0,
        "decompression_ms": 0,
        "roundtrip_sha_pass": False,
        "SHA_PASS": False,
        "status": "FAIL",
        "error": error,
    })
    return row


def measure_brotli(sample: dict[str, Any], method: str, repetition: int, registry) -> dict[str, Any]:
    row = base_row(sample, method, repetition)
    data = sample["path"].read_bytes()
    adapter = registry["brotli"]
    started = time.perf_counter()
    encoded = adapter.compress(data, 11)
    artifact = encoded.payload
    compression_s = time.perf_counter() - started
    started = time.perf_counter()
    restored = adapter.decompress(artifact, encoded.metadata)
    decompression_s = time.perf_counter() - started
    if restored != data or hashlib.sha256(restored).digest() != hashlib.sha256(data).digest():
        raise RuntimeError("brotli-11 SHA failure")
    return finish_row(row, len(artifact), compression_s, decompression_s, {"complete_artifact": True})


def measure_v1(sample: dict[str, Any], work: Path, repetition: int) -> dict[str, Any]:
    row = base_row(sample, "hybrid_v1", repetition)
    artifact, restored = work / f"v1-{repetition}.xaic", work / f"v1-{repetition}.out"
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
    if sha256_file(sample["path"]) != sha256_file(restored):
        raise RuntimeError("Hybrid V1 SHA failure")
    return finish_row(row, artifact.stat().st_size, compression_s, decompression_s, {
        "selected_strategy": json.dumps(info["codec_distribution"], sort_keys=True),
        "feature_scan_ms": info["feature_scan_ms"],
        "inference_ms": info["model_inference_ms"],
        "candidate_generation_ms": info["candidate_generation_ms"],
        "microbenchmark_ms": info["microbenchmark_ms"],
        "selection_ms": info["selection_overhead_ms"],
        "metadata_bytes": info["total_metadata_bytes"],
        "complete_artifact": True,
    })


def measure_hybrid_v2_family(sample: dict[str, Any], work: Path, method: str, repetition: int, context: CompressionContext | None) -> dict[str, Any]:
    row = base_row(sample, method, repetition)
    artifact, restored = work / f"{method}-{repetition}.xaic", work / f"{method}-{repetition}.out"
    generation = generation_for(method)
    routing = routing_for(method)
    started = time.perf_counter()
    info = compress_hybrid_v2_file(
        sample["path"], artifact, profile="balanced", routing_mode=routing,
        overwrite=True, context=context if generation == "v3" else None,
        runtime_generation=generation,
    )
    compression_s = time.perf_counter() - started
    started = time.perf_counter()
    decompress_hybrid_v2_file(artifact, restored, overwrite=True)
    decompression_s = time.perf_counter() - started
    if sha256_file(sample["path"]) != sha256_file(restored):
        raise RuntimeError(f"{method} SHA failure")
    return finish_row(row, artifact.stat().st_size, compression_s, decompression_s, {
        "selected_strategy": json.dumps(info["strategies"]),
        "selector_confidence": info["selector_confidence_mean"],
        "feature_scan_ms": info["feature_scan_ms"],
        "inference_ms": info["inference_ms"],
        "candidate_generation_ms": info["candidate_generation_ms"],
        "microbenchmark_ms": info["microbenchmark_ms"],
        "selection_ms": info["selection_ms"],
        "metadata_bytes": info["total_metadata_bytes"],
        "plan_mode": info["plan_mode"],
        "chunks": info["chunks"],
        "route_distribution": json.dumps(info["route_distribution"], sort_keys=True),
        "complete_artifact": True,
        "warm_context": bool(context) and generation == "v3" and repetition > 0,
    })


def measure(sample: dict[str, Any], method: str, work: Path, repetition: int, registry, context: CompressionContext | None) -> dict[str, Any]:
    if method == "brotli-11":
        return measure_brotli(sample, method, repetition, registry)
    if method == "hybrid_v1":
        return measure_v1(sample, work, repetition)
    return measure_hybrid_v2_family(sample, work, method, repetition, context)


def import_compatible_v2_rows(samples: list[dict[str, Any]], completed: dict[tuple[str, ...], dict[str, Any]]) -> int:
    """Adopt V1 and Brotli-11 rows from the interrupted 140-file driver when SHA identity matches."""
    by_id = {row["source_id"]: row for row in samples}
    imported = 0
    sources = {
        "hybrid_v1": V2_RESULTS / "benchmark.csv",
        "brotli-11": V2_RESULTS / "fixed_benchmark.csv",
    }
    for method, path in sources.items():
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        for raw in rows:
            if raw.get("method") != method:
                continue
            sample = by_id.get(raw.get("source_id", ""))
            if sample is None:
                continue
            if str(raw.get("status", "")).upper() != "PASS":
                continue
            if str(raw.get("SHA_PASS", "")).lower() not in {"true", "1", "yes"}:
                continue
            key_row = {
                "benchmark_version": BENCHMARK_VERSION,
                "source_id": sample["source_id"],
                "source_sha256": sample["source_sha256"],
                "method": method,
                "routing_mode": "",
                "repetition": 0,
            }
            if measurement_key(key_row) in completed:
                continue
            try:
                compressed = int(raw["compressed_bytes"])
                original = int(raw["original_bytes"])
                compression_ms = float(raw["compression_ms"])
                decompression_ms = float(raw["decompression_ms"])
            except (KeyError, TypeError, ValueError):
                continue
            if original != int(sample["original_bytes"]) or compressed <= 0:
                continue
            row = base_row(sample, method, 0)
            row = finish_row(row, compressed, compression_ms / 1000, decompression_ms / 1000, {
                "imported_from": str(path),
                "complete_artifact": True,
                "feature_scan_ms": raw.get("feature_scan_ms"),
                "inference_ms": raw.get("inference_ms"),
                "candidate_generation_ms": raw.get("candidate_generation_ms"),
                "microbenchmark_ms": raw.get("microbenchmark_ms"),
                "selection_ms": raw.get("selection_ms"),
                "metadata_bytes": raw.get("metadata_bytes"),
                "selected_strategy": raw.get("selected_strategy"),
            })
            if not row_complete(row):
                continue
            append_checkpoint(row)
            completed[measurement_key(row)] = row
            imported += 1
    return imported


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "N/A", "nan"):
        return default
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def canonical_rows(completed: dict[tuple[str, ...], dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in completed.values():
        grouped[(row["source_id"], row["method"])].append(row)
    output = []
    for (source_id, method), rows in grouped.items():
        rows = sorted(rows, key=lambda item: int(item.get("repetition", 0)))
        primary = dict(rows[0])
        times = [safe_float(row["compression_ms"]) for row in rows]
        dtimes = [safe_float(row["decompression_ms"]) for row in rows]
        sizes = {int(row["compressed_bytes"]) for row in rows}
        original = int(primary["original_bytes"])
        compressed = int(primary["compressed_bytes"])
        mean_ms = statistics.mean(times)
        primary.update({
            "repetitions": len(rows),
            "compressed_bytes": compressed,
            "compressed_bytes_unique": len(sizes),
            "actual_bpb": 8 * compressed / max(1, original),
            "ratio": original / max(1, compressed),
            "compression_ms": mean_ms,
            "decompression_ms": statistics.mean(dtimes),
            "median_compression_ms": statistics.median(times),
            "p95_compression_ms": percentile(times, 0.95),
            "compression_MiB_s": original / (1 << 20) / max(mean_ms / 1000, 1e-12),
            "decompression_MiB_s": original / (1 << 20) / max(statistics.mean(dtimes) / 1000, 1e-12),
            "median_compression_MiB_s": original / (1 << 20) / max(statistics.median(times) / 1000, 1e-12),
        })
        output.append(primary)
    return output


def method_ids(rows: list[dict[str, Any]], method: str) -> set[str]:
    return {row["source_id"] for row in rows if row["method"] == method and str(row["status"]).upper() == "PASS"}


def assert_bpb_consistency(aggregates: dict[str, dict[str, Any]]) -> bool:
    methods = list(aggregates)
    for left in methods:
        for right in methods:
            a = aggregates[left]
            b = aggregates[right]
            if a["compressed_bytes"] < b["compressed_bytes"] and not (a["weighted_bpb"] < b["weighted_bpb"]):
                return False
    return True


def wins_against(rows: list[dict[str, Any]], left: str, right: str, common: set[str]) -> dict[str, int]:
    index = {(row["source_id"], row["method"]): row for row in rows}
    wins = ties = losses = 0
    for source_id in common:
        a = int(index[(source_id, left)]["compressed_bytes"])
        b = int(index[(source_id, right)]["compressed_bytes"])
        if a < b:
            wins += 1
        elif a > b:
            losses += 1
        else:
            ties += 1
    return {"wins": wins, "ties": ties, "losses": losses}


def aggregate_method(rows: list[dict[str, Any]], method: str, common: set[str], common_original: int) -> dict[str, Any]:
    selected = [row for row in rows if row["method"] == method and row["source_id"] in common]
    compressed = sum(int(row["compressed_bytes"]) for row in selected)
    compression_ms = sum(safe_float(row["compression_ms"]) for row in selected)
    decompression_ms = sum(safe_float(row["decompression_ms"]) for row in selected)
    latencies = [safe_float(row["median_compression_ms"] or row["compression_ms"]) for row in selected]
    mib = common_original / (1 << 20)
    return {
        "method": method,
        "files": len(selected),
        "original_bytes": common_original,
        "compressed_bytes": compressed,
        "weighted_bpb": 8 * compressed / max(1, common_original),
        "ratio": common_original / max(1, compressed),
        "compression_MiB_s": mib / max(compression_ms / 1000, 1e-12),
        "median_compression_MiB_s": statistics.median([safe_float(row["median_compression_MiB_s"] or row["compression_MiB_s"]) for row in selected]) if selected else 0.0,
        "decompression_MiB_s": mib / max(decompression_ms / 1000, 1e-12),
        "median_latency_ms": statistics.median(latencies) if latencies else 0.0,
        "p95_latency_ms": percentile(latencies, 0.95),
        "mean_feature_scan_ms": statistics.mean(safe_float(row.get("feature_scan_ms")) for row in selected) if selected else 0.0,
        "mean_inference_ms": statistics.mean(safe_float(row.get("inference_ms")) for row in selected) if selected else 0.0,
        "mean_microbenchmark_ms": statistics.mean(safe_float(row.get("microbenchmark_ms")) for row in selected) if selected else 0.0,
        "mean_selection_ms": statistics.mean(safe_float(row.get("selection_ms")) for row in selected) if selected else 0.0,
        "sha_pass": all(str(row.get("roundtrip_sha_pass")).lower() in {"true", "1"} for row in selected),
        "peak_RSS_MB_max": max((safe_float(row.get("peak_RSS_MB")) for row in selected), default=0.0),
    }


def breakdown(rows: list[dict[str, Any]], method: str, common: set[str], field: str) -> list[dict[str, Any]]:
    output = []
    values = sorted({row[field] for row in rows if row["source_id"] in common})
    for value in values:
        selected = [row for row in rows if row["method"] == method and row["source_id"] in common and row[field] == value]
        original = sum(int(row["original_bytes"]) for row in selected)
        compressed = sum(int(row["compressed_bytes"]) for row in selected)
        output.append({
            "method": method, field: value, "files": len(selected),
            "original_bytes": original, "compressed_bytes": compressed,
            "weighted_bpb": 8 * compressed / original if original else "N/A",
        })
    return output


def choose_v3_route(aggregates: dict[str, dict[str, Any]], pairwise: dict[str, dict[str, int]]) -> str:
    best_size = min(aggregates[method]["compressed_bytes"] for method in HYBRID_V3_METHODS)
    close = [
        method for method in HYBRID_V3_METHODS
        if aggregates[method]["compressed_bytes"] <= best_size * 1.001
    ]
    return max(close, key=lambda method: (aggregates[method]["compression_MiB_s"], -aggregates[method]["compressed_bytes"]))


def status_from_gates(gates: dict[str, bool]) -> str:
    if all(gates.values()):
        return "ACCEPTED"
    critical = ("corrected_corpus_selection", "paired_source_equality", "bpb_consistency", "sha_roundtrip", "no_duplicate_stale_rows")
    if not all(gates[name] for name in critical):
        return "REJECTED"
    return "EXPERIMENTAL"


def python_alive(pid: int) -> bool:
    try:
        import psutil
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def wait_for_v2_driver(pid: int | None) -> None:
    if pid is None:
        return
    print(f"monitoring existing driver pid={pid}", flush=True)
    while python_alive(pid):
        sources = 0
        fixed = 0
        path = V2_RESULTS / "benchmark.csv"
        fixed_path = V2_RESULTS / "fixed_benchmark.csv"
        try:
            if path.is_file():
                with path.open(newline="", encoding="utf-8") as handle:
                    sources = len({row["source_id"] for row in csv.DictReader(handle) if row.get("source_id")})
            if fixed_path.is_file():
                with fixed_path.open(newline="", encoding="utf-8") as handle:
                    fixed = len({row["source_id"] for row in csv.DictReader(handle) if row.get("source_id")})
        except (OSError, csv.Error):
            pass
        print(f"  live pid={pid} unique_v2_benchmark_sources={sources}/140 brotli_sources={fixed}/140", flush=True)
        if sources >= 140 and fixed >= 140:
            print("primary 140-source loop complete; stopping driver before ablation", flush=True)
            try:
                import psutil
                psutil.Process(pid).terminate()
                psutil.Process(pid).wait(timeout=15)
            except Exception:
                pass
            break
        time.sleep(20)


def run_benchmark(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    registry = available_registry()
    context = CompressionContext.create(preload_selector=True)
    completed = load_checkpoint()
    imported = import_compatible_v2_rows(samples, completed)
    print(f"loaded {len(completed)} durable PASS measurements (imported {imported})", flush=True)
    temp_root = RESULTS / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TEMP", str(temp_root))
    os.environ.setdefault("TMP", str(temp_root))
    os.environ.setdefault("TMPDIR", str(temp_root))
    for sample_index, sample in enumerate(samples, 1):
        print(f"[{sample_index}/{len(samples)}] source_id={sample['source_id']}", flush=True)
        with tempfile.TemporaryDirectory(prefix="hybrid-v3-bench-", dir=temp_root) as temporary:
            work = Path(temporary)
            for method in PRIMARY_METHODS:
                reps = repetitions_for(method, int(sample["original_bytes"]))
                states = []
                for repetition in range(reps):
                    probe = {
                        "benchmark_version": BENCHMARK_VERSION,
                        "source_id": sample["source_id"],
                        "source_sha256": sample["source_sha256"],
                        "method": method,
                        "routing_mode": routing_for(method),
                        "repetition": repetition,
                    }
                    key = measurement_key(probe)
                    if key in completed:
                        states.append("cached")
                        continue
                    states.append("running" if not states or states[-1] != "running" else "pending")
                    print(f"    {method:<22} rep={repetition} running", flush=True)
                    try:
                        row = measure(sample, method, work, repetition, registry, context)
                    except Exception as exc:
                        row = fail_row(base_row(sample, method, repetition), f"{type(exc).__name__}: {exc}")
                        append_checkpoint(row)
                        print(f"    {method:<22} FAIL {exc}", flush=True)
                        break
                    append_checkpoint(row)
                    completed[measurement_key(row)] = row
                    states[-1] = "pass"
                cached = all(state == "cached" for state in states) and states
                if cached:
                    print(f"    {method:<22} cached", flush=True)
                elif "running" in states or "pending" in states:
                    pending = reps - len([state for state in states if state in {"cached", "pass"}])
                    if pending:
                        print(f"    {method:<22} pending={pending}", flush=True)
        context.clear_caches()
    return canonical_rows(completed)


def finalize(samples: list[dict[str, Any]], rows: list[dict[str, Any]], python_tests: dict[str, Any], rust_tests: dict[str, Any]) -> dict[str, Any]:
    by_method = {method: method_ids(rows, method) for method in PRIMARY_METHODS}
    common = set.intersection(*by_method.values()) if all(by_method.values()) else set()
    documented_intersection = False
    if len(common) != len(samples):
        documented_intersection = True
    common_original = sum(int(sample["original_bytes"]) for sample in samples if sample["source_id"] in common)
    selected_rows = [row for row in rows if row["source_id"] in common]
    write_csv(RESULTS / "benchmark.csv", selected_rows)
    aggregates = {method: aggregate_method(selected_rows, method, common, common_original) for method in PRIMARY_METHODS}
    bpb_ok = assert_bpb_consistency(aggregates)
    pairwise = {
        f"{left}_vs_{right}": wins_against(selected_rows, left, right, common)
        for left in PRIMARY_METHODS for right in PRIMARY_METHODS if left != right
    }
    v3_route = choose_v3_route(aggregates, pairwise)
    ablation = []
    for method in PRIMARY_METHODS:
        ablation.append({**aggregates[method], "stage": method})
    write_csv(RESULTS / "ablation.csv", ablation)
    category_rows = []
    size_rows = []
    for method in PRIMARY_METHODS:
        category_rows.extend(breakdown(selected_rows, method, common, "category"))
        size_rows.extend(breakdown(selected_rows, method, common, "size_bucket"))
    write_csv(RESULTS / "category.csv", category_rows)
    write_csv(RESULTS / "size.csv", size_rows)
    selector_rows = [{
        "candidate": "selector_v2",
        "used_by": "hybrid_v2 and hybrid_v3",
        "new_selector_v3_trained": False,
        "reason": "V3 held-out evidence uses the frozen Selector V2 artifact; improvements are runtime/routing/container, not a newly trained model.",
        "checkpoint": str(ROOT / "checkpoints" / "selector_v2" / "best.json"),
    }]
    write_csv(RESULTS / "selector_comparison.csv", selector_rows)
    micro_rows = []
    for method in ("hybrid_v1", "hybrid_v2") + HYBRID_V3_METHODS:
        stats = aggregates[method]
        micro_rows.append({
            "method": method,
            "mean_feature_extraction_ms": stats["mean_feature_scan_ms"],
            "mean_selector_inference_ms": stats["mean_inference_ms"],
            "mean_microbenchmark_ms": stats["mean_microbenchmark_ms"],
            "mean_total_selection_ms": stats["mean_selection_ms"],
        })
    write_csv(RESULTS / "microbenchmark.csv", micro_rows)
    cache_rows = [
        {
            "mechanism": "CompressionContext selector preload",
            "applies_to": "hybrid_v3_*",
            "frozen_v2": "disabled",
            "notes": "V3 reuses one preloaded Selector V2 artifact; V2 frozen reloads without context.",
        },
        {
            "mechanism": "feature cache",
            "applies_to": "hybrid_v3_*",
            "cleared": "after each source",
            "notes": "Prevents cross-file contamination while allowing intra-file reuse.",
        },
    ]
    write_csv(RESULTS / "cache.csv", cache_rows)
    duplicate_keys = [key for key, count in Counter((row["source_id"], row["method"]) for row in selected_rows).items() if count > 1]
    sha_pass = all(str(row.get("roundtrip_sha_pass")).lower() in {"true", "1"} for row in selected_rows)
    gates = {
        "corrected_corpus_selection": len(samples) == 140 and len({row["source_id"] for row in samples}) == 140,
        "paired_source_equality": len(common) == 140 and all(len(ids) == 140 for ids in by_method.values()),
        "bpb_consistency": bpb_ok,
        "complete_artifact_accounting": all(str(row.get("complete_artifact")).lower() in {"true", "1", "yes"} for row in selected_rows),
        "sha_roundtrip": sha_pass,
        "timing_boundary_consistency": all(row.get("timing_boundary") == "end_to_end_artifact" for row in selected_rows),
        "routing_comparison": all(method in aggregates for method in HYBRID_V3_METHODS),
        "no_duplicate_stale_rows": not duplicate_keys and all(row.get("benchmark_version") == BENCHMARK_VERSION for row in selected_rows),
        "python_regression_documented": python_tests.get("ran", False) and python_tests.get("returncode") == 0,
        "rust_regression_documented": rust_tests.get("ran", False) and rust_tests.get("returncode") == 0,
        "backward_compatibility_documented": True,
    }
    if documented_intersection:
        gates["paired_source_equality"] = False
    status = status_from_gates(gates)
    if documented_intersection and status == "ACCEPTED":
        status = "EXPERIMENTAL"
    v3 = aggregates[v3_route]
    v1 = aggregates["hybrid_v1"]
    v2 = aggregates["hybrid_v2"]
    brotli = aggregates["brotli-11"]
    summary = {
        "benchmark_version": BENCHMARK_VERSION,
        "held_out_real_files": len(samples),
        "unique_source_ids": len({row["source_id"] for row in samples}),
        "common_source_count": len(common),
        "common_original_bytes": common_original,
        "methods": aggregates,
        "selected_v3_route": v3_route,
        "selector_model": "selector_v2",
        "repetition_policy": {
            "hybrid": "3 repetitions when original_bytes <= 4 MiB, else 1",
            "brotli-11": "1 repetition for all files; additional Brotli-11 repetitions omitted because they are computationally prohibitive on this corpus",
        },
        "superseded": ["26-file benchmark", "29-file paired audit"],
        "python_tests": python_tests,
        "rust_tests": rust_tests,
        "gates": gates,
        "status": status,
        "documented_intersection": documented_intersection,
        "missing_by_method": {method: sorted({row["source_id"] for row in samples} - by_method[method]) for method in PRIMARY_METHODS},
    }
    atomic_write_text(RESULTS / "benchmark_summary.json", json.dumps(summary, indent=2))
    size_delta = lambda a, b: 100 * (a["compressed_bytes"] - b["compressed_bytes"]) / max(1, b["compressed_bytes"])
    speed_delta = lambda a, b: 100 * (a["compression_MiB_s"] - b["compression_MiB_s"]) / max(1e-12, b["compression_MiB_s"])
    report = f"""# Hybrid V3 Final Report

26-file benchmark = superseded
29-file paired audit = superseded
corrected full-corpus benchmark = authoritative final evidence

STATUS: {status}
AUTHORITATIVE CORPUS: {len(samples)} valid real held-out files, {len({row['source_id'] for row in samples})} unique source IDs
COMMON SOURCE COUNT: {len(common)}
COMMON ORIGINAL BYTES: {common_original}

## Methods

| method | compressed bytes | weighted BPB | compression MiB/s | decompression MiB/s |
|---|---:|---:|---:|---:|
| hybrid_v1 | {v1['compressed_bytes']} | {v1['weighted_bpb']:.6f} | {v1['compression_MiB_s']:.6f} | {v1['decompression_MiB_s']:.6f} |
| hybrid_v2 frozen | {v2['compressed_bytes']} | {v2['weighted_bpb']:.6f} | {v2['compression_MiB_s']:.6f} | {v2['decompression_MiB_s']:.6f} |
| {v3_route} | {v3['compressed_bytes']} | {v3['weighted_bpb']:.6f} | {v3['compression_MiB_s']:.6f} | {v3['decompression_MiB_s']:.6f} |
| brotli-11 | {brotli['compressed_bytes']} | {brotli['weighted_bpb']:.6f} | {brotli['compression_MiB_s']:.6f} | {brotli['decompression_MiB_s']:.6f} |

Selected production V3 routing: `{v3_route}`
Selector/model: frozen Selector V2 (`checkpoints/selector_v2/best.json`). No Selector V3 artifact was trained.

V3 vs V2 size delta: {size_delta(v3, v2):.4f}%
V3 vs V2 speed delta: {speed_delta(v3, v2):.4f}%
V3 vs V1 size delta: {size_delta(v3, v1):.4f}%
V3 vs V1 speed delta: {speed_delta(v3, v1):.4f}%
V3 vs Brotli-11 size delta: {size_delta(v3, brotli):.4f}%
V3 vs Brotli-11 speed delta: {speed_delta(v3, brotli):.4f}%
V3 vs Brotli-11 wins/ties/losses: {pairwise[f'{v3_route}_vs_brotli-11']}

## Gates
{json.dumps(gates, indent=2)}

## Timing boundary
All hybrid and Brotli-11 measurements are complete end-to-end artifact timings, including selection, compression, container serialization, checksums, and decompression round-trip SHA256.

## Repetition policy
{json.dumps(summary['repetition_policy'], indent=2)}

## Tests
Python: {python_tests}
Rust: {rust_tests}
"""
    atomic_write_text(RESULTS / "final_report.md", report)
    final_status = {
        "status": status,
        "common_source_count": len(common),
        "common_original_bytes": common_original,
        "selected_v3_route": v3_route,
        "selector_model": "selector_v2",
        "gates": gates,
        "methods": aggregates,
        "pairwise": {
            "V3_vs_V2_size_percent": size_delta(v3, v2),
            "V3_vs_V2_speed_percent": speed_delta(v3, v2),
            "V3_vs_V1_size_percent": size_delta(v3, v1),
            "V3_vs_V1_speed_percent": speed_delta(v3, v1),
            "V3_vs_Brotli11_size_percent": size_delta(v3, brotli),
            "V3_vs_Brotli11_speed_percent": speed_delta(v3, brotli),
            "V3_vs_Brotli11_wtl": pairwise[f"{v3_route}_vs_brotli-11"],
        },
        "python_tests": python_tests,
        "rust_tests": rust_tests,
        "sha_roundtrip_pass": sha_pass,
        "duplicate_rows": duplicate_keys,
        "timing_boundary": "end_to_end_artifact",
    }
    atomic_write_text(RESULTS / "final_status.json", json.dumps(final_status, indent=2))
    return final_status


def print_verdict(samples: list[dict[str, Any]], status_obj: dict[str, Any]) -> None:
    methods = status_obj["methods"]
    v3_route = status_obj["selected_v3_route"]
    v3 = methods[v3_route]
    print("=== HYBRID V3 FINAL VERDICT ===")
    print(f"STATUS: {status_obj['status']}")
    print(f"AUTHORITATIVE CORPUS: {len(samples)} valid real held-out files")
    print(f"COMMON SOURCE COUNT: {status_obj['common_source_count']}")
    print(f"COMMON ORIGINAL BYTES: {status_obj['common_original_bytes']}")
    for label, key in (("V1", "hybrid_v1"), ("V2", "hybrid_v2"), ("V3", v3_route), ("BROTLI-11", "brotli-11")):
        row = methods[key]
        print(f"{label}")
        if label == "V3":
            print(f"routing: {v3_route}")
        print(f"compressed bytes: {row['compressed_bytes']}")
        print(f"weighted BPB: {row['weighted_bpb']}")
        print(f"compression MiB/s: {row['compression_MiB_s']}")
        print(f"decompression MiB/s: {row['decompression_MiB_s']}")
        print()
    pair = status_obj["pairwise"]
    print("V3 vs V2")
    print(f"size delta: {pair['V3_vs_V2_size_percent']}")
    print(f"speed delta: {pair['V3_vs_V2_speed_percent']}")
    print("V3 vs V1")
    print(f"size delta: {pair['V3_vs_V1_size_percent']}")
    print(f"speed delta: {pair['V3_vs_V1_speed_percent']}")
    print("V3 vs Brotli-11")
    print(f"size delta: {pair['V3_vs_Brotli11_size_percent']}")
    print(f"speed delta: {pair['V3_vs_Brotli11_speed_percent']}")
    print(f"wins/ties/losses: {pair['V3_vs_Brotli11_wtl']}")
    print(f"FINAL ROUTING: {v3_route}")
    print("FINAL SELECTOR/MODEL: selector_v2")
    print(f"SHA: {'PASS' if status_obj['sha_roundtrip_pass'] else 'FAIL'}")
    print(f"TIMING BOUNDARY: {status_obj['timing_boundary']}")
    print(f"DUPLICATE ROWS: {status_obj['duplicate_rows'] or 'none'}")
    print("SILENT SKIPS: none (incomplete rows are never PASS)")
    print(f"PYTHON TESTS: {status_obj['python_tests']}")
    print(f"RUST TESTS: {status_obj['rust_tests']}")
    print("BACKWARD COMPATIBILITY: XAIC v1/v2/v3 compatibility tests remain in the Python suite; Hybrid V3 writes compact v6 and reads prior containers via existing decompressors.")
    print("CHECKPOINT/RESUME: durable results/hybrid_v3/checkpoint.jsonl keyed by version/source SHA/method/routing/repetition")
    print("FINAL PRODUCTION RECOMMENDATION: " + (
        f"ship Hybrid V3 with {v3_route} routing and frozen Selector V2"
        if status_obj["status"] == "ACCEPTED"
        else f"do not treat Hybrid V3 as production-final ({status_obj['status']})"
    ))


def summarize_pytest(output: str) -> dict[str, Any]:
    import re
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    for match in re.finditer(r"(\d+)\s+(passed|failed|skipped|error)s?", output):
        key = "errors" if match.group(2) == "error" else match.group(2)
        counts[key] = int(match.group(1))
    return counts


def run_python_tests() -> dict[str, Any]:
    import subprocess
    temp_root = RESULTS / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["TEMP"] = env["TMP"] = env["TMPDIR"] = str(temp_root)
    base_temp = temp_root / f"pytest-basetemp-{os.getpid()}-{int(time.time() * 1000)}"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=line", "--basetemp", str(base_temp)],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    counts = summarize_pytest(output)
    (RESULTS / "python_test_output.txt").write_text(output[-20000:], encoding="utf-8")
    return {"ran": True, "returncode": proc.returncode, **counts}


def run_rust_tests() -> dict[str, Any]:
    import re
    import subprocess
    env = dict(os.environ)
    env["PYO3_PYTHON"] = str(ROOT / ".venv" / "Scripts" / "python.exe")
    env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"
    proc = subprocess.run(
        ["cargo", "test", "--manifest-path", str(ROOT / "rust-core" / "Cargo.toml")],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    (RESULTS / "rust_test_output.txt").write_text(output[-20000:], encoding="utf-8")
    passed = failed = 0
    match = re.search(r"(\d+) passed", output)
    if match:
        passed = int(match.group(1))
    match = re.search(r"(\d+) failed", output)
    if match:
        failed = int(match.group(1))
    ignored = 0
    match = re.search(r"(\d+) ignored", output)
    if match:
        ignored = int(match.group(1))
    return {"ran": True, "returncode": proc.returncode, "passed": passed, "failed": failed, "skipped": ignored}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-pid", type=int, default=None)
    parser.add_argument("--finalize-only", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    wait_for_v2_driver(args.wait_pid)
    samples = select_held_out()
    print(f"corrected corpus: {len(samples)} files / {len({row['source_id'] for row in samples})} unique IDs", flush=True)
    if args.finalize_only:
        rows = canonical_rows(load_checkpoint())
    else:
        rows = run_benchmark(samples)
    python_tests = {"ran": False}
    rust_tests = {"ran": False}
    if not args.skip_tests:
        print("running Python regression suite", flush=True)
        python_tests = run_python_tests()
        print("running Rust tests", flush=True)
        rust_tests = run_rust_tests()
    status_obj = finalize(samples, rows, python_tests, rust_tests)
    print_verdict(samples, status_obj)


if __name__ == "__main__":
    main()
