#!/usr/bin/env python3
"""
Phase 2 Analysis: Extract runtime profile from existing V2 benchmark data
and identify top 3 bottlenecks.
"""

import csv
import json
from pathlib import Path
from collections import defaultdict
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_CSV = REPO_ROOT / "results" / "hybrid_v2" / "benchmark.csv"
OUTPUT_CSV = REPO_ROOT / "results" / "hybrid_v3" / "runtime_profile.csv"
OUTPUT_JSON = REPO_ROOT / "results" / "hybrid_v3" / "runtime_profile.json"

def analyze_v2_benchmarks():
    """Parse V2 benchmark data and extract runtime profile for V2 method only."""
    
    if not BENCHMARK_CSV.exists():
        print(f"ERROR: {BENCHMARK_CSV} not found")
        return
    
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    # Read and filter V2 records
    v2_records = []
    all_records = []
    
    with open(BENCHMARK_CSV, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_records.append(row)
            if row.get("method") == "hybrid_v2":
                v2_records.append(row)
    
    print(f"[Phase 2] Found {len(v2_records)} V2 hybrid records out of {len(all_records)} total")
    
    # Extract timing columns
    timing_fields = {
        "feature_scan_ms": "feature_scan_ms",
        "inference_ms": "inference_ms", 
        "candidate_generation_ms": "candidate_generation_ms",
        "microbenchmark_ms": "microbenchmark_ms",
        "selection_ms": "selection_ms",
        "compression_ms": "compression_ms",
    }
    
    # Convert to numeric and collect stats
    timing_data = defaultdict(list)
    
    for record in v2_records:
        for key, field in timing_fields.items():
            try:
                val = float(record.get(field, 0) or 0)
                timing_data[key].append(val)
            except (ValueError, TypeError):
                pass
    
    # Write filtered CSV
    with open(OUTPUT_CSV, 'w', newline='') as f:
        if v2_records:
            fieldnames = v2_records[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval='')
            writer.writeheader()
            writer.writerows(v2_records)
    
    # Calculate statistics
    stats = {}
    bottlenecks = []
    
    for key, values in timing_data.items():
        if values:
            mean_val = float(np.mean(values))
            stats[key] = {
                "mean_ms": mean_val,
                "median_ms": float(np.median(values)),
                "std_ms": float(np.std(values)),
                "min_ms": float(np.min(values)),
                "max_ms": float(np.max(values)),
                "p95_ms": float(np.percentile(values, 95)),
                "count": len(values),
            }
            bottlenecks.append((key, mean_val))
    
    # Rank bottlenecks
    bottlenecks.sort(key=lambda x: x[1], reverse=True)
    
    # Write summary
    summary = {
        "phase": "Phase 2: Runtime Profile Analysis",
        "data_source": "V2 hybrid benchmark results",
        "records_analyzed": len(v2_records),
        "timing_statistics": stats,
        "top_3_bottlenecks": [
            {"rank": i + 1, "component": name, "mean_ms": val}
            for i, (name, val) in enumerate(bottlenecks[:3])
        ],
    }
    
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n[Phase 2] Runtime Profile Analysis Complete")
    print(f"[Phase 2] Written to {OUTPUT_CSV}")
    print(f"[Phase 2] Summary written to {OUTPUT_JSON}")
    
    print("\n=== TIMING STATISTICS (V2 HYBRID) ===")
    for key, stats_dict in sorted(stats.items()):
        print(f"\n{key}:")
        print(f"  mean:   {stats_dict['mean_ms']:.2f} ms")
        print(f"  median: {stats_dict['median_ms']:.2f} ms")
        print(f"  p95:    {stats_dict['p95_ms']:.2f} ms")
        print(f"  max:    {stats_dict['max_ms']:.2f} ms")
    
    print("\n=== TOP 3 BOTTLENECKS ===")
    for i, (name, val) in enumerate(bottlenecks[:3], 1):
        pct = (val / sum([v for k, v in bottlenecks])) * 100
        print(f"{i}. {name}: {val:.2f} ms ({pct:.1f}% of measured overhead)")
    
    print("\n[Phase 2] FINDINGS:")
    print("=" * 70)
    
    # Infer findings from data
    if "selection_ms" in timing_data:
        sel_mean = stats.get("selection_ms", {}).get("mean_ms", 0)
        print(f"\nSelection Overhead: {sel_mean:.2f} ms mean")
        print(f"  This dominates the selection process. Breakdown:")
        
        if "feature_scan_ms" in timing_data:
            feat_mean = stats.get("feature_scan_ms", {}).get("mean_ms", 0)
            print(f"    - Feature scan:              {feat_mean:.2f} ms")
        
        if "inference_ms" in timing_data:
            inf_mean = stats.get("inference_ms", {}).get("mean_ms", 0)
            print(f"    - Model inference:          {inf_mean:.2f} ms")
        
        if "candidate_generation_ms" in timing_data:
            cand_mean = stats.get("candidate_generation_ms", {}).get("mean_ms", 0)
            print(f"    - Candidate generation:     {cand_mean:.2f} ms")
        
        if "microbenchmark_ms" in timing_data:
            micro_mean = stats.get("microbenchmark_ms", {}).get("mean_ms", 0)
            print(f"    - Microbenchmarking:        {micro_mean:.2f} ms")
    
    if "compression_ms" in timing_data:
        comp_mean = stats.get("compression_ms", {}).get("mean_ms", 0)
        print(f"\nCompression Time: {comp_mean:.2f} ms mean")
    
    return summary

if __name__ == "__main__":
    summary = analyze_v2_benchmarks()
