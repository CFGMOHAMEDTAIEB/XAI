# XAI-Compress final audit

Generated: 2026-08-31T22:11:36.930352+00:00

## Protected production model

- GRU: `checkpoints\kaggle\best.pt`; SHA-256 `083cda706612c3fd9ce62699741932b07e83fdf98eb6c5430d51bd29e1820429`; 20423284 bytes; epoch 8; 1,700,800 parameters.
- Integrity before/after finalization: PASS.

## Lossless

- Autoregressive CE and model BPB are distinct from actual XAIC artifact BPB.
- XAIC byte containers v1/v2 remain readable; bounded streaming is XAIC v3.
- Neural lossless supports arithmetic and deterministic rANS14; static and hybrid modes remain available.
- Whole-file and per-chunk SHA-256 checks, sequential chunk IDs, bounded lengths, trailing-data rejection and atomic replacement are implemented.

## Transformer evidence

- Candidate A: gradient instability.
- Residual-depth candidate: first non-finite `gradient:output.weight`, epoch 5 step 8522; parameters and optimizer state remained finite; unsafe step was not executed.
- Safe mode now uses FP32 sensitive paths, conservative AMP scaling, bounded skipped steps, one last-stable rollback and LR reduction. No Transformer is labeled validated without measured gates.

## Lossy

- Direct image -> encoder -> quantized latent -> rANS -> XAIC v4 -> decoder pipeline. It does not losslessly compress then distort compressed bytes.
- LOW/MEDIUM/HIGH map to quantization steps 0.5/0.25/0.125. Training uses an explicit rate-distortion proxy; the delivered checkpoint is experimental.

## Rust and acceleration

Rust is limited to byte reading, SHA-256 and probability quantization. Training remains PyTorch/CUDA. Python fallback remains automatic.

## Incomplete or bounded items

- MS-SSIM: NOT MEASURED.
- Validated Transformer checkpoint: NOT AVAILABLE at audit time.
- Rust performance improvement is claimed only where prior benchmark artifacts contain measurements.
- No TODO marker identified in core codec paths represents an unimplemented function; matching `pass` statements are exception classes/intentional branches.
