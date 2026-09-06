# XAI-Compress Research Report

## 1. Abstract

XAI-Compress is a lossless hybrid byte compressor in which causal neural models predict probability distributions consumed by arithmetic coding or rANS. Current tests establish lossless correctness. Existing measurements do not establish general superiority over classical compressors.

## 2–6. Problem, background, foundations, and limits

The system targets conditional redundancy in heterogeneous files while retaining classical fallbacks for data on which neural inference is counterproductive. Classical LZ methods exploit repeated substrings; entropy coders exploit biased probability distributions; causal neural models attempt to learn longer contextual dependencies. The formal treatment and applicable theorems are in [mathematical_foundations.md](mathematical_foundations.md).

## 7–8. Dataset and preprocessing

The lazy dataset indexes bounded `(path, offset, length)` samples, performs content deduplication, uses reproducible file-level splits, and excludes common archives and generated artifacts by default. Dataset-specific statistics must be regenerated for each declared corpus; the repository does not treat bundled development files as a universal benchmark.

## 9–14. Architecture and algorithms

Available probability models are a causal byte GRU and lightweight causal byte Transformer. Logits are converted to deterministic positive integer frequencies totaling 16384. Arithmetic coding and rANS produce real lossless payloads. The versioned XAIC container stores mode, coder version, original size and hash, payload size and hash, chunk metadata, and model fingerprint. Hybrid mode analyzes each block and selects store, zlib, static arithmetic, or neural coding.

Training supports automatic CUDA detection, AMP, gradient scaling, pinned transfers, gradient accumulation, validation, checkpoint resume, optional compilation, gradient checkpointing, and multi-GPU DataParallel. Decompression remains autoregressive and is therefore the primary neural throughput constraint.

## 15–18. Experimental setup, baselines, and results

The benchmark suite compares identical files with available gzip, bz2, LZMA, Zstandard, Brotli, 7-Zip, and XAI modes. WinRAR is reported only when an installed, callable implementation is measured. Run `python scripts/generate_report.py` to populate [benchmark_report.md](benchmark_report.md) from raw CSV data.

No general winning claim is made. The supplied historical measurements show classical codecs often producing smaller files at orders-of-magnitude higher throughput than the early neural checkpoints.

## 19–24. Evolution, ablation, errors, speed, memory, comparison

The notebook sequence derives these sections from `results/experiments.csv` and `results/benchmark_results.csv`. Until controlled experiments populate those files, cells state that evidence is unavailable. Required ablations include context length, architecture, model selection, coder, mixed precision, and hybrid routing. Error analysis retains high-entropy, archived, and pathological inputs.

## 25. Discussion

The strongest current property is correctness: the model influences probabilities but cannot approximate output bytes. The strongest engineering opportunity is to move quantization and rANS into the Rust core and make file containers genuinely streaming. The principal scientific risk is domain overfitting combined with model-size and inference-cost externalities.

## 26. Limitations

- Neural decoding is sequential and slow in Python.
- File APIs still read or accumulate complete container payloads in important paths.
- A matching checkpoint is external to neural artifacts.
- Current datasets and experiments are insufficient for a universal compression claim.
- DataParallel is available, but distributed training is not yet implemented.

## 27. Future work

Implement a streamable container revision, native quantization/rANS, profiler-backed bottleneck removal, calibrated hybrid selection using measured candidate costs, DDP training, broader versioned corpora, and preregistered held-out benchmarks.

## 28. Conclusion

XAI-Compress is a credible lossless neural-compression research baseline, not yet a replacement for mature general-purpose compressors. Its research workflow is designed to make future improvements measurable and falsifiable.

## 29. References

- C. E. Shannon, “A Mathematical Theory of Communication,” 1948.
- J. Rissanen and G. G. Langdon, “Arithmetic Coding,” 1979.
- J. Duda, “Asymmetric Numeral Systems,” 2009.
- A. Vaswani et al., “Attention Is All You Need,” 2017.
