"""Production-order Lossless V2 activation-growth diagnostic."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from xai_compress.checkpoint import load_checkpoint, save_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.datasets.pipeline import dedupe_paths
from xai_compress.model import ModelConfig
from xai_compress.models.registry import build_model
from xai_compress.telemetry import collection_l2_norm
from xai_compress.train import ByteContextDataset, collate, seed_all, usable_paths


class Indexed(Dataset):
    def __init__(self, base):
        self.base = base

    def __len__(self):
        return len(self.base)

    def __getitem__(self, index):
        x, y = self.base[index]
        return x, y, index


def collate_indexed(batch):
    x, y = collate([(a, b) for a, b, _ in batch])
    return x, y, [index for _, _, index in batch]


def tensor_stats(value):
    value = value.detach().float()
    finite = torch.isfinite(value)
    selected = value[finite]
    if not selected.numel():
        return torch.tensor([0.0, math.nan, math.nan, math.nan, math.nan], device=value.device)
    std = selected.std() if selected.numel() > 1 else selected.new_zeros(())
    return torch.stack((finite.all().float(), selected.mean(), std,
                        selected.square().mean().sqrt(), selected.abs().max()))


def materialize_activations(values):
    if not values:
        return {}
    keys = list(values)
    rows = [[float(item.detach().item()) for item in values[key]] for key in keys]
    result = {}
    for key, row in zip(keys, rows):
        result[key] = {
            "finite": bool(row[0]), "mean": row[1] if math.isfinite(row[1]) else None,
            "std": row[2] if math.isfinite(row[2]) else None,
            "rms": row[3] if math.isfinite(row[3]) else None,
            "abs_max": row[4] if math.isfinite(row[4]) else None,
        }
    return result


def parameter_stats(model):
    groups = {
        "norm_scales": {},
        "attention_weight_norms": {},
        "ffn_weight_norms": {},
        "embedding_norm": float(model.embedding.weight.detach().float().norm().item()),
    }
    for name, parameter in model.named_parameters():
        detached = parameter.detach().float()
        if name.endswith(("n1.weight", "n2.weight")) or name == "norm.weight":
            groups["norm_scales"][name] = {
                "min": float(detached.min().item()),
                "max": float(detached.max().item()),
                "norm": float(detached.norm().item()),
            }
        elif ".attn." in name and name.endswith("weight"):
            groups["attention_weight_norms"][name] = float(detached.norm().item())
        elif (".gate." in name or ".proj." in name) and name.endswith("weight"):
            groups["ffn_weight_norms"][name] = float(detached.norm().item())
    return groups


def finite_optimizer(optimizer):
    for state in optimizer.state.values():
        for value in state.values():
            if torch.is_tensor(value) and not torch.isfinite(value).all():
                return False
    return True


def finite_parameters(model):
    return all(torch.isfinite(parameter).all() for parameter in model.parameters())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("--samples", type=int, default=450000)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--init-scale", type=float, default=1024)
    parser.add_argument("--growth-interval", type=int, default=10000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    seed_all(args.seed)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA_REQUIRED")
    device = "cuda"
    paths = dedupe_paths(usable_paths(args.data))
    rng = random.Random(args.seed)
    rng.shuffle(paths)
    validation_files = max(1, int(0.1 * len(paths)))
    train_paths = paths[validation_files:]
    dataset = ByteContextDataset(
        args.data, 256, 128, 450000, 32 << 20, args.seed, False, train_paths
    )
    loader = DataLoader(
        Indexed(dataset), batch_size=16, shuffle=True, collate_fn=collate_indexed,
        num_workers=2, pin_memory=True, persistent_workers=True, prefetch_factor=2,
    )
    config = ModelConfig(192, 192, 4, 256, 0.1, "causal-byte-transformer-v2", 6, 768)
    model = build_model(config).to(device)
    model.numerical_debug = True
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    scaler = torch.amp.GradScaler(
        "cuda", enabled=True, init_scale=args.init_scale,
        growth_interval=args.growth_interval,
    )
    criterion = nn.CrossEntropyLoss(ignore_index=-100)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    trace_path = args.output.with_suffix(".jsonl")
    trace = trace_path.open("w", encoding="utf-8")
    activations = {}
    preceding = collections.deque(maxlen=20)
    thresholds = [100.0, 500.0, 1000.0, 5000.0, 10000.0]
    crossed = set()
    threshold_events = []
    residual_max = {str(layer): 0.0 for layer in range(4)}
    stage_max = {}
    dense = False
    processed = 0
    started = time.perf_counter()

    def observe(stage, value, layer):
        key = f"layer_{layer}.{stage}" if layer is not None else stage
        activations[key] = tensor_stats(value)

    model.activation_observer = observe
    try:
        for step, (x, y, indices) in enumerate(loader, 1):
            if processed >= args.samples:
                break
            activations.clear()
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            try:
                with torch.amp.autocast("cuda", enabled=True):
                    logits, _ = model(x)
                    loss = criterion(logits.flatten(0, 1), y.flatten())
                if not torch.isfinite(loss):
                    raise FloatingPointError("non-finite loss")
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                gradients = [p.grad for p in model.parameters() if p.grad is not None]
                if any(not torch.isfinite(gradient).all() for gradient in gradients):
                    raise FloatingPointError("non-finite unscaled gradient")
                grad_norm = collection_l2_norm(gradients)
                if not math.isfinite(grad_norm):
                    raise FloatingPointError("non-finite gradient norm")
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                if any(not torch.isfinite(gradient).all() for gradient in gradients):
                    raise FloatingPointError("non-finite clipped gradient")
                scaler.step(optimizer)
                scaler.update()
                if not finite_parameters(model):
                    raise FloatingPointError("non-finite parameter")
                if not finite_optimizer(optimizer):
                    raise FloatingPointError("non-finite optimizer state")
            except Exception as exc:
                activation_values = materialize_activations(activations)
                batch = [
                    {"index": index, "path": dataset.samples[index][0],
                     "offset": dataset.samples[index][1], "length": dataset.samples[index][2]}
                    for index in indices
                ]
                event = {
                    "status": "FAIL", "classification": "FORWARD_ACTIVATION_INSTABILITY",
                    "step": step, "samples": processed + len(indices), "exception": repr(exc),
                    "activations": activation_values, "preceding_20": list(preceding),
                    "batch": batch, "token_min": int(x.min().item()),
                    "token_max": int(x.max().item()), "scale": float(scaler.get_scale()),
                    "parameters": parameter_stats(model),
                    "finite_parameters": finite_parameters(model),
                    "finite_optimizer": finite_optimizer(optimizer),
                    "threshold_events": threshold_events,
                    "max_residual_ffn_by_layer": residual_max,
                    "max_activation_by_stage": stage_max,
                }
                args.output.write_text(json.dumps(event, indent=2), encoding="utf-8")
                print("FIRST NON-FINITE EVENT", json.dumps(event), flush=True)
                raise

            processed += len(indices)
            activation_values = materialize_activations(activations)
            activation_max = max(
                (entry["abs_max"] or 0.0) for entry in activation_values.values()
            )
            for name, entry in activation_values.items():
                if entry["abs_max"] is not None:
                    stage_max[name] = max(stage_max.get(name, 0.0), entry["abs_max"])
            for layer in range(4):
                entry = activation_values.get(f"layer_{layer}.residual_ffn")
                if entry and entry["abs_max"] is not None:
                    residual_max[str(layer)] = max(residual_max[str(layer)], entry["abs_max"])
            for threshold in thresholds:
                if activation_max > threshold and threshold not in crossed:
                    crossed.add(threshold)
                    threshold_events.append({"threshold": threshold, "step": step, "samples": processed})
                    print("ACTIVATION THRESHOLD", json.dumps(threshold_events[-1]), flush=True)
            dense = dense or activation_max > 100.0
            row = {
                "step": step, "samples": processed, "loss": float(loss.detach().item()),
                "lr": optimizer.param_groups[0]["lr"], "scale": float(scaler.get_scale()),
                "grad_norm": grad_norm, "activation_max": activation_max,
                "activations": activation_values,
            }
            preceding.append(row)
            if step % 100 == 0:
                row["parameters"] = parameter_stats(model)
            if step % 100 == 0 or dense:
                trace.write(json.dumps(row) + "\n")
                trace.flush()
                print("ACTIVATION", json.dumps({
                    key: row[key] for key in (
                        "step", "samples", "loss", "lr", "scale", "grad_norm", "activation_max"
                    )
                }), flush=True)
    finally:
        trace.close()

    checkpoint = args.output.with_suffix(".pt")
    save_checkpoint(checkpoint, model, optimizer, 1, {"samples": processed})
    loaded, _ = load_checkpoint(checkpoint, "cpu")
    first, _ = loaded.step(256)
    second, _ = loaded.step(256)
    deterministic = torch.equal(first, second)
    probe = b"activation-diagnostic-lossless" * 8
    blob = compress_bytes(probe, "neural-lossless", checkpoint)
    restored = decompress_bytes(blob, checkpoint)
    lossless = hashlib.sha256(probe).digest() == hashlib.sha256(restored).digest()
    result = {
        "status": "PASS", "samples": processed, "steps": step,
        "learning_rate": args.learning_rate, "init_scale": args.init_scale,
        "growth_interval": args.growth_interval, "max_residual_ffn_by_layer": residual_max,
        "max_activation_by_stage": stage_max,
        "threshold_events": threshold_events, "finite_parameters": finite_parameters(model),
        "finite_optimizer": finite_optimizer(optimizer), "checkpoint_load": True,
        "deterministic_inference": deterministic, "lossless_sha256": lossless,
        "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "duration_seconds": time.perf_counter() - started,
    }
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("FULL-EPOCH STABILITY GATE", json.dumps(result), flush=True)
    if not (deterministic and lossless):
        raise RuntimeError("post-training validation failed")


if __name__ == "__main__":
    main()
