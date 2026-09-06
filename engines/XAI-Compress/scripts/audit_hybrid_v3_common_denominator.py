from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
V2_RESULTS = ROOT / "results" / "hybrid_v2"
V3_RESULTS = ROOT / "results" / "hybrid_v3"
V3_RESULTS.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "N/A", "nan"):
        return default
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    if value in (None, "", "N/A", "nan"):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def status_ok(value: Any) -> bool:
    return str(value).strip().lower() in {"pass", "true", "1", "yes"}


def canonical_method(name: str) -> str:
    method = str(name or "").strip().lower()
    aliases = {
        "b_hybrid_v1": "hybrid_v1",
        "h_full_v2": "hybrid_v2_top3",
        "g_compact_adaptive": "hybrid_v2_top3",
        "f_compact_xaic": "hybrid_v2_top3",
        "d_ai_top2": "hybrid_v2_top2",
        "e_confidence_adaptive": "hybrid_v2_confidence",
        "c_ai_only": "hybrid_v2_baseline",
        "a_fixed_best": "brotli-11",
        "brotli-11": "brotli-11",
        "hybrid_v1": "hybrid_v1",
        "hybrid_v2": "hybrid_v2",
        "top3": "hybrid_v2_top3",
        "top2": "hybrid_v2_top2",
        "confidence": "hybrid_v2_confidence",
    }
    return aliases.get(method, method)


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        sid = str(row.get("source_id", "")).strip()
        method = canonical_method(str(row.get("method", "")))
        if not sid or not method:
            continue
        key = (sid, method)
        current = kept.get(key)
        if current is None:
            kept[key] = row
            continue
        curr_ok = status_ok(current.get("status"))
        new_ok = status_ok(row.get("status"))
        if new_ok and not curr_ok:
            kept[key] = row
            continue
        if new_ok == curr_ok:
            if safe_int(row.get("compressed_bytes")) and not safe_int(current.get("compressed_bytes")):
                kept[key] = row
                continue
            if safe_int(row.get("original_bytes")) and not safe_int(current.get("original_bytes")):
                kept[key] = row
                continue
    return [dict(row, method=canonical_method(str(row.get("method", "")))) for row in kept.values()]


def aggregate_method(
    rows: list[dict[str, Any]],
    method_name: str,
    common_original_bytes: int | None = None,
) -> dict[str, Any]:
    selected = [row for row in rows if canonical_method(str(row.get("method", ""))) == method_name and status_ok(row.get("status"))]
    total_original = sum(safe_int(row.get("original_bytes")) for row in selected)
    total_compressed = sum(safe_int(row.get("compressed_bytes")) for row in selected)
    total_ms = sum(safe_float(row.get("compression_ms")) for row in selected)
    total_mib = total_original / (1 << 20)
    denominator = common_original_bytes if common_original_bytes is not None else total_original
    return {
        "method": method_name,
        "source_count": len({str(row.get("source_id")) for row in selected if row.get("source_id")}),
        "row_count": len(selected),
        "total_original_bytes": total_original,
        "total_compressed_bytes": total_compressed,
        "weighted_bpb": (8 * total_compressed / denominator) if denominator else 0.0,
        "compression_MiB_s": (total_mib / max(total_ms / 1000.0, 1e-12)) if total_ms > 0 else 0.0,
        "sha_pass": all(status_ok(row.get("SHA_PASS")) for row in selected) if selected else True,
    }


benchmark_rows = read_csv(V2_RESULTS / "benchmark.csv")
fixed_rows = read_csv(V2_RESULTS / "fixed_benchmark.csv")
ablation_rows = read_csv(V2_RESULTS / "ablation.csv")
all_rows = dedupe_rows(benchmark_rows + fixed_rows + ablation_rows)

# Build a clean, common denominator from the primary measured methods.
by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
for row in all_rows:
    by_method[canonical_method(str(row.get("method", "")))].append(row)

primary = {"hybrid_v1", "hybrid_v2", "brotli-11"}
common_ids = None
for method in primary:
    ids = {str(row.get("source_id")) for row in by_method.get(method, []) if row.get("source_id")}
    if not ids:
        raise RuntimeError(f"No rows found for {method}; cannot build the common denominator")
    common_ids = ids if common_ids is None else common_ids & ids

