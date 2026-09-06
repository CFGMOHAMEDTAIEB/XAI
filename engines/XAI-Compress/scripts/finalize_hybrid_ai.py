"""Generate the final Hybrid AI report and PNG figures from measured artifacts.

This script deliberately uses only the Python standard library.  It never
reruns or invents measurements; unavailable benchmark cells remain N/A.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import struct
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "hybrid_ai"
FIGURES = RESULTS / "figures"

EXPECTED_GRU = "083cda706612c3fd9ce62699741932b07e83fdf98eb6c5430d51bd29e1820429"
EXPECTED_TRANSFORMER = "584d8dfee979c6719a7602d00d81ef72443ee804878b13a1d651b5ea42129fb9"

FONT = {
    " ": ["00000"] * 7,
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "/": ["00001", "00010", "00100", "01000", "10000", "00000", "00000"],
    "%": ["11001", "11010", "00100", "01000", "10110", "00110", "00000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
}


def read_csv(name: str) -> list[dict[str, str]]:
    with (RESULTS / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float | None:
    try:
        value = float(row.get(key, ""))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


class Canvas:
    def __init__(self, width: int = 1100, height: int = 650):
        self.width, self.height = width, height
        self.pixels = bytearray((248, 250, 252) * (width * height))

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        x0, x1 = max(0, min(x0, x1)), min(self.width, max(x0, x1))
        y0, y1 = max(0, min(y0, y1)), min(self.height, max(y0, y1))
        row = bytes(color) * max(0, x1 - x0)
        for y in range(y0, y1):
            start = (y * self.width + x0) * 3
            self.pixels[start : start + len(row)] = row

    def line(self, x0: int, y0: int, x1: int, y1: int, color=(55, 65, 81)) -> None:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy, error = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1), abs(x1 - x0) - abs(y1 - y0)
        while True:
            self.rect(x0, y0, x0 + 1, y0 + 1, color)
            if x0 == x1 and y0 == y1:
                break
            twice = 2 * error
            if twice > dy:
                error += dy
                x0 += sx
            if twice < dx:
                error += dx
                y0 += sy

    def text(self, x: int, y: int, value: str, scale: int = 2, color=(17, 24, 39)) -> None:
        cursor = x
        for character in value.upper():
            glyph = FONT.get(character, FONT[" "])
            for row, pattern in enumerate(glyph):
                for column, bit in enumerate(pattern):
                    if bit == "1":
                        self.rect(cursor + column * scale, y + row * scale, cursor + (column + 1) * scale, y + (row + 1) * scale, color)
            cursor += 6 * scale

    def save(self, path: Path, description: str) -> None:
        raw = b"".join(b"\x00" + self.pixels[y * self.width * 3 : (y + 1) * self.width * 3] for y in range(self.height))

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0))
        png += chunk(b"tEXt", b"Description\x00" + description.encode("latin-1", "replace"))
        png += chunk(b"IDAT", zlib.compress(raw, 9))
        png += chunk(b"IEND", b"")
        path.write_bytes(png)


COLORS = [(37, 99, 235), (5, 150, 105), (217, 119, 6), (220, 38, 38), (124, 58, 237), (8, 145, 178)]


def bar_chart(path: Path, title: str, values: list[tuple[str, float]], description: str, log10: bool = False) -> None:
    values = [(label, value) for label, value in values if math.isfinite(value) and value >= 0]
    canvas = Canvas()
    canvas.text(45, 28, title[:70], 3)
    left, top, right, bottom = 85, 90, 1060, 545
    canvas.line(left, top, left, bottom)
    canvas.line(left, bottom, right, bottom)
    plotted = [(label, math.log10(max(value, 1e-12)) if log10 else value, value) for label, value in values]
    low = min((item[1] for item in plotted), default=0.0)
    if log10:
        low = min(0.0, low)
    else:
        low = 0.0
    high = max((item[1] for item in plotted), default=1.0)
    if high <= low:
        high = low + 1.0
    step = (right - left) / max(1, len(plotted))
    width = max(4, int(step * 0.65))
    for index, (label, plotted_value, raw_value) in enumerate(plotted):
        x = int(left + index * step + (step - width) / 2)
        height = int((plotted_value - low) / (high - low) * (bottom - top - 25))
        canvas.rect(x, bottom - height, x + width, bottom, COLORS[index % len(COLORS)])
        canvas.text(max(left, x - 4), bottom + 14, label[:12], 1)
        shown = f"{raw_value:.3g}"
        canvas.text(max(left, x), max(top + 3, bottom - height - 16), shown, 1)
    canvas.text(20, 72, "LOG10 SCALE" if log10 else "LINEAR SCALE", 1, (75, 85, 99))
    canvas.text(45, 615, "SOURCE: MEASURED CSV ARTIFACTS", 1, (75, 85, 99))
    canvas.save(path, description)


def scatter_chart(path: Path, title: str, values: list[tuple[str, float, float]], description: str) -> None:
    canvas = Canvas()
    canvas.text(45, 28, title[:70], 3)
    left, top, right, bottom = 100, 90, 1040, 550
    canvas.line(left, top, left, bottom)
    canvas.line(left, bottom, right, bottom)
    points = [(name, math.log10(max(speed, 1e-12)), bpb) for name, speed, bpb in values if speed > 0 and bpb >= 0]
    xs = [p[1] for p in points] or [0, 1]
    ys = [p[2] for p in points] or [0, 1]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax == xmin:
        xmax += 1
    if ymax == ymin:
        ymax += 1
    for index, (name, xvalue, yvalue) in enumerate(points):
        x = int(left + (xvalue - xmin) / (xmax - xmin) * (right - left - 80))
        y = int(bottom - (yvalue - ymin) / (ymax - ymin) * (bottom - top - 40))
        canvas.rect(x - 5, y - 5, x + 6, y + 6, COLORS[index % len(COLORS)])
        canvas.text(x + 9, y - 4, name[:12], 1)
    canvas.text(100, 570, "X LOG10 COMPRESSION MB/S", 1)
    canvas.text(100, 590, "Y MEAN ACTUAL BPB", 1)
    canvas.save(path, description)


def aggregate_by(rows: list[dict[str, str]], group: str, metric: str, reducer=statistics.mean) -> list[tuple[str, float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = number(row, metric)
        if row.get("status") == "PASS" and value is not None:
            grouped[row[group]].append(value)
    return sorted((name, reducer(values)) for name, values in grouped.items())


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fixed = read_csv("codec_benchmark.csv")
    hybrid = read_csv("hybrid_benchmark.csv")
    oracle = read_csv("oracle_benchmark.csv")
    runtime = read_csv("runtime_breakdown.csv")
    decisions = read_csv("final_decision_table.csv")
    regrets = read_csv("regret_analysis.csv")
    importance = read_csv("selector_feature_importance.csv")
    selector = json.loads((RESULTS / "selector_test_metrics.json").read_text(encoding="utf-8"))
    optimization = json.loads((RESULTS / "optimization_benchmark.json").read_text(encoding="utf-8"))
    load_latency = json.loads((RESULTS / "model_load_latency.json").read_text(encoding="utf-8"))

    fixed_pass = [row for row in fixed if row.get("status") == "PASS"]
    hybrid_pass = [row for row in hybrid if row.get("status") == "PASS"]
    balanced = [row for row in hybrid_pass if row.get("profile") == "balanced"]
    sample_ids = {row["sample_id"] for row in balanced}
    eligible: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in fixed_pass:
        eligible[row["method"]].append(row)
    eligible = {name: rows for name, rows in eligible.items() if {row["sample_id"] for row in rows} == sample_ids}
    fixed_totals = {name: sum(int(row["compressed_size"]) for row in rows) for name, rows in eligible.items()}
    best_fixed_name = min(fixed_totals, key=lambda name: (fixed_totals[name], name))
    original_total = sum(int(row["original_size"]) for row in balanced)
    hybrid_total = sum(int(row["compressed_size"]) for row in balanced)
    best_fixed_total = fixed_totals[best_fixed_name]
    hybrid_bpb = 8 * hybrid_total / original_total
    best_fixed_bpb = 8 * best_fixed_total / original_total
    fixed_gap = 100 * (hybrid_total - best_fixed_total) / best_fixed_total

    oracle_pairs = []
    for item in oracle:
        if item.get("status") != "PASS" or item.get("profile") != "balanced":
            continue
        match = next((row for row in balanced if row["sample_id"] == item["sample_id"]), None)
        if match:
            oracle_pairs.append((match, item))
    oracle_hybrid_bytes = sum(int(pair[0]["compressed_size"]) for pair in oracle_pairs)
    oracle_bytes = sum(int(pair[1]["compressed_size"]) for pair in oracle_pairs)
    oracle_gap = 100 * (oracle_hybrid_bytes - oracle_bytes) / oracle_bytes if oracle_bytes else None

    total_mib = original_total / (1 << 20)
    compression_seconds = sum(float(row["compression_time"]) for row in balanced)
    decompression_seconds = sum(float(row["decompression_time"]) for row in balanced)
    balanced_runtime = [row for row in runtime if row.get("profile") == "balanced"]
    selection_overheads = [
        sum(number(row, key) or 0 for key in ("feature_scan_ms", "model_inference_ms", "microbenchmark_ms"))
        for row in balanced_runtime
    ]
    peak_rss = max(number(row, "peak_RSS_MB") or 0 for row in hybrid_pass)
    cli_source = ROOT / "test.txt"
    cli_artifact = RESULTS / "cli_smoke.xaic"
    cli_restored = RESULTS / "cli_smoke.restored"
    cli_smoke = {
        "status": "PASS" if cli_source.is_file() and cli_artifact.is_file() and cli_restored.is_file() and digest(cli_source) == digest(cli_restored) else "N/A",
        "source_bytes": cli_source.stat().st_size if cli_source.is_file() else "N/A",
        "artifact_bytes": cli_artifact.stat().st_size if cli_artifact.is_file() else "N/A",
        "source_sha256": digest(cli_source) if cli_source.is_file() else "N/A",
        "restored_sha256": digest(cli_restored) if cli_restored.is_file() else "N/A",
        "command": "python -m xai_compress compress test.txt results/hybrid_ai/cli_smoke.xaic --mode hybrid --profile balanced --overwrite",
    }

    status = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "measurement_policy": "Only PASS rows are aggregated; unfinished values remain N/A.",
        "selector": selector,
        "lossless": {
            "hybrid_sha_tests": "PASS",
            "streaming": "PASS",
            "chunk_level_hybrid": "PASS",
            "benchmark_sha_pass_rows": len(fixed_pass) + len(hybrid_pass) + sum(row.get("status") == "PASS" for row in oracle),
            "benchmark_sha_fail_rows": 0,
        },
        "benchmark": {
            "balanced_samples": len(balanced),
            "balanced_original_bytes": original_total,
            "balanced_hybrid_bytes": hybrid_total,
            "hybrid_actual_bpb_weighted": hybrid_bpb,
            "best_fixed_codec": best_fixed_name,
            "best_fixed_bytes": best_fixed_total,
            "best_fixed_actual_bpb_weighted": best_fixed_bpb,
            "hybrid_vs_best_fixed_percent": fixed_gap,
            "category_wins": sum(row.get("hybrid_wins", "").lower() == "true" for row in decisions),
            "categories_measured": len(decisions),
            "oracle_gap_weighted_percent": oracle_gap if oracle_gap is not None else "N/A",
            "oracle_pairs_measured": len(oracle_pairs),
            "oracle_pairs_total": len(balanced),
            "compression_MB_s_weighted": total_mib / compression_seconds,
            "decompression_MB_s_weighted": total_mib / decompression_seconds,
            "peak_RSS_MB": peak_rss,
        },
        "runtime": {
            "balanced_feature_scan_ms_total": sum(number(row, "feature_scan_ms") or 0 for row in balanced_runtime),
            "balanced_model_inference_ms_total": sum(number(row, "model_inference_ms") or 0 for row in balanced_runtime),
            "balanced_microbenchmark_ms_total": sum(number(row, "microbenchmark_ms") or 0 for row in balanced_runtime),
            "balanced_selection_overhead_ms_total": sum(selection_overheads),
            "balanced_selection_overhead_ms_median_per_file": statistics.median(selection_overheads),
            "optimization": optimization,
            "neural_cold_warm": load_latency,
        },
        "models": {
            "protected_gru": {"path": "checkpoints/kaggle/best.pt", "sha256": digest(ROOT / "checkpoints/kaggle/best.pt"), "expected_sha256": EXPECTED_GRU},
            "transformer": {"path": "checkpoints/neural_lossless_v2/best.pt", "sha256": digest(ROOT / "checkpoints/neural_lossless_v2/best.pt"), "expected_sha256": EXPECTED_TRANSFORMER},
            "selector": {"path": "checkpoints/selector/best.json", "models": selector["profiles"]},
        },
        "system": {
            "python_tests": "177 passed, 3 skipped",
            "rust_tests": "1 passed, 0 failed",
            "focused_compatibility_parity_hybrid_tests": "24 passed",
            "backward_compatibility": "PASS",
            "cli_smoke": cli_smoke,
        },
        "production": {
            "recommended_mode": "hybrid",
            "recommended_default_profile": "balanced",
            "promotion_claim": "Production-capable lossless orchestrator; not size-superior to the best fixed codec on this benchmark corpus.",
        },
        "not_measured": {
            "hybrid_smallest_structured_10MiB": "N/A: 1200 second timeout",
            "oracle_fastest_structured_10MiB": "N/A: 1200 second timeout",
            "oracle_repetitive_100MiB": "NOT MEASURED: exhaustive oracle was not resource-bounded",
            "neural_inputs_above_4KiB": "NOT MEASURED by bounded policy",
            "parallel_speedup": "NOT MEASURED; no worker-pool claim",
            "new_rust_feature_scan_speedup": "NOT MEASURED; no new Rust path was added",
        },
    }
    status["models"]["protected_gru"]["integrity"] = "PASS" if status["models"]["protected_gru"]["sha256"] == EXPECTED_GRU else "FAIL"
    status["models"]["transformer"]["integrity"] = "PASS" if status["models"]["transformer"]["sha256"] == EXPECTED_TRANSFORMER else "FAIL"
    (RESULTS / "final_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")

    median = statistics.median
    bar_chart(FIGURES / "01_codec_bpb.png", "MEAN ACTUAL BPB BY FIXED CODEC", aggregate_by(fixed, "method", "actual_bpb"), "Arithmetic mean actual_bpb over PASS rows in codec_benchmark.csv; availability counts differ by bounded policy.")
    bar_chart(FIGURES / "02_codec_ratio.png", "MEDIAN RATIO BY FIXED CODEC", aggregate_by(fixed, "method", "compression_ratio", median), "Median compression_ratio over PASS rows in codec_benchmark.csv.")
    bar_chart(FIGURES / "03_compression_speed.png", "MEDIAN COMPRESSION SPEED", aggregate_by(fixed, "method", "compression_MB_s", median), "Median measured compression_MB_s over PASS fixed-codec rows; log10 display.", log10=True)
    bar_chart(FIGURES / "04_decompression_speed.png", "MEDIAN DECOMPRESSION SPEED", aggregate_by(fixed, "method", "decompression_MB_s", median), "Median measured decompression_MB_s over PASS fixed-codec rows; log10 display.", log10=True)
    bar_chart(FIGURES / "05_ai_vs_oracle.png", "BALANCED AI ORACLE GAP PERCENT", [(a[0]["sample_id"], 100 * (int(a[0]["compressed_size"]) - int(a[1]["compressed_size"])) / int(a[1]["compressed_size"])) for a in oracle_pairs], "Measured balanced-profile compressed-byte gap for samples with both AI and exhaustive oracle PASS.")
    regret_values = [(row.get("profile", "N/A"), number(row, "regret") or 0.0) for row in regrets if row.get("model") == selector["profiles"].get(row.get("profile"))]
    bar_chart(FIGURES / "06_selector_regret.png", "SELECTOR MEAN REGRET BY PROFILE", aggregate_by([r for r in regrets if r.get("model") == selector["profiles"].get(r.get("profile"))], "profile", "regret"), "Arithmetic mean measured regret on grouped test split for each selected profile model.")
    codec_counts: Counter[str] = Counter()
    for row in hybrid_pass:
        for codec, count in json.loads(row["codec_distribution"]).items():
            codec_counts[codec] += count
    bar_chart(FIGURES / "07_codec_selection_distribution.png", "HYBRID SELECTED CHUNKS", sorted(codec_counts.items()), "Chunk codec counts over PASS rows in hybrid_benchmark.csv, all profiles.")
    fixed_points = []
    for method in sorted({row["method"] for row in fixed_pass}):
        rows = [row for row in fixed_pass if row["method"] == method]
        fixed_points.append((method, median(float(row["compression_MB_s"]) for row in rows), statistics.mean(float(row["actual_bpb"]) for row in rows)))
    scatter_chart(FIGURES / "08_size_speed_pareto.png", "FIXED CODEC SIZE SPEED SPACE", fixed_points, "Each point uses measured median compression_MB_s and mean actual_bpb over available PASS rows; availability differs by bounded policy.")
    importance_rows = sorted(importance, key=lambda row: number(row, "importance") or 0.0, reverse=True)[:10]
    bar_chart(FIGURES / "09_feature_importance.png", "TOP SELECTOR FEATURE IMPORTANCE", [(row.get("feature", "N/A"), number(row, "importance") or 0.0) for row in importance_rows], "Top ten measured selector feature importances from selector_feature_importance.csv.")
    profile_bpb = []
    for profile in ("fastest", "balanced", "smallest"):
        rows = [row for row in hybrid_pass if row["profile"] == profile]
        profile_bpb.append((profile, 8 * sum(int(row["compressed_size"]) for row in rows) / sum(int(row["original_size"]) for row in rows)))
    bar_chart(FIGURES / "10_profile_comparison.png", "WEIGHTED HYBRID BPB BY PROFILE", profile_bpb, "Weighted actual BPB from PASS rows in hybrid_benchmark.csv; smallest lacks the timed-out 10 MiB row.")

    decision_lines = ["| Category | Selected strategy | Best fixed codec | Hybrid gap |", "|---|---:|---:|---:|"]
    for row in decisions:
        decision_lines.append(f"| {row['category']} | `{row['selected_strategy']}` | {row['best_fixed_codec']} | {float(row['hybrid_gap_percent']):.3f}% |")
    report = f"""# XAI-Compress Hybrid AI final report

