"""Generate evidence-backed research reports from raw CSV results."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from xai_compress.research import read_csv, write_manifest


def number(row, *keys):
    for key in keys:
        value = row.get(key, "")
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def aggregate(rows):
    grouped = defaultdict(lambda: {"original": 0.0, "compressed": 0.0, "ct": 0.0, "dt": 0.0, "files": 0, "valid": 0})
    for row in rows:
        codec = row.get("codec", "unknown")
        original = number(row, "original_size")
        compressed = number(row, "compressed_size")
        if original is None or compressed is None:
            continue
        item = grouped[codec]
        item["original"] += original
        item["compressed"] += compressed
        item["ct"] += number(row, "compress_seconds", "compression_seconds") or 0.0
        item["dt"] += number(row, "decompress_seconds", "decompression_seconds") or 0.0
        item["files"] += 1
        match = str(row.get("lossless", row.get("sha256_match", ""))).lower()
        item["valid"] += int(match in {"true", "1", "yes"})
    result = []
    for codec, item in sorted(grouped.items()):
        original, compressed = item["original"], item["compressed"]
        result.append({
            "codec": codec, "files": item["files"], "lossless": item["valid"],
            "original_size": int(original), "compressed_size": int(compressed),
            "ratio": original / compressed if compressed else None,
            "bpb": 8 * compressed / original if original else None,
            "compression_mbs": original / 1048576 / item["ct"] if item["ct"] else None,
            "decompression_mbs": original / 1048576 / item["dt"] if item["dt"] else None,
        })
    return result


def fmt(value, digits=3):
    return "not measured" if value is None else f"{value:.{digits}f}"


def render_table(summary):
    lines = ["| Codec | Files | Verified | Size (bytes) | Ratio | BPB | Comp MB/s | Decomp MB/s |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in summary:
        lines.append(f"| {row['codec']} | {row['files']} | {row['lossless']} | {row['compressed_size']} | {fmt(row['ratio'])} | {fmt(row['bpb'])} | {fmt(row['compression_mbs'])} | {fmt(row['decompression_mbs'])} |")
    return "\n".join(lines) if summary else "No valid benchmark rows were found. Run `xcompress benchmark` first."


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="results/benchmark_results.csv")
    parser.add_argument("--report", default="reports/benchmark_report.md")
    args = parser.parse_args(argv)
    root = ROOT
    result_path = root / args.results
    rows = read_csv(result_path)
    summary = aggregate(rows)
    results_dir = root / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "benchmark_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (results_dir / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = write_manifest(results_dir / "machine_manifest.json")
    report = """# Benchmark Report

This report is generated from raw measurements. Missing codecs or metrics are reported as unmeasured; no values are synthesized.

## Reproduction

```bash
xcompress benchmark --dataset <held-out-dataset> --output results/benchmark_results.csv
python scripts/generate_report.py
```

## Aggregate results

{table}

## Experimental environment

```json
{manifest}
```

## Interpretation constraints

Ratios include container overhead. All comparisons must use identical input files. Training cost and model storage are separate from compressed payload size and must be disclosed. A result is admissible only when every decoded file is byte-identical.
""".format(table=render_table(summary), manifest=json.dumps(manifest, indent=2))
    target = root / args.report
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report, encoding="utf-8")
    print(f"generated {target} from {len(rows)} raw rows")


if __name__ == "__main__":
    main()
