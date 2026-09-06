# Hybrid V3 Final Report

26-file benchmark = superseded
29-file paired audit = superseded
corrected full-corpus benchmark = authoritative final evidence

STATUS: ACCEPTED
AUTHORITATIVE CORPUS: 140 valid real held-out files, 140 unique source IDs
COMMON SOURCE COUNT: 140
COMMON ORIGINAL BYTES: 368446658

## Methods

| method | compressed bytes | weighted BPB | compression MiB/s | decompression MiB/s |
|---|---:|---:|---:|---:|
| hybrid_v1 | 361712014 | 7.853772 | 2.816161 | 20.174976 |
| hybrid_v2 frozen | 365898448 | 7.944671 | 5.629025 | 30.124013 |
| hybrid_v3_top3 | 362188760 | 7.864124 | 18.027349 | 32.202720 |
| brotli-11 | 359459933 | 7.804873 | 0.251334 | 194.827433 |

Selected production V3 routing: `hybrid_v3_top3`
Selector/model: frozen Selector V2 (`checkpoints/selector_v2/best.json`). No Selector V3 artifact was trained.

V3 vs V2 size delta: -1.0139%
V3 vs V2 speed delta: 220.2570%
V3 vs V1 size delta: 0.1318%
V3 vs V1 speed delta: 540.1392%
V3 vs Brotli-11 size delta: 0.7591%
V3 vs Brotli-11 speed delta: 7072.6685%
V3 vs Brotli-11 wins/ties/losses: {'wins': 0, 'ties': 0, 'losses': 140}

## Gates
{
  "corrected_corpus_selection": true,
  "paired_source_equality": true,
  "bpb_consistency": true,
  "complete_artifact_accounting": true,
  "sha_roundtrip": true,
  "timing_boundary_consistency": true,
  "routing_comparison": true,
  "no_duplicate_stale_rows": true,
  "python_regression_documented": true,
  "rust_regression_documented": true,
  "backward_compatibility_documented": true
}

## Timing boundary
All hybrid and Brotli-11 measurements are complete end-to-end artifact timings, including selection, compression, container serialization, checksums, and decompression round-trip SHA256.

## Repetition policy
{
  "hybrid": "3 repetitions when original_bytes <= 4 MiB, else 1",
  "brotli-11": "1 repetition for all files; additional Brotli-11 repetitions omitted because they are computationally prohibitive on this corpus"
}

## Tests
Python: {'ran': True, 'returncode': 0, 'passed': 207, 'failed': 0, 'skipped': 3, 'errors': 0}
Rust: {'ran': True, 'returncode': 0, 'passed': 2, 'failed': 0, 'skipped': 0}
