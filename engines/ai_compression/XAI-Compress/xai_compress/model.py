from __future__ import annotations
from dataclasses import dataclass, asdict
import torch
from torch import nn

BOS_TOKEN = 256

@dataclass(frozen=True)
class ModelConfig:
    embedding_dim: int = 64
    hidden_dim: int = 128
    num_layers: int = 1
    context_length: int = 128
    dropout: float = 0.0
    architecture_id: str = "causal-byte-gru-v1"

class CausalByteGRU(nn.Module):
    """Predicts the current byte from a previous-byte token and recurrent state."""
    def __init__(self, config: ModelConfig):
        super().__init__(); self.config = config
        self.embedding = nn.Embedding(257, config.embedding_dim)
        self.gru = nn.GRU(config.embedding_dim, config.hidden_dim, config.num_layers,
                          batch_first=True, dropout=config.dropout if config.num_layers > 1 else 0.0)
        self.output = nn.Linear(config.hidden_dim, 256)
    def forward(self, tokens: torch.Tensor, hidden=None):
        emb = self.embedding(tokens); out, hidden = self.gru(emb, hidden)
        return self.output(out), hidden
    def step(self, previous_token: int, hidden=None):
        x = torch.tensor([[previous_token]], dtype=torch.long, device=next(self.parameters()).device)
        logits, hidden = self.forward(x, hidden)
        return logits[0, 0], hidden