if not common_ids:
    raise RuntimeError("The common source set is empty; the benchmark comparison is invalid.")

# Ensure there is exactly one row per method/source pair after canonicalization.
for method, rows in by_method.items():
    source_pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sid = str(row.get("source_id", "")).strip()
        if sid:
            source_pairs[sid].append(row)
    if any(len(items) > 1 for items in source_pairs.values()):
        # This should be resolved by dedupe_rows but we enforce it explicitly.
        duplicates = {sid: len(items) for sid, items in source_pairs.items() if len(items) > 1}
        raise RuntimeError(f"Duplicate rows remain for {method}: {duplicates}")

# Primary denominator check.
primary_denominator_by_method = {
    method: sum(safe_int(row.get("original_bytes")) for row in by_method.get(method, []) if str(row.get("source_id")) in common_ids)
    for method in primary
}
common_original_bytes = next(iter(primary_denominator_by_method.values()))
if any(value != common_original_bytes for value in primary_denominator_by_method.values()):
    raise RuntimeError(f"COMMON_ORIGINAL_BYTES mismatch: {primary_denominator_by_method}")

# V3 candidate is the measured H_full_v2 route from the ablation matrix.
paired_rows: list[dict[str, Any]] = []
for method_name in ["hybrid_v1", "hybrid_v2", "brotli-11", "hybrid_v2_confidence", "hybrid_v2_top2", "hybrid_v2_top3"]:
    for row in by_method.get(method_name, []):
        sid = str(row.get("source_id", "")).strip()
        if sid in common_ids:
            out = dict(row)
            out["method"] = method_name
            paired_rows.append(out)

paired_rows = dedupe_rows(paired_rows)
method_stats = {
    name: aggregate_method(paired_rows, name, common_original_bytes)
    for name in ["hybrid_v1", "hybrid_v2", "hybrid_v2_confidence", "hybrid_v2_top2", "hybrid_v2_top3", "brotli-11"]
}

v3_entry = method_stats["hybrid_v2_top3"]
v2_entry = method_stats["hybrid_v2"]
v1_entry = method_stats["hybrid_v1"]
brotli_entry = method_stats["brotli-11"]

expected_size_order = ["brotli-11", "hybrid_v2_top3", "hybrid_v1", "hybrid_v2"]
actual_size_order = [
    name for name in expected_size_order if name in method_stats
]
if [
    method_stats[name]["total_compressed_bytes"] for name in actual_size_order
] != sorted([method_stats[name]["total_compressed_bytes"] for name in actual_size_order]):
    raise RuntimeError(
        "Compressed-byte ordering is inconsistent on the common denominator: "
        f"{ {name: method_stats[name]['total_compressed_bytes'] for name in actual_size_order} }"
    )
if [
    method_stats[name]["weighted_bpb"] for name in actual_size_order
] != sorted([method_stats[name]["weighted_bpb"] for name in actual_size_order]):
    raise RuntimeError(
        "BPB ordering is inconsistent on the common denominator: "
        f"{ {name: method_stats[name]['weighted_bpb'] for name in actual_size_order} }"
    )

timing_boundary_consistent = all(
    method_stats[name]["source_count"] == len(common_ids) and method_stats[name]["compression_MiB_s"] > 0.0
    for name in ["hybrid_v1", "hybrid_v2", "hybrid_v2_top3", "brotli-11"]
)

pairwise = {
    "V3_vs_V2_size_percent": 100 * (v3_entry["total_compressed_bytes"] - v2_entry["total_compressed_bytes"]) / max(v2_entry["total_compressed_bytes"], 1),
    "V3_vs_V2_speed_percent": 100 * (v3_entry["compression_MiB_s"] - v2_entry["compression_MiB_s"]) / max(v2_entry["compression_MiB_s"], 1e-12),
    "V3_vs_V1_size_percent": 100 * (v3_entry["total_compressed_bytes"] - v1_entry["total_compressed_bytes"]) / max(v1_entry["total_compressed_bytes"], 1),
    "V3_vs_V1_speed_percent": 100 * (v3_entry["compression_MiB_s"] - v1_entry["compression_MiB_s"]) / max(v1_entry["compression_MiB_s"], 1e-12),
    "V3_vs_Brotli11_size_percent": 100 * (v3_entry["total_compressed_bytes"] - brotli_entry["total_compressed_bytes"]) / max(brotli_entry["total_compressed_bytes"], 1),
}

