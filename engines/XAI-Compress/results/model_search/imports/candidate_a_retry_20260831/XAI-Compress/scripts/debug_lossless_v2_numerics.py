"""Bounded Lossless V2 numerical-stability reproducer."""
from __future__ import annotations
import argparse, math, random, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from xai_compress.model import ModelConfig
from xai_compress.models.registry import build_model
from xai_compress.train import ByteContextDataset, collate, require_finite, seed_all

def main():
    p=argparse.ArgumentParser()
    p.add_argument("data",type=Path);p.add_argument("--samples",type=int,default=1024)
    p.add_argument("--batch-size",type=int,default=16);p.add_argument("--learning-rate",type=float,default=1e-3)
    p.add_argument("--max-steps",type=int,default=256);p.add_argument("--seed",type=int,default=42)
    p.add_argument("--gradient-clip",type=float,default=1.0);p.add_argument("--numerical-debug",action="store_true")
    amp=p.add_mutually_exclusive_group();amp.add_argument("--amp",dest="amp",action="store_true");amp.add_argument("--no-amp",dest="amp",action="store_false");p.set_defaults(amp=True)
    a=p.parse_args();seed_all(a.seed);device="cuda" if torch.cuda.is_available() else "cpu";use_amp=a.amp and device=="cuda"
    ds=ByteContextDataset(a.data,256,128,a.samples,32<<20,a.seed)
    loader=DataLoader(ds,batch_size=a.batch_size,shuffle=True,collate_fn=collate,num_workers=0)
    cfg=ModelConfig(embedding_dim=192,hidden_dim=192,num_layers=4,context_length=256,dropout=.1,
                    architecture_id="causal-byte-transformer-v2",n_heads=6,ff_dim=768)
    model=build_model(cfg).to(device);model.numerical_debug=a.numerical_debug;opt=torch.optim.AdamW(model.parameters(),lr=a.learning_rate)
    scaler=torch.amp.GradScaler("cuda",enabled=use_amp);ce=nn.CrossEntropyLoss(ignore_index=-100)
    print("step,loss,grad_norm,max_logit,max_attention_logit,parameter_abs_max,amp_scale,finite")
    for step,(x,y) in enumerate(loader,1):
        if step>a.max_steps:break
        try:
            x=x.to(device);y=y.to(device);require_finite(x.float(),"input",1,step)
            opt.zero_grad(set_to_none=True)
            with torch.amp.autocast(device_type=device,enabled=use_amp):
                logits,_=model(x);loss=ce(logits.flatten(0,1),y.flatten())
            require_finite(logits,"logits",1,step);require_finite(loss,"loss",1,step)
            scaler.scale(loss).backward();scaler.unscale_(opt)
            grads=[p.grad for p in model.parameters() if p.grad is not None]
            for i,g in enumerate(grads):require_finite(g,f"gradient:{i}",1,step)
            grad_norm=torch.linalg.vector_norm(torch.stack([g.detach().float().norm() for g in grads]))
            if a.gradient_clip>0:torch.nn.utils.clip_grad_norm_(model.parameters(),a.gradient_clip)
            scaler.step(opt);scaler.update()
            for name,pv in model.named_parameters():require_finite(pv,f"parameter:{name}",1,step)
            for state in opt.state.values():
                for key,value in state.items():
                    if torch.is_tensor(value):require_finite(value,f"optimizer:{key}",1,step)
            pmax=max(float(pv.detach().abs().max()) for pv in model.parameters())
            print(f"{step},{float(loss.detach()):.9g},{float(grad_norm):.9g},{float(logits.detach().abs().max()):.9g},N/A,{pmax:.9g},{float(scaler.get_scale()):.9g},true",flush=True)
        except Exception as exc:
            print(f"DIAGNOSTIC FAILURE epoch=1 step={step} lr={a.learning_rate} amp={use_amp} amp_scale={float(scaler.get_scale())}",flush=True)
            print(str(exc),flush=True)
            raise

if __name__=="__main__":main()
