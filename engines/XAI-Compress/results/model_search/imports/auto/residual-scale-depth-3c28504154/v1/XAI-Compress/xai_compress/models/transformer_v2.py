from __future__ import annotations

import math
from typing import Any

import torch
from torch import nn

from ..model import BOS_TOKEN, ModelConfig


class NumericalDebugError(FloatingPointError):
    pass


def _finite(stage: str, value: torch.Tensor, layer=None):
    if torch.isfinite(value).all():
        return
    finite=value.detach()[torch.isfinite(value)]
    details={"stage":stage,"layer":layer,"dtype":str(value.dtype),"shape":list(value.shape),
             "finite_min":float(finite.min()) if finite.numel() else None,
             "finite_max":float(finite.max()) if finite.numel() else None,
             "finite_mean":float(finite.float().mean()) if finite.numel() else None,
             "finite_std":float(finite.float().std()) if finite.numel()>1 else None,
             "finite_abs_max":float(finite.abs().max()) if finite.numel() else None}
    raise NumericalDebugError(f"FIRST NON-FINITE STAGE = {stage}; {details}")


def _observe(observer, stage: str, value: torch.Tensor, layer=None):
    """Send an activation to an optional diagnostic observer.

    The production path pays only a callable check.  Observers must detach any
    values they retain so diagnostics cannot keep the autograd graph alive.
    """
    if callable(observer):
        observer(stage, value, layer)


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

    def forward(self, x, positions, cache=None, max_cache=256, numerical_debug=False, layer=None, observer=None):
        b,t,c=x.shape
        q,k,v=self.qkv(x).view(b,t,3,self.heads,self.head_dim).unbind(2)
        q,k,v=q.transpose(1,2),k.transpose(1,2),v.transpose(1,2)
        _observe(observer,"attention_q",q,layer);_observe(observer,"attention_k",k,layer);_observe(observer,"attention_v",v,layer)
        if numerical_debug:
            _finite("attention_q",q,layer);_finite("attention_k",k,layer);_finite("attention_v",v,layer)
        q,k=_rope(q,positions),_rope(k,positions)
        cached = cache is not None
        if cached:
            k=torch.cat((cache[0],k),dim=2);v=torch.cat((cache[1],v),dim=2)
        keep_k,keep_v=k[:,:,-max_cache:],v[:,:,-max_cache:]
        # T4 autocast uses fp16.  Long training exposed non-finite attention
        # scores even though the short smoke test passed, so keep the
        # numerically sensitive score/softmax path in fp32 and cast its result
        # back for the remaining AMP-enabled layers.
        attention_dtype = q.dtype
        with torch.autocast(device_type=x.device.type, enabled=False):
            if numerical_debug:
                raw=q.float()@k.float().transpose(-2,-1);_finite("attention_logits_unscaled",raw,layer)
                scores=raw/math.sqrt(self.head_dim);_finite("attention_logits_scaled",scores,layer)
                if not cached:
                    mask=torch.ones((t,k.size(2)),dtype=torch.bool,device=x.device).tril()
                    if not mask.any(dim=-1).all():raise NumericalDebugError(f"fully masked attention row at layer {layer}")
                    scores=scores.masked_fill(~mask,float("-inf"))
                if torch.isnan(scores).any() or torch.isposinf(scores).any():
                    raise NumericalDebugError(f"invalid post-mask attention logits at layer {layer}")
                probs=torch.softmax(scores,dim=-1);_finite("attention_softmax",probs,layer)
                if self.training and self.dropout:probs=torch.dropout(probs,self.dropout,train=True)
                y=probs@v.float();_finite("attention_output",y,layer)
            else:
                y=torch.nn.functional.scaled_dot_product_attention(
                    q.float(),k.float(),v.float(),is_causal=not cached,
                    dropout_p=self.dropout if self.training else 0.0)
        _observe(observer,"attention_context",y,layer)
        y=y.to(attention_dtype)
        output=self.output(y.transpose(1,2).contiguous().view(b,t,c))
        _observe(observer,"attention_output",output,layer)
        return output,(keep_k,keep_v)


