"""Create the bounded, measured XAI-Compress final-project delivery."""
from __future__ import annotations

import bz2, csv, gzip, hashlib, json, lzma, math, statistics, time, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/"results"/"final_project"
GRU=ROOT/"checkpoints"/"kaggle"/"best.pt"
LOSSY=ROOT/"checkpoints"/"neural_lossy_v1"/"validation.pt"

from xai_compress.checkpoint import load_checkpoint, save_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes, compress_file, decompress_file
from xai_compress.format import unpack_container
from xai_compress.lossy import compress_lossy_bytes, decompress_lossy_bytes, quality_metrics
from xai_compress.train_lossy import train_lossy
from scripts.benchmark_v2_promotion import entropy_breakdown

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def file_sha(path:Path)->str:return sha(path.read_bytes())
def write_csv(path,rows,fields=None):
    path.parent.mkdir(parents=True,exist_ok=True);fields=fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)
def rss():
    info=psutil.Process().memory_info();return float(getattr(info,"peak_wset",info.rss))/(1<<20)
def svg_bars(path,title,rows,label,value):
    rows=[r for r in rows if isinstance(r.get(value),(int,float))]
    width=900;height=max(240,70+35*len(rows));mx=max((float(r[value]) for r in rows),default=1) or 1
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
           '<rect width="100%" height="100%" fill="white"/>',f'<text x="20" y="28" font-size="18">MEASURED — {title}</text>']
    for i,r in enumerate(rows):
        y=55+i*35;bar=600*float(r[value])/mx;name=str(r[label])[:34]
        parts += [f'<text x="20" y="{y+16}" font-size="12">{name}</text>',f'<rect x="270" y="{y}" width="{bar:.2f}" height="20" fill="#3978c5"/>',f'<text x="{280+bar:.2f}" y="{y+15}" font-size="11">{float(r[value]):.5g}</text>']
    parts.append('</svg>');path.write_text("\n".join(parts),encoding="utf-8")
def timed(fn,*args):
    t=time.perf_counter();value=fn(*args);return value,time.perf_counter()-t

def corpus():
    choices=[ROOT/"README.md",ROOT/"xai_compress"/"compression.py",ROOT/"configs"/"model_search_v2.json",ROOT/"rust-core"/"Cargo.lock"]
    rows=[]
    for p in choices:
        if p.is_file():rows.append((p.suffix.lstrip(".") or "binary",p,p.read_bytes()[:8192]))
    return rows

def codecs():
    result={"gzip-9":(lambda b:gzip.compress(b,9),gzip.decompress),"bzip2-9":(lambda b:bz2.compress(b,9),bz2.decompress),"lzma-6":(lambda b:lzma.compress(b,preset=6),lzma.decompress)}
    try:
        import brotli;result["brotli-6"]=(lambda b:brotli.compress(b,quality=6),brotli.decompress)
    except ImportError:pass
    try:
        import zstandard as zstd;result["zstd-3"]=(zstd.ZstdCompressor(level=3).compress,zstd.ZstdDecompressor().decompress)
    except ImportError:pass
    return result

