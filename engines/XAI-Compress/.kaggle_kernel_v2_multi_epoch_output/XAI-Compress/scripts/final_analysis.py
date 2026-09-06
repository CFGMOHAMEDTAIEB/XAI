from __future__ import annotations

import argparse, csv, hashlib, json, math, os, statistics, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "results" / "final_analysis"

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()

def write_csv(path: Path, rows: list[dict], fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=fields or list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)

def inventory(root=ROOT):
    from xai_compress.checkpoint import load_checkpoint
    rows=[]
    for path in sorted((root/"checkpoints").rglob("*.pt")):
        row={"name":path.name,"path":str(path.relative_to(root)),"checkpoint_size":path.stat().st_size,"sha256":sha256(path),"status":"VALID"}
        try:
            model,obj=load_checkpoint(path,"cpu");cfg=model.config
            row.update({"architecture":cfg.architecture_id,"parameters":sum(p.numel() for p in model.parameters()),"context":cfg.context_length,"embedding":cfg.embedding_dim,"hidden":cfg.hidden_dim,"layers":cfg.num_layers,"epoch":obj.get("epoch","N/A")})
            metrics=obj.get("metrics") or {};row["best_validation_loss"]=metrics.get("best_validation_cross_entropy",metrics.get("val_cross_entropy","N/A"));row["best_bpb"]=metrics.get("best_validation_bpb",metrics.get("val_bpb_estimate","N/A"))
        except Exception as exc:
            row.update({"status":"INVALID","error":str(exc),"architecture":"N/A","parameters":"N/A","context":"N/A","embedding":"N/A","hidden":"N/A","layers":"N/A","epoch":"N/A","best_validation_loss":"N/A","best_bpb":"N/A"})
        rows.append(row)
    return rows

EXT_CATEGORY={".txt":"text",".md":"text",".json":"structured",".csv":"structured",".xml":"structured",".yaml":"structured",".yml":"structured",".py":"source_code",".rs":"source_code",".js":"source_code",".bin":"binary",".png":"image",".jpg":"image",".jpeg":"image",".wav":"audio",".mp3":"audio",".mp4":"video",".zip":"already_compressed",".gz":"already_compressed",".xaic":"already_compressed"}

def build_corpus(out: Path, max_files=12, max_file_bytes=64*1024):
    preferred=ROOT/"data"/"test"; candidates=[]
    search=preferred if preferred.is_dir() and any(preferred.rglob("*")) else ROOT
    excluded={".git",".venv","checkpoints","results","target",".test-tmp",".kaggle_build"}
    for p in sorted(search.rglob("*")):
        if not p.is_file() or any(part in excluded or part.startswith(".kaggle_") for part in p.parts): continue
        if p.stat().st_size<1 or p.stat().st_size>max_file_bytes: continue
        category=EXT_CATEGORY.get(p.suffix.lower(),"binary")
        candidates.append((category,p))
    selected=[];seen=Counter()
    for category,p in candidates:
        if seen[category]>=2: continue
        selected.append((category,p));seen[category]+=1
        if len(selected)>=max_files: break
    rows=[{"file":str(p.relative_to(ROOT)),"category":c,"size":p.stat().st_size,"sha256":sha256(p),"source":"held-out data/test" if preferred in p.parents else "project fallback corpus","training_overlap_status":"NO" if preferred in p.parents else "UNKNOWN"} for c,p in selected]
    write_csv(out/"manifests"/"benchmark_manifest.csv",rows)
    return [(c,p) for c,p in selected]

def codec_functions():
    import bz2,gzip,lzma,zlib
    codecs={"gzip-9":(lambda b:gzip.compress(b,9),gzip.decompress,"gzip level 9"),"bz2-9":(lambda b:bz2.compress(b,9),bz2.decompress,"bz2 level 9"),"lzma-6":(lambda b:lzma.compress(b,preset=6),lzma.decompress,"LZMA preset 6"),"deflate-9":(lambda b:zlib.compress(b,9),zlib.decompress,"zlib level 9")}
    try:
        import zstandard as zstd; codecs["zstd-3"]=(zstd.ZstdCompressor(level=3).compress,zstd.ZstdDecompressor().decompress,"zstd level 3")
    except ImportError: pass
    try:
        import brotli; codecs["brotli-6"]=(lambda b:brotli.compress(b,quality=6),brotli.decompress,"brotli quality 6")
    except ImportError: pass
    return codecs

