from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_PATH = ROOT / "configs" / "hybrid_profiles.json"
METRIC_KEYS = ("size", "compression_time", "decompression_time", "memory")


def load_profiles(path: str | Path | None = None) -> dict[str, dict[str, float]]:
    source = Path(path) if path else DEFAULT_PROFILE_PATH
    profiles = json.loads(source.read_text(encoding="utf-8"))
    for name, weights in profiles.items():
        if set(weights) != set(METRIC_KEYS):
            raise ValueError(f"profile {name!r} has an invalid weight schema")
        values = [float(weights[key]) for key in METRIC_KEYS]
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError(f"profile {name!r} has invalid weights")
        total = sum(values)
        if total <= 0:
            raise ValueError(f"profile {name!r} has zero total weight")
        profiles[name] = {key: float(weights[key]) / total for key in METRIC_KEYS}
    return profiles


def normalized_scores(rows: list[dict], weights: dict[str, float]) -> list[float]:
    """Return deterministic min-max weighted costs for measured strategies."""
    if not rows:
        return []
    columns = {
        "size": [float(row["compressed_bytes"]) for row in rows],
        "compression_time": [float(row["compression_seconds"]) for row in rows],
        "decompression_time": [float(row["decompression_seconds"]) for row in rows],
        "memory": [float(row.get("peak_rss", 0.0) or 0.0) for row in rows],
    }
    normalized: dict[str, list[float]] = {}
    for key, values in columns.items():
        low, high = min(values), max(values)
        normalized[key] = [0.0 for _ in values] if high == low else [(value - low) / (high - low) for value in values]
    return [
        sum(weights[key] * normalized[key][index] for key in METRIC_KEYS)
        for index in range(len(rows))
    ]


def label_measurements(rows: list[dict], profile: str, profiles: dict | None = None) -> list[dict]:
    values = profiles or load_profiles()
    if profile not in values:
        raise ValueError(f"unknown profile: {profile}")
    scores = normalized_scores(rows, values[profile])
    labeled = [dict(row, profile=profile, profile_score=score) for row, score in zip(rows, scores)]
    labeled.sort(key=lambda row: (row["profile_score"], row["compressed_bytes"], row["strategy_id"]))
    return labeled
