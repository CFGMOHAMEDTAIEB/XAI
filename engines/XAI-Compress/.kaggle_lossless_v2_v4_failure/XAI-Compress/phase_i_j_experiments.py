from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from phase_h_dataset_audit import DOMAIN_EXTENSIONS


def make_domain_corpus(source: Path, destination: Path) -> dict:
    if destination.exists():
        shutil.rmtree(destination)
    copied = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in DOMAIN_EXTENSIONS:
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied.append(str(target))
    if not copied:
        raise RuntimeError(f"No domain files found under {source}")
    return {"root": str(destination), "files": len(copied), "extensions": sorted({Path(p).suffix.lower() for p in copied})}


def run_experiment(data_dir: Path, checkpoint: Path, context_length: int, args: argparse.Namespace) -> dict:
    command = [sys.executable, "-m", "xai_compress", "train", str(data_dir), str(checkpoint),
               "--epochs", str(args.epochs), "--batch-size", str(args.batch_size),
               "--context-length", str(context_length), "--stride", str(context_length),
               "--max-samples", str(args.max_samples), "--max-bytes-per-file", str(args.max_bytes_per_file),
               "--embedding-dim", "64", "--hidden-dim", "128", "--num-layers", "1", "--dropout", "0",
               "--lr", "1e-3", "--seed", "42", "--device", "cpu"]
    started = time.perf_counter()
    subprocess.run(command, check=True)
    elapsed = time.perf_counter() - started
    summary_path = checkpoint.with_suffix(".summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    actual_context = summary.get("model_config", {}).get("context_length")
    if actual_context != context_length:
        raise RuntimeError(f"context mismatch: requested {context_length}, got {actual_context}")
    return {"experiment": f"V1-{context_length}", "context_length": context_length,
            "checkpoint": str(checkpoint), "training_seconds": elapsed, **summary}


def write_results(rows: list[dict], json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    flat = []
    for row in rows:
        flat.append({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = list(dict.fromkeys(key for row in flat for key in row))
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(flat)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--domain-dir", type=Path, default=Path("data/domain_focused"))
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("checkpoints"))
    parser.add_argument("--max-samples", type=int, default=20_000)
    parser.add_argument("--max-bytes-per-file", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--contexts", type=int, nargs="+", default=[128, 256, 512])
    parser.add_argument("--json", type=Path, default=Path("phase_j_results.json"))
    parser.add_argument("--csv", type=Path, default=Path("phase_j_results.csv"))
    parser.add_argument("--phase-i-json", type=Path, default=Path("phase_i_results.json"))
    parser.add_argument("--phase-i-csv", type=Path, default=Path("phase_i_results.csv"))
    args = parser.parse_args()
    corpus = make_domain_corpus(args.data_dir, args.domain_dir)
    rows = []
    for context_length in args.contexts:
        checkpoint = args.checkpoint_dir / f"phase_j_v1_{context_length}.pt"
        row = run_experiment(args.domain_dir, checkpoint, context_length, args)
        row["corpus"] = corpus
        rows.append(row)
        write_results(rows, args.json, args.csv)
    write_results([row for row in rows if row["context_length"] == 128], args.phase_i_json, args.phase_i_csv)


if __name__ == "__main__":
    main()