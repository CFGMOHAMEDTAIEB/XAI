#!/usr/bin/env python3
"""
Analyze the mystery of high candidate_generation_ms values in V2 benchmark.
"""

import csv
from pathlib import Path

BENCHMARK_CSV = Path(__file__).resolve().parent.parent / "results" / "hybrid_v3" / "runtime_profile.csv"

def main():
    data = []
    with open(BENCHMARK_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    
    print(f"Total records: {len(data)}\n")
    
    # Separate by candidate_generation_ms
    high_cand_gen = []
    zero_cand_gen = []
    
    for row in data:
        cand_gen = float(row['candidate_generation_ms'] or 0)
        if cand_gen > 100:
            high_cand_gen.append((cand_gen, row))
        elif cand_gen == 0:
            zero_cand_gen.append(row)
    
    print(f"HIGH candidate_generation_ms (>100ms): {len(high_cand_gen)} files")
    print(f"ZERO candidate_generation_ms: {len(zero_cand_gen)} files\n")
    
    # Analyze high cand_gen files
    print("=== FILES WITH HIGH candidate_generation_ms ===")
    high_cand_gen.sort(reverse=True)
    for cand_gen_val, row in high_cand_gen:
        original = int(row['original_bytes'] or 0)
        plan_mode = row['plan_mode']
        chunks = int(row['chunks'] or 0)
        infer = float(row['inference_ms'] or 0)
        micro = float(row['microbenchmark_ms'] or 0)
        feat = float(row['feature_scan_ms'] or 0)
        sel = float(row['selection_ms'] or 0)
        
        # Verify: feat + infer + cand_gen + micro ≈ sel
        calc_sum = feat + infer + cand_gen_val + micro
        ratio = sel / calc_sum if calc_sum > 0 else 0
        
        print(f"\nFile: {Path(row['source']).name}")
        print(f"  Size: {original:,} bytes, chunks: {chunks}, plan: {plan_mode}")
        print(f"  feature_scan: {feat:.1f} ms")
        print(f"  inference:    {infer:.1f} ms")
        print(f"  candidate_gen: {cand_gen_val:.1f} ms  <-- EXPENSIVE")
        print(f"  microbench:   {micro:.1f} ms")
        print(f"  Sum: {calc_sum:.1f} ms vs selection_ms: {sel:.1f} ms (ratio: {ratio:.2f})")
    
    # Check if it's related to plan_mode or chunk count
    print("\n\n=== PATTERN ANALYSIS ===")
    
    whole_file_high = sum(1 for cg, r in high_cand_gen if r['plan_mode'] == 'whole_file')
    adaptive_high = sum(1 for cg, r in high_cand_gen if r['plan_mode'] == 'adaptive_chunks')
    
    whole_file_zero = sum(1 for r in zero_cand_gen if r['plan_mode'] == 'whole_file')
    adaptive_zero = sum(1 for r in zero_cand_gen if r['plan_mode'] == 'adaptive_chunks')
    
    print(f"Whole-file plans with high candidate_gen: {whole_file_high}")
    print(f"Whole-file plans with zero candidate_gen: {whole_file_zero}")
    print(f"Adaptive plans with high candidate_gen: {adaptive_high}")
    print(f"Adaptive plans with zero candidate_gen: {adaptive_zero}")
    
    # Check if first file in batch
    print(f"\n\nORDER OF FILES IN BENCHMARK:")
    for i, row in enumerate(data[:5], 1):
        cand_gen = float(row['candidate_generation_ms'] or 0)
        print(f"  {i}. {Path(row['source']).name}: candidate_gen={cand_gen:.0f}ms")

if __name__ == "__main__":
    main()
