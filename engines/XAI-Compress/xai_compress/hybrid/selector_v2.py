"""Confidence-aware, bounded Selector V2 decision policy."""
from __future__ import annotations

import hashlib
import math
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .codecs import CodecAdapter, Strategy, available_registry
from .features import extract_features
from .ml import SelectorArtifact
from .profiles import label_measurements
from .selector import measure_strategy, rule_candidates

if TYPE_CHECKING:
    from .context import CompressionContext

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "checkpoints" / "selector_v2" / "best.json"
COMPRESSED_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"PK\x03\x04", b"\x1f\x8b", b"7z\xbc\xaf'\x1c", b"Rar!\x1a\x07", b"OggS")


@dataclass(frozen=True)
class V2Selection:
    strategy: Strategy
    confidence: float | None
    route: str
    candidates_benchmarked: int
    feature_scan_ms: float
    inference_ms: float
    candidate_generation_ms: float
    microbenchmark_ms: float
    cache_hit: bool
    direct_reason: str | None
    minimum_gain_applied: bool
    ranked_candidates: tuple[tuple[str, float], ...]


def _quick_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


# Phase 5: Extended magic signatures for pre-compressed detection
# Includes additional formats that are already compressed or don't benefit from compression
EXTENDED_MAGIC_SIGNATURES = COMPRESSED_MAGIC + (
    b"BZh",      # bzip2
    b"\xfd7zXZ", # xz
    b"LZIP",     # lzip
    b"\xc0\xad\xde\xc0",  # RAR5
)


def quick_bypass(data: bytes, runtime_generation: str = "v3") -> tuple[Strategy | None, str | None]:
    """Detect files that do not benefit from selection/compression.

    Frozen Hybrid V2 keeps the original bypass: tiny files at 256 B, the
    original compressed-magic set, and entropy 7.2 on an 8 KiB sample.
    Hybrid V3 keeps the Phase 5 production bypass.
    """
    if len(data) == 0:
        return None, None
    generation = "v2" if runtime_generation == "v2" else "v3"
    if generation == "v2":
        if len(data) <= 256:
            return Strategy("raw"), "tiny_input"
        if any(data.startswith(magic) for magic in COMPRESSED_MAGIC):
            return Strategy("raw"), "precompressed_detected"
        sample = data[:8192]
        if len(sample) >= 4096 and _quick_entropy(sample) >= 7.2:
            return Strategy("raw"), "high_entropy_incompressible"
        return None, None

    if len(data) <= 64:
        return Strategy("raw"), "tiny_input"
    sample = data[:4096]
    if any(sample.startswith(magic) for magic in EXTENDED_MAGIC_SIGNATURES):
        return Strategy("raw"), "precompressed_detected"
    if len(sample) >= 256 and _quick_entropy(sample) >= 7.6:
        return Strategy("raw"), "high_entropy_incompressible"
    return None, None


def small_file_rule(data: bytes, extension: str = "") -> tuple[Strategy | None, str | None]:
    """Phase 10-style small-file fast path.

    Keep this extremely narrow so the standard selection pipeline continues to.
    benchmark realistic small payloads rather than forcing a truncated direct route.
    """
    if not data:
        return None, None
    if len(data) <= 64:
        return Strategy("raw"), "tiny_input"
    if len(data) > 256:
        return None, None
    text_like_ext = (".txt", ".md", ".json", ".csv", ".log", ".xml", ".html", ".yaml", ".yml",
                     ".toml", ".ini", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".rs", ".go",
                     ".cs", ".sql", ".sh")
    ext = extension.lower()
    sample = data[: min(len(data), 128)]
    has_textish_bytes = bool(sample) and b"\x00" not in sample and (sample.strip() != b"")
    is_textual = has_textish_bytes and (ext in text_like_ext or any(ch in b"\t\r\n " for ch in sample[:64]))
    if is_textual:
        return Strategy("brotli", 1), "small_text_brotli_fast_path"
    return Strategy("raw"), "small_noncompressible_fast_path"