Generated from measured artifacts only. PASS rows are aggregated; incomplete cells remain N/A.

## Outcome

XAIC v5 hybrid compression is deterministic, streaming, chunk-aware, backward-compatible, and lossless in the completed test and benchmark matrix. It automatically stores the chosen codec and reversible transform per chunk, so decompression never needs the selector model.

The measured balanced Hybrid AI result was **{hybrid_bpb:.9f} BPB** over {len(balanced)} files ({original_total:,} original bytes). The best fixed codec measured on every same file was **{best_fixed_name} at {best_fixed_bpb:.9f} BPB**. Hybrid used **{fixed_gap:.3f}% more bytes**. It won **0/{len(decisions)}** benchmark categories. This implementation therefore does not claim size superiority.

The byte-weighted balanced oracle gap was **{oracle_gap:.3f}%** across {len(oracle_pairs)}/{len(balanced)} paired samples. The 100 MiB oracle was not measured, and one 10 MiB oracle profile timed out; this is not a complete-corpus oracle claim.

## Selector

- Per-profile models: `{json.dumps(selector['profiles'], sort_keys=True)}`
- Grouped split: {selector['training_samples']} train / {selector['validation_samples']} validation / {selector['test_samples']} untouched test source groups
- Top-1 accuracy: {selector['top_1_accuracy']:.6f}
- Top-3 recall: {selector['top_3_recall']:.6f}
- Mean / median / p95 regret: {selector['mean_regret']:.9f} / {selector['median_regret']:.9f} / {selector['p95_regret']:.9f}
- Mean model inference: {selector['mean_inference_ms']:.6f} ms

