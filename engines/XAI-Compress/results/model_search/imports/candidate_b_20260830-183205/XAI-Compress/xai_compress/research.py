"""Reproducible research metadata and result utilities.

This module deliberately separates measured values from narrative reports.
Reports and notebooks consume these records; they never invent missing metrics.
"""
from __future__ import annotations

import csv
import json
import os
import platform
import socket
import subprocess
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass
class ExperimentRecord:
    experiment_id: str
    timestamp_utc: str
    status: str
    model: str = ""
    model_version: str = ""
    dataset: str = ""
    dataset_version: str = ""
    parameters: int | None = None
    epochs: int | None = None
    batch_size: int | None = None
    context_length: int | None = None
    learning_rate: float | None = None
    loss: float | None = None
    bpb: float | None = None
    compression_ratio: float | None = None
    compression_mbs: float | None = None
    decompression_mbs: float | None = None
    peak_vram_bytes: int | None = None
    peak_ram_bytes: int | None = None
    configuration_json: str = "{}"
    notes: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def software_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for name in ("torch", "numpy", "zstandard", "brotli", "psutil"):
        try:
            module = __import__(name)
            versions[name] = str(getattr(module, "__version__", "installed"))
        except ImportError:
            versions[name] = None
    return versions


def machine_manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "timestamp_utc": utc_now(),
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "cpu": platform.processor() or "unknown",
        "logical_cpu_count": os.cpu_count(),
        "software": software_versions(),
    }
    try:
        import psutil

        manifest["ram_bytes"] = int(psutil.virtual_memory().total)
    except ImportError:
        manifest["ram_bytes"] = None
    try:
        from .utils.device import detect_device

        manifest["accelerator"] = detect_device().as_dict()
    except Exception as exc:
        manifest["accelerator"] = {"available": False, "error": str(exc)}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=False
        ).stdout.strip()
        manifest["git_commit"] = commit or None
    except OSError:
        manifest["git_commit"] = None
    return manifest


def write_manifest(path: str | Path) -> dict[str, Any]:
    value = machine_manifest()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    return value


def append_experiment(path: str | Path, record: ExperimentRecord) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    names = [field.name for field in fields(ExperimentRecord)]
    exists = target.is_file() and target.stat().st_size > 0
    with target.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        if not exists:
            writer.writeheader()
        writer.writerow(asdict(record))


def read_csv(path: str | Path) -> list[dict[str, str]]:
    target = Path(path)
    if not target.is_file():
        return []
    with target.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_json_records(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(list(rows), indent=2, default=str), encoding="utf-8")
