from __future__ import annotations
import argparse,bz2,csv,gzip,lzma,time,hashlib
from pathlib import Path
from xai_compress.compression import compress_bytes,decompress_bytes

def timed(fn,*args):
    t=time.perf_counter(); out=fn(*args); return out,time.perf_counter()-t

def main():
    p=argparse.ArgumentParser(); p.add_argument("data_dir"); p.add_argument("--checkpoint"); p.add_argument("--output",default="benchmark_results.csv"); a=p.parse_args()
    rows=[]
    for path in [x for x in Path(a.data_dir).rglob("*") if x.is_file()]:
        data=path.read_bytes(); codecs={"gzip":(gzip.compress,gzip.decompress),"bz2":(bz2.compress,bz2.decompress),"lzma":(lzma.compress,lzma.decompress)}
        try:
            import zstandard as zstd; codecs["zstd"]=(zstd.ZstdCompressor().compress,zstd.ZstdDecompressor().decompress)
        except ImportError: pass
        try:
            import brotli; codecs["brotli"]=(brotli.compress,brotli.decompress)
        except ImportError: pass
        for name,(enc,dec) in codecs.items():
            blob,ct=timed(enc,data); restored,dt=timed(dec,blob); ok=restored==data
            rows.append({"file":str(path),"codec":name,"original_size":len(data),"compressed_size":len(blob),"bpb":8*len(blob)/max(1,len(data)),"compress_seconds":ct,"decompress_seconds":dt,"lossless":ok})
        modes=[("mouve_static",None)]+([("mouve_neural",a.checkpoint)] if a.checkpoint else [])
        for name,ckpt in modes:
            mode="neural" if ckpt else "static"; blob,ct=timed(compress_bytes,data,mode,ckpt); restored,dt=timed(decompress_bytes,blob,ckpt); ok=restored==data
            rows.append({"file":str(path),"codec":name,"original_size":len(data),"compressed_size":len(blob),"bpb":8*len(blob)/max(1,len(data)),"compress_seconds":ct,"decompress_seconds":dt,"lossless":ok})
    with open(a.output,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print(f"wrote {a.output}: {len(rows)} rows")
if __name__=="__main__": main()
