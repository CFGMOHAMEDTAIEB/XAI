# Lossless V2 180k gradient diagnostic

Kaggle kernel `mohameddtaieb/xai-compress-v2-gradient-diagnostic`, version 1, completed on a Tesla T4 using the Version 4 source hashes.

## Reproduction

Baseline AMP (`lr=0.001`, GradScaler initial scale 65536, growth interval 2000) reproduced a non-finite gradient at step 7,205 after 115,280 samples. Loss remained finite at 5.5399003029. The scaler had grown to 524,288. The first gradient found non-finite by parameter traversal was `embedding.weight`; blocks 0 and 1 QKV gradients were also non-finite in that batch, while blocks 2 and 3 QKV gradients remained finite. Total gradient norm was NaN. Tokens were valid in range 0..256.

The preceding step (7,204) was finite: total gradient norm 0.0720055774; block 2 QKV norm 0.0144172003 and absolute maximum 0.0012922287. Step 7,203 had total norm 0.3050257564. There was no smooth monotonic gradient explosion before the event.

## Classification

An identical FP32 replay passed 180,000 samples / 11,250 steps, including finite forward, loss, gradients, parameters and AdamW state, checkpoint save/load, deterministic inference and lossless SHA-256. Classification: `AMP_GRADIENT_OVERFLOW`.

## Proven fix

AMP with unchanged LR 0.001, clipping 1.0, GradScaler initial scale 1024 and growth interval 10000 passed 180,000 samples / 11,250 steps and every stability gate. Checkpoint SHA-256 reported by Kaggle: `58872c464c953fa5d4f9afa48d1a85eab082409da4c86e6690373de815ce7d26`.

Version 5 production is READY with the scaler configuration above, but was not submitted.
