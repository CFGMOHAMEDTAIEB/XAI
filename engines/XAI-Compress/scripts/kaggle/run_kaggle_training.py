"""Kaggle script-kernel entry point. Runs with notebook Internet disabled."""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
import hashlib
import json
import os
import platform
from pathlib import Path

INPUT = Path("/kaggle/input")
WORK = Path("/kaggle/working")
PROJECT = WORK / "XAI-Compress"


def materialize_source() -> Path:
    sources = [p.parent for p in INPUT.rglob("pyproject.toml") if (p.parent / "xai_compress.zip").is_file() or (p.parent / "xai_compress").is_dir()]
    if not sources:
        raise RuntimeError("xai-compress-source input was not attached")
    source = sources[0]
    if PROJECT.exists():
        shutil.rmtree(PROJECT)
    PROJECT.mkdir(parents=True)
    for item in source.iterdir():
        if item.is_file() and item.suffix == ".zip":
            destination = PROJECT / item.stem
            with zipfile.ZipFile(item) as archive:
                names = [Path(name) for name in archive.namelist() if name and not name.endswith("/")]
                # Kaggle's `-r zip` may either preserve the source directory
                # in member names or store only its contents.
                preserves_root = bool(names) and all(name.parts and name.parts[0] == item.stem for name in names)
                target = PROJECT if preserves_root else destination
                target.mkdir(parents=True, exist_ok=True)
                archive.extractall(target)
        elif item.is_file():
            shutil.copy2(item, PROJECT / item.name)
        elif item.is_dir():
            shutil.copytree(item, PROJECT / item.name)
    if not (PROJECT / "xai_compress" / "__init__.py").is_file():
        raise RuntimeError("Packaged xai_compress source could not be reconstructed")
    return PROJECT


project = materialize_source()
expected_hashes = {
    "xai_compress/models/transformer_v2.py": "3c0e5a825f08f13c014a302ec9dd45dca60d38f69f8b553c1e4a46b02c8a0be3",
    "xai_compress/train.py": "43ba8e6f688aeaa8b8ea20dd21ae7f38aa0fee7fcce5a8448c5b15f5da586152",
}
actual_hashes = {name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in expected_hashes}
print("PRODUCTION SOURCE HASHES", json.dumps(actual_hashes), flush=True)
if actual_hashes != expected_hashes:
    raise RuntimeError("PRODUCTION_SOURCE_HASH_MISMATCH")
subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(project), "--no-deps", "--no-build-isolation"], check=True)
sys.path.insert(0, str(project))
sys.path.insert(0, str(project / "scripts" / "kaggle"))

# Optional, bounded native build. Offline failure is non-fatal and the Python
# implementation remains authoritative. Kaggle images do not always include
# Cargo or cached crates.
if shutil.which("cargo"):
    native = subprocess.run(["cargo", "build", "--release", "--offline"], cwd=project/"rust-core", check=False)
    library = project/"rust-core"/"target"/"release"/"libxai_compress_core.so"
    if native.returncode == 0 and library.is_file():
        shutil.copy2(library, project/"xai_compress_core.so")
        print("Rust probability quantization enabled")
    else:
        print("RUST EXTENSION UNAVAILABLE — USING PYTHON FALLBACK")
else:
    print("RUST EXTENSION UNAVAILABLE — USING PYTHON FALLBACK")

import torch
if not torch.cuda.is_available():
    raise RuntimeError("CUDA GPU NOT AVAILABLE")
