"""Measure Hybrid V1 stage latency and exact XAIC v5 byte overhead."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_hybrid_ai import make_corpus
from xai_compress.hybrid.container import compress_hybrid_file, decompress_hybrid_file

RESULTS = ROOT / "results" / "hybrid_v2"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="hybrid-v2-profile-", dir=RESULTS) as temporary:
        root = Path(temporary)
        for source in make_corpus(root, include_100_mib=True):
            path = source["path"]
            artifact = root / f"{source['sample_id']}.v5.xaic"
            restored = root / f"{source['sample_id']}.restored"
            chunk_size = min(max(4096, source["size"]), 1 << 20)
            started = time.perf_counter()
            info = compress_hybrid_file(
                path,
                artifact,
                profile="balanced",
                selector_mode="ai-benchmark",
                chunk_size=chunk_size,
                top_k=3,
                microbench_bytes=min(64 << 10, chunk_size),
                selector_model=ROOT / "checkpoints" / "selector" / "best.json",
            )
            total_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            decompress_hybrid_file(artifact, restored)
            decompression_ms = (time.perf_counter() - started) * 1000
            final_bytes = artifact.stat().st_size
            row = {
                "sample_id": source["sample_id"],
                "category": source["category"],
                "original_bytes": source["size"],
                "chunks": info["chunks"],
                "feature_scan_ms": info["feature_scan_ms"],
                "selector_inference_ms": info["model_inference_ms"],
                "candidate_generation_ms": info["candidate_generation_ms"],
                "microbenchmark_ms": info["microbenchmark_ms"],
                "transform_ms": info["transform_ms"],
                "codec_compression_ms": info["codec_compression_ms"],
                "container_serialization_ms": info["container_serialization_ms"],
                "total_compression_ms": total_ms,
                "decompression_ms": decompression_ms,
                "unattributed_container_io_ms": max(
                    0.0,
                    total_ms
                    - info["feature_scan_ms"]
                    - info["model_inference_ms"]
                    - info["candidate_generation_ms"]
                    - info["microbenchmark_ms"]
                    - info["transform_ms"]
                    - info["codec_compression_ms"]
                    - info["container_serialization_ms"],
                ),
                "raw_payload_bytes": info["raw_payload_bytes"],
                "codec_payload_bytes": info["codec_payload_bytes"],
                "XAIC_header_bytes": info["XAIC_header_bytes"],
                "XAIC_chunk_metadata_bytes": info["XAIC_chunk_metadata_bytes"],
                "chunk_framing_bytes": info["chunk_framing_bytes"],
                "checksum_bytes": info["checksum_bytes"],
                "footer_bytes": info["footer_bytes"],
                "total_metadata_bytes": info["total_metadata_bytes"],
                "final_artifact_bytes": final_bytes,
                "metadata_overhead_percent": 100 * info["total_metadata_bytes"] / final_bytes,
                "container_penalty_bytes": info["container_penalty_bytes"],
                "codec_distribution": json.dumps(info["codec_distribution"], sort_keys=True),
                "transform_distribution": json.dumps(info["transform_distribution"], sort_keys=True),
                "sha_pass": sha256(path) == sha256(restored),
            }
            rows.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)
    write_csv(RESULTS / "overhead_breakdown.csv", rows)
    summary = {
        "rows": len(rows),
        "sha_pass": all(row["sha_pass"] for row in rows),
        "total_original_bytes": sum(row["original_bytes"] for row in rows),
        "total_artifact_bytes": sum(row["final_artifact_bytes"] for row in rows),
        "total_codec_payload_bytes": sum(row["codec_payload_bytes"] for row in rows),
        "total_metadata_bytes": sum(row["total_metadata_bytes"] for row in rows),
    }
    summary["weighted_metadata_percent"] = 100 * summary["total_metadata_bytes"] / summary["total_artifact_bytes"]
    (RESULTS / "overhead_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
