from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.codecs import available_registry, build_registry
from xai_compress.hybrid.selector_v2 import HybridSelectorV2

MANIFEST = ROOT / "results" / "hybrid_v2" / "corpus_manifest.csv"


def read_real_samples(limit: int | None = None) -> list[tuple[Path, bytes, int]]:
    rows = list(csv.DictReader(MANIFEST.open(newline="", encoding="utf-8")))
    samples: list[tuple[Path, bytes, int]] = []
    for row in rows:
        if row.get("split") != "test" or row.get("origin") != "real":
            continue
        path = Path(row["source_path"])
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        samples.append((path, data, int(row["original_bytes"])))
        if limit is not None and len(samples) >= limit:
            break
    return samples


def phase8_routing_cost(samples: list[tuple[Path, bytes, int]]) -> dict:
    registry = available_registry()
    summary = {}
    for mode in ("confidence", "top2", "top3"):
        latencies = []
        for path, data, size in samples:
            selector = HybridSelectorV2(profile="balanced", registry=registry, routing_mode=mode, microbench_bytes=4096)
            started = time.perf_counter()
            selector.select(data, extension=path.suffix, file_size=size)
            latencies.append((time.perf_counter() - started) * 1000.0)
        summary[mode] = {
            "mean_ms": round(statistics.mean(latencies), 3),
            "p95_ms": round(sorted(latencies)[min(len(latencies) - 1, int(len(latencies) * 0.95))], 3),
            "count": len(latencies),
        }
    return summary


def phase9_registry_cache() -> dict:
    t0 = time.perf_counter()
    for _ in range(200):
        build_registry()
    build_ms = (time.perf_counter() - t0) * 1000.0
    t1 = time.perf_counter()
    for _ in range(200):
        available_registry()
    avail_ms = (time.perf_counter() - t1) * 1000.0
    return {
        "build_registry_200_ms": round(build_ms, 3),
        "build_registry_mean_ms": round(build_ms / 200.0, 3),
        "available_registry_200_ms": round(avail_ms, 3),
        "available_registry_mean_ms": round(avail_ms / 200.0, 3),
    }


def phase10_small_text_fastpath() -> dict:
    registry = available_registry()
    selector = HybridSelectorV2(profile="balanced", registry=registry)
    payload = b"tiny text payload\n" * 12
    direct = selector.select(payload, extension=".txt", file_size=len(payload))
    return {
        "route": direct.route,
        "strategy": direct.strategy.strategy_id,
        "feature_scan_ms": round(direct.feature_scan_ms, 4),
        "microbenchmark_ms": round(direct.microbenchmark_ms, 4),
        "inference_ms": round(direct.inference_ms, 4),
        "direct_reason": direct.direct_reason,
    }


def main() -> None:
    samples = read_real_samples(limit=12)
    summary = {
        "phase8_routing_cost": phase8_routing_cost(samples),
        "phase9_registry_cache": phase9_registry_cache(),
        "phase10_small_text_fastpath": phase10_small_text_fastpath(),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