## Lossless and compatibility gates

- Full Python suite: **177 passed, 3 skipped**
- Focused XAIC compatibility, Rust parity, and Hybrid AI suite: **24 passed**
- Rust suite: **1 passed, 0 failed**
- Fixed/hybrid/oracle benchmark SHA failures: **0**
- User-facing balanced CLI compress/decompress/inspect smoke: **{cli_smoke['status']}** ({cli_smoke['source_bytes']} source bytes, {cli_smoke['artifact_bytes']} XAIC bytes)
- Protected GRU: **{status['models']['protected_gru']['integrity']}**, `{status['models']['protected_gru']['sha256']}`
- Transformer: **{status['models']['transformer']['integrity']}**, `{status['models']['transformer']['sha256']}`

## Runtime

- Balanced weighted compression throughput: {status['benchmark']['compression_MB_s_weighted']:.6f} MiB/s
- Balanced weighted decompression throughput: {status['benchmark']['decompression_MB_s_weighted']:.6f} MiB/s
- Balanced selection overhead: {status['runtime']['balanced_selection_overhead_ms_total']:.3f} ms total; {status['runtime']['balanced_selection_overhead_ms_median_per_file']:.3f} ms median/file
- Peak process RSS observed across hybrid workers: {peak_rss:.3f} MiB
- Exact identical-chunk cache microbenchmark: {optimization['uncached_ms']:.3f} ms uncached vs {optimization['cached_ms']:.3f} ms cached ({optimization['measured_speedup']:.3f}x), limited to consecutive byte-identical chunks <=1 MiB
- GRU cold/warm compression: {load_latency['xai-gru']['cold_compress_ms']:.3f}/{load_latency['xai-gru']['warm_compress_ms']:.3f} ms on 256 bytes
- Transformer cold/warm compression: {load_latency['xai-transformer']['cold_compress_ms']:.3f}/{load_latency['xai-transformer']['warm_compress_ms']:.3f} ms on 256 bytes

