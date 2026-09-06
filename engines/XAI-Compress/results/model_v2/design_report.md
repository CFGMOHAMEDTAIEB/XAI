# XAI-Compress three-mode architecture audit and design

Status labels in this report are **MEASURED**, **CODE INSPECTION**, or **PROPOSED**. No V2/V1 training result is claimed.

## Compatibility baseline — CODE INSPECTION

- `checkpoints/kaggle/best.pt` remains the immutable old neural-lossless baseline. Its checkpoint format is `xai-compress-checkpoint-v1` and includes a deterministic model fingerprint.
- Byte APIs use XAIC v1 for single-codec static/neural data and XAIC v2 for hybrid chunks. File APIs write bounded-memory XAIC v3 records with per-chunk SHA-256 plus a whole-file SHA-256 footer.
- The decoder selects static, zlib, neural arithmetic, or neural rANS from container metadata/codec IDs. XAIC v1/v2 parsing and XAIC v3 streaming decoding must remain unchanged.
- Neural arithmetic/rANS decoding is autoregressive. Encoder and decoder deliberately use the identical `model.step()` path to prevent fused-kernel floating-point differences from crossing quantization boundaries.
- PyTorch owns training and inference. Rust is optional and currently covers file scanning/block reads/SHA-256 and batch probability quantization; Python is the authoritative fallback.

## Current lossless model and bottlenecks — CODE INSPECTION

The baseline is a two-layer causal byte GRU. Each symbol requires embedding lookup, recurrent state update, a 256-logit projection, CPU float64 softmax, deterministic frequency quantization, and an entropy-coder operation. The decoder cannot batch future symbols because each decoded byte determines the next probability distribution. Current cold APIs also load and fingerprint the checkpoint per call and file-mode neural coding resets state at every chunk.

Consequences:

1. Autoregressive CPU inference dominates latency.
2. CPU/GPU transfers during float64 quantization can dominate a small model.
3. Chunk state reset discards cross-chunk context.
4. A GRU state is a fixed-size summary and may under-model long/local byte structure.
5. The rANS Python encoder stores every symbol and its 257-entry table until `finish()`, which is unsuitable for very large neural blocks.
6. XAIC metadata is deliberately integrity-rich but expensive for tiny inputs.

## Why validation BPB and artifact BPB differ — MEASURED

Validation BPB is mean cross-entropy divided by `ln(2)`; it excludes the container and entropy implementation. On the exact 4,000-byte audit corpus, the old checkpoint measured:

| Component | Aggregate BPB |
|---|---:|
| Model negative log-likelihood | 5.362253 |
| Quantized-frequency delta on realized symbols | -0.068398 |
| Arithmetic-coder termination/finite-stream overhead | 0.028145 |
| XAIC header, metadata, and integrity overhead | 3.564000 |
| End-to-end artifact | 8.886000 |

The components sum exactly; the recorded identity error is zero. The negative quantization term is not a claim that quantization is generally beneficial: on this realized sample, rounding happened to assign slightly more mass to observed symbols. Across an expectation it can differ. Per-file evidence is in `lossless_bpb_breakdown.csv`.

Container overhead was 594–595 bytes per tiny artifact, producing 19.849 BPB overhead for the 239-byte file but 1.770 BPB for the 2,690-byte file. Therefore the earlier 8.886 aggregate BPB cannot be generalized to large FF-C23 inputs.

The Kaggle validation value (7.96871 BPB) and the audit model entropy (5.36225 BPB) are from different data distributions and cannot be subtracted as a coder-overhead estimate.

## Proposed neural-lossless V2 — PROPOSED

Use a streaming local Transformer V2 rather than merely widening the GRU:

- causal byte embedding and 256-way next-byte logits;
- pre-normalized local self-attention with a bounded KV cache;
- relative/rotary position treatment so chunk/position rollover is explicit;
- gated feed-forward layers;
- identical incremental `step()` semantics at encoder and decoder;
- deterministic float64 CPU probability quantization at the coding boundary;
- optional cached model session so warm throughput is measured separately from load/fingerprint time.

This choice offers richer local context than a fixed GRU state while retaining bounded streaming memory. It is expected—not proven—to improve conditional modeling. Its principal risk is slower per-symbol decode; V2 is not an improvement unless actual end-to-end BPB and Pareto measurements beat the old checkpoint.

V2 checkpoints will live only under `checkpoints/neural_lossless_v2/`. Old checkpoint/config/fingerprint behavior remains supported.

## Proposed neural-lossy V1 — PROPOSED

Lossy coding is restricted to supported visual media. Arbitrary source, executables, archives, and generic binary inputs must be rejected. For initial reproducible scope, use decoded RGB images/frames:

`RGB frame → convolutional/residual encoder → quantized latent → entropy payload → convolutional/residual decoder → reconstructed RGB frame`.

Train with an explicit rate–distortion objective `L = R + λD`, where `R` is estimated latent rate and `D` is reconstruction distortion. Low/medium/high select distinct measured quantization/rate–distortion settings. PSNR and SSIM are quality metrics; SHA-256 equality is neither expected nor presented. Video support requires preserving frame dimensions/rate and a validated media demux/remux dependency; until that is implemented and tested, video must be reported unsupported rather than treated as arbitrary bytes.

Lossy checkpoints will live only under `checkpoints/neural_lossy_v1/`.

## Container and application design — PROPOSED

Expose canonical modes `static`, `neural-lossless`, and `neural-lossy`; keep `neural` as a backward-compatible alias for old neural lossless. Lossless files continue using XAIC v1–v3. Lossy media requires a new explicitly lossy container version/family containing decoder architecture, model fingerprint, quality level, dimensions/media metadata, and payload integrity. It must omit any promise of original-byte SHA-256 reconstruction. Decompression dispatches from metadata and rejects unknown/corrupted mode metadata.

## Benchmark design — PROPOSED

- Lossless table: static, old neural, V2, gzip, Brotli, Zstandard, Bzip2, LZMA; SHA-256 gates every row.
- Lossy table: only supported media, separate rate–distortion results with ratio/bitrate/BPP, PSNR, SSIM, and speed.
- Report cold neural latency and warm persistent-model latency separately.
- Report checkpoint distribution size separately from artifact bytes and calculate break-even only where average bytes saved is positive.
- Produce figures only from measured CSV rows. Missing V2/lossy checkpoints remain `N/A / NOT MEASURED`.

## Immediate implementation boundaries

Architecture registration, mode aliases, metadata validation, unsupported-lossy rejection, checkpoint namespaces, and smoke tests can be implemented locally. Claims about V2 quality, lossy rate–distortion performance, old-vs-new deltas, and final figures require trained checkpoints and are intentionally deferred.
