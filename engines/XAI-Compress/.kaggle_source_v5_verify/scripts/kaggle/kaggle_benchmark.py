from __future__ import annotations
import argparse, csv, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from xai_compress.benchmarks.suite import run_suite
from xai_compress.compression import compress_file, decompress_file

def run(dataset: Path, checkpoint: Path, results: Path, limit=3, max_sample_bytes=256 * 1024):
    files = [p for p in dataset.rglob("*") if p.is_file() and p.stat().st_size and p.suffix.lower() not in {".pt", ".pth", ".xaic"}][:limit]
    if not files: raise ValueError("No safe benchmark samples")
    results.mkdir(parents=True, exist_ok=True)
    roundtrips=[]
    for i, src in enumerate(files):
        artifact, restored = results/f"roundtrip_{i}.xaic", results/f"roundtrip_{i}.restored"
        compress_file(src, artifact, "hybrid", checkpoint, overwrite=True)
        decompress_file(artifact, restored, checkpoint, overwrite=True)
        digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        ok=digest(src)==digest(restored); roundtrips.append({"source":str(src),"sha256":digest(src),"pass":ok})
        artifact.unlink(missing_ok=True); restored.unlink(missing_ok=True)
        if not ok: raise RuntimeError("LOSSLESS ROUND-TRIP FAILED")
    rows=run_suite(dataset, str(checkpoint), str(results/"benchmark.csv")) if limit is None else []
    # Bound Kaggle validation cost by benchmarking selected samples in a temporary sample directory.
    sample=results/"benchmark_samples"; sample.mkdir(exist_ok=True)
    for i,p in enumerate(files):
        with p.open("rb") as source, (sample/f"{i}_{p.name}").open("wb") as target:
            target.write(source.read(max_sample_bytes))
    rows=run_suite(sample, str(checkpoint), str(results/"benchmark.csv")); shutil.rmtree(sample)
    (results/"roundtrip.json").write_text(json.dumps(roundtrips,indent=2),encoding="utf-8")
    return rows

def export(work=Path("/kaggle/working")):
    target=work/"export"; target.mkdir(exist_ok=True)
    for folder in (work/"checkpoints", work/"results"):
        if folder.exists(): shutil.copytree(folder,target/folder.name,dirs_exist_ok=True)
    if (work/"model.pth").is_file(): shutil.copy2(work/"model.pth", target/"model.pth")
    mappings = {
        work/"checkpoints"/"best.pt": target/"best.pt",
        work/"checkpoints"/"best.latest.pt": target/"latest.pt",
        work/"checkpoints"/"best.metrics.csv": target/"metrics.csv",
        work/"checkpoints"/"best.history.json": target/"history.json",
        work/"checkpoints"/"best.summary.json": target/"summary.json",
        work/"results"/"benchmark.csv": target/"benchmark.csv",
    }
    for source, destination in mappings.items():
        if source.is_file(): shutil.copy2(source, destination)
    (target/"figures").mkdir(exist_ok=True)
    try:
        import matplotlib.pyplot as plt
        metrics_path = target/"metrics.csv"
        if metrics_path.is_file():
            with metrics_path.open(newline="", encoding="utf-8") as handle: history=list(csv.DictReader(handle))
            epochs=[int(r["epoch"]) for r in history]
            fig,ax=plt.subplots();ax.plot(epochs,[float(r["train_cross_entropy"]) for r in history],label="train");ax.plot(epochs,[float(r["val_cross_entropy"]) for r in history],label="validation");ax.set(xlabel="Epoch",ylabel="Cross entropy",title="Training history");ax.legend();fig.tight_layout();fig.savefig(target/"figures"/"loss.png",dpi=160);plt.close(fig)
            fig,ax=plt.subplots();ax.plot(epochs,[float(r["val_bpb_estimate"]) for r in history]);ax.set(xlabel="Epoch",ylabel="Bits per byte",title="Validation BPB");fig.tight_layout();fig.savefig(target/"figures"/"bpb.png",dpi=160);plt.close(fig)
        benchmark_path=target/"benchmark.csv"
        if benchmark_path.is_file():
            with benchmark_path.open(newline="",encoding="utf-8") as handle: rows=list(csv.DictReader(handle))
            codecs=sorted(set(r["codec"] for r in rows)); ratios=[sum(float(r["ratio"]) for r in rows if r["codec"]==c)/sum(1 for r in rows if r["codec"]==c) for c in codecs]
            fig,ax=plt.subplots(figsize=(9,4));ax.bar(codecs,ratios);ax.tick_params(axis="x",rotation=45);ax.set(ylabel="Compression ratio",title="Measured codec comparison");fig.tight_layout();fig.savefig(target/"figures"/"compression_ratio.png",dpi=160);plt.close(fig)
    except (ImportError, OSError, ValueError, KeyError) as exc:
        print("Figure generation unavailable:", exc)
    return shutil.make_archive(str(work/"xai_compress_experiment"),"zip",target)

def publish_model_dataset(work=Path("/kaggle/working"), dataset_id=None):
    dataset_id = dataset_id or os.getenv("KAGGLE_MODEL_DATASET", "mohameddtaieb/xai-compress-trained-model")
    credential = bool(os.getenv("KAGGLE_API_TOKEN")) or (Path.home()/".kaggle"/"access_token").is_file()
    kaggle = shutil.which("kaggle")
    if not credential or not kaggle:
        print("Kaggle credentials unavailable; artifacts remain in /kaggle/working.")
        print(f"Manual download: kaggle kernels output mohameddtaieb/xai-compress-gpu-training -p ./kaggle-output")
        print(f"Optional publish: kaggle datasets create -p /kaggle/working/export")
        return None
    export_dir = work/"export"
    metadata = {"title":"XAI-Compress Trained Model","id":dataset_id,"licenses":[{"name":"other"}],"isPrivate":True}
    (export_dir/"dataset-metadata.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    exists = subprocess.run([kaggle,"datasets","files",dataset_id,"--page-size","1"],capture_output=True).returncode == 0
    command = [kaggle,"datasets","version","-p",str(export_dir),"-m","Automated XAI-Compress research checkpoint","-r","zip"] if exists else [kaggle,"datasets","create","-p",str(export_dir),"-r","zip"]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        print("Automatic model publication failed; local Kaggle outputs are preserved.")
        return None
    print("Published model dataset:", dataset_id)
    return dataset_id

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("dataset",type=Path);p.add_argument("checkpoint",type=Path);p.add_argument("--results",type=Path,default=Path("/kaggle/working/results"));a=p.parse_args();run(a.dataset,a.checkpoint,a.results);print(export());publish_model_dataset()