class GatedBlock(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__();d=cfg.embedding_dim;ff=cfg.ff_dim or 4*d
        self.n1=nn.LayerNorm(d);self.attn=LocalRotaryAttention(d,cfg.n_heads,cfg.dropout)
        self.n2=nn.LayerNorm(d);self.gate=nn.Linear(d,2*ff);self.proj=nn.Linear(ff,d);self.drop=nn.Dropout(cfg.dropout)
        self.residual_scale=float(cfg.residual_scale)

    def forward(self,x,positions,cache=None,max_cache=256,numerical_debug=False,layer=None,observer=None):
        _observe(observer,"block_input",x,layer)
        normalized_attention=self.n1(x);_observe(observer,"attention_normalized_input",normalized_attention,layer)
        a,cache=self.attn(normalized_attention,positions,cache,max_cache,numerical_debug,layer,observer);x=x+self.residual_scale*a
        _observe(observer,"residual_attention",x,layer)
        if numerical_debug:_finite("residual_attention",x,layer)
        normalized_ffn=self.n2(x);_observe(observer,"ffn_normalized_input",normalized_ffn,layer)
        projected=self.gate(normalized_ffn);_observe(observer,"ffn_first_projection",projected,layer)
        value,gate=projected.chunk(2,dim=-1)
        if numerical_debug:_finite("ffn_value",value,layer);_finite("ffn_gate",gate,layer)
        activated_gate=torch.nn.functional.silu(gate);_observe(observer,"ffn_gate_activation",activated_gate,layer)
        gated=value*activated_gate;_observe(observer,"ffn_gated_product",gated,layer)
        out=self.proj(gated);_observe(observer,"ffn_output",out,layer)
        if numerical_debug:_finite("ffn_output",out,layer)
        # Dropout scales retained values by 1 / (1 - p).  On T4 autocast the
        # finite FP16 FFN output can therefore overflow inside dropout before
        # it reaches the FP32 residual stream.  Preserve the same operation,
        # but execute this numerically sensitive rescale in the residual dtype.
        with torch.autocast(device_type=x.device.type, enabled=False):
            dropped=self.drop(out.to(x.dtype))
        _observe(observer,"ffn_dropout",dropped,layer)
        if numerical_debug:_finite("ffn_dropout",dropped,layer)
        x=x+self.residual_scale*dropped
        _observe(observer,"residual_ffn",x,layer)
        if numerical_debug:_finite("residual_ffn",x,layer)
        return x,cache


class CausalByteTransformerV2(nn.Module):
    """Bounded-cache rotary/SwiGLU byte Transformer for lossless coding."""
    def __init__(self, config: ModelConfig):
        super().__init__();self.config=config
        self.embedding=nn.Embedding(257,config.embedding_dim)
        self.blocks=nn.ModuleList(GatedBlock(config) for _ in range(config.num_layers))
        self.norm=nn.LayerNorm(config.embedding_dim);self.output=nn.Linear(config.embedding_dim,256,bias=False)
        self.numerical_debug=False
        self.activation_observer=None

    def forward(self,tokens:torch.Tensor,hidden:Any=None):
        if tokens.dim()==1:tokens=tokens.unsqueeze(0)
        layers = hidden.get("layers") if isinstance(hidden,dict) else None
        absolute = int(hidden.get("position",0)) if isinstance(hidden,dict) else 0
        positions=torch.arange(absolute,absolute+tokens.size(1),device=tokens.device)
        if self.numerical_debug:
            if tokens.numel() and (int(tokens.min())<0 or int(tokens.max())>256):raise NumericalDebugError("input token outside 0..256")
        x=self.embedding(tokens);new=[]
        _observe(self.activation_observer,"embedding",x)
        if self.numerical_debug:_finite("embedding",x)
        for i,block in enumerate(self.blocks):
            x,cache=block(x,positions,layers[i] if layers else None,self.config.context_length,self.numerical_debug,i,self.activation_observer);new.append(cache)
        x=self.norm(x)
        if self.numerical_debug:_finite("final_norm",x)
        logits=self.output(x)
        _observe(self.activation_observer,"output_logits",logits)
        if self.numerical_debug:_finite("output_logits",logits)
        return logits,{"layers":new,"position":absolute+tokens.size(1)}

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
