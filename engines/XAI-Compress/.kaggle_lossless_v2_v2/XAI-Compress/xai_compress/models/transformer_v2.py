from __future__ import annotations

import math
from typing import Any

import torch
from torch import nn

from ..model import BOS_TOKEN, ModelConfig


def _rope(x: torch.Tensor, positions: torch.Tensor) -> torch.Tensor:
    """Apply deterministic rotary positions to [B,H,T,D] queries/keys."""
    d = x.size(-1)
    rotary = d - (d % 2)
    if rotary == 0:
        return x
    inv = torch.exp(torch.arange(0, rotary, 2, device=x.device, dtype=torch.float32) * (-math.log(10000.0) / rotary))
    angles = positions.float().unsqueeze(-1) * inv.unsqueeze(0)
    cos, sin = angles.cos().to(x.dtype)[None, None], angles.sin().to(x.dtype)[None, None]
    head, tail = x[..., :rotary], x[..., rotary:]
    even, odd = head[..., 0::2], head[..., 1::2]
    rotated = torch.stack((even*cos-odd*sin, even*sin+odd*cos), dim=-1).flatten(-2)
    return torch.cat((rotated, tail), dim=-1)


class LocalRotaryAttention(nn.Module):
    def __init__(self, dim: int, heads: int, dropout: float):
        super().__init__()
        if dim % heads:
            raise ValueError("embedding_dim must be divisible by n_heads")
        self.heads, self.head_dim = heads, dim // heads
        self.qkv = nn.Linear(dim, 3*dim, bias=False)
        self.output = nn.Linear(dim, dim, bias=False)
        self.dropout = dropout

    def forward(self, x, positions, cache=None, max_cache=256):
        b,t,c=x.shape
        q,k,v=self.qkv(x).view(b,t,3,self.heads,self.head_dim).unbind(2)
        q,k,v=q.transpose(1,2),k.transpose(1,2),v.transpose(1,2)
        q,k=_rope(q,positions),_rope(k,positions)
        cached = cache is not None
        if cached:
            k=torch.cat((cache[0],k),dim=2);v=torch.cat((cache[1],v),dim=2)
        keep_k,keep_v=k[:,:,-max_cache:],v[:,:,-max_cache:]
        y=torch.nn.functional.scaled_dot_product_attention(q,k,v,is_causal=not cached,
            dropout_p=self.dropout if self.training else 0.0)
        return self.output(y.transpose(1,2).contiguous().view(b,t,c)),(keep_k,keep_v)


class GatedBlock(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__();d=cfg.embedding_dim;ff=cfg.ff_dim or 4*d
        self.n1=nn.LayerNorm(d);self.attn=LocalRotaryAttention(d,cfg.n_heads,cfg.dropout)
        self.n2=nn.LayerNorm(d);self.gate=nn.Linear(d,2*ff);self.proj=nn.Linear(ff,d);self.drop=nn.Dropout(cfg.dropout)

    def forward(self,x,positions,cache=None,max_cache=256):
        a,cache=self.attn(self.n1(x),positions,cache,max_cache);x=x+a
        value,gate=self.gate(self.n2(x)).chunk(2,dim=-1)
        return x+self.drop(self.proj(value*torch.nn.functional.silu(gate))),cache


class CausalByteTransformerV2(nn.Module):
    """Bounded-cache rotary/SwiGLU byte Transformer for lossless coding."""
    def __init__(self, config: ModelConfig):
        super().__init__();self.config=config
        self.embedding=nn.Embedding(257,config.embedding_dim)
        self.blocks=nn.ModuleList(GatedBlock(config) for _ in range(config.num_layers))
        self.norm=nn.LayerNorm(config.embedding_dim);self.output=nn.Linear(config.embedding_dim,256,bias=False)

    def forward(self,tokens:torch.Tensor,hidden:Any=None):
        if tokens.dim()==1:tokens=tokens.unsqueeze(0)
        layers = hidden.get("layers") if isinstance(hidden,dict) else None
        absolute = int(hidden.get("position",0)) if isinstance(hidden,dict) else 0
        positions=torch.arange(absolute,absolute+tokens.size(1),device=tokens.device)
        x=self.embedding(tokens);new=[]
        for i,block in enumerate(self.blocks):
            x,cache=block(x,positions,layers[i] if layers else None,self.config.context_length);new.append(cache)
        return self.output(self.norm(x)),{"layers":new,"position":absolute+tokens.size(1)}

    def forward_sequence(self,tokens,hidden=None):
        if isinstance(tokens,(list,tuple)):tokens=torch.as_tensor(tokens,dtype=torch.long,device=next(self.parameters()).device)
        logits,hidden=self.forward(tokens,hidden)
        return (logits[0] if logits.dim()==3 and logits.size(0)==1 else logits),hidden

    def predict_block(self,block,prev_token=BOS_TOKEN,hidden=None):
        if not block:return torch.empty((0,256),device=next(self.parameters()).device),hidden
        return self.forward_sequence(torch.as_tensor([prev_token,*block[:-1]],device=next(self.parameters()).device),hidden)

    def step(self,previous_token:int,hidden=None):
        x=torch.tensor([[previous_token]],dtype=torch.long,device=next(self.parameters()).device)
        logits,hidden=self.forward(x,hidden);return logits[0,0],hidden
