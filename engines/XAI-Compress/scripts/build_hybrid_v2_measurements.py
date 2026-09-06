"""Measure real codec strategies for the source-group-split V2 corpus."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))

from xai_compress.hybrid.codecs import Strategy, available_registry
from xai_compress.hybrid.features import extract_features
from xai_compress.hybrid.profiles import label_measurements, load_profiles
from xai_compress.hybrid.selector import measure_strategy

RESULTS = ENGINE / "results" / "hybrid_v2"


def bounded_regions(path: Path, maximum: int) -> bytes:
    size = path.stat().st_size
    if size <= maximum:
        return path.read_bytes()
    third = maximum // 3
    with path.open("rb") as handle:
        beginning = handle.read(third)
        handle.seek(max(0, size // 2 - third // 2))
        middle = handle.read(third)
        handle.seek(max(0, size - (maximum - 2 * third)))
        end = handle.read(maximum - 2 * third)
    return beginning + middle + end


def strategies(category: str, size: int) -> list[Strategy]:
    result = [
        Strategy("raw"),
        Strategy("zstd", 1), Strategy("zstd", 3), Strategy("zstd", 6), Strategy("zstd", 9),
        Strategy("brotli", 1), Strategy("brotli", 4), Strategy("brotli", 6), Strategy("brotli", 9),
        Strategy("deflate", 1), Strategy("deflate", 6), Strategy("deflate", 9),
        Strategy("lzma2", 0), Strategy("lzma2", 3),
    ]
    if size <= 256 << 10:
        result.extend((Strategy("brotli", 11), Strategy("lzma2", 6), Strategy("bzip2", 9)))
    if category in {"json", "xml", "csv", "html", "markdown", "source_code", "text", "logs", "structured"}:
        result.extend((Strategy("brotli", 6, "dictionary"), Strategy("zstd", 6, "dictionary")))
    if category in {"numeric", "database", "binary", "repetitive"}:
        result.extend((Strategy("zstd", 6, "delta"), Strategy("zstd", 6, "byte-shuffle")))
    return result


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=RESULTS / "corpus_manifest.csv")
    parser.add_argument("--max-real-bytes", type=int, default=64 << 10)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    if args.limit:
        manifest = manifest[: args.limit]
    registry = available_registry(device="cpu")
    rows = []
    failures = []
    feature_names = set()
    for index, source in enumerate(manifest, 1):
        path = Path(source["source_path"])
        actual_size = int(source["original_bytes"])
        maximum = actual_size if source["origin"] == "synthetic" else min(actual_size, args.max_real_bytes)
        data = bounded_regions(path, maximum)
        features = extract_features(data, file_size=actual_size, extension=path.suffix)
        feature_names.update(features)
        measured_count = 0
        for strategy in strategies(source["category"], len(data)):
            adapter = registry.get(strategy.codec)
            if adapter is None or not adapter.available() or strategy.level not in adapter.available_levels():
                continue
            try:
                measured = measure_strategy(data, strategy, registry)
            except Exception as exc:
                failures.append({"source_id": source["source_id"], "strategy": strategy.strategy_id, "error": f"{type(exc).__name__}: {exc}"})
                continue
            measured.pop("payload", None)
            measured["codec_metadata"] = json.dumps(measured["codec_metadata"], sort_keys=True)
            measured["transform_metadata"] = json.dumps(measured["transform_metadata"], sort_keys=True)
            rows.append({
                "sample_id": source["source_id"],
                "source_group": source["source_group"],
                "source_category": source["category"],
                "split": source["split"],
                "source_origin": source["origin"],
                "source_path": source["source_path"],
                "source_size": actual_size,
                "measurement_bytes": len(data),
                "source_sha256": source["sha256"],
                **features,
                **measured,
            })
            measured_count += 1
        if index % 25 == 0 or index == len(manifest):
            print(f"MEASURED {index}/{len(manifest)} rows={len(rows)} last_strategies={measured_count}", flush=True)
    dataset = RESULTS / "selector_dataset.csv"
    write_csv(dataset, rows)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["sample_id"]].append(row)
    labels = []
    profiles = load_profiles()
    for sample_id, values in sorted(grouped.items()):
        for profile in profiles:
            winner = label_measurements(values, profile, profiles)[0]
            labels.append({
                "sample_id": sample_id,
                "source_group": winner["source_group"],
                "source_category": winner["source_category"],
                "split": winner["split"],
                "profile": profile,
                "best_strategy": winner["strategy_id"],
                "best_codec": winner["codec"],
                "best_level": winner["level"],
                "best_transform": winner["transform"],
                "expected_bpb": winner["actual_bpb"],
                "expected_compression_time": winner["compression_seconds"],
                "expected_decompression_time": winner["decompression_seconds"],
                "profile_score": winner["profile_score"],
            })
    write_csv(RESULTS / "selector_labels.csv", labels)
    write_csv(RESULTS / "measurement_failures.csv", failures or [{"source_id": "N/A", "strategy": "N/A", "error": "none"}])
    (RESULTS / "feature_schema.json").write_text(json.dumps({
        "features": sorted(feature_names),
        "categorical": ["extension", "mime_category", "magic_signature_category"],
    }, indent=2), encoding="utf-8")
    summary = {
        "source_groups": len(grouped),
        "measurements": len(rows),
        "labels": len(labels),
        "failures": len(failures),
        "splits": dict(Counter(source["split"] for source in manifest)),
        "measurement_policy": "real files are measured on bounded beginning/middle/end regions up to max_real_bytes; controlled synthetic multi-size files are measured at full size",
        "max_real_bytes": args.max_real_bytes,
    }
    (RESULTS / "measurement_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
