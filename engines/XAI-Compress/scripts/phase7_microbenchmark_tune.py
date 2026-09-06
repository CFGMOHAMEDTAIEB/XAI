from __future__ import annotations

import csv
import hashlib
import json
import os
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.codecs import available_registry
from xai_compress.hybrid.container_v2 import compress_hybrid_v2_file, decompress_hybrid_v2_file
from xai_compress.hybrid.profiles import label_measurements, load_profiles
from xai_compress.hybrid.selector_v2 import HybridSelectorV2

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "hybrid_v3"
MANIFEST = ROOT / "results" / "hybrid_v2" / "corpus_manifest.csv"
DATASET = ROOT / "results" / "hybrid_v2" / "selector_dataset.csv"

SIZES = [2 << 10, 4 << 10, 8 << 10, 16 << 10, 32 << 10]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_manifest() -> list[dict]:
    rows = list(csv.DictReader(MANIFEST.open(newline="", encoding="utf-8")))
    real = []
    for row in rows:
        if row.get("split") != "test" or row.get("origin") != "real":
            continue
        path = Path(row["source_path"])
        if path.is_file() and os.access(path, os.R_OK):
            real.append({**row, "path": path})
    return real


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    readable = read_manifest()
    selector_rows = list(csv.DictReader(DATASET.open(newline="", encoding="utf-8")))
    by_sample: dict[str, list[dict]] = defaultdict(list)
    for row in selector_rows:
        by_sample[row["sample_id"]].append(row)
    profiles = load_profiles()
    registry = available_registry()

    summary_rows = []
    for size in SIZES:
        regret_values = []
        latency_values = []
        compression_values = []
        decompression_values = []
        artifact_bytes = []
        route_counts = defaultdict(int)
        for sample in readable:
            original = sample["path"].read_bytes()
            selector = HybridSelectorV2(profile="balanced", registry=registry, microbench_bytes=size)
            start = time.perf_counter()
            selection = selector.select(original, extension=sample["path"].suffix, file_size=int(sample["original_bytes"]))
            latency_values.append((time.perf_counter() - start) * 1000.0)
            route_counts[selection.route] += 1

            ranking = label_measurements(by_sample[sample["source_id"]], "balanced", profiles)
            selected_score = next((row["profile_score"] for row in ranking if row["strategy_id"] == selection.strategy.strategy_id), ranking[0]["profile_score"])
            regret_values.append(float(ranking[0]["profile_score"]) - float(selected_score))

            with tempfile.TemporaryDirectory(prefix="phase7-", dir=RESULTS) as tmpdir:
                artifact = Path(tmpdir) / "candidate.xaic"
                restored = Path(tmpdir) / "candidate.out"
                start = time.perf_counter()
                info = compress_hybrid_v2_file(sample["path"], artifact, profile="balanced", microbench_bytes=size, overwrite=True)
                compression_ms = (time.perf_counter() - start) * 1000.0
                start = time.perf_counter()
                result = decompress_hybrid_v2_file(artifact, restored, overwrite=True)
                decompression_ms = (time.perf_counter() - start) * 1000.0
                if sha256_bytes(original) != sha256_bytes(restored.read_bytes()):
                    raise RuntimeError(f"roundtrip failure for {sample['source_id']} at {size}")
                compression_values.append(compression_ms)
                decompression_values.append(decompression_ms)
                artifact_bytes.append(artifact.stat().st_size)

        p95_regret = sorted(regret_values)[max(0, min(len(regret_values) - 1, int(len(regret_values) * 0.95)))] if regret_values else 0.0
        summary_rows.append({
            "microbench_bytes": size,
            "mean_regret": statistics.mean(regret_values) if regret_values else 0.0,
            "p95_regret": p95_regret,
            "mean_select_ms": statistics.mean(latency_values) if latency_values else 0.0,
            "median_select_ms": statistics.median(latency_values) if latency_values else 0.0,
            "mean_compression_ms": statistics.mean(compression_values) if compression_values else 0.0,
            "mean_decompression_ms": statistics.mean(decompression_values) if decompression_values else 0.0,
            "mean_artifact_bytes": statistics.mean(artifact_bytes) if artifact_bytes else 0.0,
            "route_counts": dict(sorted(route_counts.items())),
            "files_measured": len(readable),
        })

    JSON_PATH = RESULTS / "phase7_microbenchmark_tuning.json"
    JSON_PATH.write_text(json.dumps(summary_rows, indent=2), encoding="utf-8")
    best = min(summary_rows, key=lambda row: (row["mean_regret"], row["mean_select_ms"]))
    print(json.dumps({"chosen_size": best["microbench_bytes"], "summary": summary_rows}, indent=2))


if __name__ == "__main__":
    main()
