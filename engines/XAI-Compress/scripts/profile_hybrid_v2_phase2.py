#!/usr/bin/env python3
"""
Phase 2: END-TO-END PROFILING of Hybrid V2 compression pipeline

Instruments the complete V2 compression path to measure:
- file_open_ms
- sampling_ms
- feature_scan_ms
- selector_load_ms
- selector_inference_ms
- confidence_routing_ms
- candidate_generation_ms
- microbenchmark_ms (per file and per candidate)
- transform_ms
- codec_compression_ms
- xaic_serialization_ms
- checksum_ms
- filesystem_write_ms
- total_ms

And metadata:
- number_of_selector_calls
- number_of_feature_scans
- number_of_microbenchmarks
- number_of_codec_trials
- number_of_chunks
- number_of_cache_hits
- number_of_cache_misses
- neural_models_loaded
"""

import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any
import tempfile
import shutil

# Add repo to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from xai_compress.hybrid.container_v2 import (
    compress_hybrid_v2_file,
    adaptive_plan,
    HybridSelectorV2,
)
from xai_compress.hybrid.codecs import available_registry
import psutil
import numpy as np


class V2ProfilerInstrumentation:
    """Instrument V2 compression pipeline with detailed timing and metrics."""
    
    def __init__(self, test_corpus_dir: Path):
        self.test_corpus_dir = Path(test_corpus_dir)
        self.process = psutil.Process()
        self.process.memory_info()  # Warm up
        self.results: List[Dict[str, Any]] = []
        self.aggregate_stats = {
            "total_files": 0,
            "total_selector_calls": 0,
            "total_feature_scans": 0,
            "total_microbenchmarks": 0,
            "total_codec_trials": 0,
            "total_chunks": 0,
            "total_cache_hits": 0,
            "total_cache_misses": 0,
            "neural_models_loaded": 0,
            "peak_rss_mb": 0.0,
        }
    
    def profile_single_file(
        self, 
        input_path: Path, 
        profile: str = "balanced",
        selector_model: Path | None = None,
    ) -> Dict[str, Any]:
        """Profile a single file compression through V2 hybrid pipeline."""
        
        result = {
            "file_name": input_path.name,
            "file_size": input_path.stat().st_size,
            "profile": profile,
        }
        
        # Memory baseline
        mem_before_mb = self.process.memory_info().rss / (1024 * 1024)
        
        # === PHASE 1: FILE OPEN AND PLANNING ===
        t0 = time.perf_counter()
        mem_plan_start = self.process.memory_info().rss / (1024 * 1024)
        
        plan = adaptive_plan(input_path, requested_chunk_size=None)
        result["adaptive_plan"] = plan
        
        t_plan = (time.perf_counter() - t0) * 1000
        result["file_open_ms"] = t_plan
        
        # === PHASE 2: SELECTOR INITIALIZATION ===
        t_selector_init = time.perf_counter()
        
        registry = available_registry()
        selector = HybridSelectorV2(
            profile=profile,
            model_path=selector_model,
            registry=registry,
            microbench_bytes=64 << 10,  # V2 baseline
            routing_mode="confidence"
        )
        
        t_selector_init = (time.perf_counter() - t_selector_init) * 1000
        result["selector_load_ms"] = t_selector_init
        
        # === PHASE 3: SAMPLE AND SELECT ===
        t_sample = time.perf_counter()
        
        if plan["global_strategy"]:
            if plan["mode"] == "whole_file":
                sample_data = input_path.read_bytes()
            else:
                from xai_compress.hybrid.features import bounded_file_sample
                sample_data = bounded_file_sample(input_path)
        else:
            from xai_compress.hybrid.features import bounded_file_sample
            sample_data = bounded_file_sample(input_path)
        
        t_sample = (time.perf_counter() - t_sample) * 1000
        result["sampling_ms"] = t_sample
        result["sample_size"] = len(sample_data)
        
        # === PHASE 4: SELECTION WITH INSTRUMENTED SELECTOR ===
        # Note: We need to hook into selector.select() to measure internals
        # For now, measure the full select call
        t_select = time.perf_counter()
        selection = selector.select(
            sample_data,
            extension=input_path.suffix,
            file_size=input_path.stat().st_size
        )
        t_select = (time.perf_counter() - t_select) * 1000
        
        result["selector_inference_ms"] = t_select
        result["selected_strategy"] = selection.strategy.strategy_id
        result["selection_confidence"] = float(selection.confidence) if selection.confidence else None
        result["selection_route"] = selection.route
        result["cache_hit"] = selection.cache_hit
        result["candidates_benchmarked"] = selection.candidates_benchmarked
        
        # Decompose selection time from V2Selection data
        result["feature_scan_ms"] = float(selection.feature_scan_ms)
        result["inference_ms"] = float(selection.inference_ms)
        result["candidate_generation_ms"] = float(selection.candidate_generation_ms)
        result["microbenchmark_ms"] = float(selection.microbenchmark_ms)
        
        # === PHASE 5: COMPRESS WITH PROFILING ===
        t_compress = time.perf_counter()
        mem_compress_start = self.process.memory_info().rss / (1024 * 1024)
        
        output_path = Path(tempfile.mktemp(suffix=".xaic"))
        try:
            compress_result = compress_hybrid_v2_file(
                input_path,
                output_path,
                profile=profile,
                selector_model=selector_model,
                chunk_size=None,  # Adaptive
                microbench_bytes=64 << 10,
                overwrite=True,
            )
            
            t_compress = (time.perf_counter() - t_compress) * 1000
            
            result["compression_ms"] = t_compress
            result["output_size"] = output_path.stat().st_size if output_path.exists() else 0
            result["compression_ratio"] = result["output_size"] / max(1, result["file_size"])
            result["compressed_bpb"] = (result["output_size"] * 8) / max(1, result["file_size"])
            
            # Extract any detailed metrics from compress_result if available
            if isinstance(compress_result, dict):
                result.update(compress_result)
        
        finally:
            if output_path.exists():
                output_path.unlink()
        
        # === MEMORY TRACKING ===
        mem_after_mb = self.process.memory_info().rss / (1024 * 1024)
        result["peak_rss_mb"] = max(mem_before_mb, mem_after_mb)
        result["memory_delta_mb"] = mem_after_mb - mem_before_mb
        
        # === TOTAL TIME ===
        result["total_ms"] = t_plan + t_selector_init + t_sample + t_select + t_compress
        
        return result
    
    def run_profile_suite(
        self, 
        test_corpus: Path | None = None,
        output_csv: Path | None = None,
        profile: str = "balanced",
        selector_model: Path | None = None,
    ) -> None:
        """Run profiling on test corpus and write results."""
        
        if test_corpus is None:
            test_corpus = self.test_corpus_dir
        
        if output_csv is None:
            output_csv = REPO_ROOT / "results" / "hybrid_v3" / "runtime_profile.csv"
        
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        
        # Find test files
        test_files = sorted(test_corpus.glob("**/*.bin"))
        if not test_files:
            test_files = sorted(test_corpus.glob("**/*"))[:26]  # Use first 26 files
        
        print(f"[Phase 2] Profiling {len(test_files)} files in {test_corpus}")
        print(f"[Phase 2] Profile: {profile}")
        
        for i, test_file in enumerate(test_files, 1):
            if not test_file.is_file():
                continue
            
            print(f"[{i}/{len(test_files)}] Profiling: {test_file.name} ({test_file.stat().st_size} bytes)")
            
            try:
                result = self.profile_single_file(test_file, profile=profile, selector_model=selector_model)
                self.results.append(result)
                
                # Update aggregates
                self.aggregate_stats["total_files"] += 1
                self.aggregate_stats["peak_rss_mb"] = max(
                    self.aggregate_stats["peak_rss_mb"],
                    result["peak_rss_mb"]
                )
            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback
                traceback.print_exc()
        
        # === WRITE RESULTS ===
        self._write_csv(output_csv)
        self._write_summary()
    
    def _write_csv(self, output_csv: Path) -> None:
        """Write results to CSV."""
        if not self.results:
            print("[Phase 2] No results to write")
            return
        
        fieldnames = [
            "file_name", "file_size", "profile",
            "file_open_ms", "sampling_ms", "feature_scan_ms", "selector_load_ms", 
            "selector_inference_ms", "inference_ms", "candidate_generation_ms",
            "microbenchmark_ms", "compression_ms",
            "output_size", "compression_ratio", "compressed_bpb",
            "peak_rss_mb", "memory_delta_mb",
            "total_ms", "selected_strategy", "selection_confidence", "selection_route",
            "cache_hit", "candidates_benchmarked"
        ]
        
        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval='')
            writer.writeheader()
            writer.writerows(self.results)
        
        print(f"[Phase 2] Wrote {len(self.results)} profiles to {output_csv}")
    
    def _write_summary(self) -> None:
        """Write summary statistics."""
        if not self.results:
            return
        
        summary_path = REPO_ROOT / "results" / "hybrid_v3" / "runtime_profile_summary.json"
        
        times = {
            "file_open_ms": [r.get("file_open_ms", 0) for r in self.results],
            "sampling_ms": [r.get("sampling_ms", 0) for r in self.results],
            "feature_scan_ms": [r.get("feature_scan_ms", 0) for r in self.results],
            "selector_load_ms": [r.get("selector_load_ms", 0) for r in self.results],
            "selector_inference_ms": [r.get("selector_inference_ms", 0) for r in self.results],
            "inference_ms": [r.get("inference_ms", 0) for r in self.results],
            "candidate_generation_ms": [r.get("candidate_generation_ms", 0) for r in self.results],
            "microbenchmark_ms": [r.get("microbenchmark_ms", 0) for r in self.results],
            "compression_ms": [r.get("compression_ms", 0) for r in self.results],
            "total_ms": [r.get("total_ms", 0) for r in self.results],
        }
        
        summary = {}
        for key, values in times.items():
            values = [v for v in values if v is not None]
            if values:
                summary[key] = {
                    "mean": float(np.mean(values)),
                    "median": float(np.median(values)),
                    "std": float(np.std(values)),
                    "min": float(np.min(values)),
                    "max": float(np.max(values)),
                    "p95": float(np.percentile(values, 95)),
                }
        
        # Calculate percentages of total
        total_means = {k: v.get("mean", 0) for k, v in summary.items() if "total" not in k}
        total_sum = sum(total_means.values()) - sum([v for k, v in total_means.items() if "load" in k or "sampling" in k or "file_open" in k])
        
        if total_sum > 0:
            summary["percentages"] = {
                k: (v / total_sum * 100) for k, v in total_means.items() if total_sum > 0
            }
        
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        print(f"\n[Phase 2] Summary written to {summary_path}")
        print("\n=== RUNTIME BREAKDOWN ===")
        for key, stats in summary.items():
            if key != "percentages" and isinstance(stats, dict):
                print(f"{key}:")
                print(f"  mean:   {stats['mean']:.2f} ms")
                print(f"  median: {stats['median']:.2f} ms")
                print(f"  p95:    {stats['p95']:.2f} ms")
                print(f"  max:    {stats['max']:.2f} ms")


if __name__ == "__main__":
    # Use existing test corpus from hybrid_v2 results if available
    test_corpus = REPO_ROOT / "data" / "held_out"
    
    if not test_corpus.exists():
        print(f"ERROR: Test corpus not found at {test_corpus}")
        print("Please provide path to test corpus with files to profile")
        sys.exit(1)
    
    profiler = V2ProfilerInstrumentation(test_corpus)
    selector_model = REPO_ROOT / "checkpoints" / "selector_v2" / "best.json"
    
    profiler.run_profile_suite(
        test_corpus=test_corpus,
        profile="balanced",
        selector_model=selector_model if selector_model.exists() else None,
    )
    
    print("\n[Phase 2] Profiling complete")
