import torch

from xai_compress.model import BOS_TOKEN, CausalByteGRU, ModelConfig


def test_forward_sequence_matches_step_semantics():
    model = CausalByteGRU(ModelConfig(embedding_dim=8, hidden_dim=12, num_layers=1, context_length=8))
    tokens = torch.tensor([BOS_TOKEN, 10, 20, 30], dtype=torch.long)

    with torch.no_grad():
        seq_logits, seq_hidden = model.forward_sequence(tokens)
        step_logits = []
        hidden = None
        for token in tokens:
            logits, hidden = model.step(int(token), hidden)
            step_logits.append(logits)

    assert seq_logits.shape == (len(tokens), 256)
    for i, expected in enumerate(step_logits):
        assert torch.allclose(seq_logits[i], expected, atol=1e-6, rtol=1e-6)
    assert seq_hidden is not None
