# Lossless V2 Kaggle pre-flight

## Exact production configuration

| Setting | Value |
|---|---:|
| Architecture | `causal-byte-transformer-v2` |
| Parameters | 2,468,160 |
| Context / KV-cache bound | 256 bytes |
| Transformer blocks | 4 |
| Attention heads | 6 |
| Embedding dimension | 192 |
| FFN dimension | 768 |
| Dropout | 0.1 |
| Epoch limit | 60 |
| Early-stopping patience | 8 |
| Batch size on a 16 GB T4 | 16 |
| Gradient accumulation | 1 |
| Effective batch size | 16 |
| Optimizer | AdamW |
| Initial learning rate | 0.001 |
| Scheduler | ReduceLROnPlateau, factor 0.5, patience 1 |
| Gradient clipping | global norm 1.0 |
| AMP / gradient scaler | enabled on CUDA |
| Maximum samples | 500,000 |
| Context stride | 128 |
| Maximum bytes per file | 33,554,432 |
| Validation split | deterministic file-level 10% |
| DataLoader workers | 2 |
| Prefetch factor | 2 |
| Persistent workers | enabled |
| Checkpoint cadence | latest every epoch; periodic every 5 epochs |
| Periodic retention | newest 3 |
| Resume | latest valid attached checkpoint, otherwise epoch 0 |
| Model compilation | disabled |
| Multi-GPU / DataParallel / DDP | disabled |

## Parameter and storage expectations

The exact parameter count is 2,468,160. FP32 parameter tensors occupy 9,872,640 bytes. A training checkpoint also contains AdamW moments, scaler, scheduler, configuration, and metadata. A precise checkpoint size is **NOT MEASURED** before training; it is expected to exceed raw parameter storage and will be recorded from Kaggle.

Persistent training state has a lower bound of roughly 39.5 MB for FP32 parameters, gradients, and two Adam moments, excluding activations, CUDA kernels/workspaces, allocator reservations, and DataLoader memory. Actual peak VRAM is **NOT MEASURED** and the smoke run is authoritative.

## GPU plan

The kernel requests `NvidiaTeslaT4`. Kaggle previously supplied two T4 devices, but the current trainer selects `cuda:0`; `multi_gpu=False`, and neither DataParallel nor DDP is active. Therefore only one T4 is expected to train V2. The second GPU will not be claimed as utilized.

## Determinism and durability

- The validation file split and sample selection use fixed seeds.
- Training uses deterministic cuDNN settings where available.
- Encoder and decoder use the same incremental `step()` path and deterministic float64 probability quantization.
- Checkpoints are written to a same-filesystem temporary file, flushed/fsynced, reloaded/fingerprint-validated, and atomically replaced.
- Metrics CSV/history JSON and training status are updated incrementally.

## Known risks

1. Transformer incremental neural compression remains serial per decoded byte and may be slower than the GRU.
2. Training data reads tiny byte windows by opening/seeking files per sample. With only two workers, CPU/filesystem input may limit GPU utilization; this is a code-inspection risk, not a measured conclusion.
3. Four attention blocks increase training activation memory relative to the old GRU. Smoke VRAM must be checked before the long run.
4. A valid but architecture-mismatched resume checkpoint must be rejected rather than partially loaded.
5. Model entropy may improve without end-to-end BPB improving on small files because fixed XAIC metadata dominates.
6. Kaggle runtime limits may interrupt 60 epochs; latest/periodic checkpoints and incremental histories are required for recovery.

## Smoke gate

The Kaggle smoke path must pass offline installation, CUDA tensor execution, V2 construction, forward/backward/optimizer/AMP, validation, atomic save/reload, architecture identity, deterministic incremental logits, and an exact neural-lossless SHA-256 round trip before production training begins.