class HybridSelectorV2:
    def __init__(
        self,
        *,
        profile: str = "balanced",
        model_path: str | Path = DEFAULT_MODEL,
        registry: dict[str, CodecAdapter] | None = None,
        microbench_bytes: int = 16 << 10,
        exact_cache_entries: int = 64,
        routing_mode: str = "top3",
        preloaded_artifact: "SelectorArtifact | None" = None,
        context: "CompressionContext | None" = None,
        runtime_generation: str = "v3",
    ):
        if routing_mode not in {"confidence", "top1", "top2", "top3"}:
            raise ValueError(f"unknown Selector V2 routing mode: {routing_mode}")
        if runtime_generation not in {"v2", "v3"}:
            raise ValueError(f"unknown runtime generation: {runtime_generation}")
        self.profile = profile
        self.model_path = Path(model_path)
        self.registry = registry or available_registry()
        self.microbench_bytes = max(4096, min(int(microbench_bytes), 64 << 10))
        self.exact_cache_entries = max(1, min(int(exact_cache_entries), 256))
        self.routing_mode = routing_mode
        self.runtime_generation = runtime_generation
        self._artifact: SelectorArtifact | None = preloaded_artifact
        self._cache: OrderedDict[tuple[str, str, str, int, int, str], V2Selection] = OrderedDict()
        self._context: "CompressionContext | None" = context if runtime_generation != "v2" else None

    def _load(self) -> SelectorArtifact:
        if self._artifact is None:
            self._artifact = SelectorArtifact.load(self.model_path)
        return self._artifact

    def _available(self, ranked: list[tuple[str, float]], size: int) -> list[tuple[Strategy, float]]:
        output = []
        for strategy_id, probability in ranked:
            try:
                strategy = Strategy.parse(strategy_id)
            except Exception:
                continue
            adapter = self.registry.get(strategy.codec)
            if adapter is None or not adapter.available() or strategy.level not in adapter.available_levels():
                continue
            if strategy.codec in {"xai-gru", "xai-transformer"} and size > 4096:
                continue
            if strategy.codec == "xai-static" and size > (1 << 20):
                continue
            output.append((strategy, probability))
        return output

    def select(self, data: bytes, extension: str = "", file_size: int | None = None) -> V2Selection:
        raw = bytes(data)
        effective_size = len(raw) if file_size is None else int(file_size)
        cache_key = (hashlib.sha256(raw).hexdigest(), extension.lower(), self.profile, self.microbench_bytes, effective_size, self.routing_mode, self.runtime_generation)
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return V2Selection(cached.strategy, cached.confidence, cached.route, 0, 0.0, 0.0, 0.0, 0.0, True, cached.direct_reason, cached.minimum_gain_applied, cached.ranked_candidates)
        quick_started = time.perf_counter()
        direct, reason = quick_bypass(raw, self.runtime_generation)
        quick_ms = (time.perf_counter() - quick_started) * 1000
        if direct is not None:
            selection = V2Selection(direct, 1.0, "direct_bypass", 0, quick_ms, 0.0, 0.0, 0.0, False, reason, False, ((direct.strategy_id, 1.0),))
            self._remember(cache_key, selection)
            return selection

        if self.runtime_generation != "v2":
            direct, reason = small_file_rule(raw, extension)
            if direct is not None:
                selection = V2Selection(direct, 1.0, "small_file_rule_direct", 0, quick_ms, 0.0, 0.0, 0.0, False, reason, False, ((direct.strategy_id, 1.0),))
                self._remember(cache_key, selection)
                return selection

        feature_started = time.perf_counter()
        sample = raw[: self.microbench_bytes]
        # Phase 4 optimization: Use context feature cache if available
        if self._context is not None:
            features = self._context.extract_and_cache_features(sample, extension, effective_size)
        else:
            features = extract_features(sample, file_size=effective_size, extension=extension)
        feature_ms = quick_ms + (time.perf_counter() - feature_started) * 1000
        candidate_started = time.perf_counter()
        try:
            artifact = self._load()
            inference_started = time.perf_counter()
            predicted = artifact.predict_top_k(features, self.profile, 3)
            inference_ms = (time.perf_counter() - inference_started) * 1000
            available = self._available(predicted, len(raw))
            thresholds = artifact.metrics.get("confidence_thresholds", {}).get(self.profile, {"low": 0.5, "high": 0.8})
        except Exception:
            inference_ms = 0.0
            predicted = [(item.strategy_id, 0.0) for item in rule_candidates(features, self.profile, 3)]
            available = self._available(predicted, len(raw))
            thresholds = {"low": 1.0, "high": 1.1}
        candidate_ms = max(0.0, (time.perf_counter() - candidate_started) * 1000 - inference_ms)
        if not available:
            available = [(Strategy("raw"), 0.0)]
        confidence = available[0][1]
        if self.routing_mode == "confidence":
            count = 1 if confidence >= float(thresholds["high"]) else 2 if confidence >= float(thresholds["low"]) else 3
        else:
            count = int(self.routing_mode[-1])
        count = min(count, len(available))
        candidates = available[:count]
        route = (
            "high_confidence_direct" if count == 1 and self.routing_mode == "confidence"
            else "top1_direct" if count == 1
            else f"top_{count}_microbenchmark"
        )
        micro_ms = 0.0
        gain_applied = False
        if count == 1:
            chosen = candidates[0][0]
        else:
            measured = []
            started = time.perf_counter()
            for strategy, _ in candidates:
                try:
                    measured.append(measure_strategy(sample, strategy, self.registry))
                except Exception:
                    continue
            micro_ms = (time.perf_counter() - started) * 1000
            if measured:
                ranked_measured = label_measurements(measured, self.profile)
                chosen = Strategy.parse(ranked_measured[0]["strategy_id"])
                baseline = next((row for row in measured if row["codec"] == "zstd" and row["level"] in {1, 3}), None)
                winner = ranked_measured[0]
                if baseline is not None and chosen.codec != baseline["codec"]:
                    gain = int(baseline["compressed_bytes"]) - int(winner["compressed_bytes"])
                    # Compact v6 strategy/framing needs roughly 12 additional
                    # bytes when departing from the baseline strategy.
                    if gain <= 12 and self.profile != "smallest":
                        chosen = Strategy.parse(baseline["strategy_id"])
                        gain_applied = True
                        route += "_minimum_gain_baseline"
            else:
                chosen = Strategy("raw")
                route = "safe_fallback"
        selection = V2Selection(
            chosen, confidence, route, len(candidates) if count > 1 else 0,
            feature_ms, inference_ms, candidate_ms, micro_ms, False, None,
            gain_applied, tuple((strategy.strategy_id, probability) for strategy, probability in available),
        )
        self._remember(cache_key, selection)
        return selection

    def _remember(self, key, selection: V2Selection) -> None:
        self._cache[key] = selection
        self._cache.move_to_end(key)
        while len(self._cache) > self.exact_cache_entries:
            self._cache.popitem(last=False)
