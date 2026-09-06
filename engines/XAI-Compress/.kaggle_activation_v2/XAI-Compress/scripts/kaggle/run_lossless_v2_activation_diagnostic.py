"""Kaggle entry point for the Version 5 activation-growth reproduction."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

INPUT = Path("/kaggle/input")
WORK = Path("/kaggle/working")
PROJECT = WORK / "XAI-Compress"
RESULTS = WORK / "activation_diagnostic"
RESULTS.mkdir(exist_ok=True)

source = next(
    (path.parent for path in INPUT.rglob("pyproject.toml")
     if (path.parent / "xai_compress.zip").is_file() or (path.parent / "xai_compress").is_dir()),
    None,
)
if source is None:
    raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH")
PROJECT.mkdir(exist_ok=True)
for item in source.iterdir():
    if item.is_file() and item.suffix == ".zip":
        with zipfile.ZipFile(item) as archive:
            names = [Path(name) for name in archive.namelist() if name and not name.endswith("/")]
            target = PROJECT if names and all(name.parts[0] == item.stem for name in names) else PROJECT / item.stem
            target.mkdir(exist_ok=True)
            archive.extractall(target)
    elif item.is_file():
        shutil.copy2(item, PROJECT / item.name)
    elif item.is_dir():
        shutil.copytree(item, PROJECT / item.name, dirs_exist_ok=True)

expected = {
    "xai_compress/models/transformer_v2.py": "3454c776af72121ca139470d90a296cb8ea0a9a7965586742e0bb29028498b43",
    "xai_compress/train.py": "fc7993ea20b28ae4a8dd62017878f7638f546ef4c2427f22f0dd6cef4c901989",
    "scripts/debug_lossless_v2_activations.py": "8c4b88d3af621b5f4407686d88909dfd6c9fe62850975f8157bc20395eb32e28",
}
actual = {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() for name in expected}
print("SOURCE HASHES", json.dumps(actual), flush=True)
if actual != expected:
    raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-e", str(PROJECT), "--no-deps", "--no-build-isolation"],
    check=True,
)

import torch

print(json.dumps({
    "gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
    "cuda": torch.version.cuda, "device_count": torch.cuda.device_count(),
}), flush=True)
data = INPUT / "ff-c23"
if not data.is_dir():
    data = next(path for path in INPUT.iterdir() if path != source and path.is_dir())
command = [
    sys.executable, "-u", str(PROJECT / "scripts/debug_lossless_v2_activations.py"), str(data),
    "--samples", "450000", "--learning-rate", "0.001", "--init-scale", "1024",
    "--growth-interval", "10000", "--output", str(RESULTS / "original.json"),
]
print("RUN ORIGINAL VERSION 5 REPRODUCTION", command, flush=True)
raise SystemExit(subprocess.run(command, check=False).returncode)
