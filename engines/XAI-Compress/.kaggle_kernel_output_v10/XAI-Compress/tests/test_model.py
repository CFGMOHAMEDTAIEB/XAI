import torch
from xai_compress.model import BOS_TOKEN, CausalByteGRU, ModelConfig
from xai_compress.models.registry import build_model
from xai_compress.models.transformer import CausalByteTransformer, preset_config


def test_gru_step_matches_sequence():
    model = CausalByteGRU(ModelConfig(embedding_dim=8, hidden_dim=12, num_layers=1, context_length=8))
    tokens = torch.tensor([BOS_TOKEN, 10, 20, 30], dtype=torch.long)
    with torch.no_grad():
        seq_logits, _ = model.forward_sequence(tokens)
        hidden = None
        step_logits = []
        for token in tokens:
            logits, hidden = model.step(int(token), hidden)
            step_logits.append(logits)
    for i, expected in enumerate(step_logits):
        assert torch.allclose(seq_logits[i], expected, atol=1e-5, rtol=1e-5)


def test_build_transformer_preset():
    cfg = preset_config("small")
    model = build_model(cfg)
    assert isinstance(model, CausalByteTransformer)
    x = torch.randint(0, 256, (2, 16))
    logits, _ = model(x)
    assert logits.shape == (2, 16, 256)


def test_parameter_counts_reasonable():
    tiny = build_model(preset_config("tiny"))
    large = build_model(preset_config("large"))
    n_tiny = sum(p.numel() for p in tiny.parameters())
    n_large = sum(p.numel() for p in large.parameters())
    assert n_tiny < n_large
    assert n_large < 20_000_000
