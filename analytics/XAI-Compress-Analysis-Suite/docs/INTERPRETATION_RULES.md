# Automated Interpretation Rules

Use these rules when reading generated outputs.

## Model learning

- Training and validation loss both decrease: learning is progressing.
- Training loss decreases while validation loss increases: likely overfitting.
- Validation BPB remains close to 8: weak predictive advantage over a uniform byte model.
- Validation BPB substantially below 8: the model is learning predictable byte structure.

## Compression results

- Neural BPB below static BPB on held-out files: the neural context model adds value.
- Neural BPB above static BPB: training data, architecture, or domain fit needs improvement.
- Neural wins only on one category: specialize the model or use adaptive routing.
- Negative saving on ZIP/JPEG/MP4: expected for already-compressed data.

## Speed

- Low neural throughput with good BPB: optimize inference, use blocks, export ONNX, or move entropy coding to Rust.
- Fast static mode with weaker BPB: suitable as a robust fallback.

## Production decision

A practical system should select among neural, zstd, Brotli, LZMA, and raw storage based on predicted size, time, and resource constraints.
