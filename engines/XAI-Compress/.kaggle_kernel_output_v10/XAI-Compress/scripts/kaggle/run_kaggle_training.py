"""Kaggle script-kernel entry point. Runs with notebook Internet disabled."""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
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

training_candidates = [p for p in INPUT.iterdir() if p.is_dir() and not any(p == q or p in q.parents for q in INPUT.rglob("pyproject.toml"))]
preferred = INPUT / "ff-c23"
dataset = preferred if preferred.is_dir() else next((p for p in training_candidates if any(x.is_file() for x in p.rglob("*"))), None)
if dataset is None:
    raise RuntimeError("No attached training dataset was found")
print("Training dataset:", dataset)

from kaggle_train import run
from kaggle_benchmark import run as benchmark, export, publish_model_dataset

from xai_compress.checkpoint import load_checkpoint
resume = None
for candidate in sorted(INPUT.rglob("*.pt"), key=lambda p: ("latest" not in p.name.lower(), str(p))):
    try:
        load_checkpoint(candidate, "cpu")
        resume = candidate
        print("Valid attached recovery checkpoint:", candidate)
        break
    except Exception:
        pass
# Same architecture/CUDA/AMP/checkpoint path, bounded to one short epoch.
research_architecture = {"context_length":256, "embedding_dim":192, "hidden_dim":384,
                         "num_layers":2, "dropout":0.1, "epochs":1,
                         "max_samples":1024, "checkpoint_every":1}
print("STARTING RESEARCH-PATH SMOKE TEST")
smoke_checkpoint, smoke_results = run(dataset, preset="RESEARCH", overrides=research_architecture, label="smoke")
load_checkpoint(smoke_checkpoint, "cpu")
print("SMOKE TEST PASSED")
print("RESUME FROM:", resume) if resume else print("NO VALID CHECKPOINT — STARTING NEW TRAINING")
checkpoint, results = run(dataset, preset="RESEARCH", resume=resume, label="best")
# Stable application-facing filename in addition to the experiment's best.pt.
model_path = WORK / "model.pth"
shutil.copy2(checkpoint, model_path)
benchmark(dataset, checkpoint, results, limit=3)
archive = export(WORK)
publish_model_dataset(WORK)
print("Training, lossless validation and bounded benchmark completed")
print("Application model:", model_path)
print("Export:", archive)
