"""Device-neutral diagnostic aggregation.

Every tensor is reduced on its own device and only the resulting scalar is
copied to Python.  These helpers are observational: they never mutate source
tensors or participate in model/optimizer math.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real
from typing import Any, Iterator

import torch


def diagnostic_leaves(value: Any) -> Iterator[Any]:
    """Yield tensors and numeric leaves from nested diagnostic collections."""
    if value is None:
        return
    if torch.is_tensor(value) or isinstance(value, Real):
        yield value
        return
    if isinstance(value, Mapping):
        for item in value.values():
            yield from diagnostic_leaves(item)
        return
    if isinstance(value, (list, tuple, set)) or hasattr(value, "__iter__"):
        for item in value:
            yield from diagnostic_leaves(item)
        return
    raise TypeError(f"unsupported diagnostic value: {type(value).__name__}")


def diagnostic_scalar_values(values: Any) -> list[float]:
    """Materialize scalar observations as Python floats without device coupling."""
    result: list[float] = []
    for value in diagnostic_leaves(values):
        if torch.is_tensor(value):
            if value.numel() != 1:
                raise ValueError("diagnostic scalar aggregation accepts scalar tensors only")
            result.append(float(value.detach().item()))
        else:
            result.append(float(value))
    return result


def diagnostic_scalar_max(values: Any, default: float = 0.0) -> float:
    numbers = diagnostic_scalar_values(values)
    if not numbers:
        return float(default)
    if any(math.isnan(value) for value in numbers):
        return math.nan
    return max(numbers)


def collection_abs_max(values: Any, default: float = 0.0) -> float:
    """Return abs-max after reducing each tensor locally to one Python scalar."""
    maxima: list[float] = []
    for value in diagnostic_leaves(values):
        if torch.is_tensor(value):
            if value.numel():
                maxima.append(float(value.detach().float().abs().max().item()))
        else:
            maxima.append(abs(float(value)))
    return diagnostic_scalar_max(maxima, default)


def collection_finite_and_abs_max(values: Any) -> tuple[bool, float | None]:
    """Scan nested tensors locally and return finiteness plus finite-value abs-max."""
    finite = True
    maxima: list[float] = []
    for value in diagnostic_leaves(values):
        if torch.is_tensor(value):
            detached = value.detach().float()
            mask = torch.isfinite(detached)
            all_finite = bool(mask.all().item())
            finite = finite and all_finite
            if bool(mask.any().item()):
                maxima.append(float(detached[mask].abs().max().item()))
        else:
            number = float(value)
            finite = finite and math.isfinite(number)
            if math.isfinite(number):
                maxima.append(abs(number))
    return finite, max(maxima) if maxima else None


def collection_l2_norm(values: Any) -> float:
    """Combine per-tensor L2 norms as Python numbers, never as device tensors."""
    norms: list[float] = []
    for value in diagnostic_leaves(values):
        if torch.is_tensor(value):
            if value.numel():
                norms.append(float(value.detach().float().norm().item()))
        else:
            norms.append(abs(float(value)))
    if not norms:
        return 0.0
    if any(not math.isfinite(value) for value in norms):
        if any(math.isnan(value) for value in norms):
            return math.nan
        return math.inf
    return math.sqrt(math.fsum(value * value for value in norms))
