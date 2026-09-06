# XAI-Compress Hybrid AI final report

Generated from measured artifacts only. PASS rows are aggregated; incomplete cells remain N/A.

## Outcome

XAIC v5 hybrid compression is deterministic, streaming, chunk-aware, backward-compatible, and lossless in the completed test and benchmark matrix. It automatically stores the chosen codec and reversible transform per chunk, so decompression never needs the selector model.

The measured balanced Hybrid AI result was **0.008826191 BPB** over 5 files (116,461,568 original bytes). The best fixed codec measured on every same file was **brotli-6 at 0.004589119 BPB**. Hybrid used **92.329% more bytes**. It won **0/5** benchmark categories. This implementation therefore does not claim size superiority.

The byte-weighted balanced oracle gap was **1.068%** across 4/5 paired samples. The 100 MiB oracle was not measured, and one 10 MiB oracle profile timed out; this is not a complete-corpus oracle claim.

## Selector

- Per-profile models: `{"balanced": "gradient_boosted_stumps", "fastest": "random_forest", "smallest": "gradient_boosted_stumps"}`
- Grouped split: 18 train / 2 validation / 9 untouched test source groups
- Top-1 accuracy: 0.703704
- Top-3 recall: 0.814815
- Mean / median / p95 regret: 0.005558571 / 0.000000000 / 0.029473149
- Mean model inference: 1.237144 ms

## Lossless and compatibility gates

- Full Python suite: **177 passed, 3 skipped**
- Focused XAIC compatibility, Rust parity, and Hybrid AI suite: **24 passed**
- Rust suite: **1 passed, 0 failed**
- Fixed/hybrid/oracle benchmark SHA failures: **0**
- User-facing balanced CLI compress/decompress/inspect smoke: **PASS** (46 source bytes, 811 XAIC bytes)
- Protected GRU: **PASS**, `083cda706612c3fd9ce62699741932b07e83fdf98eb6c5430d51bd29e1820429`
- Transformer: **PASS**, `584d8dfee979c6719a7602d00d81ef72443ee804878b13a1d651b5ea42129fb9`

## Runtime

- Balanced weighted compression throughput: 8.465241 MiB/s
- Balanced weighted decompression throughput: 75.420186 MiB/s
- Balanced selection overhead: 11302.807 ms total; 184.944 ms median/file
- Peak process RSS observed across hybrid workers: 220.785 MiB
- Exact identical-chunk cache microbenchmark: 2342.421 ms uncached vs 93.898 ms cached (24.946x), limited to consecutive byte-identical chunks <=1 MiB
- GRU cold/warm compression: 260.418/228.673 ms on 256 bytes
- Transformer cold/warm compression: 1342.629/1244.753 ms on 256 bytes

## Decision table

| Category | Selected strategy | Best fixed codec | Hybrid gap |
|---|---:|---:|---:|
| text | `{"brotli": 1}` | brotli-6 | 1270.000% |
| random | `{"raw": 1}` | raw-default | 1.176% |
| scientific | `{"deflate": 1}` | brotli-6 | 576.952% |
| json | `{"brotli": 10}` | brotli-6 | 3499.379% |
| repetitive | `{"brotli": 100}` | brotli-6 | 6816.860% |

## Production recommendation

Use `--mode hybrid --profile balanced` when automatic, auditable codec orchestration and a unified lossless container are more important than minimizing bytes on this measured corpus. Use the measured fixed codec directly when minimum size for a known homogeneous workload is the only goal.

## Known limitations

- The final five-file benchmark corpus is deterministic and spans 4 KiB through 100 MiB, but it is synthetic. The selector training corpus is broader (29 source groups), while final end-to-end category coverage remains limited.
- XAIC v5 per-chunk metadata is costly for extremely compressible inputs: 4 KiB text was 822 bytes with balanced Hybrid AI versus 60 bytes with fixed Brotli; 100 MiB repetitive data was 53,744 versus 777 bytes.
- Hybrid smallest on structured 10 MiB and oracle fastest on that sample timed out after 1,200 seconds and remain N/A. Exhaustive 100 MiB oracle results are NOT MEASURED.
- Neural codecs were measured only at 4 KiB in the final fixed benchmark; larger neural cases remain NOT MEASURED under the bounded-cost policy.
- Peak RSS is process peak working set, not isolated incremental memory per operation.
- No bounded parallel worker-pool speedup was measured, so none is claimed. Profiling justified an exact repeated-chunk cache; it did not justify adding a new Rust feature path in this iteration.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\build_codec_selector_dataset.py
.\.venv\Scripts\python.exe scripts\train_codec_selector.py
.\.venv\Scripts\python.exe scripts\benchmark_hybrid_ai.py
.\.venv\Scripts\python.exe scripts\finalize_hybrid_ai.py
.\.venv\Scripts\python.exe -m pytest -q
$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY='1'; cargo test --manifest-path rust-core\Cargo.toml
```
