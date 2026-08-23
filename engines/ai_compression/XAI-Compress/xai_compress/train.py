from __future__ import annotations
import argparse, csv, random
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader, random_split
from .model import CausalByteGRU, ModelConfig, BOS_TOKEN
from .checkpoint import save_checkpoint

EXCLUDED_EXTENSIONS = {".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".xaic", ".pt", ".pth"}

class ByteContextDataset(Dataset):
    """Bounded, lazy byte dataset for large on-disk corpora.

    Only (path, offset, length) tuples are kept in memory. Each chunk is read
    on demand. The number of samples and bytes considered per file are capped.
    """
    def __init__(self, root, context_length=128, stride=128, max_samples=200_000,
                 max_bytes_per_file=16*1024*1024, seed=42, include_archives=False):
        root=Path(root)
        if not root.is_dir(): raise ValueError(f"training directory not found: {root}")
        if min(context_length,stride,max_samples,max_bytes_per_file) < 1:
            raise ValueError("context_length, stride, max_samples and max_bytes_per_file must be positive")
        self.context_length=int(context_length); self.samples=[]
        paths=sorted(p for p in root.rglob("*") if p.is_file() and (include_archives or p.suffix.lower() not in EXCLUDED_EXTENSIONS))
        if not paths: raise ValueError("training directory contains no usable files")
        candidates=[]; files_used=0; bytes_considered=0
        # Deterministic bounded indexing. Stop before the index itself becomes large.
        candidate_cap=max_samples*4
        for path in paths:
            try: size=path.stat().st_size
            except OSError: continue
            usable=min(size,max_bytes_per_file)
            if usable <= 0: continue
            files_used+=1; bytes_considered+=usable
            last=max(0,usable-context_length)
            offsets=range(0,last+1,stride) if usable>context_length else (0,)
            for offset in offsets:
                length=min(context_length,usable-offset)
                if length>0: candidates.append((str(path),int(offset),int(length)))
                if len(candidates)>=candidate_cap: break
            if len(candidates)>=candidate_cap: break
        if not candidates: raise ValueError("no non-empty training samples")
        rng=random.Random(seed)
        self.samples=rng.sample(candidates,max_samples) if len(candidates)>max_samples else candidates
        rng.shuffle(self.samples)
        self.summary={"files_discovered":len(paths),"files_used":files_used,"samples":len(self.samples),
                      "bytes_considered":bytes_considered,"context_length":context_length,"stride":stride,
                      "max_bytes_per_file":max_bytes_per_file,"archives_included":include_archives}
        print(self.summary)
    def __len__(self): return len(self.samples)
    def __getitem__(self,idx):
        path,offset,length=self.samples[idx]
        try:
            import xai_compress_core
            chunk=bytes(xai_compress_core.read_block(path,offset,length))
        except ImportError:
            with open(path,"rb",buffering=1024*1024) as f:
                f.seek(offset); chunk=f.read(length)
        if len(chunk)!=length: raise OSError(f"short read: {path} offset={offset}")
        values=list(chunk); inputs=[BOS_TOKEN]+values[:-1]
        return torch.tensor(inputs,dtype=torch.long),torch.tensor(values,dtype=torch.long)

def collate(batch):
    lengths=torch.tensor([len(x[0]) for x in batch]); maxlen=int(lengths.max().item())
    inputs=torch.zeros((len(batch),maxlen),dtype=torch.long); targets=torch.full((len(batch),maxlen),-100,dtype=torch.long)
    for i,(x,y) in enumerate(batch): inputs[i,:len(x)]=x; targets[i,:len(y)]=y
    return inputs,targets

def seed_all(seed):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)

