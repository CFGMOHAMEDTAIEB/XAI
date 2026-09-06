#!/usr/bin/env python3
"""
Phase 3 Verification: Test pre-loaded artifact optimization.

Compares compression timing with and without pre-loaded selector artifact.
Expected result: ~600ms saved per file in selection_ms.
"""

import csv
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

# Add parent directory to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.container_v2 import compress_hybrid_v2_file
from xai_compress.hybrid.context import CompressionContext


REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_CSV = REPO_ROOT / "results" / "hybrid_v2" / "benchmark.csv"
TEST_RESULTS = REPO_ROOT / "results" / "hybrid_v3" / "phase3_test.json"


def select_test_files(limit: int = 5) -> list[dict]:
    """Get first N unique files from benchmark that are NOT quick_bypass candidates."""
    if not BENCHMARK_CSV.exists():
        print(f"ERROR: {BENCHMARK_CSV} not found")
        return []
    
    test_files = []
    seen = set()
    
    with open(BENCHMARK_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("method") != "hybrid_v2":
                continue
            source = row.get("source", "")
            if source in seen:
                continue
            seen.add(source)
            
            # Skip files that hit quick_bypass (candidate_generation_ms ≈ 0)
            cand_gen = float(row.get("candidate_generation_ms", 0) or 0)
            if cand_gen < 100:
                continue
            
            test_files.append({
                "path": Path(source),
                "size": int(row.get("original_bytes", 0)),
                "original_selection_ms": float(row.get("selection_ms", 0)),
            })
            
            if len(test_files) >= limit:
                break
    
    return test_files


def test_with_preloaded_context():
    """Test compression with pre-loaded selector context."""
    test_files = select_test_files(limit=3)
    
    if not test_files:
        print("ERROR: No suitable test files found (files with high candidate_generation_ms)")
        return None
    
    print(f"\n=== PHASE 3 VERIFICATION: Pre-loaded Artifact Optimization ===")
    print(f"Test files: {len(test_files)}")
    
    # Prepare context
    print("\n[SETUP] Pre-loading selector artifact...")
    context_start = time.perf_counter()
    context = CompressionContext.create(preload_selector=True)
    if context.selector_artifact is None:
        print("ERROR: Failed to pre-load selector artifact")
        return None
    context_load_ms = (time.perf_counter() - context_start) * 1000
    print(f"  Loaded in {context_load_ms:.2f} ms")
    
    results = {
        "test_date": time.ctime(),
        "total_tests": len(test_files),
        "context_load_ms": context_load_ms,
        "file_results": [],
    }
    
    # Test each file
    print("\n[COMPRESS] Testing with pre-loaded context...")
    for i, test_file in enumerate(test_files, 1):
        if not test_file["path"].exists():
            print(f"  {i}. SKIP {test_file['path'].name} (file not found)")
            continue
        
        try:
            # Compress with pre-loaded artifact
            started = time.perf_counter()
            output = test_file["path"].parent / f"test_phase3_{test_file['path'].name}.xaic"
            try:
                info = compress_hybrid_v2_file(
                    test_file["path"],
                    output,
                    profile="balanced",
                    routing_mode="confidence",
                    context=context,
                    overwrite=True,
                )
                compression_ms = (time.perf_counter() - started) * 1000
                
                # Cleanup
                output.unlink(missing_ok=True)
                
                selection_ms = info.get("selection_ms", 0)
                candidate_generation_ms = info.get("candidate_generation_ms", 0)
                
                result = {
                    "file": test_file["path"].name,
                    "size": test_file["size"],
                    "selection_ms": selection_ms,
                    "candidate_generation_ms": candidate_generation_ms,
                    "expected_original": test_file["original_selection_ms"],
                    "estimated_savings_ms": test_file["original_selection_ms"] - selection_ms,
                }
                results["file_results"].append(result)
                
                savings = result["estimated_savings_ms"]
                savings_pct = (savings / test_file["original_selection_ms"] * 100) if test_file["original_selection_ms"] > 0 else 0
                
                print(f"  {i}. {test_file['path'].name}")
                print(f"      Original selection_ms: {test_file['original_selection_ms']:.2f} (from benchmark)")
                print(f"      With pre-loaded:       {selection_ms:.2f} (this run)")
                print(f"      Est. savings:          {savings:.2f} ms ({savings_pct:.1f}%)")
                
            finally:
                output.unlink(missing_ok=True)
        
        except Exception as exc:
            print(f"  {i}. ERROR {test_file['path'].name}: {exc}")
    
    # Summary statistics
    if results["file_results"]:
        print("\n[SUMMARY]")
        total_savings = sum(r["estimated_savings_ms"] for r in results["file_results"])
        avg_savings = total_savings / len(results["file_results"])
        
        print(f"  Context pre-load cost: {context_load_ms:.2f} ms (amortized across files)")
        print(f"  Total estimated savings: {total_savings:.2f} ms across {len(results['file_results'])} files")
        print(f"  Average savings per file: {avg_savings:.2f} ms")
        print(f"  Amortization breakeven: {context_load_ms / avg_savings:.1f} files")
        
        results["total_estimated_savings_ms"] = total_savings
        results["avg_savings_per_file_ms"] = avg_savings
        results["amortization_breakeven_files"] = context_load_ms / avg_savings if avg_savings > 0 else 0
    
    return results


def main():
    results = test_with_preloaded_context()
    
    if results:
        TEST_RESULTS.parent.mkdir(parents=True, exist_ok=True)
        with open(TEST_RESULTS, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Results saved to {TEST_RESULTS}")
    else:
        print("\n✗ Test failed")


if __name__ == "__main__":
    main()