props = torch.cuda.get_device_properties(0)
free_vram, total_vram = torch.cuda.mem_get_info(0)
probe = torch.ones(16, device="cuda"); assert float((probe * 2).sum()) == 32.0
del probe; torch.cuda.empty_cache()
print(json.dumps({"python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda,
                  "cuda_available": True, "gpu": props.name, "gpu_count": torch.cuda.device_count(),
                  "total_vram": total_vram, "free_vram": free_vram,
                  "working_free_disk": shutil.disk_usage(WORK).free,
                  "input_usage": sum(p.stat().st_size for p in INPUT.rglob("*") if p.is_file()),
                  "system_ram": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
                  "available_ram": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")}, indent=2))

preferred = INPUT / "ff-c23"
source_roots = {p.parent for p in INPUT.rglob("pyproject.toml")}
training_files = [p for p in INPUT.rglob("*") if p.is_file() and not any(root == p.parent or root in p.parents for root in source_roots)]
top_level = sorted({INPUT / p.relative_to(INPUT).parts[0] for p in training_files})
print("Input roots:", [(str(p), sum(1 for x in p.rglob("*") if x.is_file())) for p in INPUT.iterdir()])
dataset = preferred if preferred.is_dir() and any(preferred.rglob("*")) else (top_level[0] if top_level else None)
if dataset is None:
    raise RuntimeError(f"No attached training dataset was found; source roots={sorted(map(str, source_roots))}")
print("Training dataset:", dataset)

from kaggle_train import run
from kaggle_benchmark import run as benchmark, export, publish_model_dataset

from xai_compress.checkpoint import load_checkpoint
family = os.getenv("XAI_TRAINING_FAMILY", "baseline")

if family == "lossy_v1":
    from xai_compress.train_lossy import train_lossy
    frame_root = WORK / "lossy_frames"; frame_root.mkdir(exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("LOSSY DATA PREPARATION FAILED: ffmpeg is unavailable; MP4 bytes will not be mislabeled as images")
    videos = sorted(dataset.rglob("*.mp4"))[:100]
    for index, video in enumerate(videos):
        subprocess.run([ffmpeg,"-loglevel","error","-i",str(video),"-frames:v","1","-vf","scale=128:128",str(frame_root/f"frame-{index:04d}.ppm")],check=False)
    frames = list(frame_root.glob("*.ppm"))
    if len(frames) < 2: raise RuntimeError("LOSSY DATA PREPARATION FAILED: fewer than two video frames decoded")
    smoke = WORK/"checkpoints"/"neural_lossy_v1"/"smoke.pt"
    train_lossy(frame_root,smoke,epochs=1,batch_size=2,latent_channels=16,crop=64,max_samples=8,device="cuda")
    load_checkpoint(smoke,"cpu");print("SMOKE TEST PASSED: neural_lossy_v1")
    checkpoint = train_lossy(frame_root,WORK/"checkpoints"/"neural_lossy_v1"/"best.pt",epochs=30,batch_size=16,
                             latent_channels=32,crop=64,max_samples=len(frames),device="cuda",resume=None)
    print("LOSSY V1 TRAINING COMPLETED:",checkpoint)
    raise SystemExit(0)
resume = None
for candidate in sorted(INPUT.rglob("*.pt"), key=lambda p: ("latest" not in p.name.lower(), str(p))):
    try:
        candidate_model, _ = load_checkpoint(candidate, "cpu")
        expected_arch = "causal-byte-transformer-v2" if family == "lossless_v2" else "causal-byte-gru-v1"
        if candidate_model.config.architecture_id != expected_arch:
            print("Ignoring recovery checkpoint with architecture", candidate_model.config.architecture_id, candidate)
            continue
        resume = candidate
        print("Valid attached recovery checkpoint:", candidate)
        break
    except Exception:
        pass
# Same architecture/CUDA/AMP/checkpoint path, bounded to one short epoch.
research_architecture = {"context_length":256, "embedding_dim":192, "hidden_dim":384,
                         "num_layers":2, "dropout":0.1, "epochs":1,
                         "max_samples":1024, "checkpoint_every":1}
if family == "lossless_v2":
    research_architecture.update({"architecture":"causal-byte-transformer-v2","embedding_dim":192,
                                  "hidden_dim":192,"num_layers":4,"n_heads":6,"ff_dim":768,
                                  "lr":0.0005})
print("STARTING RESEARCH-PATH SMOKE TEST")
smoke_label = "lossless_v2_smoke" if family == "lossless_v2" else "smoke"
smoke_checkpoint, smoke_results = run(dataset, preset="RESEARCH", overrides=research_architecture, label=smoke_label)
smoke_model, _ = load_checkpoint(smoke_checkpoint, "cpu")
if family == "lossless_v2":
    if smoke_model.config.architecture_id != "causal-byte-transformer-v2":
        raise RuntimeError(f"SMOKE ARCHITECTURE MISMATCH: {smoke_model.config.architecture_id}")
    from xai_compress.compression import compress_bytes, decompress_bytes
    first, _ = smoke_model.step(256, None); second, _ = smoke_model.step(256, None)
    if not torch.equal(first, second): raise RuntimeError("SMOKE DETERMINISTIC INFERENCE FAILURE")
    probe_bytes = b"lossless-v2-kaggle-smoke" * 4
    probe_artifact = compress_bytes(probe_bytes, "neural-lossless", smoke_checkpoint, device="cpu")
    probe_restored = decompress_bytes(probe_artifact, smoke_checkpoint, device="cpu")
    if hashlib.sha256(probe_bytes).digest() != hashlib.sha256(probe_restored).digest():
        raise RuntimeError("SMOKE LOSSLESS SHA256 FAILURE")
    print("DETERMINISTIC INFERENCE PASSED")
    print("LOSSLESS SHA256 SMOKE PASSED")
print("SMOKE TEST PASSED")
print("RESUME FROM:", resume) if resume else print("NO VALID CHECKPOINT — STARTING NEW TRAINING")
if family == "lossless_v2":
    research_architecture.update({"epochs":60,"max_samples":500000,"checkpoint_every":5,
                                  "numerical_debug":True,"amp_initial_scale":1024,
                                  "amp_growth_interval":10000})
checkpoint, results = run(dataset, preset="RESEARCH", resume=resume,
                          overrides=research_architecture if family == "lossless_v2" else None,
                          label="lossless_v2" if family == "lossless_v2" else "best")
# The exporter uses a stable best.pt name inside this disposable Kaggle run;
# the local immutable baseline is never part of or modified by this operation.
if family == "lossless_v2":
    shutil.copy2(checkpoint, WORK/"checkpoints"/"best.pt")
    companion_mappings = {
        checkpoint.with_name(checkpoint.stem + ".latest" + checkpoint.suffix): WORK/"checkpoints"/"best.latest.pt",
        checkpoint.with_suffix(".metrics.csv"): WORK/"checkpoints"/"best.metrics.csv",
        checkpoint.with_suffix(".history.json"): WORK/"checkpoints"/"best.history.json",
        checkpoint.with_suffix(".summary.json"): WORK/"checkpoints"/"best.summary.json",
    }
    for source, destination in companion_mappings.items():
        if not source.is_file():
            raise RuntimeError(f"Missing required training artifact: {source}")
        shutil.copy2(source, destination)
# Stable application-facing filename in addition to the experiment's best.pt.
model_path = WORK / "model.pth"
shutil.copy2(checkpoint, model_path)
benchmark(dataset, checkpoint, results, limit=3)
archive = export(WORK)
publish_model_dataset(WORK)
print("Training, lossless validation and bounded benchmark completed")
print("Application model:", model_path)
print("Export:", archive)
