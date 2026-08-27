from __future__ import annotations

import argparse
import csv
import json
import logging
import random
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from .checkpoint import load_checkpoint, save_checkpoint
from .datasets.pipeline import dedupe_paths, discover_files
from .model import BOS_TOKEN, CausalByteGRU, ModelConfig
from .models.registry import build_model
from .models.transformer import preset_config
from .utils.device import detect_device, gpu_memory_stats, reset_peak_memory, select_device

EXCLUDED_EXTENSIONS = {".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".xaic", ".pt", ".pth"}
LOGGER = logging.getLogger("xai_compress.train")


class ByteContextDataset(Dataset):
    """Bounded, lazy byte dataset for large on-disk corpora.

    Only (path, offset, length) tuples are kept in memory. Each chunk is read
    on demand. The number of samples and bytes considered per file are capped.
    """

    def __init__(
        self,
        root,
        context_length=128,
        stride=128,
        max_samples=200_000,
        max_bytes_per_file=16 * 1024 * 1024,
        seed=42,
        include_archives=False,
        paths=None,
        dedupe=True,
    ):
        root = Path(root)
        if not root.is_dir():
            raise ValueError(f"training directory not found: {root}")
        if min(context_length, stride, max_samples, max_bytes_per_file) < 1:
            raise ValueError("context_length, stride, max_samples and max_bytes_per_file must be positive")
        self.context_length = int(context_length)
        if paths is None:
            paths = discover_files(root, include_archives)
        else:
            paths = [Path(p) for p in paths]
        if dedupe:
            before = len(paths)
            paths = dedupe_paths(paths)
            LOGGER.info("deduplicated files: %s -> %s", before, len(paths))
        paths = sorted(paths)
        if not paths:
            raise ValueError("training directory contains no usable files")
        files_used = 0
        bytes_considered = 0
        rng = random.Random(seed)
        reservoir = []
        seen = 0
        for path in paths:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            usable = min(size, max_bytes_per_file)
            if usable <= 0:
                continue
            files_used += 1
            bytes_considered += usable
            last = max(0, usable - context_length)
            offsets = range(0, last + 1, stride) if usable > context_length else (0,)
            for offset in offsets:
                length = min(context_length, usable - offset)
                if length <= 0:
                    continue
                candidate = (str(path), int(offset), int(length))
                seen += 1
                if len(reservoir) < max_samples:
                    reservoir.append(candidate)
                else:
                    j = rng.randrange(seen)
                    if j < max_samples:
                        reservoir[j] = candidate
        if not reservoir:
            raise ValueError("no non-empty training samples")
        self.samples = reservoir
        rng.shuffle(self.samples)
        self.summary = {
            "files_discovered": len(paths),
            "files_used": files_used,
            "samples": len(self.samples),
            "bytes_considered": bytes_considered,
            "context_length": context_length,
            "stride": stride,
            "max_bytes_per_file": max_bytes_per_file,
            "archives_included": include_archives,
        }
        print(self.summary)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, offset, length = self.samples[idx]
        try:
            import xai_compress_core

            chunk = bytes(xai_compress_core.read_block(path, offset, length))
        except ImportError:
            with open(path, "rb", buffering=1024 * 1024) as handle:
                handle.seek(offset)
                chunk = handle.read(length)
        if len(chunk) != length:
            raise OSError(f"short read: {path} offset={offset}")
        values = np.frombuffer(chunk, dtype=np.uint8).astype(np.int64, copy=True)
        inputs = np.empty(length, dtype=np.int64)
        inputs[0] = BOS_TOKEN
        inputs[1:] = values[:-1]
        return torch.from_numpy(inputs), torch.from_numpy(values)


def collate(batch):
    lengths = torch.tensor([len(x[0]) for x in batch])
    maxlen = int(lengths.max().item())
    inputs = torch.zeros((len(batch), maxlen), dtype=torch.long)
    targets = torch.full((len(batch), maxlen), -100, dtype=torch.long)
    for i, (x, y) in enumerate(batch):
        inputs[i, : len(x)] = x
        targets[i, : len(y)] = y
    return inputs, targets


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def usable_paths(root, include_archives=False):
    return discover_files(Path(root), include_archives)


def _autocast(device: str, enabled: bool):
    if hasattr(torch, "amp") and hasattr(torch.amp, "autocast"):
        dtype = "cuda" if str(device).startswith("cuda") else "cpu"
        return torch.amp.autocast(device_type=dtype, enabled=enabled and dtype == "cuda")
    from torch.cuda.amp import autocast

    return autocast(enabled=enabled and str(device).startswith("cuda"))


def _grad_scaler(enabled: bool):
    if hasattr(torch, "amp") and hasattr(torch.amp, "GradScaler"):
        return torch.amp.GradScaler("cuda", enabled=enabled)
    from torch.cuda.amp import GradScaler

    return GradScaler(enabled=enabled)


def train(
    data_dir,
    output,
    epochs=10,
    batch_size=64,
    lr=1e-3,
    context_length=128,
    seed=42,
    device=None,
    stride=128,
    max_samples=200_000,
    max_bytes_per_file=16 * 1024 * 1024,
    num_workers=0,
    embedding_dim=64,
    hidden_dim=128,
    num_layers=1,
    dropout=0.0,
    include_archives=False,
    amp=True,
    grad_accum=1,
    resume=None,
    preset=None,
    architecture=None,
    n_heads=4,
    ff_dim=256,
    compile_model=False,
    multi_gpu=False,
    gradient_checkpointing=False,
    val_frac=0.1,
):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    seed_all(seed)
    info = detect_device()
    device = select_device(device)
    for line in info.report_lines():
        print(line)
    paths = usable_paths(data_dir, include_archives)
    paths = dedupe_paths(paths)
    if len(paths) < 2:
        raise ValueError("at least two usable files are required for file-level validation")
    path_rng = random.Random(seed)
    path_rng.shuffle(paths)
    n_val_files = max(1, int(val_frac * len(paths)))
    val_paths = paths[:n_val_files]
    train_paths = paths[n_val_files:]
    train_limit = max(1, int(max_samples * (1 - val_frac)))
    val_limit = max(1, max_samples - train_limit)
    train_ds = ByteContextDataset(
        data_dir, context_length, stride, train_limit, max_bytes_per_file, seed, include_archives, train_paths
    )
    val_ds = ByteContextDataset(
        data_dir, context_length, stride, val_limit, max_bytes_per_file, seed + 1, include_archives, val_paths
    )
    if len(train_ds) < 1 or len(val_ds) < 1:
        raise ValueError("file split produced no usable samples")
    pin = str(device).startswith("cuda")
    workers = int(num_workers)
    common = {
        "batch_size": batch_size,
        "collate_fn": collate,
        "num_workers": workers,
        "pin_memory": pin,
        "persistent_workers": workers > 0,
        "prefetch_factor": 2 if workers > 0 else None,
    }
    if workers == 0:
        common.pop("prefetch_factor")
        common.pop("persistent_workers")
    train_loader = DataLoader(train_ds, shuffle=True, **common)
    val_loader = DataLoader(val_ds, shuffle=False, **common)
    if preset:
        cfg = preset_config(preset, context_length=context_length, dropout=dropout)
    else:
        arch = architecture or "causal-byte-gru-v1"
        if arch in ("transformer", "causal-byte-transformer-v1"):
            arch = "causal-byte-transformer-v1"
        else:
            arch = "causal-byte-gru-v1"
        cfg = ModelConfig(
            embedding_dim=embedding_dim,
            hidden_dim=hidden_dim,
            num_layers=num_layers,
            context_length=context_length,
            dropout=dropout,
            architecture_id=arch,
            n_heads=n_heads,
            ff_dim=ff_dim,
        )
    start_epoch = 1
    model = build_model(cfg).to(device)
    if gradient_checkpointing and hasattr(model, "gradient_checkpointing"):
        model.gradient_checkpointing = True
    if multi_gpu and torch.cuda.device_count() > 1:
        model = nn.DataParallel(model)
        print(f"DataParallel on {torch.cuda.device_count()} GPUs")
    if compile_model and hasattr(torch, "compile"):
        model = torch.compile(model)
    opt = torch.optim.AdamW((model.module if hasattr(model, "module") else model).parameters(), lr=lr)
    use_amp = bool(amp) and str(device).startswith("cuda")
    scaler = _grad_scaler(use_amp)
    if resume:
        loaded, obj = load_checkpoint(resume, device)
        core = model.module if hasattr(model, "module") else model
        core.load_state_dict(loaded.state_dict())
        if obj.get("optimizer_state"):
            opt.load_state_dict(obj["optimizer_state"])
        if obj.get("scaler_state") and use_amp:
            scaler.load_state_dict(obj["scaler_state"])
        start_epoch = int(obj.get("epoch", 0)) + 1
        print(f"resumed from {resume} at epoch {start_epoch}")
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="min", factor=0.5, patience=1)
    criterion = nn.CrossEntropyLoss(ignore_index=-100)
    best = float("inf")
    patience = 5
    stale = 0
    metrics = []
    reset_peak_memory()
    for epoch in range(start_epoch, epochs + 1):
        model.train()
        total = n = 0
        opt.zero_grad(set_to_none=True)
        for step, (x, y) in enumerate(train_loader, start=1):
            x = x.to(device, non_blocking=pin)
            y = y.to(device, non_blocking=pin)
            with _autocast(device, use_amp):
                logits, _ = model(x)
                loss = criterion(logits.reshape(-1, 256), y.reshape(-1)) / max(1, grad_accum)
            scaler.scale(loss).backward()
            if step % max(1, grad_accum) == 0:
                scaler.unscale_(opt)
                nn.utils.clip_grad_norm_((model.module if hasattr(model, "module") else model).parameters(), 1.0)
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
            count = int((y != -100).sum().item())
            total += float(loss.detach().item()) * max(1, grad_accum) * count
            n += count
        model.eval()
        vt = vn = 0
        with torch.inference_mode():
            for x, y in val_loader:
                x = x.to(device, non_blocking=pin)
                y = y.to(device, non_blocking=pin)
                with _autocast(device, use_amp):
                    logits, _ = model(x)
                    loss = criterion(logits.reshape(-1, 256), y.reshape(-1))
                count = int((y != -100).sum().item())
                vt += float(loss.detach().item()) * count
                vn += count
        tr = total / max(1, n)
        va = vt / max(1, vn)
        scheduler.step(va)
        gpu = gpu_memory_stats()
        row = {
            "epoch": epoch,
            "train_cross_entropy": tr,
            "val_cross_entropy": va,
            "val_bpb_estimate": float(va / np.log(2)),
            "learning_rate": opt.param_groups[0]["lr"],
            "vram_max_bytes": gpu.get("max_allocated_bytes", 0.0),
        }
        metrics.append(row)
        print(row)
        if va < best:
            best = va
            stale = 0
            core = model.module if hasattr(model, "module") else model
            save_checkpoint(
                output,
                core,
                opt,
                epoch,
                {
                    **row,
                    "parameter_count": sum(p.numel() for p in core.parameters()),
                    "train_dataset": train_ds.summary,
                    "validation_dataset": val_ds.summary,
                    "train_files": len(train_paths),
                    "validation_files": len(val_paths),
                },
                scaler=scaler if use_amp else None,
            )
        else:
            stale += 1
            if stale >= patience:
                break
    csv_path = Path(output).with_suffix(".metrics.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=metrics[0].keys())
        writer.writeheader()
        writer.writerows(metrics)
    core = model.module if hasattr(model, "module") else model
    summary_path = Path(output).with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(
            {
                "checkpoint": str(output),
                "parameter_count": sum(p.numel() for p in core.parameters()),
                "best_validation_cross_entropy": best,
                "best_validation_bpb": best / np.log(2),
                "epochs_completed": len(metrics),
                "train_files": len(train_paths),
                "validation_files": len(val_paths),
                "train_dataset": train_ds.summary,
                "validation_dataset": val_ds.summary,
                "model_config": core.config.__dict__,
                "seed": seed,
                "device": device,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir")
    parser.add_argument("output")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--context-length", type=int, default=128)
    parser.add_argument("--stride", type=int, default=128)
    parser.add_argument("--max-samples", type=int, default=200_000)
    parser.add_argument("--max-bytes-per-file", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--embedding-dim", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.0)
    parser.add_argument("--include-archives", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device")
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--resume")
    parser.add_argument("--preset")
    parser.add_argument("--architecture")
    parser.add_argument("--n-heads", type=int, default=4)
    parser.add_argument("--ff-dim", type=int, default=256)
    parser.add_argument("--compile-model", action="store_true")
    parser.add_argument("--multi-gpu", action="store_true")
    parser.add_argument("--gradient-checkpointing", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    train(**vars(args))


if __name__ == "__main__":
    main()