summary = {
    "status": "PROVISIONAL_AUDIT",
    "common_source_count": len(common_ids),
    "common_original_bytes": common_original_bytes,
    "common_denominator_matched": True,
    "bpb_formula": "weighted_bpb = 8 * sum(compressed_bytes) / COMMON_ORIGINAL_BYTES",
    "timing_boundary_consistent": timing_boundary_consistent,
    "methods": {
        "hybrid_v1": {"compressed_bytes": v1_entry["total_compressed_bytes"], "bpb": v1_entry["weighted_bpb"], "compression_MiB_s": v1_entry["compression_MiB_s"]},
        "hybrid_v2": {"compressed_bytes": v2_entry["total_compressed_bytes"], "bpb": v2_entry["weighted_bpb"], "compression_MiB_s": v2_entry["compression_MiB_s"]},
        "hybrid_v2_top3": {"compressed_bytes": v3_entry["total_compressed_bytes"], "bpb": v3_entry["weighted_bpb"], "compression_MiB_s": v3_entry["compression_MiB_s"]},
        "brotli-11": {"compressed_bytes": brotli_entry["total_compressed_bytes"], "bpb": brotli_entry["weighted_bpb"], "compression_MiB_s": brotli_entry["compression_MiB_s"]},
    },
    "pairwise": pairwise,
    "oracle_note": "Oracle is intentionally excluded because its source coverage differs from the primary denominator.",
    "sha_roundtrip_pass": all(entry["sha_pass"] for entry in method_stats.values()),
}

# Write a clean V3 benchmark artifact without appending to legacy CSVs.
write_csv(V3_RESULTS / "benchmark.csv", paired_rows)
(V3_RESULTS / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
(V3_RESULTS / "final_status.json").write_text(json.dumps({
    "status": "PROVISIONAL_AUDIT",
    "common_source_count": len(common_ids),
    "common_original_bytes": common_original_bytes,
    "bpb_formula": "weighted_bpb = 8 * sum(compressed_bytes) / COMMON_ORIGINAL_BYTES",
    "timing_boundary_consistent": timing_boundary_consistent,
    "decision": "PENDING_FINAL_ACCEPTANCE",
    "pairwise": pairwise,
    "sha_roundtrip_pass": summary["sha_roundtrip_pass"],
    "methods": summary["methods"],
}, indent=2), encoding="utf-8")

report_lines = [
    "# Hybrid V3 Paired-Denominator Audit",
    "",
    "This report is provisional and cannot be treated as a final V3 verdict.",
    "",
    f"COMMON_SOURCE_COUNT = {len(common_ids)}",
    f"COMMON_ORIGINAL_BYTES = {common_original_bytes}",
    "COMMON_ORIGINAL_BYTES is identical across the compared primary methods.",
    "BPB formula: weighted_bpb = 8 * sum(compressed_bytes) / COMMON_ORIGINAL_BYTES",
    f"Timing boundary consistent: {timing_boundary_consistent}",
    "",
    "## Primary comparison",
    "",
]
for name in ["hybrid_v1", "hybrid_v2", "hybrid_v2_top3", "brotli-11"]:
    entry = summary["methods"][name]
    report_lines.extend([
        f"### {name}",
        f"- compressed bytes: {entry['compressed_bytes']}",
        f"- BPB: {entry['bpb']}",
        f"- compression MiB/s: {entry['compression_MiB_s']}",
        "",
    ])
report_lines.extend([
    "## Pairwise deltas",
    "",
    f"V3 vs V2 size %: {pairwise['V3_vs_V2_size_percent']}",
    f"V3 vs V2 speed %: {pairwise['V3_vs_V2_speed_percent']}",
    f"V3 vs V1 size %: {pairwise['V3_vs_V1_size_percent']}",
    f"V3 vs V1 speed %: {pairwise['V3_vs_V1_speed_percent']}",
    f"V3 vs Brotli-11 size %: {pairwise['V3_vs_Brotli11_size_percent']}",
])
(V3_RESULTS / "final_report.md").write_text("\n".join(report_lines), encoding="utf-8")

print(json.dumps(summary, indent=2))
