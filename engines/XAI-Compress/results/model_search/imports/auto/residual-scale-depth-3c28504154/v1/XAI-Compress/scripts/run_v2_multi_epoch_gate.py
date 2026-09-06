"""Run and validate one production-equivalent five-epoch V2 stability gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
import traceback
from pathlib import Path

import torch

from xai_compress.checkpoint import load_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.train import train


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def classify_growth(values: list[float]) -> str:
    """Conservative descriptive classification; no fitted curve is claimed."""
    if len(values) < 5 or min(values) <= 0:
        return "INSUFFICIENT_EVIDENCE"
    differences = [right - left for left, right in zip(values, values[1:])]
    if max(values) / min(values) <= 1.25:
        return "STABLE"
    if all(delta > 0 for delta in differences):
        early = sum(differences[:2]) / 2
        late = sum(differences[-2:]) / 2
        if early > 0 and late > 2 * early and values[-1] > 2 * values[0]:
            return "STRONGLY_ACCELERATING"
        spread = max(differences) - min(differences)
        if spread <= 0.35 * max(differences):
            return "APPROXIMATELY_LINEAR"
    return "NON_MONOTONIC_OR_SUBLINEAR"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("--learning-rate", type=float, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--context-length", type=int, default=256)
    parser.add_argument("--embedding-dim", type=int, default=192)
    parser.add_argument("--hidden-dim", type=int, default=192)
    parser.add_argument("--num-layers", type=int, default=4)
    parser.add_argument("--n-heads", type=int, default=6)
    parser.add_argument("--ff-dim", type=int, default=768)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--residual-scale", type=float, default=1.0)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "best.pt"
    stability_csv = output_dir / "multi_epoch_stability.csv"
    status = output_dir / "training_status.json"
    started = time.perf_counter()
    result_path = output_dir / "diagnostic_summary.json"
    try:
        short_checkpoint = output_dir / "short_screen.pt"
        short_started = time.perf_counter()
        train(
            args.data,
            short_checkpoint,
            epochs=1,
            batch_size=16,
            lr=args.learning_rate,
            context_length=args.context_length,
            seed=42,
            device="cuda",
            stride=128,
            max_samples=32_768,
            max_bytes_per_file=32 << 20,
            num_workers=2,
            embedding_dim=args.embedding_dim,
            hidden_dim=args.hidden_dim,
            num_layers=args.num_layers,
            dropout=args.dropout,
            amp=True,
            architecture="causal-byte-transformer-v2",
            n_heads=args.n_heads,
            ff_dim=args.ff_dim,
            residual_scale=args.residual_scale,
            val_frac=0.1,
            early_stopping_patience=2,
            checkpoint_every=1,
            max_periodic_checkpoints=1,
            status_path=output_dir / "short_screen_status.json",
            numerical_debug=True,
            amp_initial_scale=1024,
            amp_growth_interval=10000,
            stability_output=output_dir / "short_screen_stability.csv",
        )
        short_model, short_object = load_checkpoint(short_checkpoint, "cpu")
        if not all(torch.isfinite(parameter).all() for parameter in short_model.parameters()):
            raise FloatingPointError("SHORT_GPU_SCREEN_NON_FINITE_PARAMETER")
        short_summary = {
            "status": "PASS", "samples": 32768, "checkpoint_load": True,
            "finite_parameters": True, "checkpoint_epoch": short_object.get("epoch"),
            "duration_seconds": time.perf_counter() - short_started,
            "checkpoint_sha256": hashlib.sha256(short_checkpoint.read_bytes()).hexdigest(),
        }
        (output_dir / "short_screen_summary.json").write_text(
            json.dumps(short_summary, indent=2), encoding="utf-8"
        )
        print("SHORT GPU STABILITY SCREEN", json.dumps(short_summary), flush=True)
        train(
            args.data,
            checkpoint,
            epochs=5,
            batch_size=16,
            lr=args.learning_rate,
            context_length=args.context_length,
            seed=42,
            device="cuda",
            stride=128,
            max_samples=500_000,
            max_bytes_per_file=32 << 20,
            num_workers=2,
            embedding_dim=args.embedding_dim,
            hidden_dim=args.hidden_dim,
            num_layers=args.num_layers,
            dropout=args.dropout,
            amp=True,
            architecture="causal-byte-transformer-v2",
            n_heads=args.n_heads,
            ff_dim=args.ff_dim,
            residual_scale=args.residual_scale,
            val_frac=0.1,
            early_stopping_patience=8,
            checkpoint_every=5,
            max_periodic_checkpoints=3,
            status_path=status,
            numerical_debug=True,
            amp_initial_scale=1024,
            amp_growth_interval=10000,
            stability_output=stability_csv,
        )
        history = json.loads(checkpoint.with_suffix(".history.json").read_text(encoding="utf-8"))
        if len(history) != 5 or [int(row["epoch"]) for row in history] != [1, 2, 3, 4, 5]:
            raise RuntimeError(f"FIVE_EPOCH_GATE_INCOMPLETE: epochs={[row.get('epoch') for row in history]}")
        model, checkpoint_object = load_checkpoint(checkpoint, "cpu")
        if not all(torch.isfinite(parameter).all() for parameter in model.parameters()):
            raise FloatingPointError("NON_FINITE_CHECKPOINT_PARAMETER")
        optimizer_tensors = []
        pending = [checkpoint_object.get("optimizer_state", {})]
        while pending:
            current = pending.pop()
            if isinstance(current, dict):
                pending.extend(current.values())
            elif isinstance(current, (list, tuple)):
                pending.extend(current)
            elif torch.is_tensor(current):
                optimizer_tensors.append(current)
        finite_optimizer_state = bool(optimizer_tensors) and all(
            torch.isfinite(tensor).all() for tensor in optimizer_tensors
        )
        if not finite_optimizer_state:
            raise FloatingPointError("NON_FINITE_OR_MISSING_CHECKPOINT_OPTIMIZER_STATE")
        first, _ = model.step(256, None)
        second, _ = model.step(256, None)
        deterministic = torch.equal(first, second)
        generator = random.Random(20260830)
        corpus = {
            "empty": b"",
            "tiny": b"x",
            "text": b"XAI-Compress multi-epoch stability gate\n" * 16,
            "all_bytes": bytes(range(256)) * 2,
            "random": bytes(generator.randrange(256) for _ in range(1024)),
        }
        roundtrips = []
        for name, original in corpus.items():
            artifact = compress_bytes(original, "neural-lossless", checkpoint, device="cpu")
            reconstructed = decompress_bytes(artifact, checkpoint, device="cpu")
            passed = sha256_bytes(original) == sha256_bytes(reconstructed)
            roundtrips.append({
                "name": name, "bytes": len(original), "artifact_bytes": len(artifact),
                "original_sha256": sha256_bytes(original),
                "reconstructed_sha256": sha256_bytes(reconstructed), "pass": passed,
            })
        layer_trajectories = {
            str(layer): [float(row[f"max_activation_layer_{layer}"]) for row in history]
            for layer in range(args.num_layers)
        }
        layer_3_growth = classify_growth(layer_trajectories["3"])
        all_activation_fields = [
            float(value)
            for row in history
            for key, value in row.items()
            if key.endswith("_abs_max") and (key.startswith("block_") or key in {"logits_abs_max", "embedding_activation_abs_max"})
        ]
        max_activation = max(all_activation_fields)
        finite_metrics = all(
            math.isfinite(float(row[key]))
            for row in history
            for key in (
                "train_cross_entropy", "val_cross_entropy", "val_bpb_estimate",
                "gradient_norm_epoch_max", "gradient_abs_max", "parameter_abs_max",
                "optimizer_state_abs_max", "logits_abs_max",
            )
        )
        passed = (
            finite_metrics and deterministic and all(item["pass"] for item in roundtrips)
            and max_activation < 32752.0 and layer_3_growth != "STRONGLY_ACCELERATING"
        )
        result = {
            "status": "PASS" if passed else "FAIL",
            "short_gpu_screen": short_summary,
            "learning_rate": args.learning_rate,
            "epochs": 5,
            "training_samples_per_epoch": 450000,
            "validation_samples_per_epoch": 50000,
            "training_samples_total": 2250000,
            "steps_per_epoch": math.ceil(450000 / 16),
            "max_activation": max_activation,
            "two_x_fp16_headroom": max_activation < 32752.0,
            "preferred_activation_range": max_activation < 16000.0,
            "layer_trajectories": layer_trajectories,
            "layer_3_growth": layer_3_growth,
            "finite_metrics": finite_metrics,
            "checkpoint_load": True,
            "checkpoint_epoch": checkpoint_object.get("epoch"),
            "checkpoint_size": checkpoint.stat().st_size,
            "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            "finite_parameters": True,
            "finite_optimizer_state": finite_optimizer_state,
            "deterministic_inference": deterministic,
            "roundtrips": roundtrips,
            "lossless_sha256": all(item["pass"] for item in roundtrips),
            "duration_seconds": time.perf_counter() - started,
            "history": history,
        }
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("MULTI-EPOCH STABILITY GATE", json.dumps(result), flush=True)
        return 0 if passed else 2
    except Exception as exc:
        result = {
            "status": "FAIL", "learning_rate": args.learning_rate,
            "exception_type": type(exc).__name__, "exception": str(exc),
            "traceback": traceback.format_exc(),
            "duration_seconds": time.perf_counter() - started,
        }
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("MULTI-EPOCH STABILITY GATE FAILED", json.dumps(result), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
