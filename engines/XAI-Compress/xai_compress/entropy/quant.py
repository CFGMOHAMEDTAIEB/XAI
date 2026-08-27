from __future__ import annotations

from typing import Sequence

import numpy as np
import torch

NEURAL_TOTAL = 16384


class QuantError(ValueError):
    pass


def logits_to_cumulative(logits, total: int = NEURAL_TOTAL) -> list[int]:
    if torch.is_tensor(logits):
        logits = logits.detach().to(device="cpu", dtype=torch.float64)
    logits = torch.as_tensor(logits, dtype=torch.float64, device="cpu")
    if logits.numel() != 256:
        raise QuantError("neural model must output 256 logits")
    probs = torch.softmax(logits, dim=-1).to(dtype=torch.float64, device="cpu").numpy()
    if not np.isfinite(probs).all():
        raise QuantError("non-finite model probabilities")
    remaining = total - 256
    raw = probs * remaining
    base = np.floor(raw).astype(np.int64)
    freq = base + 1
    left = total - int(freq.sum())
    fractions = raw - base
    order = np.lexsort((np.arange(256, dtype=np.int64), -fractions))
    for i in order[:left]:
        freq[int(i)] += 1
    cum = [0]
    running = 0
    for f in freq.tolist():
        running += int(f)
        cum.append(running)
    if running != total:
        raise QuantError("frequency quantization error")
    return cum


def logits_batch_to_cumulative(logits, total: int = NEURAL_TOTAL) -> list[list[int]]:
    if torch.is_tensor(logits):
        logits = logits.detach().to(device="cpu", dtype=torch.float64)
    else:
        logits = torch.as_tensor(logits, dtype=torch.float64, device="cpu")
    if logits.dim() == 1:
        logits = logits.unsqueeze(0)
    if logits.size(-1) != 256:
        raise QuantError("neural model must output 256 logits")
    # Treat every leading dimension as a collection of symbol predictions.
    # This accepts both [time, 256] and conventional [batch, time, 256]
    # model output without letting NumPy broadcasting corrupt row totals.
    logits = logits.reshape(-1, 256)
    probs = torch.softmax(logits, dim=-1).numpy()
    if not np.isfinite(probs).all():
        raise QuantError("non-finite model probabilities")
    remaining = total - 256
    raw = probs * remaining
    base = np.floor(raw).astype(np.int64)
    freq = base + 1
    left = total - freq.sum(axis=1)
    fractions = raw - base
    index = np.broadcast_to(np.arange(256, dtype=np.int64), fractions.shape)
    order = np.lexsort((index, -fractions), axis=1)
    tables: list[list[int]] = []
    for i in range(freq.shape[0]):
        extra = int(left[i])
        if extra:
            freq[i, order[i, :extra]] += 1
        running = np.cumsum(freq[i])
        if int(running[-1]) != total:
            raise QuantError("frequency quantization error")
        tables.append([0, *running.tolist()])
    return tables


def uniform_cumulative(total: int = NEURAL_TOTAL) -> list[int]:
    if total % 256 != 0:
        raise QuantError("total must be divisible by 256 for a uniform table")
    f = total // 256
    return [i * f for i in range(257)]