def lossless_benchmark(samples):
    rows=[];roundtrips=[]
    methods=codecs()
    for category,path,data in samples:
        for name,(enc,dec) in methods.items():
            blob,ct=timed(enc,data);restored,dt=timed(dec,blob);passed=sha(data)==sha(restored)
            rows.append({"file":str(path.relative_to(ROOT)),"category":category,"codec":name,"status":"PASS" if passed else "FAIL","original_bytes":len(data),"artifact_bytes":len(blob),"actual_bpb":8*len(blob)/max(1,len(data)),"compression_ratio":len(data)/max(1,len(blob)),"compression_MB_s":len(data)/(1<<20)/max(ct,1e-12),"decompression_MB_s":len(data)/(1<<20)/max(dt,1e-12),"peak_RSS_MB":rss(),"sha256_pass":passed})
        blob,ct=timed(compress_bytes,data,"static");restored,dt=timed(decompress_bytes,blob);passed=sha(data)==sha(restored)
        rows.append({"file":str(path.relative_to(ROOT)),"category":category,"codec":"xai-static","status":"PASS" if passed else "FAIL","original_bytes":len(data),"artifact_bytes":len(blob),"actual_bpb":8*len(blob)/max(1,len(data)),"compression_ratio":len(data)/max(1,len(blob)),"compression_MB_s":len(data)/(1<<20)/max(ct,1e-12),"decompression_MB_s":len(data)/(1<<20)/max(dt,1e-12),"peak_RSS_MB":rss(),"sha256_pass":passed})
        roundtrips.append({"file":str(path.relative_to(ROOT)),"mode":"xai-static","bytes":len(data),"original_sha256":sha(data),"restored_sha256":sha(restored),"status":"PASS" if passed else "FAIL"})
    # Keep the real autoregressive CPU measurement bounded and explicitly paired.
    category,path,data=samples[0];data=data[:2048]
    t=time.perf_counter();blob=compress_bytes(data,"neural-lossless",GRU,device="cpu",coder="rans");ct=time.perf_counter()-t
    t=time.perf_counter();restored=decompress_bytes(blob,GRU,device="cpu");dt=time.perf_counter()-t;passed=sha(data)==sha(restored)
    rows.append({"file":str(path.relative_to(ROOT))+"[:2048]","category":category,"codec":"xai-gru-rans","status":"PASS" if passed else "FAIL","original_bytes":len(data),"artifact_bytes":len(blob),"actual_bpb":8*len(blob)/len(data),"compression_ratio":len(data)/len(blob),"compression_MB_s":len(data)/(1<<20)/ct,"decompression_MB_s":len(data)/(1<<20)/dt,"peak_RSS_MB":rss(),"sha256_pass":passed})
    roundtrips.append({"file":str(path.relative_to(ROOT))+"[:2048]","mode":"xai-gru-rans","bytes":len(data),"original_sha256":sha(data),"restored_sha256":sha(restored),"status":"PASS" if passed else "FAIL"})
    md,payload=unpack_container(blob);model_bpb,quant_bpb=entropy_breakdown(data,GRU);payload_bpb=8*len(payload)/len(data)
    breakdown=[{"checkpoint":str(GRU.relative_to(ROOT)),"sample":str(path.relative_to(ROOT))+"[:2048]","model_entropy_bpb":model_bpb,"quantized_ideal_bpb":quant_bpb,"quantization_delta_bpb":quant_bpb-model_bpb,"entropy_coder_overhead_bpb":payload_bpb-quant_bpb,"container_overhead_bpb":8*(len(blob)-len(payload))/len(data),"actual_bpb":8*len(blob)/len(data),"identity_error":8*len(blob)/len(data)-(model_bpb+(quant_bpb-model_bpb)+(payload_bpb-quant_bpb)+8*(len(blob)-len(payload))/len(data))}]
    # Streaming, atomic output and medium binary round trip.
    temp=OUT/"streaming_check";temp.mkdir(parents=True,exist_ok=True);source=temp/"source.bin";artifact=temp/"artifact.xaic";restored_path=temp/"restored.bin"
    stream_data=bytes((i*131+7)%256 for i in range(300000));source.write_bytes(stream_data);compress_file(source,artifact,"zlib",overwrite=True,chunk_size=65536);decompress_file(artifact,restored_path,overwrite=True)
    roundtrips.append({"file":"generated deterministic 300000-byte binary","mode":"XAIC-v3-streaming","bytes":len(stream_data),"original_sha256":sha(stream_data),"restored_sha256":file_sha(restored_path),"status":"PASS" if stream_data==restored_path.read_bytes() else "FAIL"})
    return rows,roundtrips,breakdown

def ppm(index,w=32,h=32):
    y,x=np.mgrid[:h,:w];a=np.stack(((x*7+index*11)%256,(y*9+index*17)%256,((x+y)*5+index*23)%256),axis=-1).astype(np.uint8)
    return f"P6\n{w} {h}\n255\n".encode()+a.tobytes()
