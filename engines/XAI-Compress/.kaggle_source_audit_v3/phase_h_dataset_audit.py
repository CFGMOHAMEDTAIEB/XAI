from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


COMPRESSED_EXTENSIONS = {".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".mp4", ".mkv", ".jpg", ".jpeg", ".png", ".webp"}
MODEL_EXTENSIONS = {".pt", ".pth", ".safetensors", ".model", ".bin", ".onnx"}
DOMAIN_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".xml", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".conf", ".txt", ".md", ".rst", ".csv", ".log", ".sql", ".html",
    ".css", ".scss", ".java", ".cs", ".cpp", ".c", ".h", ".hpp", ".go", ".rs", ".sh",
    ".bat", ".ps1", "",
}


def classify(extension: str) -> str:
    if extension in COMPRESSED_EXTENSIONS:
        return "already_compressed_or_media"
    if extension in MODEL_EXTENSIONS:
        return "binary_model"
    if extension in DOMAIN_EXTENSIONS:
        return "source_text_configuration"
    return "other"


def audit(root: Path, largest_count: int = 20) -> tuple[dict, list[dict]]:
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        extension = path.suffix.lower()
        records.append({
            "file": str(path), "extension": extension or "[none]", "bytes": size,
            "category": classify(extension),
        })
    total_bytes = sum(row["bytes"] for row in records)
    by_extension = defaultdict(lambda: {"files": 0, "bytes": 0})
    by_category = defaultdict(lambda: {"files": 0, "bytes": 0})
    for row in records:
        by_extension[row["extension"]]["files"] += 1
        by_extension[row["extension"]]["bytes"] += row["bytes"]
        by_category[row["category"]]["files"] += 1
        by_category[row["category"]]["bytes"] += row["bytes"]
    for value in by_extension.values():
        value["percentage_of_corpus"] = 100 * value["bytes"] / total_bytes if total_bytes else 0.0
    for value in by_category.values():
        value["percentage_of_corpus"] = 100 * value["bytes"] / total_bytes if total_bytes else 0.0
    sizes = [row["bytes"] for row in records]
    report = {
        "root": str(root), "number_of_files": len(records), "total_bytes": total_bytes,
        "file_extensions": sorted(by_extension), "files_per_extension": {k: v["files"] for k, v in sorted(by_extension.items())},
        "bytes_per_extension": {k: v["bytes"] for k, v in sorted(by_extension.items())},
        "extension_statistics": dict(sorted(by_extension.items())),
        "category_statistics": dict(sorted(by_category.items())),
        "average_file_size": statistics.mean(sizes) if sizes else 0,
        "median_file_size": statistics.median(sizes) if sizes else 0,
        "min_file_size": min(sizes) if sizes else 0, "max_file_size": max(sizes) if sizes else 0,
        "largest_files": sorted(records, key=lambda row: (-row["bytes"], row["file"]))[:largest_count],
        "smallest_files": sorted(records, key=lambda row: (row["bytes"], row["file"]))[:largest_count],
        "domain_focused_extensions": sorted(DOMAIN_EXTENSIONS),
        "resembles_real_source_compression_benchmark": (
            by_category["source_text_configuration"]["bytes"] >= total_bytes * 0.5
            if total_bytes else False
        ),
    }
    return report, records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--json", type=Path, default=Path("phase_h_dataset_report.json"))
    parser.add_argument("--csv", type=Path, default=Path("phase_h_dataset_report.csv"))
    args = parser.parse_args()
    report, records = audit(args.data_dir)
    args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "extension", "bytes", "category"])
        writer.writeheader(); writer.writerows(records)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()