def train(data_dir,output,epochs=10,batch_size=64,lr=1e-3,context_length=128,seed=42,device=None,
          stride=128,max_samples=200_000,max_bytes_per_file=16*1024*1024,num_workers=0,
          embedding_dim=64,hidden_dim=128,num_layers=1,dropout=0.0,include_archives=False):
    seed_all(seed); device=device or ("cuda" if torch.cuda.is_available() else "cpu")
    ds=ByteContextDataset(data_dir,context_length,stride,max_samples,max_bytes_per_file,seed,include_archives)
    n_val=max(1,int(0.1*len(ds))); n_train=len(ds)-n_val
    if n_train<1: raise ValueError("not enough samples; provide more data")
    train_ds,val_ds=random_split(ds,[n_train,n_val],generator=torch.Generator().manual_seed(seed))
    common={"batch_size":batch_size,"collate_fn":collate,"num_workers":num_workers,"pin_memory":device=="cuda"}
    train_loader=DataLoader(train_ds,shuffle=True,**common); val_loader=DataLoader(val_ds,shuffle=False,**common)
    cfg=ModelConfig(embedding_dim=embedding_dim,hidden_dim=hidden_dim,num_layers=num_layers,
                    context_length=context_length,dropout=dropout)
    model=CausalByteGRU(cfg).to(device); opt=torch.optim.AdamW(model.parameters(),lr=lr)
    scheduler=torch.optim.lr_scheduler.ReduceLROnPlateau(opt,mode="min",factor=0.5,patience=1)
    criterion=nn.CrossEntropyLoss(ignore_index=-100); best=float("inf"); patience=3; stale=0; metrics=[]
    for epoch in range(1,epochs+1):
        model.train(); total=n=0
        for x,y in train_loader:
            x,y=x.to(device),y.to(device); opt.zero_grad(set_to_none=True); logits,_=model(x)
            loss=criterion(logits.reshape(-1,256),y.reshape(-1)); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step()
            count=int((y!=-100).sum().item()); total+=loss.detach().item()*count; n+=count
        model.eval(); vt=vn=0
        with torch.inference_mode():
            for x,y in val_loader:
                x,y=x.to(device),y.to(device); logits,_=model(x); loss=criterion(logits.reshape(-1,256),y.reshape(-1))
                count=int((y!=-100).sum().item()); vt+=loss.detach().item()*count; vn+=count
        tr=total/n; va=vt/vn; scheduler.step(va)
        row={"epoch":epoch,"train_cross_entropy":tr,"val_cross_entropy":va,"val_bpb_estimate":float(va/np.log(2)),"learning_rate":opt.param_groups[0]["lr"]}
        metrics.append(row); print(row)
        if va<best: best=va; stale=0; save_checkpoint(output,model,opt,epoch,{**row,"dataset":ds.summary})
        else:
            stale+=1
            if stale>=patience: break
    csv_path=Path(output).with_suffix(".metrics.csv"); csv_path.parent.mkdir(parents=True,exist_ok=True)
    with csv_path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=metrics[0].keys()); w.writeheader(); w.writerows(metrics)
    return output

def build_parser():
    p=argparse.ArgumentParser(); p.add_argument("data_dir"); p.add_argument("output")
    p.add_argument("--epochs",type=int,default=10); p.add_argument("--batch-size",type=int,default=64); p.add_argument("--lr",type=float,default=1e-3)
    p.add_argument("--context-length",type=int,default=128); p.add_argument("--stride",type=int,default=128); p.add_argument("--max-samples",type=int,default=200_000)
    p.add_argument("--max-bytes-per-file",type=int,default=16*1024*1024); p.add_argument("--num-workers",type=int,default=0)
    p.add_argument("--embedding-dim",type=int,default=64); p.add_argument("--hidden-dim",type=int,default=128); p.add_argument("--num-layers",type=int,default=1)
    p.add_argument("--dropout",type=float,default=0.0); p.add_argument("--include-archives",action="store_true"); p.add_argument("--seed",type=int,default=42); p.add_argument("--device")
    return p

def main(argv=None):
    a=build_parser().parse_args(argv); train(**vars(a))
if __name__=="__main__": main()
