from __future__ import annotations

import argparse,csv,json,math,random,time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader,Dataset

from .checkpoint import load_checkpoint,save_checkpoint
from .lossy import read_ppm
from .model import ModelConfig
from .models.registry import build_model


class PPMDataset(Dataset):
    def __init__(self,root,crop=64,max_samples=10000,seed=42):
        self.crop=crop;self.paths=[]
        for p in sorted(Path(root).rglob("*.ppm")):
            try:
                _,w,h=read_ppm(p.read_bytes())
                if w>=crop and h>=crop:self.paths.append(p)
            except Exception:pass
        random.Random(seed).shuffle(self.paths);self.paths=self.paths[:max_samples]
        if len(self.paths)<2:raise ValueError("lossy training requires at least two readable P6 PPM images")
    def __len__(self):return len(self.paths)
    def __getitem__(self,index):
        a,_,_=read_ppm(self.paths[index].read_bytes());h,w,_=a.shape;y=(h-self.crop)//2;x=(w-self.crop)//2
        return torch.from_numpy(a[y:y+self.crop,x:x+self.crop].copy()).permute(2,0,1).float()/255


def train_lossy(data_dir,output="checkpoints/neural_lossy_v1/best.pt",epochs=20,batch_size=16,lr=1e-3,
                latent_channels=32,crop=64,max_samples=10000,quality="medium",device=None,resume=None,
                early_stopping_patience=5,checkpoint_every=5):
    device=device or ("cuda" if torch.cuda.is_available() else "cpu");dataset=PPMDataset(data_dir,crop,max_samples)
    nval=max(1,len(dataset)//10);train_ds,val_ds=torch.utils.data.random_split(dataset,[len(dataset)-nval,nval],generator=torch.Generator().manual_seed(42))
    train_loader=DataLoader(train_ds,batch_size=batch_size,shuffle=True);val_loader=DataLoader(val_ds,batch_size=batch_size)
    cfg=ModelConfig(embedding_dim=latent_channels,hidden_dim=latent_channels,num_layers=1,context_length=1,dropout=0,architecture_id="conv-image-autoencoder-v1")
    model=build_model(cfg).to(device);opt=torch.optim.AdamW(model.parameters(),lr=lr);start=1;best=float("inf")
    if resume:
        loaded,obj=load_checkpoint(resume,device);model.load_state_dict(loaded.state_dict());opt.load_state_dict(obj.get("optimizer_state",opt.state_dict()));start=int(obj.get("epoch",0))+1;best=float((obj.get("metrics") or {}).get("best_val_objective",best))
    scaler=torch.amp.GradScaler("cuda",enabled=str(device).startswith("cuda"));scheduler=torch.optim.lr_scheduler.ReduceLROnPlateau(opt,patience=1,factor=.5)
    lambdas={"low":.002,"medium":.01,"high":.05};lam=lambdas[quality];rows=[];stale=0;output=Path(output);latest=output.with_name(output.stem+".latest.pt");started=time.perf_counter()
    def objective(x,training=True):
        z=model.encode(x);noisy=z+(torch.empty_like(z).uniform_(-.5,.5) if training else 0);recon=model.decode(noisy)[...,:x.shape[-2],:x.shape[-1]]
        distortion=torch.mean((recon-x)**2);rate=torch.mean(torch.log2(1+torch.abs(z)));return rate+lam*distortion,rate,distortion
    for epoch in range(start,epochs+1):
        model.train();tot=0
        for x in train_loader:
            x=x.to(device);opt.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda",enabled=str(device).startswith("cuda")):loss,rate,dist=objective(x,True)
            scaler.scale(loss).backward();scaler.unscale_(opt);nn.utils.clip_grad_norm_(model.parameters(),1);scaler.step(opt);scaler.update();tot+=float(loss.detach())*len(x)
        model.eval();vt=vr=vd=0
        with torch.inference_mode():
            for x in val_loader:
                x=x.to(device);loss,rate,dist=objective(x,False);vt+=float(loss)*len(x);vr+=float(rate)*len(x);vd+=float(dist)*len(x)
        val=vt/len(val_ds);scheduler.step(val);row={"epoch":epoch,"train_objective":tot/len(train_ds),"val_objective":val,"val_rate_proxy":vr/len(val_ds),"val_mse":vd/len(val_ds),"learning_rate":opt.param_groups[0]["lr"],"elapsed_seconds":time.perf_counter()-started,"quality":quality,"lambda":lam};rows.append(row)
        metrics={**row,"best_val_objective":min(best,val),"rate_distortion_objective":"R + lambda*D"};save_checkpoint(latest,model,opt,epoch,metrics,scaler,scheduler)
        if checkpoint_every and epoch%checkpoint_every==0:save_checkpoint(output.with_name(f"{output.stem}.epoch-{epoch:04d}.pt"),model,opt,epoch,metrics,scaler,scheduler)
        if val<best:best=val;stale=0;save_checkpoint(output,model,opt,epoch,metrics,scaler,scheduler)
        else:stale+=1
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.with_suffix(".metrics.csv").open("w",newline="",encoding="utf-8") as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
        output.with_suffix(".history.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
        if stale>=early_stopping_patience:break
    output.with_suffix(".summary.json").write_text(json.dumps({"checkpoint":str(output),"best_val_objective":best,"quality":quality,"lambda":lam,"model_config":cfg.__dict__},indent=2),encoding="utf-8")
    return output


def main():
    p=argparse.ArgumentParser();p.add_argument("data_dir");p.add_argument("--output",default="checkpoints/neural_lossy_v1/best.pt");p.add_argument("--epochs",type=int,default=20);p.add_argument("--quality",choices=["low","medium","high"],default="medium");p.add_argument("--resume");a=p.parse_args();train_lossy(**vars(a))
if __name__=="__main__":main()
