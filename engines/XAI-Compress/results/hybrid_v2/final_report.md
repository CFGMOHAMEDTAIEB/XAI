# XAI-Compress Hybrid V2 Final Report

Generated: 2026-09-01T21:52:21.259252+00:00

## Scientific Decision

HYBRID_V2_STATUS = IMPROVED_OVER_HYBRID_V1_SIZE_ONLY

Hybrid V2 reduces final bytes and metadata versus Hybrid V1, but it is slower on this held-out set and does not beat Brotli-11 for smallest overall artifact bytes.

## Selector V2

- Selected models: {"balanced": "random_forest", "fastest": "extra_trees", "smallest": "decision_tree"}
- Top-1 / Top-2 / Top-3: 0.666667 / 0.810753 / 0.890323
- Mean / median / P95 regret: 0.003482628 / 0.000000000 / 0.021321162
- Inference latency: 0.325453 ms

## Compression

- Hybrid V1: 14010562 bytes, 7.929191370 BPB
- Hybrid V2: 13997801 bytes, 7.921969360 BPB
- V2 size improvement over V1: 0.091081%
- V2 speed change vs V1: -44.175744%
- Best fixed codec: brotli-11 at 7.731020472 BPB
- V2 vs best fixed: 2.469905%
- Bounded oracle BPB: 7.652133239; V2 oracle gap: 0.118371%

## Category Results

| Category | Files | V2 BPB | Best fixed | Result |
| --- | ---: | ---: | --- | --- |
| archive | 2 | 8.000129 | brotli-11 | LOSS |
| binary | 2 | 27.450980 | raw | LOSS |
| csv | 2 | 15.750000 | brotli-4 | LOSS |
| executable | 2 | 4.258119 | brotli-11 | LOSS |
| image | 2 | 2.882166 | brotli-11 | LOSS |
| json | 3 | 0.816233 | brotli-11 | LOSS |
| logs | 2 | 2.209820 | brotli-11 | LOSS |
| markdown | 2 | 6.910506 | brotli-11 | LOSS |
| model | 2 | 6.918897 | brotli-11 | LOSS |
| source_code | 3 | 2.415116 | brotli-11 | LOSS |
| text | 2 | 4.102775 | brotli-11 | LOSS |
| video | 2 | 8.000379 | brotli-11 | LOSS |

## Size Buckets

| Bucket | Files | V2 BPB | Best fixed BPB |
| --- | ---: | ---: | ---: |
| lt_16KiB | 18 | 3.724869 | 3.200057 |
| 16_64KiB | 4 | 4.617164 | 4.297243 |
| 64KiB_1MiB | 1 | 0.802130 | 0.671134 |
| 1_10MiB | 2 | 8.000379 | 7.986662 |
| gt_10MiB | 1 | 8.000080 | 7.761283 |

## Ablation

| Stage | BPB | Compression MiB/s | Selection ms | SHA |
| --- | ---: | ---: | ---: | --- |
| A fixed best | 7.731020 | 0.034599 | 0.000 | True |
| B hybrid v1 | 7.929191 | 1.118625 | 263.888 | True |
| C AI only | 7.967926 | 0.152440 | 1430.594 | True |
| D AI top2 | 7.979353 | 0.139834 | 1974.033 | True |
| E confidence | 7.978171 | 0.141125 | 2098.954 | True |
| F compact | 7.915835 | 0.127240 | 3818.031 | True |
| G adaptive | 7.921409 | 0.293312 | 1429.148 | True |
| H full v2 | 7.921969 | 0.624464 | 668.870 | True |

## Correctness

- Fixed benchmark SHA: True
- V1/V2 SHA: True
- Oracle SHA: True
- Ablation SHA: True
- Streaming/chunk hybrid/XAIC compatibility: PASS via full pytest, including XAIC v1-v6 regression coverage

## System

- Python tests: 199 passed, 3 skipped
- Rust tests: 2 passed, 0 failed
- Native build: PASS
- Python/Rust parity: PASS

## Limitations

- Held-out benchmark contains 26 real files; audio was not measured in the real corpus.
- Bounded oracle excludes files above 10 MiB and excludes pure-Python xai-static above 4 KiB by measured cost policy.
- V2 did not beat Brotli-11 in total artifact bytes on this held-out benchmark.
- V2 compression throughput was lower than Hybrid V1 in the measured local run.
- Peak RSS is process-level local measurement, not isolated per codec.
