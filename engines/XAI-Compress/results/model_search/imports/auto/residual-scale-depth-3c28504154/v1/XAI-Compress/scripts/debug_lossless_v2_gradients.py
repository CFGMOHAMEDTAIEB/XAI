"""Production-order Lossless V2 gradient diagnostic."""
from __future__ import annotations
import argparse,collections,hashlib,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
from torch import nn
from torch.utils.data import DataLoader,Dataset
from xai_compress.checkpoint import load_checkpoint,save_checkpoint
from xai_compress.compression import compress_bytes,decompress_bytes
from xai_compress.datasets.pipeline import dedupe_paths
from xai_compress.model import ModelConfig
from xai_compress.models.registry import build_model
from xai_compress.telemetry import collection_l2_norm
from xai_compress.train import ByteContextDataset,collate,seed_all,usable_paths

class Indexed(Dataset):
    def __init__(self,base):self.base=base
    def __len__(self):return len(self.base)
    def __getitem__(self,i):
        x,y=self.base[i];return x,y,i
def collate_indexed(batch):
    x,y=collate([(a,b) for a,b,_ in batch]);return x,y,[i for _,_,i in batch]
def stats(t):
    f=t.detach().float();finite=f[torch.isfinite(f)]
    return {"finite":bool(torch.isfinite(f).all()),"min":float(finite.min()) if finite.numel() else None,
            "max":float(finite.max()) if finite.numel() else None,"mean":float(finite.mean()) if finite.numel() else None,
            "norm":float(finite.norm()) if finite.numel() else None,"abs_max":float(finite.abs().max()) if finite.numel() else None}

def main():
    p=argparse.ArgumentParser();p.add_argument("data",type=Path);p.add_argument("--samples",type=int,default=180000)
    p.add_argument("--learning-rate",type=float,default=.001);p.add_argument("--seed",type=int,default=42)
    p.add_argument("--amp",action=argparse.BooleanOptionalAction,default=True);p.add_argument("--init-scale",type=float,default=65536)
    p.add_argument("--growth-interval",type=int,default=2000);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();seed_all(a.seed);device="cuda" if torch.cuda.is_available() else "cpu";use_amp=a.amp and device=="cuda"
    paths=dedupe_paths(usable_paths(a.data));rng=random.Random(a.seed);rng.shuffle(paths);nv=max(1,int(.1*len(paths)));train_paths=paths[nv:]
    # Build the exact Version 4 450k training sample population, then stop at
    # the requested diagnostic boundary so RandomSampler order is identical.
    base=ByteContextDataset(a.data,256,128,450000,32<<20,a.seed,False,train_paths)
    loader=DataLoader(Indexed(base),batch_size=16,shuffle=True,collate_fn=collate_indexed,num_workers=2,pin_memory=True,persistent_workers=True,prefetch_factor=2)
    cfg=ModelConfig(192,192,4,256,.1,"causal-byte-transformer-v2",6,768);model=build_model(cfg).to(device);model.numerical_debug=True
    opt=torch.optim.AdamW(model.parameters(),lr=a.learning_rate);scaler=torch.amp.GradScaler("cuda",enabled=use_amp,init_scale=a.init_scale,growth_interval=a.growth_interval)
    ce=nn.CrossEntropyLoss(ignore_index=-100);trend=collections.deque(maxlen=20);processed=0
    for step,(x,y,indices) in enumerate(loader,1):
        x=x.to(device);y=y.to(device);opt.zero_grad(set_to_none=True)
        with torch.amp.autocast("cuda",enabled=use_amp):logits,_=model(x);loss=ce(logits.flatten(0,1),y.flatten())
        if not torch.isfinite(loss):raise FloatingPointError(json.dumps({"stage":"loss","step":step,"loss":float(loss)}))
        scaler.scale(loss).backward();scaler.unscale_(opt)
        named={n:p.grad for n,p in model.named_parameters() if p.grad is not None};qkv={n:stats(g) for n,g in named.items() if n.endswith("attn.qkv.weight")}
        bad=next(((n,g) for n,g in named.items() if not torch.isfinite(g).all()),None)
        total=collection_l2_norm(named);processed+=len(indices)
        row={"step":step,"samples":processed,"loss":float(loss.detach()),"grad_norm":total,"scale":float(scaler.get_scale()),"qkv":qkv}
        trend.append(row)
        if step%100==0 or step>=9500:print("GRAD",json.dumps(row),flush=True)
        if bad:
            metas=[{"index":i,"path":base.samples[i][0],"offset":base.samples[i][1],"length":base.samples[i][2]} for i in indices]
            event={"classification":"NONFINITE_GRADIENT","step":step,"samples":processed,"tensor":bad[0],"gradient":stats(bad[1]),
                   "loss":float(loss.detach()),"scale":float(scaler.get_scale()),"total_grad_norm":total,"token_min":int(x.min()),"token_max":int(x.max()),
                   "batch":metas,"preceding_20":list(trend)}
            print("FIRST NON-FINITE EVENT",json.dumps(event),flush=True);a.output.write_text(json.dumps(event,indent=2));raise FloatingPointError(bad[0])
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
        if any(not torch.isfinite(g).all() for g in named.values()):raise FloatingPointError("nonfinite gradient after clipping")
        scaler.step(opt);scaler.update()
        for n,pv in model.named_parameters():
            if not torch.isfinite(pv).all():raise FloatingPointError("parameter:"+n)
        for state in opt.state.values():
            for k,v in state.items():
                if torch.is_tensor(v) and not torch.isfinite(v).all():raise FloatingPointError("optimizer:"+k)
        if processed>=a.samples:break
    a.output.parent.mkdir(parents=True,exist_ok=True);ckpt=a.output.with_suffix(".pt");save_checkpoint(ckpt,model,opt,1,{"samples":processed})
    loaded,_=load_checkpoint(ckpt,"cpu");p1,_=loaded.step(256);p2,_=loaded.step(256);assert torch.equal(p1,p2)
    probe=b"gradient-diagnostic-lossless"*8;blob=compress_bytes(probe,"neural-lossless",ckpt);restored=decompress_bytes(blob,ckpt)
    assert hashlib.sha256(probe).digest()==hashlib.sha256(restored).digest()
    result={"status":"PASS","samples":processed,"steps":step,"amp":use_amp,"lr":a.learning_rate,"init_scale":a.init_scale,"growth_interval":a.growth_interval,
            "checkpoint":str(ckpt),"checkpoint_sha256":hashlib.sha256(ckpt.read_bytes()).hexdigest(),"lossless_sha256":True}
    a.output.write_text(json.dumps(result,indent=2));print("STABILITY GATE PASS",json.dumps(result),flush=True)
if __name__=="__main__":main()
