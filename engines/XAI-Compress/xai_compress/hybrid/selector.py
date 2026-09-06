from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .codecs import CodecAdapter, Strategy, available_registry
from .features import extract_features
from .ml import SelectorArtifact
from .profiles import label_measurements, load_profiles
from .transforms import get_transform

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "checkpoints" / "selector" / "best.json"


def peak_rss_mb() -> float | None:
    try:
        import psutil

        info = psutil.Process().memory_info()
        return float(getattr(info, "peak_wset", info.rss)) / (1 << 20)
    except (ImportError, OSError):
        return None


def candidate_catalog(include_neural: bool = True) -> list[Strategy]:
    candidates = [
        Strategy("raw"),
        Strategy("zstd", 1), Strategy("zstd", 3), Strategy("zstd", 6), Strategy("zstd", 9),
        Strategy("brotli", 1), Strategy("brotli", 4), Strategy("brotli", 6), Strategy("brotli", 9), Strategy("brotli", 11),
        Strategy("deflate", 1), Strategy("deflate", 6), Strategy("deflate", 9),
        Strategy("lzma2", 0), Strategy("lzma2", 3), Strategy("lzma2", 6),
        Strategy("bzip2", 1), Strategy("bzip2", 9),
        Strategy("xai-static"),
        Strategy("zstd", 3, "rle"),
        Strategy("zstd", 3, "delta"),
        Strategy("zstd", 3, "byte-shuffle"),
        Strategy("zstd", 3, "zero-run"),
        Strategy("zstd", 3, "dictionary"),
        Strategy("brotli", 6, "dictionary"),
        Strategy("deflate", 6, "delta"),
        Strategy("lzma2", 3, "byte-shuffle"),
    ]
    if include_neural:
        candidates += [Strategy("xai-gru"), Strategy("xai-transformer")]
    return candidates


def rule_candidates(features: dict[str, Any], profile: str, top_k: int = 3) -> list[Strategy]:
    size = int(features.get("file_size", 0))
    entropy = float(features.get("byte_entropy", 0.0))
    compressed = bool(features.get("is_already_compressed"))
    text = bool(features.get("is_text_like"))
    repetitive = float(features.get("repetition_score", 0.0)) > 0.25 or float(features.get("run_length_score", 0.0)) > 0.2
    structured = float(features.get("structured_text_score", 0.0)) > 0.25
    if size < 96:
        ordered = [Strategy("raw"), Strategy("zstd", 1), Strategy("deflate", 1)]
    elif compressed and entropy >= 7.2:
        ordered = [Strategy("raw"), Strategy("zstd", 1), Strategy("deflate", 1)]
    elif profile == "fastest":
        ordered = [Strategy("zstd", 1), Strategy("deflate", 1), Strategy("raw")]
    elif repetitive:
        ordered = [Strategy("zstd", 9, "rle"), Strategy("brotli", 9), Strategy("lzma2", 6)]
    elif text and structured:
        ordered = [Strategy("brotli", 9, "dictionary"), Strategy("zstd", 9), Strategy("lzma2", 6)]
    elif text:
        ordered = [Strategy("brotli", 9), Strategy("zstd", 9), Strategy("lzma2", 6)]
    elif profile == "smallest":
        ordered = [Strategy("lzma2", 6), Strategy("brotli", 9), Strategy("zstd", 9)]
    else:
        ordered = [Strategy("zstd", 3), Strategy("brotli", 6), Strategy("deflate", 6)]
    return ordered[: max(1, int(top_k))]


def measure_strategy(
    data: bytes,
    strategy: Strategy,
    registry: dict[str, CodecAdapter],
) -> dict[str, Any]:
    if strategy.codec not in registry:
        raise ValueError(f"codec unavailable: {strategy.codec}")
    transform = get_transform(strategy.transform)
    transformed, transform_metadata = transform.forward(data)
    adapter = registry[strategy.codec]
    started = time.perf_counter()
    result = adapter.compress(transformed, strategy.level)
    compression_seconds = time.perf_counter() - started
    started = time.perf_counter()
    decoded_transform = adapter.decompress(result.payload, result.metadata)
    restored = transform.inverse(decoded_transform, transform_metadata)
    decompression_seconds = time.perf_counter() - started
    if restored != data:
        raise RuntimeError(f"strategy round trip failed: {strategy.strategy_id}")
    return {
        "strategy_id": strategy.strategy_id,
        "codec": strategy.codec,
        "level": strategy.level,
        "transform": strategy.transform,
        "transformed_bytes": len(transformed),
        "compressed_bytes": len(result.payload),
        "actual_bpb": 8 * len(result.payload) / max(1, len(data)),
        "ratio": len(data) / max(1, len(result.payload)),
        "compression_seconds": compression_seconds,
        "decompression_seconds": decompression_seconds,
        "compression_MB_s": len(data) / (1 << 20) / max(compression_seconds, 1e-12),
        "decompression_MB_s": len(data) / (1 << 20) / max(decompression_seconds, 1e-12),
        "peak_rss": peak_rss_mb(),
        "sha_pass": True,
        "codec_metadata": result.metadata,
        "transform_metadata": transform_metadata,
        "payload": result.payload,
    }


