from __future__ import annotations
import argparse,json
from pathlib import Path
from .compression import compress_file,decompress_file
from .format import unpack_container

def main(argv=None):
    p=argparse.ArgumentParser(prog="xai-compress"); sub=p.add_subparsers(dest="command",required=True)
    c=sub.add_parser("compress"); c.add_argument("input"); c.add_argument("output"); c.add_argument("--mode",choices=["static","neural"],default="static"); c.add_argument("--checkpoint"); c.add_argument("--overwrite",action="store_true")
    d=sub.add_parser("decompress"); d.add_argument("input"); d.add_argument("output"); d.add_argument("--checkpoint"); d.add_argument("--overwrite",action="store_true"); d.add_argument("--max-output-size",type=int,default=8<<30)
    i=sub.add_parser("inspect"); i.add_argument("input")
    t=sub.add_parser("train"); t.add_argument("data_dir"); t.add_argument("output")
    t.add_argument("--epochs",type=int,default=10); t.add_argument("--batch-size",type=int,default=64); t.add_argument("--lr",type=float,default=1e-3)
    t.add_argument("--context-length",type=int,default=128); t.add_argument("--stride",type=int,default=128); t.add_argument("--max-samples",type=int,default=200_000)
    t.add_argument("--max-bytes-per-file",type=int,default=16*1024*1024); t.add_argument("--num-workers",type=int,default=0)
    t.add_argument("--embedding-dim",type=int,default=64); t.add_argument("--hidden-dim",type=int,default=128); t.add_argument("--num-layers",type=int,default=1)
    t.add_argument("--dropout",type=float,default=0.0); t.add_argument("--include-archives",action="store_true"); t.add_argument("--seed",type=int,default=42); t.add_argument("--device")
    a=p.parse_args(argv)
    if a.command=="compress": print(json.dumps(compress_file(a.input,a.output,a.mode,a.checkpoint,a.overwrite),indent=2))
    elif a.command=="decompress": print(json.dumps(decompress_file(a.input,a.output,a.checkpoint,a.overwrite,a.max_output_size),indent=2))
    elif a.command=="inspect": md,_=unpack_container(Path(a.input).read_bytes()); print(json.dumps(md,indent=2,sort_keys=True))
    else:
        from .train import train
        kwargs=vars(a); kwargs.pop("command"); train(**kwargs)
