"""Kaggle T4 entry point for the guarded five-epoch V2 LR diagnostic."""
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
RESULTS = WORK / "results" / "model_v2"
RESULTS.mkdir(parents=True, exist_ok=True)


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
actual = {
    name: hashlib.sha256((project / name).read_bytes()).hexdigest()
    for name in manifest if (project / name).is_file()
}
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

worker = project / "scripts" / "run_v2_multi_epoch_gate.py"
assessments = []
selected = None
for learning_rate in (0.0003, 0.0002):
    label = f"lr_{str(learning_rate).replace('.', '_')}"
    destination = RESULTS / label
    command = [
        sys.executable, "-u", str(worker), str(dataset),
        "--learning-rate", str(learning_rate), "--output-dir", str(destination),
    ]
    print("STARTING FIVE-EPOCH DIAGNOSTIC", json.dumps(command), flush=True)
    returncode = subprocess.run(command, check=False).returncode
    summary_path = destination / "diagnostic_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {
        "status": "FAIL", "exception": "diagnostic summary missing",
    }
    assessment = {"learning_rate": learning_rate, "returncode": returncode, "summary": summary}
    assessments.append(assessment)
    if returncode == 0 and summary.get("status") == "PASS":
        selected = assessment
        shutil.copy2(destination / "multi_epoch_stability.csv", RESULTS / "multi_epoch_stability.csv")
        break
    print("DIAGNOSTIC CANDIDATE REJECTED", json.dumps(assessment), flush=True)
    numerical_failure = (
        returncode == 2
        or summary.get("exception_type") in {"FloatingPointError", "NumericalDebugError"}
        or "NON_FINITE" in str(summary.get("exception", "")).upper()
        or "FIRST NON-FINITE" in str(summary.get("exception", "")).upper()
    )
    if learning_rate == 0.0003 and not numerical_failure:
        print("INFRASTRUCTURE_OR_CODE_FAILURE; LR 0.0002 NOT STARTED", flush=True)
        break

selection = {
    "status": "PASS" if selected else "FAIL",
    "selected": selected,
    "assessments": assessments,
    "production_submitted": False,
}
(RESULTS / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
print("V2 MULTI-EPOCH SELECTION", json.dumps(selection), flush=True)
if selected is None:
    print("ARCHITECTURE_NORMALIZATION_INVESTIGATION_REQUIRED", flush=True)
    raise SystemExit(1)
print("PRODUCTION CANDIDATE PROVEN; PRODUCTION NOT SUBMITTED BY DIAGNOSTIC", flush=True)