@dataclass
class SelectionResult:
    strategy: Strategy
    selector_mode: str
    profile: str
    feature_scan_ms: float
    model_inference_ms: float
    microbenchmark_ms: float
    fallback_reason: str | None
    ranked_candidates: list[dict[str, Any]]
    measured: dict[str, Any] | None = None
    candidate_generation_ms: float = 0.0

    def metadata(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy.strategy_id,
            "selector_mode": self.selector_mode,
            "profile": self.profile,
            "feature_scan_ms": self.feature_scan_ms,
            "model_inference_ms": self.model_inference_ms,
            "microbenchmark_ms": self.microbenchmark_ms,
            "fallback_reason": self.fallback_reason,
            "ranked_candidates": self.ranked_candidates,
        }


class HybridSelector:
    def __init__(
        self,
        *,
        profile: str = "balanced",
        mode: str = "ai-benchmark",
        top_k: int = 3,
        microbench_bytes: int = 64 << 10,
        model_path: str | Path | None = None,
        registry: dict[str, CodecAdapter] | None = None,
        collect_path: str | Path | None = None,
    ):
        profiles = load_profiles()
        if profile not in profiles:
            raise ValueError(f"unknown profile: {profile}")
        if mode not in {"ai", "ai-benchmark", "benchmark-only", "rules"}:
            raise ValueError(f"unknown selector mode: {mode}")
        self.profile = profile
        self.mode = mode
        self.top_k = max(1, int(top_k))
        self.microbench_bytes = max(1, int(microbench_bytes))
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL
        self.registry = registry or available_registry()
        self.collect_path = Path(collect_path) if collect_path else None
        self._artifact: SelectorArtifact | None = None
        # Keep at most one bounded chunk.  Consecutive identical chunks are
        # common in sparse/repetitive streams, and their feature vector and
        # strategy decision are exactly identical for a fixed extension and
        # selector configuration.  Exact byte equality avoids hash-collision
        # assumptions and keeps deterministic output unchanged.
        self._last_data: bytes | None = None
        self._last_extension = ""
        self._last_selection: SelectionResult | None = None

    def _cached_selection(self, data: bytes, extension: str) -> SelectionResult | None:
        if (
            self._last_selection is None
            or self._last_extension != extension
            or self._last_data != data
        ):
            return None
        previous = self._last_selection
        return SelectionResult(
            strategy=previous.strategy,
            selector_mode=previous.selector_mode,
            profile=previous.profile,
            feature_scan_ms=0.0,
            model_inference_ms=0.0,
            microbenchmark_ms=0.0,
            fallback_reason=previous.fallback_reason,
            ranked_candidates=list(previous.ranked_candidates),
            measured=previous.measured,
            candidate_generation_ms=0.0,
        )

    def _remember_selection(self, data: bytes, extension: str, selection: SelectionResult) -> SelectionResult:
        # One MiB matches the default streaming chunk and bounds cache memory.
        # Larger custom chunks still use the normal measured path.
        if len(data) <= (1 << 20):
            self._last_data = data
            self._last_extension = extension
            self._last_selection = selection
        else:
            self._last_data = None
            self._last_extension = ""
            self._last_selection = None
        return selection

    def _load_artifact(self) -> tuple[SelectorArtifact | None, str | None]:
        if self._artifact is not None:
            return self._artifact, None
        if not self.model_path.is_file():
            return None, "selector model unavailable"
        try:
            self._artifact = SelectorArtifact.load(self.model_path)
            return self._artifact, None
        except Exception as exc:
            return None, f"selector model load failed: {type(exc).__name__}"

    def _available(self, strategies: list[Strategy]) -> list[Strategy]:
        result = []
        for strategy in strategies:
            adapter = self.registry.get(strategy.codec)
            if adapter is not None and adapter.available() and strategy.level in adapter.available_levels():
                result.append(strategy)
        return result

    @staticmethod
    def _bounded_cost_candidates(strategies: list[Strategy], data_size: int) -> list[Strategy]:
        """Avoid known disproportionate pure-Python/neural costs on large chunks."""
        return [
            strategy
            for strategy in strategies
            if not (strategy.codec in {"xai-gru", "xai-transformer"} and data_size > 4096)
            and not (strategy.codec == "xai-static" and data_size > (1 << 20))
        ]

    def select(self, data: bytes, extension: str = "") -> SelectionResult:
        cached = self._cached_selection(data, extension)
        if cached is not None:
            return cached
        feature_started = time.perf_counter()
        features = extract_features(data[: self.microbench_bytes], file_size=len(data), extension=extension)
        feature_ms = (time.perf_counter() - feature_started) * 1000
        fallback: str | None = None
        inference_ms = 0.0
        candidate_started = time.perf_counter()
        if self.mode in {"ai", "ai-benchmark"}:
            artifact, fallback = self._load_artifact()
            if artifact is not None:
                started = time.perf_counter()
                predictions = artifact.predict_top_k(features, self.profile, self.top_k)
                inference_ms = (time.perf_counter() - started) * 1000
                candidates = self._bounded_cost_candidates(
                    self._available([Strategy.parse(strategy) for strategy, _ in predictions]), len(data)
                )
                ranked = [{"strategy_id": strategy, "probability": probability} for strategy, probability in predictions]
                if not candidates:
                    fallback = "all predicted codecs unavailable"
                    candidates = self._bounded_cost_candidates(
                        self._available(rule_candidates(features, self.profile, self.top_k)), len(data)
                    )
            else:
                candidates = self._bounded_cost_candidates(
                    self._available(rule_candidates(features, self.profile, self.top_k)), len(data)
                )
                ranked = [{"strategy_id": item.strategy_id, "source": "rule fallback"} for item in candidates]
        elif self.mode == "benchmark-only":
            candidates = self._bounded_cost_candidates(
                self._available(candidate_catalog(include_neural=len(data) <= 4096)), len(data)
            )
            ranked = [{"strategy_id": item.strategy_id, "source": "benchmark catalog"} for item in candidates]
        else:
            candidates = self._bounded_cost_candidates(
                self._available(rule_candidates(features, self.profile, self.top_k)), len(data)
            )
            ranked = [{"strategy_id": item.strategy_id, "source": "rules"} for item in candidates]
        if not candidates:
            candidates = [Strategy("raw")]
            fallback = fallback or "no candidate available"
        candidate_ms = max(0.0, (time.perf_counter() - candidate_started) * 1000 - inference_ms)
        if self.mode in {"ai", "rules"}:
            chosen = candidates[0]
            selection = SelectionResult(chosen, self.mode, self.profile, feature_ms, inference_ms, 0.0, fallback, ranked)
            selection.candidate_generation_ms = candidate_ms
            return self._remember_selection(
                data,
                extension,
                selection,
            )

        sample = data[: self.microbench_bytes]
        started = time.perf_counter()
        measurements = []
        for candidate in candidates:
            try:
                measurements.append(measure_strategy(sample, candidate, self.registry))
            except Exception as exc:
                ranked.append({"strategy_id": candidate.strategy_id, "status": "N/A", "error": str(exc)})
        microbench_ms = (time.perf_counter() - started) * 1000
        if not measurements:
            chosen = Strategy("raw")
            fallback = fallback or "all microbenchmarks failed"
            measured = None
        else:
            labeled = label_measurements(measurements, self.profile)
            measured = labeled[0]
            chosen = Strategy.parse(measured["strategy_id"])
            for item in labeled:
                ranked.append(
                    {
                        "strategy_id": item["strategy_id"],
                        "measured_compressed_bytes": item["compressed_bytes"],
                        "measured_compression_seconds": item["compression_seconds"],
                        "measured_decompression_seconds": item["decompression_seconds"],
                        "profile_score": item["profile_score"],
                    }
                )
        selection = SelectionResult(chosen, self.mode, self.profile, feature_ms, inference_ms, microbench_ms, fallback, ranked, measured)
        selection.candidate_generation_ms = candidate_ms
        if self.collect_path is not None:
            self.collect_path.parent.mkdir(parents=True, exist_ok=True)
            observation = {"features": features, "selection": selection.metadata()}
            with self.collect_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(observation, sort_keys=True) + "\n")
        return self._remember_selection(data, extension, selection)
