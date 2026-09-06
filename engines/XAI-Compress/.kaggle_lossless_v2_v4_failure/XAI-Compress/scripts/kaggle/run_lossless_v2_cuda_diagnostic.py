"""Short Kaggle CUDA/AMP numerical diagnostic; never starts production training."""
from __future__ import annotations
import hashlib,json,shutil,subprocess,sys
from pathlib import Path

INPUT=Path("/kaggle/input");WORK=Path("/kaggle/working");PROJECT=WORK/"XAI-Compress"
source=next((p.parent for p in INPUT.rglob("pyproject.toml") if (p.parent/"xai_compress").is_dir()),None)
if source is None:raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH: source root unavailable")
if PROJECT.exists():shutil.rmtree(PROJECT)
shutil.copytree(source,PROJECT)
files=[PROJECT/"xai_compress/models/transformer_v2.py",PROJECT/"xai_compress/train.py",PROJECT/"scripts/debug_lossless_v2_numerics.py"]
markers=["FIRST NON-FINITE STAGE","require_finite(loss","--numerical-debug"]
snapshot={str(p.relative_to(PROJECT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
print("SOURCE SNAPSHOT",json.dumps(snapshot,indent=2),flush=True)
if len(snapshot)!=3 or any(marker not in files[i].read_text(encoding="utf-8") for i,marker in enumerate(markers)):
    raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH")
print("SOURCE SNAPSHOT MATCH",flush=True)
subprocess.run([sys.executable,"-m","pip","install","-e",str(PROJECT),"--no-deps","--no-build-isolation"],check=True)
import torch
if not torch.cuda.is_available():raise RuntimeError("CUDA unavailable")
print(json.dumps({"gpu":torch.cuda.get_device_name(0),"gpu_count":torch.cuda.device_count(),"torch":torch.__version__,"cuda":torch.version.cuda},indent=2),flush=True)
dataset=INPUT/"ff-c23"
if not dataset.is_dir():
    roots=[p for p in INPUT.iterdir() if p.is_dir() and p!=source];dataset=roots[0] if roots else None
if dataset is None:raise RuntimeError("dataset unavailable")
script=PROJECT/"scripts/debug_lossless_v2_numerics.py"
base=[sys.executable,"-u",str(script),str(dataset),"--batch-size","16","--learning-rate","0.001","--gradient-clip","1","--numerical-debug"]
for samples in (1024,4096,16384,65536):
    print(f"AMP DIAGNOSTIC samples={samples}",flush=True)
    amp=subprocess.run(base+["--samples",str(samples),"--max-steps",str((samples+15)//16),"--amp"],check=False)
    if amp.returncode:
        print(f"AMP FAILED samples={samples}; STARTING IDENTICAL FP32 CONTROL",flush=True)
        fp32=subprocess.run(base+["--samples",str(samples),"--max-steps",str((samples+15)//16),"--no-amp"],check=False)
        print(json.dumps({"failing_samples":samples,"amp":"FAIL","fp32":"PASS" if fp32.returncode==0 else "FAIL"}),flush=True)
        raise SystemExit(amp.returncode)
    print(f"AMP PASS samples={samples}",flush=True)
print("STABILITY GATE PASS: 65536 AMP samples",flush=True)
