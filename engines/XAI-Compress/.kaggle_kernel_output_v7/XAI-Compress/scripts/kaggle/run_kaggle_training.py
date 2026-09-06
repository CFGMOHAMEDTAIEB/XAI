"""Kaggle script-kernel entry point. Runs with notebook Internet disabled."""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
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
subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(project), "--no-deps"], check=True)
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
        print("Rust extension unavailable offline; using verified Python fallback")
else:
    print("Cargo unavailable; using verified Python fallback")

import torch
if not torch.cuda.is_available():
    raise RuntimeError("CUDA GPU NOT AVAILABLE")
print("GPU:", torch.cuda.get_device_name(0), "CUDA:", torch.version.cuda)

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
checkpoint, results = run(dataset, preset="RESEARCH", resume=resume)
# Stable application-facing filename in addition to the experiment's best.pt.
model_path = WORK / "model.pth"
shutil.copy2(checkpoint, model_path)
benchmark(dataset, checkpoint, results, limit=3)
archive = export(WORK)
publish_model_dataset(WORK)
print("Training, lossless validation and bounded benchmark completed")
print("Application model:", model_path)
print("Export:", archive)
