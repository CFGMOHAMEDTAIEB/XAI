from __future__ import annotations

import hashlib
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Sequence

EXCLUDED_EXTENSIONS = {".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".xaic", ".pt", ".pth", ".xcomp"}


def content_id(path: Path, sample: int = 65536) -> str:
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    digest = hashlib.blake2b(digest_size=16)
    digest.update(struct.pack("<Q", size))
    with path.open("rb") as handle:
        digest.update(handle.read(sample))
        if size > sample * 2:
            handle.seek(size // 2)
            digest.update(handle.read(sample))
            handle.seek(max(0, size - sample))
            digest.update(handle.read(sample))
    return digest.hexdigest()


def discover_files(root: Path, include_archives: bool = False) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if not include_archives and path.suffix.lower() in EXCLUDED_EXTENSIONS:
            continue
        files.append(path)
    return files


def dedupe_paths(paths: Sequence[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        ident = content_id(path)
        if not ident or ident in seen:
            continue
        seen.add(ident)
        unique.append(path)
    return unique


def split_paths(paths: Sequence[Path], seed: int = 42, val_frac: float = 0.1, test_frac: float = 0.1):
    import random

    items = list(paths)
    rng = random.Random(seed)
    rng.shuffle(items)
    n = len(items)
    n_test = max(1, int(n * test_frac)) if n >= 3 else 0
    n_val = max(1, int(n * val_frac)) if n >= 2 else 0
    test = items[:n_test]
    val = items[n_test : n_test + n_val]
    train = items[n_test + n_val :]
    if not train and items:
        train, val, test = items, [], []
    return train, val, test


def dataset_report(root: Path, seed: int = 42, sample_bytes: int = 1 << 20) -> dict:
    """Return bounded, JSON-serializable corpus statistics.

    Entropy is measured on at most ``sample_bytes`` per file, so auditing a
    very large corpus remains memory bounded. Split counts are file-level and
    computed after content deduplication.
    """
    from ..analyzer import byte_entropy

    discovered = discover_files(Path(root))
    unique = dedupe_paths(discovered)
    train, validation, test = split_paths(unique, seed=seed)
    sizes: list[int] = []
    entropies: list[float] = []
    extensions: Counter[str] = Counter()
    byte_counts = [0] * 256
    sampled_bytes = 0
    corrupt: list[str] = []
    for path in unique:
        try:
            size = path.stat().st_size
            with path.open("rb") as handle:
                sample = handle.read(sample_bytes)
        except OSError:
            corrupt.append(str(path))
            continue
        sizes.append(size)
        extensions[path.suffix.lower() or "<none>"] += 1
        entropies.append(byte_entropy(sample))
        sampled_bytes += len(sample)
        for value in sample:
            byte_counts[value] += 1
    return {
        "root": str(Path(root).resolve()),
        "seed": seed,
        "files_discovered": len(discovered),
        "files_unique": len(unique),
        "duplicates_removed": len(discovered) - len(unique),
        "total_size_bytes": sum(sizes),
        "min_size_bytes": min(sizes) if sizes else None,
        "max_size_bytes": max(sizes) if sizes else None,
        "mean_size_bytes": sum(sizes) / len(sizes) if sizes else None,
        "mean_sample_entropy_bpb": sum(entropies) / len(entropies) if entropies else None,
        "sampled_bytes": sampled_bytes,
        "extensions": dict(sorted(extensions.items())),
        "split_files": {"train": len(train), "validation": len(validation), "test": len(test)},
        "file_sizes": sizes,
        "sample_entropies": entropies,
        "byte_frequencies": byte_counts,
        "unreadable_files": corrupt,
    }