def stats(values):
    values=list(values); ordered=sorted(values);idx=max(0,math.ceil(.95*len(ordered))-1)
    return {"median":statistics.median(values),"mean":statistics.mean(values),"stddev":statistics.stdev(values) if len(values)>1 else 0.0,"p95":ordered[idx]}

def benchmark(corpus, models, out: Path, repeats=3):
    from xai_compress.compression import compress_bytes,decompress_bytes
    raw=[];roundtrips=[]
    methods=[(n,e,d,cfg,None) for n,(e,d,cfg) in codec_functions().items()]
    valid_models=[r for r in models if r["status"]=="VALID"]
    for model in valid_models:
        checkpoint=ROOT/model["path"]
        methods.append((f"xai:{model['name']}",lambda b,p=checkpoint:compress_bytes(b,"neural",p),lambda b,p=checkpoint:decompress_bytes(b,p),"XAIC neural arithmetic",model))
    for category,path in corpus:
        data=path.read_bytes()
        for name,encode,decode,config,model in methods:
            try:
                warm=encode(data);assert decode(warm)==data
                ok=True
                for rep in range(repeats):
                    t=time.perf_counter();blob=encode(data);ct=time.perf_counter()-t
                    t=time.perf_counter();restored=decode(blob);dt=time.perf_counter()-t
                    match=hashlib.sha256(restored).digest()==hashlib.sha256(data).digest();ok &= match
                    raw.append({"method":name,"configuration":config,"file":str(path.relative_to(ROOT)),"category":category,"repetition":rep+1,"original_bytes":len(data),"compressed_bytes":len(blob),"compression_ratio":len(data)/max(1,len(blob)),"bits_per_byte":8*len(blob)/max(1,len(data)),"compression_time_s":ct,"decompression_time_s":dt,"compression_MB_s":len(data)/(1<<20)/max(ct,1e-12),"decompression_MB_s":len(data)/(1<<20)/max(dt,1e-12),"peak_RSS_MB":"N/A","SHA256_match":match})
                if model is not None: roundtrips.append({"model":model["name"],"file":str(path.relative_to(ROOT)),"sha256_match":ok,"status":"PASS" if ok else "CORRECTNESS FAILURE"})
            except Exception as exc:
                if model is not None: roundtrips.append({"model":model["name"],"file":str(path.relative_to(ROOT)),"sha256_match":False,"status":"CORRECTNESS FAILURE","error":str(exc)})
    write_csv(out/"raw"/"benchmark_repetitions.csv",raw);write_csv(out/"roundtrip_results.csv",roundtrips)
    grouped=defaultdict(list)
    for r in raw: grouped[r["method"]].append(r)
    summary=[]
    failing={r["model"] for r in roundtrips if r["status"]!="PASS"}
    for method,rows in grouped.items():
        original=sum(r["original_bytes"] for r in rows)/repeats; compressed=sum(r["compressed_bytes"] for r in rows)/repeats
        cs=stats(r["compression_MB_s"] for r in rows);ds=stats(r["decompression_MB_s"] for r in rows)
        model_name=method.split(":",1)[1] if method.startswith("xai:") else None
        summary.append({"method":method,"BPB":8*compressed/max(1,original),"ratio":original/max(1,compressed),"compress_MB_s":cs["median"],"decompress_MB_s":ds["median"],"compress_mean":cs["mean"],"compress_stddev":cs["stddev"],"compress_p95":cs["p95"],"decompress_mean":ds["mean"],"decompress_stddev":ds["stddev"],"decompress_p95":ds["p95"],"peak_RSS_MB":"N/A","model_size_MB":next((r["checkpoint_size"]/(1<<20) for r in models if r["name"]==model_name),0),"lossless":model_name not in failing,"Pareto":""})
    for speed in ("compress_MB_s","decompress_MB_s"):
        for row in summary:
            dominated=any(other["BPB"]<=row["BPB"] and other[speed]>=row[speed] and (other["BPB"]<row["BPB"] or other[speed]>row[speed]) for other in summary if other["lossless"])
            if not dominated and row["lossless"]: row["Pareto"]=(row["Pareto"]+"," if row["Pareto"] else "")+("compression" if speed.startswith("compress") else "decompression")
    write_csv(out/"final_comparison.csv",summary)
    bytype=[]
    for (method,category),rows in {(r["method"],r["category"]):[q for q in raw if q["method"]==r["method"] and q["category"]==r["category"]] for r in raw}.items():
        bytype.append({"method":method,"category":category,"BPB":statistics.mean(r["bits_per_byte"] for r in rows),"ratio":statistics.mean(r["compression_ratio"] for r in rows),"compression_MB_s":statistics.median(r["compression_MB_s"] for r in rows),"decompression_MB_s":statistics.median(r["decompression_MB_s"] for r in rows)})
    write_csv(out/"results_by_data_type.csv",bytype)
    return raw,summary

