from __future__ import annotations

from typing import Any

import torch
from torch import nn
from torch.utils.checkpoint import checkpoint as ckpt_fn

from ..model import BOS_TOKEN, ModelConfig


class CausalSelfAttention(nn.Module):
    def __init__(self, dim: int, n_heads: int, dropout: float) -> None:
        super().__init__()
        if dim % n_heads != 0:
            raise ValueError("embedding_dim must be divisible by n_heads")
        self.n_heads = n_heads
        self.head_dim = dim // n_heads
        self.qkv = nn.Linear(dim, 3 * dim, bias=False)
        self.proj = nn.Linear(dim, dim, bias=False)
        self.drop = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        cache: tuple[torch.Tensor, torch.Tensor] | None = None,
        max_cache: int | None = None,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor]]:
        b, t, c = x.shape
        qkv = self.qkv(x).view(b, t, 3, self.n_heads, self.head_dim)
        q, k, v = qkv.unbind(dim=2)
        q = q.transpose(1, 2)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)
        if cache is not None:
            k = torch.cat([cache[0], k], dim=2)
            v = torch.cat([cache[1], v], dim=2)
            if max_cache is not None and k.size(2) > max_cache:
                k = k[:, :, -max_cache:]
                v = v[:, :, -max_cache:]
        attn = torch.nn.functional.scaled_dot_product_attention(
            q, k, v, is_causal=cache is None, dropout_p=self.drop.p if self.training else 0.0
        )
        if cache is not None:
            # Incremental decode: query is the new tokens; no future exists.
            pass
        out = attn.transpose(1, 2).contiguous().view(b, t, c)
        return self.proj(out), (k, v)


class TransformerBlock(nn.Module):
    def __init__(self, dim: int, n_heads: int, ff_dim: int, dropout: float) -> None:
        super().__init__()
        self.n1 = nn.LayerNorm(dim)
        self.attn = CausalSelfAttention(dim, n_heads, dropout)
        self.n2 = nn.LayerNorm(dim)
        self.ff = nn.Sequential(
            nn.Linear(dim, ff_dim),
            nn.GELU(),
            nn.Linear(ff_dim, dim),
            nn.Dropout(dropout),
        )

    def forward(self, x, cache=None, max_cache=None):
        h = self.n1(x)
        a, cache = self.attn(h, cache=cache, max_cache=max_cache)
        x = x + a
        x = x + self.ff(self.n2(x))
        return x, cache


class CausalByteTransformer(nn.Module):
    """Lightweight causal byte Transformer with optional KV cache."""

    def __init__(self, config: ModelConfig):
        super().__init__()
        self.config = config
        dim = config.embedding_dim
        self.embedding = nn.Embedding(257, dim)
        self.pos = nn.Embedding(config.context_length + 1, dim)
        self.drop = nn.Dropout(config.dropout)
        ff = config.ff_dim or (4 * dim)
        self.blocks = nn.ModuleList(
            [
                TransformerBlock(dim, config.n_heads, ff, config.dropout)
                for _ in range(config.num_layers)
            ]
        )
        self.norm = nn.LayerNorm(dim)
        self.output = nn.Linear(dim, 256, bias=False)
        self.gradient_checkpointing = False

    def _positions(self, t: int, device: torch.device, past: int = 0) -> torch.Tensor:
        ctx = self.config.context_length
        idx = torch.arange(past, past + t, device=device)
        return idx % ctx

    def forward(self, tokens: torch.Tensor, hidden: Any = None):
        if tokens.dim() == 1:
            tokens = tokens.unsqueeze(0)
        b, t = tokens.shape
        past = 0
        caches = hidden
        if caches:
            past = int(caches[0][0].size(2))
        x = self.embedding(tokens) + self.pos(self._positions(t, tokens.device, past))
        x = self.drop(x)
        new_caches = []
        for i, block in enumerate(self.blocks):
            cache_i = caches[i] if caches else None
            if self.gradient_checkpointing and self.training and cache_i is None:
                x, cache_i = ckpt_fn(block, x, cache_i, self.config.context_length, use_reentrant=False)
            else:
                x, cache_i = block(x, cache=cache_i, max_cache=self.config.context_length)
            new_caches.append(cache_i)
        logits = self.output(self.norm(x))
        return logits, new_caches

    def forward_sequence(self, tokens: torch.Tensor, hidden=None):
        if isinstance(tokens, (list, tuple)):
            tokens = torch.as_tensor(tokens, dtype=torch.long, device=next(self.parameters()).device)
        logits, hidden = self.forward(tokens, hidden)
        if logits.dim() == 3 and logits.size(0) == 1:
            logits = logits[0]
        return logits, hidden

    def predict_block(self, block, prev_token: int = BOS_TOKEN, hidden=None):
        device = next(self.parameters()).device
        if not block:
            return torch.empty((0, 256), dtype=torch.float32, device=device), hidden
        prev_tokens = [int(prev_token)] + [int(x) for x in block[:-1]]
        x = torch.as_tensor(prev_tokens, dtype=torch.long, device=device)
        logits, hidden = self.forward_sequence(x, hidden)
        return logits, hidden

    def step(self, previous_token: int, hidden=None):
        device = next(self.parameters()).device
        x = torch.tensor([[previous_token]], dtype=torch.long, device=device)
        logits, hidden = self.forward(x, hidden)
        return logits[0, 0], hidden


MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "architecture_id": "causal-byte-gru-v1",
        "embedding_dim": 64,
        "hidden_dim": 128,
        "num_layers": 1,
        "n_heads": 4,
        "ff_dim": 256,
        "context_length": 128,
        "dropout": 0.0,
    },
    "balanced": {
        "architecture_id": "causal-byte-transformer-v1",
        "embedding_dim": 128,
        "hidden_dim": 128,
        "num_layers": 4,
        "n_heads": 4,
        "ff_dim": 512,
        "context_length": 256,
        "dropout": 0.1,
    },
    "ultra": {
        "architecture_id": "causal-byte-transformer-v1",
        "embedding_dim": 256,
        "hidden_dim": 256,
        "num_layers": 6,
        "n_heads": 8,
        "ff_dim": 1024,
        "context_length": 512,
        "dropout": 0.1,
    },
    "tiny": {
        "architecture_id": "causal-byte-gru-v1",
        "embedding_dim": 32,
        "hidden_dim": 64,
        "num_layers": 1,
        "n_heads": 4,
        "ff_dim": 128,
        "context_length": 64,
        "dropout": 0.0,
    },
    "small": {
        "architecture_id": "causal-byte-transformer-v1",
        "embedding_dim": 64,
        "hidden_dim": 64,
        "num_layers": 2,
        "n_heads": 4,
        "ff_dim": 256,
        "context_length": 128,
        "dropout": 0.05,
    },
    "medium": {
        "architecture_id": "causal-byte-transformer-v1",
        "embedding_dim": 128,
        "hidden_dim": 128,
        "num_layers": 4,
        "n_heads": 4,
        "ff_dim": 512,
        "context_length": 256,
        "dropout": 0.1,
    },
    "large": {
        "architecture_id": "causal-byte-transformer-v1",
        "embedding_dim": 256,
        "hidden_dim": 256,
        "num_layers": 6,
        "n_heads": 8,
        "ff_dim": 1024,
        "context_length": 512,
        "dropout": 0.1,
    },
}


def preset_config(name: str, **overrides) -> ModelConfig:
    key = name.lower().strip()
    if key not in MODEL_PRESETS:
        raise KeyError(f"unknown model preset: {name}")
    params = dict(MODEL_PRESETS[key])
    params.update({k: v for k, v in overrides.items() if v is not None})
    return ModelConfig(**{k: v for k, v in params.items() if k in ModelConfig.__dataclass_fields__})