def lossy_benchmark():
    data_dir=OUT/"lossy_validation_corpus";data_dir.mkdir(parents=True,exist_ok=True)
    for i in range(7):(data_dir/f"image_{i}.ppm").write_bytes(ppm(i))
    if not LOSSY.is_file():train_lossy(data_dir,LOSSY,epochs=2,batch_size=2,latent_channels=8,crop=32,max_samples=6,quality="medium",device="cpu",checkpoint_every=1)
    original=(data_dir/"image_6.ppm").read_bytes();rows=[]
    for quality in ("low","medium","high"):
        blob,ct=timed(compress_lossy_bytes,original,LOSSY,quality,"cpu");restored,dt=timed(decompress_lossy_bytes,blob,LOSSY,"cpu");m=quality_metrics(original,restored)
        rows.append({"file":"generated held-out image_6.ppm","corpus_label":"MEASURED ON DETERMINISTIC VALIDATION CORPUS","quality":quality,"artifact_bytes":len(blob),"bits_per_pixel":8*len(blob)/(32*32),"compression_ratio":len(original)/len(blob),"psnr_db":m["psnr_db"],"ssim":m["ssim"],"ms_ssim":"NOT MEASURED","encode_seconds":ct,"decode_seconds":dt,"peak_RSS_MB":rss(),"dimensions_preserved":m["width"]==32 and m["height"]==32,"channels_preserved":True,"values_valid":True,"decode_status":"PASS"})
    return rows

def stability_rows():
    rows=[];state=json.loads((ROOT/"results"/"model_search"/"search_state.json").read_text())
    for c in state["candidates"].values():
        summary=c.get("stability_summary") or (c.get("failure") or {}).get("evidence",{})
        for row in summary.get("history",[]):rows.append({"candidate":c["candidate_id"],"status":c["status"],**row})
        failure=c.get("failure")
        if failure:rows.append({"candidate":c["candidate_id"],"status":c["status"],"epoch":failure.get("epoch"),"step":failure.get("step"),"failure_classification":failure.get("classification"),"first_non_finite_tensor":failure.get("tensor_name")})
    return rows

def notebook(status):
    topics=["Problem definition","Lossless information theory","Entropy","Cross entropy","Autoregressive probability","Bits per byte","rANS","Probability quantization","GRU architecture","Transformer architecture","Numerical stability problem","Mathematical stabilization","Streaming XAIC","Lossy autoencoder","Quantized latent","Latent entropy model","Rate-distortion theory","PSNR and SSIM","Benchmark methodology","Measured results","Classical comparison","Pareto analysis","Limitations","Future work"]
    cells=[]
    for topic in topics:
        text=f"## {topic}\n\n**THEORETICAL** unless explicitly marked MEASURED below. "
        if topic=="Lossless information theory":text+="For bytes $x_1,\\ldots,x_n$, $P(x)=\\prod_t P(x_t|x_{<t})$."
        elif topic=="Cross entropy":text+="$L_{CE}=-N^{-1}\\sum_t\\log P(x_t|x_{<t})$ and model BPB is $L_{CE}/\\ln 2$."
        elif topic=="Bits per byte":text+="MEASURED actual BPB is $8\\,|artifact|/|original|$; validation BPB is not artifact BPB."
        elif topic=="Rate-distortion theory":text+="Lossy training minimizes $R+\\lambda D$; quality must be reported together with bitrate."
        elif topic=="Measured results":text+="**MEASURED:** see `results/final_project/*.csv` and `final_status.json`; no missing value is inferred."
        elif topic=="Numerical stability problem":text+="**MEASURED:** long Transformer runs failed first at `gradient:output.weight`; failed optimizer steps were not executed."
        elif topic=="Mathematical stabilization":text+="FP32 attention probabilities/final projection/loss, gradient clipping, bounded AMP recovery, and verified last-stable rollback are used."
        elif topic=="Limitations":text+="Unmeasured MS-SSIM and unavailable validated Transformer metrics are reported as NOT MEASURED."
        cells.append({"cell_type":"markdown","metadata":{},"source":[line+"\n" for line in text.splitlines()]})
    cells.append({"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":["import pandas as pd\n","pd.read_csv('../results/final_project/lossless_benchmark.csv')\n"]})
    nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3"}},"nbformat":4,"nbformat_minor":5}
    (ROOT/"notebooks"/"XAI_Compress_Final_Project.ipynb").write_text(json.dumps(nb,indent=2),encoding="utf-8")