def rust_benchmark(out: Path, workloads=(256,1024,4096,16384), repeats=5):
    import numpy as np, torch
    try: import xai_compress_core
    except ImportError: return []
    if not hasattr(xai_compress_core,"quantize_probabilities_batch"): return []
    torch.manual_seed(42);rows=[]
    for count in workloads:
        logits=torch.randn(count,256,dtype=torch.float64);probs=torch.softmax(logits,dim=-1).numpy();remaining=16384-256
        def python():
            scaled=probs*remaining;base=np.floor(scaled).astype(np.int64);freq=base+1;order=np.lexsort((np.broadcast_to(np.arange(256),scaled.shape),-(scaled-base)),axis=1)
            for i,left in enumerate(16384-freq.sum(axis=1)):freq[i,order[i,:int(left)]]+=1
            return [[0,*r.tolist()] for r in np.cumsum(freq,axis=1)]
        def rust(): return xai_compress_core.quantize_probabilities_batch(probs,16384)
        if python()!=rust(): raise RuntimeError("Python/Rust parity failure")
        # Warm both implementations before measuring to reduce import/cache bias.
        python();rust()
        for implementation,fn in (("Python",python),("Rust",rust)):
            times=[]
            for _ in range(repeats):t=time.perf_counter();fn();times.append(time.perf_counter()-t)
            s=stats(times);rows.append({"implementation":implementation,"rows":count,"median_latency_s":s["median"],"mean_latency_s":s["mean"],"p95_latency_s":s["p95"],"throughput_rows_s":count/s["median"],"peak_RSS_MB":"N/A","parity":True})
    write_csv(out/"rust_vs_python.csv",rows);return rows

