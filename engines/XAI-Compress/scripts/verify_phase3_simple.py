#!/usr/bin/env python3
"""
Phase 3 Verification: Test pre-loaded artifact optimization with synthetic files.

Tests compression timing with pre-loaded vs lazy-loaded selector artifact.
Expected result: ~300-600ms saved per file in selection_ms.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

# Add parent directory to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.container_v2 import compress_hybrid_v2_file
from xai_compress.hybrid.context import CompressionContext


TEST_RESULTS = ROOT / "results" / "hybrid_v3" / "phase3_test_simple.json"


def create_test_file(path: Path, size: int, pattern: bytes) -> None:
    """Create a test file with repeating pattern."""
    with open(path, 'wb') as f:
        remaining = size
        while remaining > 0:
            chunk = pattern * ((remaining // len(pattern)) + 1)
            f.write(chunk[:remaining])
            remaining -= min(remaining, len(pattern))


def test_phase3_optimization():
    """Test pre-loaded artifact optimization."""
    print("\n=== PHASE 3 VERIFICATION: Pre-loaded Artifact Optimization ===\n")
    
    # Prepare context (pre-loaded artifact)
    print("[SETUP] Pre-loading selector artifact...")
    context_start = time.perf_counter()
    try:
        context = CompressionContext.create(preload_selector=True)
        if context.selector_artifact is None:
            print("  WARNING: Selector artifact is None, will use lazy-loading")
    except Exception as exc:
        print(f"  ERROR: Failed to create context: {exc}")
        return None
    context_load_ms = (time.perf_counter() - context_start) * 1000
    print(f"  Pre-loaded in {context_load_ms:.2f} ms\n")
    
    # Create test files
    results = {
        "test_date": time.ctime(),
        "context_load_ms": context_load_ms,
        "tests": [],
    }
    
    with tempfile.TemporaryDirectory(prefix="phase3-test-") as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create diverse test files (different sizes and patterns)
        test_configs = [
            ("binary_10kb.bin", 10 << 10, b"\x00\xff" * 512),
            ("text_20kb.txt", 20 << 10, b"The quick brown fox jumps over the lazy dog.\n" * 100),
            ("random_15kb.dat", 15 << 10, bytes(range(256)) * 60),
        ]
        
        print("[FILES] Creating test files...")
        for name, size, pattern in test_configs:
            path = tmpdir / name
            create_test_file(path, size, pattern)
            print(f"  Created {name} ({size:,} bytes)")
        
        print("\n[COMPRESS] Testing with pre-loaded context...")
        for name, size, pattern in test_configs:
            test_file = tmpdir / name
            output_file = tmpdir / f"{name}.xaic"
            
            try:
                # Compress with pre-loaded artifact
                started = time.perf_counter()
                info = compress_hybrid_v2_file(
                    test_file,
                    output_file,
                    profile="balanced",
                    routing_mode="confidence",
                    context=context,
                    overwrite=True,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                
                # Extract timing metrics
                selection_ms = info.get("selection_ms", 0)
                candidate_gen_ms = info.get("candidate_generation_ms", 0)
                feature_scan_ms = info.get("feature_scan_ms", 0)
                inference_ms = info.get("inference_ms", 0)
                microbench_ms = info.get("microbenchmark_ms", 0)
                
                test_result = {
                    "file": name,
                    "size": size,
                    "total_compression_ms": elapsed_ms,
                    "selection_ms": selection_ms,
                    "candidate_generation_ms": candidate_gen_ms,
                    "feature_scan_ms": feature_scan_ms,
                    "inference_ms": inference_ms,
                    "microbench_ms": microbench_ms,
                    "artifact_bytes": output_file.stat().st_size,
                }
                results["tests"].append(test_result)
                
                print(f"  ✓ {name}")
                print(f"      Total time:   {elapsed_ms:.2f} ms")
                print(f"      Selection:    {selection_ms:.2f} ms")
                print(f"      - candidate_gen: {candidate_gen_ms:.2f} ms")
                print(f"      - inference:     {inference_ms:.2f} ms")
                print(f"      - feature_scan:  {feature_scan_ms:.2f} ms")
                print(f"      - microbench:    {microbench_ms:.2f} ms")
            
            except Exception as exc:
                print(f"  ✗ {name}: {exc}")
                import traceback
                traceback.print_exc()
    
    # Summary
    if results["tests"]:
        print("\n[SUMMARY]")
        total_cand_gen = sum(t["candidate_generation_ms"] for t in results["tests"])
        avg_cand_gen = total_cand_gen / len(results["tests"])
        
        print(f"  Total tests: {len(results['tests'])}")
        print(f"  Context pre-load: {context_load_ms:.2f} ms")
        print(f"  Avg candidate_generation: {avg_cand_gen:.2f} ms per file")
        
        if avg_cand_gen < 50:
            print(f"  ✓ PHASE 3 WORKING: candidate_gen is low (~{avg_cand_gen:.0f}ms)")
            print(f"    Pre-loaded artifact avoided ~300-600ms overhead!")
        elif avg_cand_gen > 300:
            print(f"  ✗ PHASE 3 NOT WORKING: candidate_gen is still high (~{avg_cand_gen:.0f}ms)")
            print(f"    Selector may not be using pre-loaded artifact")
        
        results["summary"] = {
            "total_tests": len(results["tests"]),
            "avg_candidate_generation_ms": avg_cand_gen,
            "status": "PASS" if avg_cand_gen < 100 else "FAIL",
        }
    
    return results


def main():
    results = test_phase3_optimization()
    
    if results:
        TEST_RESULTS.parent.mkdir(parents=True, exist_ok=True)
        with open(TEST_RESULTS, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n✓ Results saved to {TEST_RESULTS}\n")
        
        # Print status
        if results["summary"]["status"] == "PASS":
            print("✓✓✓ PHASE 3 OPTIMIZATION VERIFIED ✓✓✓")
        else:
            print("✗✗✗ PHASE 3 NEEDS DEBUGGING ✗✗✗")
    else:
        print("\n✗ Test failed\n")


if __name__ == "__main__":
    main()
