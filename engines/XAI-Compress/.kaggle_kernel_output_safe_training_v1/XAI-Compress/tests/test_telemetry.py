import json
import math

import pytest
import torch

from xai_compress.telemetry import (
    collection_abs_max,
    collection_finite_and_abs_max,
    collection_l2_norm,
    diagnostic_scalar_max,
    diagnostic_scalar_values,
)


def test_scalar_telemetry_accepts_cpu_float_int_none_and_empty():
    assert diagnostic_scalar_values([torch.tensor(2.5), 3.0, 4, None]) == [2.5, 3.0, 4.0]
    assert diagnostic_scalar_max([torch.tensor(2.5), 3.0, 4, None]) == 4.0
    assert diagnostic_scalar_max([]) == 0.0


def test_nested_optimizer_state_is_device_neutral_json_serializable_and_not_mutated():
    exp_avg = torch.tensor([-2.0, 3.5])
    exp_avg_sq = torch.tensor([4.0, 1.0])
    state = {"state": {0: {"step": torch.tensor(7), "exp_avg": exp_avg, "exp_avg_sq": exp_avg_sq}}}
    before_avg = exp_avg.clone()
    before_sq = exp_avg_sq.clone()
    maximum = collection_abs_max(state)
    finite, finite_maximum = collection_finite_and_abs_max(state)
    norm = collection_l2_norm(state)
    json.dumps({"maximum": maximum, "finite": finite, "finite_maximum": finite_maximum, "norm": norm}, allow_nan=False)
    assert maximum == 7.0
    assert finite and finite_maximum == 7.0
    assert math.isfinite(norm)
    assert torch.equal(exp_avg, before_avg)
    assert torch.equal(exp_avg_sq, before_sq)


def test_nonfinite_values_are_reported_not_silently_dropped():
    assert math.isnan(diagnostic_scalar_max([1.0, float("nan"), 2.0]))
    assert collection_abs_max([torch.tensor(float("inf"))]) == float("inf")
    finite, maximum = collection_finite_and_abs_max(
        [torch.tensor([1.0, float("nan"), -3.0]), float("inf")]
    )
    assert not finite
    assert maximum == 3.0


def test_nonscalar_tensor_rejected_by_scalar_aggregation():
    with pytest.raises(ValueError, match="scalar tensors only"):
        diagnostic_scalar_values([torch.tensor([1.0, 2.0])])


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is unavailable")
def test_cuda_and_mixed_device_telemetry():
    cpu = torch.tensor([-3.0, 2.0], device="cpu")
    cuda = torch.tensor([1.0, 8.0], device="cuda")
    assert collection_abs_max([cpu, cuda]) == 8.0
    finite, maximum = collection_finite_and_abs_max({"cpu": cpu, "cuda": cuda})
    assert finite and maximum == 8.0
    assert math.isfinite(collection_l2_norm([cpu, cuda]))
