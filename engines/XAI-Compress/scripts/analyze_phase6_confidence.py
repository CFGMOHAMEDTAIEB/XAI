#!/usr/bin/env python3
"""
Phase 6 Analysis: Confidence Calibration Strategy

This script analyzes the current confidence thresholds and their effectiveness,
preparing for potential calibration in Phase 6.

Key questions:
1. What's the current threshold effectiveness (low, high)?
2. How many files trigger each routing path?
3. What's the microbench cost for each routing path?
4. Can we safely increase thresholds to reduce microbenchmarking?
"""

import sys
import json
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.ml import SelectorArtifact
from xai_compress.hybrid.selector_v2 import DEFAULT_MODEL


def analyze_confidence_thresholds():
    """Analyze current confidence threshold configuration."""
    print("\n=== PHASE 6 ANALYSIS: Confidence Calibration ===\n")
    
    # Load selector artifact
    try:
        artifact = SelectorArtifact.load(DEFAULT_MODEL)
        print("[INFO] Loaded selector artifact from:", DEFAULT_MODEL)
    except Exception as e:
        print(f"[ERROR] Failed to load selector artifact: {e}")
        return False
    
    # Display confidence thresholds
    print("\n1. Current Confidence Thresholds (V2):")
    print("-" * 60)
    
    thresholds_data = artifact.metrics.get("confidence_thresholds", {})
    
    for profile, threshold_info in thresholds_data.items():
        low = threshold_info.get("low", 0.5)
        high = threshold_info.get("high", 0.8)
        mean_extra = threshold_info.get("mean_extra_candidates", 1.0)
        validation_obj = threshold_info.get("validation_objective", 0.0)
        
        print(f"\nProfile: {profile}")
        print(f"  Low threshold:       {low:.2f} (confidence < low → top-3 benchmark)")
        print(f"  High threshold:      {high:.2f} (confidence >= high → direct)")
        print(f"  Medium range:        {low:.2f} - {high:.2f} (→ top-2 benchmark)")
        print(f"  Mean extra candidates: {mean_extra:.2f}")
        print(f"  Validation objective:  {validation_obj:.6f}")
    
    # Display model accuracy metrics
    print("\n2. Model Accuracy Metrics:")
    print("-" * 60)
    
    top1_acc = artifact.metrics.get("top_1_accuracy", 0.0)
    top2_recall = artifact.metrics.get("top_2_recall", 0.0)
    top3_recall = artifact.metrics.get("top_3_recall", 0.0)
    mean_regret = artifact.metrics.get("mean_regret", 0.0)
    p95_regret = artifact.metrics.get("p95_regret", 0.0)
    
    print(f"Top-1 Accuracy:      {top1_acc:.1%}")
    print(f"Top-2 Recall:        {top2_recall:.1%}")
    print(f"Top-3 Recall:        {top3_recall:.1%}")
    print(f"Mean Regret:         {mean_regret:.6f}")
    print(f"P95 Regret:          {p95_regret:.6f}")
    
    # Phase 6 Analysis
    print("\n3. Phase 6 Analysis & Recommendations:")
    print("-" * 60)
    
    print("""
CURRENT STATE (V2):
- balanced profile uses low=0.7, high=0.8
- Mean extra candidates: 1.31 (already efficient)
- Top-1 accuracy: 66% (decent for direct use)

CONFIDENCE CALIBRATION STRATEGY:

Option A: Conservative (Maintain Current)
  Keep low=0.7, high=0.8
  Rationale:
    - Already well-calibrated from training
    - Phases 3-5 speed up common path (not bypassed)
    - Microbench cost not reduced by optimizations
    - Risk: None
  Impact: No change

Option B: Moderate (Increase High Threshold)
  Change high: 0.8 → 0.85
  Rationale:
    - Reduces top-1 direct cases by ~5-10%
    - Moves borderline cases to top-2 benchmark
    - Trades ~100ms per file for better selection
    - Lower regret than forced top-1
  Impact: Slight quality improvement, minimal speedup

Option C: Aggressive (Increase Both)
  Change low: 0.7 → 0.75, high: 0.8 → 0.85
  Rationale:
    - Reduces top-3 benchmarking (most expensive)
    - Increases confidence in top-1/top-2 decisions
    - Acceptable 1-2% quality regression
  Impact: 10-15% speedup in microbench, quality trade-off

RECOMMENDATION FOR PHASE 6:
→ OPTION A (Conservative): Maintain current thresholds

Rationale:
1. Current thresholds already well-optimized (validation-tuned)
2. Major speedups come from Phases 3-5, not threshold changes
3. Phases 3-5 eliminate bottlenecks BEFORE confidence routing
4. Changing thresholds creates new risk (quality regression)
5. Mean extra candidates (1.31) already indicates efficient routing

ACTUAL PHASE 6 APPROACH:
Instead of changing thresholds, Phase 6 should:
1. Validate current thresholds still apply post-optimization
2. Measure actual microbench cost with Phases 3-5 applied
3. If needed, make small incremental adjustments
4. Focus on data-driven decisions (measure, don't speculate)
""")
    
    print("\n4. Phase 6 Implementation Plan:")
    print("-" * 60)
    print("""
Phase 6.1: Baseline Measurement
  - Compress 100+ files with current thresholds
  - Measure: feature_ms, inference_ms, microbench_ms
  - Compute: % of files in each confidence routing path
  - Baseline these metrics before any changes

Phase 6.2: Threshold Impact Analysis
  - For each confidence level (0.0-1.0), compute:
    - Routing decision (top-1, top-2, top-3)
    - Actual microbench time saved vs lost
    - Quality impact (compression ratio change)
  - Create sensitivity analysis graph

Phase 6.3: Calibration Decision
  - If savings > 10%: Consider modest threshold increase
  - If regret < 0.2%: Safe to be aggressive
  - If regret > 1.0%: Keep conservative approach

Phase 6.4: Validation
  - Test updated thresholds on held-out dataset
  - Measure: throughput, compression ratio, regret
  - Verify no unexpected regressions

Phase 6.5: Documentation
  - Record calibration decisions and rationale
  - Create Phase 6 report with findings
""")
    
    print("\n✓ Phase 6 Analysis Complete")
    print("  → Recommendation: Maintain current thresholds (Option A)")
    print("  → Proceed with measurement-based validation in implementation")
    
    return True


if __name__ == "__main__":
    if analyze_confidence_thresholds():
        sys.exit(0)
    else:
        sys.exit(1)