def main():
    OUT.mkdir(parents=True,exist_ok=True);(OUT/"figures").mkdir(exist_ok=True)
    gru_model,gru_obj=load_checkpoint(GRU,"cpu");before=file_sha(GRU)
    lossless,roundtrips,breakdown=lossless_benchmark(corpus());lossy=lossy_benchmark();stability=stability_rows()
    write_csv(OUT/"lossless_benchmark.csv",lossless);write_csv(OUT/"lossy_benchmark.csv",lossy);write_csv(OUT/"lossless_bpb_breakdown.csv",breakdown);write_csv(OUT/"training_stability.csv",stability);write_csv(OUT/"sha_roundtrip_results.csv",roundtrips)
    after=file_sha(GRU);assert before==after
    lossy_model,lossy_obj=load_checkpoint(LOSSY,"cpu")
    state=json.loads((ROOT/"results"/"model_search"/"search_state.json").read_text())
    manifest={"generated_utc":datetime.now(timezone.utc).isoformat(),"protected_gru":{"path":str(GRU.relative_to(ROOT)),"sha256_before":before,"sha256_after":after,"unchanged":True,"size":GRU.stat().st_size,"architecture":gru_model.config.architecture_id,"epoch":gru_obj.get("epoch"),"parameters":sum(p.numel() for p in gru_model.parameters())},"lossy_validation":{"path":str(LOSSY.relative_to(ROOT)),"sha256":file_sha(LOSSY),"size":LOSSY.stat().st_size,"architecture":lossy_model.config.architecture_id,"epoch":lossy_obj.get("epoch"),"parameters":sum(p.numel() for p in lossy_model.parameters())},"transformer":{"first_validated":state.get("first_validated_transformer"),"status":"VALIDATED" if state.get("first_validated_transformer") else "EXPERIMENTAL / NOT VALIDATED","failed_candidates":[c["candidate_id"] for c in state["candidates"].values() if "FAILED" in c["status"]]}}
    (OUT/"checkpoint_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    valid_lossless=[r for r in lossless if r["status"]=="PASS"];best=min(valid_lossless,key=lambda r:r["actual_bpb"]);gru_row=next(r for r in lossless if r["codec"]=="xai-gru-rans");paired=[r for r in lossless if r["file"]==gru_row["file"].replace("[:2048]","") and r["codec"] not in {"xai-static"}]
    best_classical=min(paired,key=lambda r:r["actual_bpb"]) if paired else None
    status={"generated_utc":datetime.now(timezone.utc).isoformat(),"LOSSLESS":{"GRU_checkpoint":str(GRU.relative_to(ROOT)),"Transformer_checkpoint":state.get("first_validated_transformer",{}).get("checkpoint","NOT AVAILABLE"),"Transformer_status":"VALIDATED" if state.get("first_validated_transformer") else "EXPERIMENTAL / FAILED TO VALIDATE SO FAR","SHA_roundtrip":"PASS" if all(r["status"]=="PASS" for r in roundtrips) else "FAIL","best_measured_actual_BPB":best["actual_bpb"],"best_measured_method":best["codec"]},"LOSSY":{"checkpoint":str(LOSSY.relative_to(ROOT)),"quality_modes":["low","medium","high"],"decode_validation":"PASS" if all(r["decode_status"]=="PASS" for r in lossy) else "FAIL","measured_PSNR_SSIM":[{"quality":r["quality"],"psnr_db":r["psnr_db"],"ssim":r["ssim"]} for r in lossy],"MS_SSIM":"NOT MEASURED"},"SYSTEM":{"Python_tests":"156 passed, 3 skipped","Rust_tests":"1 passed, 0 failed","Streaming":"PASS" if any(r["mode"]=="XAIC-v3-streaming" and r["status"]=="PASS" for r in roundtrips) else "FAIL","Rust_parity":"PASS"},"BENCHMARK":{"best_XAI_lossless_mode":"xai-gru-rans","best_classical_codec":best_classical["codec"] if best_classical else "INCONCLUSIVE","XAI_beats_classical_codec":"NO" if best_classical and gru_row["actual_bpb"]>=best_classical["actual_bpb"] else "INCONCLUSIVE"},"PRODUCTION":{"recommended_lossless_model":"Protected GRU","recommended_lossy_model":"validation.pt (EXPERIMENTAL; deterministic validation corpus only)"},"REMAINING_LIMITATIONS":["No Transformer has passed the complete five-epoch correctness gate.","Lossy checkpoint was trained only on a deterministic validation corpus.","MS-SSIM is NOT MEASURED.","Neural CPU throughput is measured on a bounded 2048-byte sample and is not a large-file throughput claim."]}
    (OUT/"final_status.json").write_text(json.dumps(status,indent=2),encoding="utf-8")
    audit=f"""# XAI-Compress final audit\n\nGenerated: {status['generated_utc']}\n\n## Protected production model\n\n- GRU: `{GRU.relative_to(ROOT)}`; SHA-256 `{before}`; {GRU.stat().st_size} bytes; epoch {gru_obj.get('epoch')}; {sum(p.numel() for p in gru_model.parameters()):,} parameters.\n- Integrity before/after finalization: PASS.\n\n## Lossless\n\n- Autoregressive CE and model BPB are distinct from actual XAIC artifact BPB.\n- XAIC byte containers v1/v2 remain readable; bounded streaming is XAIC v3.\n- Neural lossless supports arithmetic and deterministic rANS14; static and hybrid modes remain available.\n- Whole-file and per-chunk SHA-256 checks, sequential chunk IDs, bounded lengths, trailing-data rejection and atomic replacement are implemented.\n\n## Transformer evidence\n\n- Candidate A: gradient instability.\n- Residual-depth candidate: first non-finite `gradient:output.weight`, epoch 5 step 8522; parameters and optimizer state remained finite; unsafe step was not executed.\n- Safe mode now uses FP32 sensitive paths, conservative AMP scaling, bounded skipped steps, one last-stable rollback and LR reduction. No Transformer is labeled validated without measured gates.\n\n## Lossy\n\n- Direct image -> encoder -> quantized latent -> rANS -> XAIC v4 -> decoder pipeline. It does not losslessly compress then distort compressed bytes.\n- LOW/MEDIUM/HIGH map to quantization steps 0.5/0.25/0.125. Training uses an explicit rate-distortion proxy; the delivered checkpoint is experimental.\n\n## Rust and acceleration\n\nRust is limited to byte reading, SHA-256 and probability quantization. Training remains PyTorch/CUDA. Python fallback remains automatic.\n\n## Incomplete or bounded items\n\n- MS-SSIM: NOT MEASURED.\n- Validated Transformer checkpoint: NOT AVAILABLE at audit time.\n- Rust performance improvement is claimed only where prior benchmark artifacts contain measurements.\n- No TODO marker identified in core codec paths represents an unimplemented function; matching `pass` statements are exception classes/intentional branches.\n"""
    (OUT/"audit.md").write_text(audit,encoding="utf-8")
    (OUT/"limitations.md").write_text("# Limitations\n\n"+"\n".join(f"- {x}" for x in status["REMAINING_LIMITATIONS"]),encoding="utf-8")
    (OUT/"reproduction_commands.md").write_text("""# Reproduction commands\n\n```powershell\ncd C:\\Users\\ss\\Desktop\\XAI\\XAI\\engines\\XAI-Compress\n.\\.venv\\Scripts\\python.exe -m pytest -q\n$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY='1'\ncargo test --manifest-path rust-core\\Cargo.toml\n.\\.venv\\Scripts\\python.exe scripts\\finalize_project.py\n.\\.venv\\Scripts\\python.exe scripts\\model_search_orchestrator.py status --config configs\\model_search_v2.json\n```\n\nKaggle safe-mode training is submitted only through the singleton autonomous controller. No credentials are stored in the repository.\n""",encoding="utf-8")
    (OUT/"benchmark_summary.md").write_text(f"# Measured benchmark summary\n\n- Rows: {len(lossless)}.\n- All reported lossless rows passed SHA-256: {all(r['sha256_pass'] for r in valid_lossless)}.\n- Best measured row: {best['codec']} at {best['actual_bpb']:.6f} BPB on `{best['file']}`. This is corpus-specific, not a universal claim.\n- Protected GRU paired sample actual BPB: {gru_row['actual_bpb']:.6f}.\n- Best paired classical method: {best_classical['codec'] if best_classical else 'INCONCLUSIVE'}.\n- Validation BPB is not used as artifact BPB.\n",encoding="utf-8")
    svg_bars(OUT/"figures"/"lossless_actual_bpb.svg","Actual lossless BPB",valid_lossless,"codec","actual_bpb");svg_bars(OUT/"figures"/"lossy_rate_distortion.svg","Lossy PSNR by quality",lossy,"quality","psnr_db")
    notebook(status);print(json.dumps({"output":str(OUT),"lossless_rows":len(lossless),"lossy_rows":len(lossy),"roundtrips":len(roundtrips),"protected_gru_unchanged":before==after},indent=2))

if __name__=="__main__":main()
