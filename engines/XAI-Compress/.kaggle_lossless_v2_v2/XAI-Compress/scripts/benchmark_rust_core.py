from __future__ import annotations
import argparse, json, os, statistics, time
import psutil, torch
from xai_compress.entropy import quant

def timed(fn, repeats=5):
    samples=[]; process=psutil.Process(os.getpid()); peak=process.memory_info().rss
    for _ in range(repeats):
        start=time.perf_counter(); fn(); samples.append(time.perf_counter()-start); peak=max(peak,process.memory_info().rss)
    return {"median_seconds":statistics.median(samples),"latency_samples":samples,"peak_rss_bytes":peak}

def main():
    p=argparse.ArgumentParser();p.add_argument("--rows",type=int,default=4096);p.add_argument("--output",default="results/rust_core_benchmark.json");a=p.parse_args()
    logits=torch.randn(a.rows,256,dtype=torch.float64); probabilities=torch.softmax(logits,dim=-1).numpy()
    import xai_compress_core
    native=timed(lambda:xai_compress_core.quantize_probabilities_batch(probabilities,quant.NEURAL_TOTAL))
    # Force the explicit NumPy reference rather than the native-dispatch wrapper.
    def reference():
        remaining=quant.NEURAL_TOTAL-256;scaled=probabilities*remaining;base=np.floor(scaled).astype(np.int64);freq=base+1
        order=np.lexsort((np.broadcast_to(np.arange(256),scaled.shape),-(scaled-base)),axis=1)
        for i,left in enumerate(quant.NEURAL_TOTAL-freq.sum(axis=1)): freq[i,order[i,:int(left)]]+=1
        return [[0, *row.tolist()] for row in np.cumsum(freq,axis=1)]
    import numpy as np
    python=timed(reference); report={"rows":a.rows,"python":python,"rust":native,"measured_speedup":python["median_seconds"]/native["median_seconds"],"same":reference()==xai_compress_core.quantize_probabilities_batch(probabilities,quant.NEURAL_TOTAL)}
    from pathlib import Path
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=="__main__":main()
