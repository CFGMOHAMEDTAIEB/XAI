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
    n_heads: int = 4
    ff_dim: int = 256

class CausalByteGRU(nn.Module):
    """Predicts the current byte from a previous-byte token and recurrent state."""
    def __init__(self, config: ModelConfig):
        super().__init__(); self.config = config
        self.embedding = nn.Embedding(257, config.embedding_dim)
        self.gru = nn.GRU(config.embedding_dim, config.hidden_dim, config.num_layers,
                          batch_first=True, dropout=config.dropout if config.num_layers > 1 else 0.0)
        self.output = nn.Linear(config.hidden_dim, 256)

    def forward(self, tokens: torch.Tensor, hidden=None):
        if tokens.dim() == 1:
            tokens = tokens.unsqueeze(0)
        emb = self.embedding(tokens)
        out, hidden = self.gru(emb, hidden)
        return self.output(out), hidden

    def forward_sequence(self, tokens: torch.Tensor, hidden=None):
        if isinstance(tokens, (list, tuple)):
            tokens = torch.as_tensor(tokens, dtype=torch.long, device=next(self.parameters()).device)
        logits, hidden = self.forward(tokens, hidden)
        if logits.dim() == 3 and logits.size(0) == 1:
            logits = logits[0]
        return logits, hidden

    def predict_block(self, block, prev_token: int = BOS_TOKEN, hidden=None):
        if not block:
            return torch.empty((0, 256), dtype=torch.float32, device=next(self.parameters()).device), hidden
        prev_tokens = [int(prev_token)] + [int(x) for x in block[:-1]]
        x = torch.as_tensor(prev_tokens, dtype=torch.long, device=next(self.parameters()).device)
        logits, hidden = self.forward(x, hidden)
        if logits.dim() == 3 and logits.size(0) == 1:
            logits = logits[0]
        return logits, hidden

    def step(self, previous_token: int, hidden=None):
        x = torch.tensor([[previous_token]], dtype=torch.long, device=next(self.parameters()).device)
        logits, hidden = self.forward(x, hidden)
        return logits[0, 0], hidden
