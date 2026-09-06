# Methodology

## Research questions

1. Does a learned conditional byte model reduce held-out artifact BPB after all container overhead?
2. On which file categories does hybrid selection improve over a fixed codec?
3. What compression, decompression, memory, and model-storage costs accompany any size gain?

## Dataset protocol

Files are content-hash deduplicated before splitting. Splits occur at file level with a fixed seed so chunks from one file cannot leak across training and validation. Archives, checkpoints, and generated compression artifacts are excluded by default. Reports record file count, byte count, extensions, size distribution, marginal entropy, split seed, and dataset manifest hash.

## Correctness gate

Every admissible benchmark requires decoded bytes to equal original bytes. Container payload and output SHA-256 checks provide corruption detection. A codec with any failed file is marked invalid and cannot win an aggregate comparison.

## Model protocol

The baseline is the causal byte GRU. Transformer experiments change one declared configuration at a time where practical. Training records configuration, seed, checkpoint fingerprint, parameter count, epoch, validation cross entropy and BPB, throughput, and peak VRAM. Selection uses validation data only; test data is reserved for the final benchmark.

## Benchmark protocol

All codecs receive identical bytes. Timings use a monotonic clock and exclude dataset discovery. Warm-up policy, codec versions, command lines, hardware, OS, and software versions are captured. Results include per-file rows and size-weighted aggregates. Neural model size, startup latency, and training cost are disclosed separately.

## Scientific controls

- No missing value is replaced with an estimate in final tables.
- No unavailable executable is represented as a zero-sized result.
- High-entropy and already-compressed inputs remain in the suite.
- Aggregate and per-category results accompany any favorable subset.
- Changes are retained only after reproducible improvement on the declared target metric.