def training_analysis(model_dir: Path, out: Path):
    candidates=list(model_dir.rglob("*metrics.csv"))+list(model_dir.rglob("metrics.csv"));
    if not candidates:return {"status":"N/A"}
    with candidates[0].open(newline="",encoding="utf-8") as f:rows=list(csv.DictReader(f))
    def number(row,key):
        try:return float(row[key])
        except:return None
    valid=[r for r in rows if number(r,"val_cross_entropy") is not None];best=min(valid,key=lambda r:number(r,"val_cross_entropy"))
    gaps=[number(r,"val_cross_entropy")-number(r,"train_cross_entropy") for r in valid if number(r,"train_cross_entropy") is not None]
    classification="INSUFFICIENT DATA"
    if len(gaps)>=4:
        tail=gaps[-max(2,len(gaps)//3):];classification="POSSIBLE OVERFITTING" if statistics.mean(tail)>statistics.mean(gaps[:len(tail)])*1.25 and number(valid[-1],"val_cross_entropy")>number(best,"val_cross_entropy") else "NO CLEAR OVERFITTING"
    return {"status":"AVAILABLE","best_epoch":int(best["epoch"]),"best_validation_loss":number(best,"val_cross_entropy"),"best_validation_BPB":number(best,"val_bpb_estimate"),"final_epoch":int(valid[-1]["epoch"]),"early_stopping":int(valid[-1]["epoch"])<60,"total_runtime_s":number(valid[-1],"elapsed_seconds"),"peak_VRAM_bytes":max((number(r,"vram_max_bytes") or 0 for r in valid),default=None),"average_samples_s":statistics.mean(number(r,"samples_per_second") for r in valid if number(r,"samples_per_second") is not None) if any(number(r,"samples_per_second") is not None for r in valid) else None,"generalization_gap_final":gaps[-1] if gaps else None,"overfitting_classification":classification,"history":rows}

def figures(out: Path, comparison, rust_rows, training):
    try: import matplotlib.pyplot as plt
    except ImportError:return
    fdir=out/"figures";fdir.mkdir(parents=True,exist_ok=True)
    def save(fig,name):fig.tight_layout();fig.savefig(fdir/f"{name}.png",dpi=180);fig.savefig(fdir/f"{name}.svg");plt.close(fig)
    if comparison:
        for field,title,name in (("ratio","Compression ratio (higher is better)","compression_ratio_comparison"),("BPB","Bits per byte (lower is better)","bits_per_byte_comparison"),("compress_MB_s","Compression MB/s","compression_speed_comparison"),("decompress_MB_s","Decompression MB/s","decompression_speed_comparison")):
            fig,ax=plt.subplots(figsize=(10,5));ax.bar([r["method"] for r in comparison],[r[field] for r in comparison]);ax.tick_params(axis="x",rotation=60);ax.set_title(title);save(fig,name)
        for speed,name in (("compress_MB_s","pareto_compression"),("decompress_MB_s","pareto_decompression")):
            fig,ax=plt.subplots();
            for r in comparison:ax.scatter(r["BPB"],r[speed]);ax.annotate(r["method"],(r["BPB"],r[speed]),fontsize=7)
            ax.set(xlabel="BPB (lower better)",ylabel=f"{speed} (higher better)");save(fig,name)
    if rust_rows:
        by=defaultdict(dict)
        for r in rust_rows:by[r["rows"]][r["implementation"]]=r
        xs=sorted(by);speed=[by[x]["Python"]["median_latency_s"]/by[x]["Rust"]["median_latency_s"] for x in xs]
        fig,ax=plt.subplots();ax.plot(xs,speed,marker="o");ax.set(xlabel="Rows",ylabel="Measured speedup",xscale="log",title="Rust quantization speedup");save(fig,"rust_speedup")
        fig,ax=plt.subplots();
        for impl in ("Python","Rust"):ax.plot(xs,[by[x][impl]["median_latency_s"] for x in xs],marker="o",label=impl)
        ax.legend();ax.set(xlabel="Rows",ylabel="Median latency (s)",xscale="log",yscale="log");save(fig,"rust_latency")
    if training.get("status")=="AVAILABLE":
        rows=training["history"];epochs=[int(r["epoch"]) for r in rows];best=training["best_epoch"]
        specs=[("train_cross_entropy","Training loss","training_loss"),("val_cross_entropy","Validation loss","validation_loss"),("val_bpb_estimate","Validation BPB","bpb_evolution"),("learning_rate","Learning rate","learning_rate"),("gpu_utilization_percent","GPU utilization %","gpu_utilization"),("vram_max_bytes","VRAM bytes","vram_usage"),("samples_per_second","Samples/s","training_throughput")]
        for key,title,name in specs:
            vals=[]
            for r in rows:
                try:vals.append(float(r[key]))
                except:vals.append(float("nan"))
            fig,ax=plt.subplots();ax.plot(epochs,vals);ax.axvline(best,color="red",linestyle="--",label="best epoch");ax.legend();ax.set(xlabel="Epoch",ylabel=title,title=title);save(fig,name)

def dataset_figures(out: Path, corpus):
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:return
    if not corpus:return
    fdir=out/"figures"
    categories=Counter(c for c,_ in corpus)
    fig,ax=plt.subplots();ax.bar(categories.keys(),categories.values());ax.tick_params(axis="x",rotation=45);ax.set(ylabel="Files",title="Benchmark corpus composition");fig.tight_layout();fig.savefig(fdir/"dataset_composition.png",dpi=180);fig.savefig(fdir/"dataset_composition.svg");plt.close(fig)
    sizes=[p.stat().st_size for _,p in corpus]
    fig,ax=plt.subplots();ax.hist(sizes,bins=min(10,len(sizes)));ax.set(xlabel="Bytes",ylabel="Files",title="Benchmark file-size distribution");fig.tight_layout();fig.savefig(fdir/"file_size_distribution.png",dpi=180);fig.savefig(fdir/"file_size_distribution.svg");plt.close(fig)
    sample=corpus[0][1].read_bytes()[:65536];values=np.frombuffer(sample,dtype=np.uint8)
    if values.size:
        counts=np.bincount(values,minlength=256)
        fig,ax=plt.subplots();ax.bar(np.arange(256),counts);ax.set(xlabel="Byte value",ylabel="Count",title=f"Byte frequencies: {corpus[0][1].name}");fig.tight_layout();fig.savefig(fdir/"byte_frequency.png",dpi=180);fig.savefig(fdir/"byte_frequency.svg");plt.close(fig)
        shown=values[:min(2048,values.size)]
        fig,ax=plt.subplots();ax.plot(shown,linewidth=.6);ax.set(xlabel="Byte offset",ylabel="Value",title=f"Raw byte signal: {corpus[0][1].name}");fig.tight_layout();fig.savefig(fdir/"raw_signal.png",dpi=180);fig.savefig(fdir/"raw_signal.svg");plt.close(fig)

def markdown_table(rows):
    fields=["method","BPB","ratio","compress_MB_s","decompress_MB_s","peak_RSS_MB","model_size_MB","lossless","Pareto"]
    lines=["|"+"|".join(fields)+"|","|"+"|".join(["---"]*len(fields))+"|"]
    for r in rows:lines.append("|"+"|".join(str(r.get(k,"N/A")) for k in fields)+"|")
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,default=DEFAULT_OUT);p.add_argument("--repetitions",type=int,default=3);p.add_argument("--skip-model-benchmark",action="store_true");p.add_argument("--kaggle-status",default="NOT CHECKED");a=p.parse_args();out=a.output;[ (out/d).mkdir(parents=True,exist_ok=True) for d in ("raw","figures","tables","manifests") ]
    models=inventory();write_csv(out/"model_inventory.csv",models)
    corpus=build_corpus(out);raw,comparison=([],[])
    if not a.skip_model_benchmark:raw,comparison=benchmark(corpus,models,out,a.repetitions)
    else:
        write_csv(out/"raw"/"benchmark_repetitions.csv",[],["method","configuration","file","category","repetition","original_bytes","compressed_bytes","compression_ratio","bits_per_byte","compression_time_s","decompression_time_s","compression_MB_s","decompression_MB_s","peak_RSS_MB","SHA256_match"])
        write_csv(out/"roundtrip_results.csv",[],["model","file","sha256_match","status","error"])
        write_csv(out/"final_comparison.csv",[],["method","BPB","ratio","compress_MB_s","decompress_MB_s","peak_RSS_MB","model_size_MB","lossless","Pareto"])
        write_csv(out/"results_by_data_type.csv",[],["method","category","BPB","ratio","compression_MB_s","decompression_MB_s"])
    rust_rows=rust_benchmark(out)
    research_dirs=sorted((ROOT/"checkpoints"/"kaggle").glob("research*")) if (ROOT/"checkpoints"/"kaggle").exists() else []
    training=training_analysis(research_dirs[-1],out) if research_dirs else {"status":"N/A"}
    figures(out,comparison,rust_rows,training);dataset_figures(out,corpus)
    evolution=[]
    for r in models:evolution.append({"Experiment":r["name"],"Architecture":r["architecture"],"Parameters":r["parameters"],"Context":r["context"],"Dataset":"N/A","Samples":"N/A","Epochs":r["epoch"],"Best validation loss":r["best_validation_loss"],"Best BPB":r["best_bpb"],"Checkpoint size":r["checkpoint_size"],"Compression ratio":"N/A","Compression speed":"N/A","Decompression speed":"N/A","Peak RSS":"N/A","Round-trip status":next(("CORRECTNESS FAILURE" for x in (out/"roundtrip_results.csv",) if x.exists() and r["status"]!="VALID"),"N/A")})
    write_csv(out/"model_evolution.csv",evolution)
    (out/"final_comparison.md").write_text("# Final measured comparison\n\n"+(markdown_table(comparison) if comparison else "N/A: benchmark not run."),encoding="utf-8")
    conclusion=["# Conservative conclusion","",f"RESEARCH training analysis: {training.get('status')}. Final RESEARCH claims are unavailable until a valid synchronized best.pt and history exist.","",f"Discovered checkpoints: {len(models)} ({sum(r['status']=='VALID' for r in models)} valid).",f"Rust workloads measured: {len(rust_rows)//2}. Exact parity is required before timing.","","No method is declared a universal winner; consult the measured Pareto tables after the RESEARCH artifact is available."]
    (out/"conclusion.md").write_text("\n".join(conclusion),encoding="utf-8")
    report={"generated_utc":datetime.now(timezone.utc).isoformat(),"kaggle_status":a.kaggle_status,"research_training":training,"models":models,"benchmark_manifest_count":len(corpus),"benchmark_rows":len(raw),"comparison":comparison,"rust":rust_rows,"limitations":["Peak RSS is N/A where no isolated-process measurement was available.","Training overlap is UNKNOWN for fallback project files.","RESEARCH conclusions require a completed synchronized Kaggle model."]}
    report.pop("research_training") if False else None
    (out/"final_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(out),"models":len(models),"valid_models":sum(r["status"]=="VALID" for r in models),"benchmark_rows":len(raw),"research":training.get("status")},indent=2))

if __name__=="__main__":main()
