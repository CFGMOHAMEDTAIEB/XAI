"""Template used by the bounded model-search controller.

The controller replaces the marker below with canonical JSON before pushing a
private Kaggle script.  The generated kernel runs exactly one candidate.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

CANDIDATE = json.loads(r'''{"config":{"amp":true,"amp_growth_interval":10000,"amp_initial_scale":1024,"architecture":"causal-byte-transformer-v2","batch_size":16,"context_length":256,"dropout":0.1,"embedding_dim":192,"ff_dim":768,"gradient_clip":1.0,"hidden_dim":192,"lr":0.0001,"max_bytes_per_file":33554432,"n_heads":6,"num_layers":4,"residual_scale":0.25,"stride":128},"id":"safe-training-lr-0-0001-54a4e17570","key":"safe_training_lr_0_0001","source_hashes":{"scripts/run_v2_multi_epoch_gate.py":"5f830da97c4b4e20b580b8d1ac4688081782c04e618b666b00569575af0e5caa","xai_compress/checkpoint.py":"937ded4da47d478aead69ba6fdc077fdb52f85fecb7ef9327fd060e1508a66af","xai_compress/compression.py":"c4565d3d8b2dd98b923894cb9f3d13aec97bdb1928f57a219b9db6abb4bfa934","xai_compress/models/transformer_v2.py":"c62ce7f35919de33f80546f0646f7ebfeb4bd8e00a31623ae7ed53b5e4ad1368","xai_compress/train.py":"fc08272318105e495bdf2c7c7ddadf8c3689dabf1aad57c809492c39b8d52e43"}}''')
INPUT = Path("/kaggle/input")
WORK = Path("/kaggle/working")
PROJECT = WORK / "XAI-Compress"
RESULTS = WORK / "results" / "model_search" / CANDIDATE["key"]
RESULTS.mkdir(parents=True, exist_ok=True)


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    resolved = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != resolved and resolved not in target.parents:
            raise RuntimeError(f"unsafe source archive member: {member.filename}")
    archive.extractall(destination)


sources = [path.parent for path in INPUT.rglob("source-sha256.json") if (path.parent / "pyproject.toml").is_file()]
if not sources:
    raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH: manifest unavailable")
source = sources[0]
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

manifest = json.loads((PROJECT / "source-sha256.json").read_text(encoding="utf-8"))
required = {
    "xai_compress/models/transformer_v2.py", "xai_compress/train.py",
    "xai_compress/checkpoint.py", "xai_compress/compression.py",
    "scripts/run_v2_multi_epoch_gate.py",
}
if not required.issubset(manifest):
    raise RuntimeError(f"SOURCE_SNAPSHOT_MISMATCH: missing {sorted(required - set(manifest))}")
actual = {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() for name in manifest}
print("SOURCE HASH MANIFEST", json.dumps({"expected": manifest, "actual": actual}, indent=2), flush=True)
if actual != manifest or actual != CANDIDATE["source_hashes"]:
    raise RuntimeError("SOURCE_SNAPSHOT_MISMATCH")

subprocess.run(
    [sys.executable, "-m", "pip", "install", "-e", str(PROJECT), "--no-deps", "--no-build-isolation"],
    check=True,
)
import torch
if not torch.cuda.is_available():
    raise RuntimeError("CUDA_REQUIRED")

config = CANDIDATE["config"]
source_roots = {path.parent for path in INPUT.rglob("source-sha256.json")}
preferred = INPUT / "ff-c23"
if preferred.is_dir() and any(preferred.rglob("*")):
    dataset = preferred
else:
    roots = [path for path in INPUT.iterdir() if path.is_dir() and not any(path == root or root in path.parents for root in source_roots)]
    dataset = roots[0] if roots else None
if dataset is None:
    raise RuntimeError("REAL_TRAINING_DATASET_UNAVAILABLE")

command = [
    sys.executable, "-u", str(PROJECT / "scripts" / "run_v2_multi_epoch_gate.py"), str(dataset),
    "--learning-rate", str(config["lr"]), "--output-dir", str(RESULTS),
    "--context-length", str(config["context_length"]),
    "--embedding-dim", str(config["embedding_dim"]),
    "--hidden-dim", str(config["hidden_dim"]),
    "--num-layers", str(config["num_layers"]),
    "--n-heads", str(config["n_heads"]), "--ff-dim", str(config["ff_dim"]),
    "--dropout", str(config["dropout"]), "--residual-scale", str(config.get("residual_scale", 1.0)),
]
print("STARTING ONE APPROVED CANDIDATE", json.dumps({"candidate": CANDIDATE, "command": command}), flush=True)
returncode = subprocess.run(command, check=False).returncode
summary_path = RESULTS / "diagnostic_summary.json"
summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {
    "status": "FAIL", "exception": "diagnostic summary missing",
}
selection = {
    "status": summary.get("status", "FAIL"),
    "selected": {"candidate_key": CANDIDATE["key"], "learning_rate": config["lr"], "returncode": returncode, "summary": summary}
    if returncode == 0 and summary.get("status") == "PASS" else None,
    "assessments": [{"candidate_key": CANDIDATE["key"], "learning_rate": config["lr"], "returncode": returncode, "summary": summary}],
    "production_submitted": False,
    "autonomous": True,
}
(RESULTS.parent / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
print("AUTONOMOUS SELECTION", json.dumps(selection), flush=True)
raise SystemExit(returncode)
