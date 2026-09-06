import numpy as np
import pytest
import torch

from xai_compress.entropy import quant

def test_rust_quantization_parity_when_available(monkeypatch):
    core = pytest.importorskip("xai_compress_core")
    if not hasattr(core, "quantize_probabilities_batch"):
        pytest.skip("installed native core predates quantization support")
    logits = torch.tensor(np.random.default_rng(42).normal(size=(32, 256)), dtype=torch.float64)
    probabilities = torch.softmax(logits, dim=-1).numpy()
    native = core.quantize_probabilities_batch(probabilities, quant.NEURAL_TOTAL)
    monkeypatch.setitem(__import__("sys").modules, "xai_compress_core", None)
    python = quant.logits_batch_to_cumulative(logits)
    assert native == python