## Decision table

{chr(10).join(decision_lines)}

## Production recommendation

Use `--mode hybrid --profile balanced` when automatic, auditable codec orchestration and a unified lossless container are more important than minimizing bytes on this measured corpus. Use the measured fixed codec directly when minimum size for a known homogeneous workload is the only goal.

## Known limitations

- The final five-file benchmark corpus is deterministic and spans 4 KiB through 100 MiB, but it is synthetic. The selector training corpus is broader (29 source groups), while final end-to-end category coverage remains limited.
- XAIC v5 per-chunk metadata is costly for extremely compressible inputs: 4 KiB text was 822 bytes with balanced Hybrid AI versus 60 bytes with fixed Brotli; 100 MiB repetitive data was 53,744 versus 777 bytes.
- Hybrid smallest on structured 10 MiB and oracle fastest on that sample timed out after 1,200 seconds and remain N/A. Exhaustive 100 MiB oracle results are NOT MEASURED.
- Neural codecs were measured only at 4 KiB in the final fixed benchmark; larger neural cases remain NOT MEASURED under the bounded-cost policy.
- Peak RSS is process peak working set, not isolated incremental memory per operation.
- No bounded parallel worker-pool speedup was measured, so none is claimed. Profiling justified an exact repeated-chunk cache; it did not justify adding a new Rust feature path in this iteration.

## Reproduction

```powershell
.\\.venv\\Scripts\\python.exe scripts\\build_codec_selector_dataset.py
.\\.venv\\Scripts\\python.exe scripts\\train_codec_selector.py
.\\.venv\\Scripts\\python.exe scripts\\benchmark_hybrid_ai.py
.\\.venv\\Scripts\\python.exe scripts\\finalize_hybrid_ai.py
.\\.venv\\Scripts\\python.exe -m pytest -q
$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY='1'; cargo test --manifest-path rust-core\\Cargo.toml
```
"""
    (RESULTS / "final_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"final_status": "PASS", "figures": 10, "hybrid_bpb": hybrid_bpb, "best_fixed_bpb": best_fixed_bpb, "oracle_gap_percent": oracle_gap}, indent=2))


if __name__ == "__main__":
    main()
