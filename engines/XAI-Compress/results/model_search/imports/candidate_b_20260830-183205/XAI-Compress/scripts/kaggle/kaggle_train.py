from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

from kaggle_setup import dataset_stats

PRESETS = {
    "SMOKE": dict(epochs=1, context_length=64, batch_size=16, stride=64, max_samples=1000, max_bytes_per_file=1 << 20, embedding_dim=32, hidden_dim=64, num_layers=1, dropout=0.0),
    "BALANCED": dict(epochs=10, context_length=128, batch_size=32, stride=128, max_samples=100_000, max_bytes_per_file=8 << 20, embedding_dim=64, hidden_dim=128, num_layers=1, dropout=0.05),
    "HIGH_QUALITY": dict(epochs=20, context_length=256, batch_size=32, stride=256, max_samples=200_000, max_bytes_per_file=16 << 20, embedding_dim=128, hidden_dim=256, num_layers=2, dropout=0.1),
    "RESEARCH": dict(epochs=60, context_length=256, batch_size=16, stride=128, max_samples=500_000, max_bytes_per_file=32 << 20, embedding_dim=192, hidden_dim=384, num_layers=2, dropout=0.1, early_stopping_patience=8, checkpoint_every=5),
}

def gpu_info():
    import torch
    if not torch.cuda.is_available(): raise SystemExit("CUDA GPU NOT AVAILABLE; refusing expensive CPU training")
    props = torch.cuda.get_device_properties(0)
    return {"name": props.name, "count": torch.cuda.device_count(), "vram_bytes": props.total_memory, "torch": torch.__version__, "cuda": torch.version.cuda}

def adjusted_config(name, overrides=None):
    cfg = dict(PRESETS[name])
    info = gpu_info(); gib = info["vram_bytes"] / 2**30
    cfg["batch_size"] = min(cfg["batch_size"], 16 if gib < 12 else 32 if gib < 20 else 64)
    cfg.update({k: v for k, v in (overrides or {}).items() if v is not None})
    return cfg, info

def run(dataset: Path, preset="BALANCED", resume=None, overrides=None, label="best"):
    import torch
    from xai_compress.checkpoint import load_checkpoint
    from xai_compress.train import train
    dataset = dataset.resolve()
    stats = dataset_stats(dataset)
    if stats["files"] < 2: raise ValueError("Training needs at least two usable files")
    cfg, gpu = adjusted_config(preset, overrides)
    work = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path.cwd() / ".kaggle_run"
    checkpoints, results = work / "checkpoints", work / "results"
    checkpoints.mkdir(parents=True, exist_ok=True); results.mkdir(parents=True, exist_ok=True)
    output = checkpoints / f"{label}.pt"
    if resume is None:
        recovery_candidates = sorted(checkpoints.glob("best.latest.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in recovery_candidates:
            try:
                load_checkpoint(candidate, "cpu")
                resume = candidate
                print("Automatically recovering from:", candidate)
                break
            except Exception as exc:
                print("Ignoring invalid recovery checkpoint:", candidate, exc)
    print(json.dumps({"dataset": stats, "gpu": gpu, "selected": cfg, "resume": str(resume) if resume else None}, indent=2))
    started = time.time()
    status_path = results / ("training_status.json" if label == "best" else f"{label}_training_status.json")
    try:
        train(dataset, output, device="cuda", amp=True, num_workers=2, resume=resume,
              status_path=status_path, max_periodic_checkpoints=3, **cfg)
    except Exception as exc:
        existing = {}
        try:
            existing = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            existing = {}
        payload = {
            **existing,
            "status": "FAILED",
            "exception_type": existing.get("exception_type", type(exc).__name__),
            "exception": existing.get("exception", str(exc)),
            "last_update_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        temporary = status_path.with_suffix(status_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(status_path)
        raise
    model, obj = load_checkpoint(output, "cpu")
    if output.stat().st_size <= 0: raise RuntimeError("Empty checkpoint")
    summary_file = output.with_suffix(".summary.json")
    summary = json.loads(summary_file.read_text()) if summary_file.exists() else {}
    experiment = {
        "timestamp": datetime.now(timezone.utc).isoformat(), "experiment_id": uuid.uuid4().hex,
        "dataset": stats, "model_configuration": model.config.__dict__, "training_configuration": cfg,
        "gpu": gpu, "python": platform.python_version(), "checkpoint": str(output),
        "epochs": obj.get("epoch"), "best_validation_loss": summary.get("best_validation_cross_entropy"),
        "best_bpb": summary.get("best_validation_bpb"), "runtime_seconds": time.time() - started,
    }
    (results / "experiment.json").write_text(json.dumps(experiment, indent=2), encoding="utf-8")
    print("Verified checkpoint:", output, output.stat().st_size, "bytes")
    return output, results

def main():
    p=argparse.ArgumentParser(); p.add_argument("dataset", type=Path); p.add_argument("--preset", choices=PRESETS, default="BALANCED"); p.add_argument("--resume", type=Path); args=p.parse_args()
    run(args.dataset, args.preset, args.resume)
if __name__ == "__main__": main()
