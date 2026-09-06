# XAI-Compress three-mode evidence report

## Measured

- Old neural checkpoint load and SHA-256 round trip pass.
- Old-model 4,000-byte cold-path text/source benchmark is recorded in `lossless_benchmark.csv`.
- BPB identity decomposition is recorded in `lossless_bpb_breakdown.csv`.
- Local untrained architecture smoke tests pass for Lossless V2 and Lossy V1.

## Not measured

Lossless V2 and Lossy V1 have no trained checkpoints. Their validation quality, actual BPB/rate-distortion, speed, memory, old-vs-new deltas, break-even point, publication figures, and Kaggle execution are N/A. No superiority claim is made.
