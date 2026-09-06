"""Kaggle T4 entry point for exactly one LR=0.0002 five-epoch gate.

This intentionally cannot launch LR=0.0003.  Candidate A already consumed its
single authorized run and is retained as measured CUDA post-validation failure
evidence in the local model-search state.
"""
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
RESULTS = WORK / "results" / "model_search" / "lr_0_0002"
RESULTS.mkdir(parents=True, exist_ok=True)
LEARNING_RATE = 0.0002


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    resolved = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != resolved and resolved not in target.parents:
            raise RuntimeError(f"unsafe source archive member: {member.filename}")
    archive.extractall(destination)


def materialize_source() -> Path:
    candidates = [
        path.parent for path in INPUT.rglob("source-sha256.json")
        if (path.parent / "pyproject.toml").is_file()
    ]
    if not candidates:
        raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH: manifest unavailable")
    source = candidates[0]
    if PROJECT.exists():
        shutil.rmtree(PROJECT)
    PROJECT.mkdir(parents=True)
    for item in source.iterdir():
        if item.is_file() and item.suffix == ".zip":
            with zipfile.ZipFile(item) as archive:
                names = [Path(name) for name in archive.namelist() if name and not name.endswith("/")]
                preserves_root = bool(names) and all(name.parts and name.parts[0] == item.stem for name in names)
                destination = PROJECT if preserves_root else PROJECT / item.stem
                destination.mkdir(parents=True, exist_ok=True)
                safe_extract(archive, destination)
        elif item.is_file():
            shutil.copy2(item, PROJECT / item.name)
        elif item.is_dir():
            shutil.copytree(item, PROJECT / item.name, dirs_exist_ok=True)
    return PROJECT


project = materialize_source()
manifest = json.loads((project / "source-sha256.json").read_text(encoding="utf-8"))
required_hashes = {
    "xai_compress/models/transformer_v2.py",
    "xai_compress/train.py",
    "xai_compress/checkpoint.py",
    "xai_compress/compression.py",
    "scripts/run_v2_multi_epoch_gate.py",
}
if not required_hashes.issubset(manifest):
    raise RuntimeError(f"SOURCE_SNAPSHOT_MISMATCH: missing hashes {sorted(required_hashes - set(manifest))}")
actual = {name: hashlib.sha256((project / name).read_bytes()).hexdigest() for name in manifest}
print("SOURCE HASH MANIFEST", json.dumps({"expected": manifest, "actual": actual}, indent=2), flush=True)
if actual != manifest:
    raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH")

subprocess.run(
    [sys.executable, "-m", "pip", "install", "-e", str(project), "--no-deps", "--no-build-isolation"],
    check=True,
)
import torch

if not torch.cuda.is_available():
    raise RuntimeError("CUDA_REQUIRED")
print(json.dumps({
    "candidate": "lr_0_0002", "learning_rate": LEARNING_RATE,
    "gpu": torch.cuda.get_device_name(0), "torch": torch.__version__,
    "cuda": torch.version.cuda, "device_count": torch.cuda.device_count(),
}), flush=True)

source_roots = {path.parent for path in INPUT.rglob("source-sha256.json")}
preferred = INPUT / "ff-c23"
if preferred.is_dir() and any(preferred.rglob("*")):
    dataset = preferred
else:
    roots = [
        path for path in INPUT.iterdir()
        if path.is_dir() and not any(path == source or source in path.parents for source in source_roots)
    ]
    dataset = roots[0] if roots else None
if dataset is None:
    raise RuntimeError("REAL_TRAINING_DATASET_UNAVAILABLE")

command = [
    sys.executable, "-u", str(project / "scripts" / "run_v2_multi_epoch_gate.py"), str(dataset),
    "--learning-rate", str(LEARNING_RATE), "--output-dir", str(RESULTS),
]
print("STARTING APPROVED CANDIDATE B ONLY", json.dumps(command), flush=True)
returncode = subprocess.run(command, check=False).returncode
summary_path = RESULTS / "diagnostic_summary.json"
summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {
    "status": "FAIL", "exception": "diagnostic summary missing",
}
selection = {
    "status": summary.get("status", "FAIL"),
    "selected": {"learning_rate": LEARNING_RATE, "returncode": returncode, "summary": summary}
    if returncode == 0 and summary.get("status") == "PASS" else None,
    "assessments": [{"learning_rate": LEARNING_RATE, "returncode": returncode, "summary": summary}],
    "production_submitted": False,
    "candidate_a_retrained": False,
}
(RESULTS.parent / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
print("CANDIDATE B SELECTION", json.dumps(selection), flush=True)
raise SystemExit(returncode)
