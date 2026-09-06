"""Build a deterministic, source-group-split Hybrid V2 corpus manifest."""
from __future__ import annotations

import csv
import hashlib
import math
import os
import random
from collections import Counter, defaultdict
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
WORKSPACE = ENGINE.parents[1]
DATA = ENGINE / "data" / "hybrid_selector"
SYNTHETIC = DATA / "synthetic"
RESULTS = ENGINE / "results" / "hybrid_v2"
SEED = 20260901

EXCLUDED_PARTS = {
    ".git", ".venv", "__pycache__", "node_modules", "target",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "kaggle_debug",
}

CATEGORY_BY_EXTENSION = {
    ".txt": "text", ".md": "markdown", ".rst": "text", ".log": "logs",
    ".py": "source_code", ".js": "source_code", ".ts": "source_code",
    ".tsx": "source_code", ".java": "source_code", ".c": "source_code",
    ".cpp": "source_code", ".h": "source_code", ".rs": "source_code",
    ".cs": "source_code", ".dart": "source_code", ".ps1": "source_code",
    ".bat": "source_code", ".json": "json", ".ipynb": "json",
    ".xml": "xml", ".svg": "xml", ".csv": "csv", ".html": "html",
    ".htm": "html", ".pdf": "pdf", ".png": "image", ".jpg": "image",
    ".jpeg": "image", ".webp": "image", ".wav": "audio", ".mp3": "audio",
    ".ogg": "audio", ".mp4": "video", ".mkv": "video", ".avi": "video",
    ".zip": "archive", ".gz": "archive", ".7z": "archive", ".xz": "archive",
    ".bz2": "archive", ".pt": "model", ".pth": "model", ".onnx": "model",
    ".db": "database", ".sqlite": "database", ".npy": "numeric",
    ".npz": "numeric", ".bin": "binary", ".exe": "executable", ".dll": "executable",
}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def category(path: Path) -> str:
    return CATEGORY_BY_EXTENSION.get(path.suffix.lower(), "binary")


def size_bucket(size: int) -> str:
    if size < 16 << 10:
        return "lt_16KiB"
    if size < 64 << 10:
        return "16_64KiB"
    if size < 1 << 20:
        return "64KiB_1MiB"
    if size < 10 << 20:
        return "1_10MiB"
    return "gt_10MiB"


def split_for(group: str) -> str:
    bucket = int(hashlib.sha256((str(SEED) + group).encode()).hexdigest()[:8], 16) % 100
    return "train" if bucket < 70 else "validation" if bucket < 85 else "test"


def write_pattern(path: Path, size: int, pattern: bytes) -> None:
    remaining = size
    with path.open("wb") as handle:
        while remaining:
            block = pattern[: min(remaining, len(pattern))]
            handle.write(block)
            remaining -= len(block)


def make_synthetic() -> list[Path]:
    SYNTHETIC.mkdir(parents=True, exist_ok=True)
    sizes = [4 << 10, 16 << 10, 64 << 10, 256 << 10, 1 << 20, 4 << 20, 10 << 20]
    paths = []
    for size in sizes:
        label = f"{size // 1024}KiB"
        structured = SYNTHETIC / f"structured_{label}.json"
        repetitive = SYNTHETIC / f"repetitive_{label}.bin"
        random_path = SYNTHETIC / f"high_entropy_{label}.rand"
        write_pattern(structured, size, b'{"id":123,"kind":"hybrid-v2","value":456789,"ok":true}\n' * 1024)
        write_pattern(repetitive, size, b"HYBRID-V2-REPETITIVE|" * 4096)
        rng = random.Random(SEED + size)
        with random_path.open("wb") as handle:
            remaining = size
            while remaining:
                block = rng.randbytes(min(1 << 20, remaining))
                handle.write(block)
                remaining -= len(block)
        paths.extend((structured, repetitive, random_path))
    return paths


def real_candidates() -> list[Path]:
    result = []
    for path in WORKSPACE.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        relative_parts = set(path.relative_to(WORKSPACE).parts)
        if relative_parts & EXCLUDED_PARTS:
            continue
        rendered = str(path).lower()
        if "\\.kaggle" in rendered or "/.kaggle" in rendered:
            continue
        if "results\\pytest" in rendered or "results/pytest" in rendered:
            continue
        if path.is_relative_to(RESULTS) or path.is_relative_to(SYNTHETIC):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if 0 < size <= 64 << 20:
            result.append(path)
    return sorted(result, key=lambda path: str(path).lower())


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    synthetic = make_synthetic()
    by_category: dict[str, list[Path]] = defaultdict(list)
    for path in real_candidates():
        by_category[category(path)].append(path)
    selected = []
    # Round-robin prevents source code from consuming the whole 1,500-file cap.
    positions = Counter()
    categories = sorted(by_category)
    while len(selected) < 1500:
        progressed = False
        for name in categories:
            index = positions[name]
            if index < len(by_category[name]):
                selected.append(by_category[name][index])
                positions[name] += 1
                progressed = True
                if len(selected) >= 1500:
                    break
        if not progressed:
            break
    rows = []
    seen_hashes = set()
    for path, origin in [(path, "real") for path in selected] + [(path, "synthetic") for path in synthetic]:
        value = sha256(path)
        if origin == "real" and value in seen_hashes:
            continue
        seen_hashes.add(value)
        size = path.stat().st_size
        group = f"{origin}:{path.relative_to(WORKSPACE) if path.is_relative_to(WORKSPACE) else path.name}"
        rows.append({
            "source_id": hashlib.sha256(group.encode()).hexdigest()[:20],
            "source_group": group,
            "source_path": str(path.resolve()),
            "origin": origin,
            "category": category(path) if origin == "real" else ("high_entropy" if path.suffix == ".rand" else "structured" if path.suffix == ".json" else "repetitive"),
            "original_bytes": size,
            "log2_file_size": math.log2(max(1, size)),
            "size_bucket": size_bucket(size),
            "sha256": value,
            "split": split_for(group),
        })
    fields = list(rows[0])
    for output in (DATA / "corpus_manifest.csv", RESULTS / "corpus_manifest.csv"):
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    counts = Counter(row["split"] for row in rows)
    origins = Counter(row["origin"] for row in rows)
    categories_count = Counter(row["category"] for row in rows)
    print({"files": len(rows), "splits": dict(counts), "origins": dict(origins), "categories": dict(categories_count)})
    if origins["real"] < 1000:
        raise RuntimeError(f"real-file target not met: {origins['real']} < 1000")


if __name__ == "__main__":
    main()
