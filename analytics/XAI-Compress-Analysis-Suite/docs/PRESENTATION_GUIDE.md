# Presentation Guide for XAI-Compress

## Slide 1: Problem

Classical codecs use fixed algorithms. XAI-Compress studies whether a causal neural probability model can improve lossless compression on structured or domain-specific data while preserving exact reconstruction.

## Slide 2: Core idea

```text
Previous bytes
→ Embedding
→ Causal GRU
→ 256 next-byte probabilities
→ Integer frequency quantization
→ Arithmetic coder
→ .xaic artifact
```

The neural model does not reconstruct an approximate file. The model predicts probabilities. Arithmetic coding guarantees reversibility.

## Slide 3: Why it is lossless

Show a SHA-256 comparison and a binary equality test. Explain that a prediction error affects compressed size, not reconstructed content.

## Slide 4: Architecture

Discuss:
- 257 input tokens: 256 bytes plus BOS
- configurable embedding size
- configurable GRU hidden size and depth
- linear projection to 256 logits
- deterministic frequency quantization
- checkpoint fingerprint stored in metadata

## Slide 5: Python and Rust

Python/PyTorch handles research and training. Rust handles memory-safe block reading, file scanning, and hashing. The current Rust core accelerates file access; future work can move rANS and streaming container processing to Rust.

## Slide 6: Data pipeline

Explain lazy block reading, maximum samples, maximum bytes per file, excluded archive formats, and held-out test data. Emphasize that test files are never used for training.

## Slide 7: Training curves

Show training and validation cross-entropy. Explain convergence, best epoch, generalization gap, and early stopping.

## Slide 8: Compression benchmark

Show mean BPB and space-saving charts. Include only codecs that passed SHA-256. Compare XAI static, XAI neural, gzip, zstd, Brotli, bz2, and LZMA.

## Slide 9: Performance trade-off

Show compression time versus BPB. Explain that neural compression may improve modeling but is usually slower because decoding is sequential.

## Slide 10: Results by category

Show text, logs, automotive, binary, database, and already-compressed categories. Explain that no codec is best for every type.

## Slide 11: Explainability

Present explanations such as:
- detected category
- entropy/compressibility estimate
- codec selected
- predicted versus actual gain
- integrity status
- reason for fallback to raw or standard codec

## Slide 12: Security

Discuss magic/version validation, exact payload length, payload checksum, original SHA-256, checkpoint fingerprint, output-size limits, temporary output, and atomic rename.

## Slide 13: Limitations

State honestly:
- current neural byte decoding is sequential
- large files need block-based compression for bounded memory
- training quality depends on representative data
- already-compressed files often expand
- superiority must be demonstrated on held-out benchmarks

## Slide 14: Future work

- Rust rANS backend
- block-level parallelism
- CNN plus GRU or causal Transformer
- file-type conditioning
- adaptive codec selector
- ONNX inference inside Rust
- desktop and cloud integration

## Recommended wording

> XAI-Compress is a functional neural lossless compression prototype. It combines causal next-byte prediction with deterministic arithmetic coding and verifies reconstruction through SHA-256. The benchmark evaluates whether the neural model improves the compression trade-off on held-out domain-specific data.

Avoid saying:

> XAI-Compress is better than ZIP for all files.

unless the evidence truly supports that claim.
