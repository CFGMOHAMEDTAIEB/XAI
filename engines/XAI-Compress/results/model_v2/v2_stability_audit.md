# Transformer V2 numerical-stability audit

## Scope and evidence

This audit covers `causal-byte-transformer-v2`, the PyTorch training loop, and the observed long-run failures from Kaggle Versions 4--6. It does not change or reinterpret the validated GRU checkpoint.

Observed evidence:

- Version 4, LR 0.001: first non-finite tensor was `blocks.2.attn.qkv.weight`'s unscaled gradient at step 10,169. The loss, parameters, and optimizer state were finite before the rejected step.
- Focused LR 0.001 reproduction: layer-3 FFN output reached 62,624 in FP16 and ordinary training dropout overflowed when applying its `1 / 0.9` scale. Running that dropout rescale in the FP32 residual dtype removed this specific overflow location.
- LR 0.0005 passed one complete 450,000-sample epoch, but Version 6 subsequently showed layer-3 maxima 2,371.74, 3,596.60, and 6,558.25 in epochs 1--3, then failed at epoch 4, step 24,024 in `gradient:output.weight`.
- The monotone and accelerating layer-3 trajectory proves that a one-epoch finite check is not a sufficient stability gate. It does not, by itself, prove that the residual equation is incorrect.

## Implementation audit

### Block equations

The implementation is pre-LayerNorm:

```text
u  = LayerNorm(x)
a  = Wo(Attention(RoPE(Wq(u)), RoPE(Wk(u)), Wv(u)))
x1 = x + a
v, g = split(Wgate(LayerNorm(x1)) + bgate)
f  = Wproj(v * SiLU(g)) + bproj
x2 = x1 + Dropout(f)
```

Each attention and FFN residual is added exactly once. Tensor shapes are `[batch, time, embedding]`; attention is reshaped to `[batch, heads, time, head_dim]` and restored before `Wo`. No unintended broadcast or double residual addition was found. The gated FFN is a valid SwiGLU-like variant (`value * SiLU(gate)`), not a mathematically invalid gate.

### Attention, rotary positions, and mask

- `embedding_dim=192` is divisible by six heads; each head has dimension 32.
- RoPE rotates paired dimensions with absolute incremental positions. Cached decoding advances the stored absolute position and retains at most `context_length` keys and values.
- Full-sequence training uses a lower-triangular causal mask through scaled-dot-product attention. Incremental decoding attends to the bounded cache and current token without a causal mask, which is correct because no future tokens are present.
- Attention score construction and softmax run in FP32 with AMP disabled. Their result is cast back for the output projection. This is an intentional AMP safeguard and preserves deterministic incremental semantics.

### Normalization and initialization

- Both branches are pre-normalized and a final LayerNorm precedes the byte-logit projection. No missing normalization operation was found.
- The code uses PyTorch defaults: embeddings are normally initialized; linear layers use `nn.Linear`'s Kaiming-uniform weight initialization and matching bias initialization; LayerNorm scale is one and bias is zero.
- The output projection has no bias and uses the standard `nn.Linear` initialization. It is not zero-initialized or depth-scaled. That is not an implementation bug, but it leaves branch magnitude control entirely to optimization and pre-normalization.

### Optimizer and AMP ordering

The update ordering is correct: scaled backward, `GradScaler.unscale_`, non-finite gradient inspection, global norm clipping at 1.0, clipped-gradient inspection, scaler step/update, then parameter and AdamW-state inspection. A failing step is rejected before `optimizer.step`. Initial scale 1,024 and growth interval 10,000 are explicitly configurable and checkpointed.

## Findings by category

### Implementation bugs

1. **Confirmed and corrected before this audit:** dropout rescaling had occurred on an FP16 FFN result. A finite value near FP16's limit could overflow during the `1/(1-p)` training rescale. Dropout now executes with autocast disabled after conversion to the FP32 residual dtype.
2. **Telemetry gap corrected in this audit:** the trainer previously retained only the maximum `residual_ffn` value per layer and the last gradient norm. It did not persist logits, gradient maximum, parameter maximum, optimizer-state maximum, or per-stage RMS trajectories.
3. **Failure-reporting gap corrected in this audit:** non-finite failures after backward did not all pass through the atomic `training_status.json` failure writer. Gradient and optimizer checks now preserve the first named stage in status output.
4. **Resume-history gap corrected in this audit:** checkpoint state resumed, but an existing output history was not reloaded before appending later epochs. Multi-epoch history now survives a normal `best.latest.pt` resume.

No residual double-add, FFN algebra error, mask inversion, RoPE dimension error, or output broadcast bug was found.

### Architectural risks

- Pre-normalization keeps branch inputs normalized, but it does not bound the accumulated residual stream. Four unscaled attention/FFN residual pairs can grow across optimizer steps even when every normalized branch input remains well-conditioned.
- Neither branch output projection is zero-initialized or depth-scaled. This is a plausible residual-growth risk, not yet a demonstrated defect.
- LayerNorm is applied in the model's current autocast context. PyTorch commonly promotes its internal reduction for stability, but the exact CUDA kernel behavior must be confirmed through recorded finite/RMS telemetry rather than assumed.
- The layer-3 trajectory is consistent with depth-amplified residual growth. Residual scaling is scientifically eligible only if LR 0.0003 and 0.0002 both fail the five-epoch gate or show unsafe acceleration.

### Optimizer/training risks

- LR 0.001 caused rapid parameter/activation growth and is rejected.
- LR 0.0005 delayed rather than eliminated the instability. Its epoch-1 pass is superseded by the epoch-4 output-gradient failure.
- AdamW moment tensors can remain finite while parameter updates move projections into an unsafe activation regime. Finite optimizer state is necessary but not sufficient.
- ReduceLROnPlateau changes LR only after validation behavior warrants it; the actual LR per epoch must therefore be retained in every diagnostic record.

### AMP-specific risks

- FP16 has a maximum finite magnitude near 65,504. The gate product, FFN projection, attention projection, logits, and their backward paths remain AMP-exposed even after FP32 attention-score and dropout safeguards.
- A forward activation below 65,504 can still produce a non-finite gradient. The required two-times activation headroom (<32,752), per-step gradient checks, and five-epoch duration address distinct risks.
- GradScaler growth may expose an overflow in scaled backward; `unscale_` and named-gradient inspection correctly occur before clipping. Scale trajectory is evidence, not a substitute for tensor checks.

## Evidence-supported conclusion

The failure is a **multi-epoch activation/gradient-growth instability**. LR 0.0005 is not production-stable. The known FP16-dropout bug was real but was only one failure mechanism. Current evidence supports testing LR 0.0003 with unchanged architecture for five complete production-equivalent epochs. It does not yet justify residual scaling, RMSNorm, a larger model, or promotion of Transformer V2.

## Unresolved hypotheses

- Whether LR 0.0003 bounds layer-3 residual growth for at least five epochs.
- Whether layer-3 growth remains accelerating below the hard FP16 headroom threshold.
- Whether output-gradient failure is driven primarily by residual-stream magnitude, output-weight magnitude, a particular data subsequence, or interaction with GradScaler growth.
- Whether LR 0.0002 is sufficient if LR 0.0003 fails.
- Whether depth-aware residual scaling is necessary after the two controlled LR tests.

These hypotheses require measured multi-epoch CUDA traces; they are not resolved by code inspection.
