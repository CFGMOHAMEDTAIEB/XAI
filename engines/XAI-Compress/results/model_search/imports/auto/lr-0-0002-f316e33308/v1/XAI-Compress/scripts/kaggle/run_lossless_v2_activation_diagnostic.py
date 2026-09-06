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
    "xai_compress/models/transformer_v2.py": "3c0e5a825f08f13c014a302ec9dd45dca60d38f69f8b553c1e4a46b02c8a0be3",
    "xai_compress/train.py": "fc7993ea20b28ae4a8dd62017878f7638f546ef4c2427f22f0dd6cef4c901989",
    "scripts/debug_lossless_v2_activations.py": "f1a9d02233b38fef6507cd2990efa56fb434efcc28a0cce5d9b9929c87974c82",
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
script = PROJECT / "scripts/debug_lossless_v2_activations.py"
fp16_stages = (
    "attention_q", "attention_k", "attention_v", "attention_output",
    "ffn_first_projection", "ffn_gate_activation", "ffn_gated_product", "ffn_output",
)


def run(name, learning_rate):
    output = RESULTS / f"{name}.json"
    command = [
        sys.executable, "-u", str(script), str(data), "--samples", "450000",
        "--learning-rate", str(learning_rate), "--init-scale", "1024",
        "--growth-interval", "10000", "--output", str(output),
    ]
    print("RUN FULL-EPOCH FIX TEST", name, command, flush=True)
    code = subprocess.run(command, check=False).returncode
    if code:
        return False, {"name": name, "learning_rate": learning_rate, "process_exit": code}
    result = json.loads(output.read_text())
    fp16_max = max(
        value for key, value in result["max_activation_by_stage"].items()
        if key.endswith(fp16_stages)
    )
    # Require 2x headroom below FP16 max (65504), not merely a finite epoch.
    safe = fp16_max < 32752.0
    assessment = {
        "name": name, "learning_rate": learning_rate, "process_exit": code,
        "finite_gate": result["status"] == "PASS", "fp16_activation_max": fp16_max,
        "fp16_two_x_headroom": safe, "result": result,
    }
    print("FIX ASSESSMENT", json.dumps(assessment), flush=True)
    return safe, assessment


assessments = []
for name, learning_rate in (("fp32_dropout_lr_0_001", 0.001),
                            ("fp32_dropout_lr_0_0005", 0.0005),
                            ("fp32_dropout_lr_0_0003", 0.0003)):
    safe, assessment = run(name, learning_rate)
    assessments.append(assessment)
    if safe:
        selection = {"status": "PASS", "selected": assessment, "assessments": assessments}
        (RESULTS / "selected_configuration.json").write_text(json.dumps(selection, indent=2))
        print("VERSION 6 PRODUCTION = READY", json.dumps(selection), flush=True)
        raise SystemExit(0)
selection = {"status": "FAIL", "selected": None, "assessments": assessments}
(RESULTS / "selected_configuration.json").write_text(json.dumps(selection, indent=2))
print("VERSION 6 PRODUCTION = NOT READY", json.dumps(selection), flush=True)
raise SystemExit(1)
