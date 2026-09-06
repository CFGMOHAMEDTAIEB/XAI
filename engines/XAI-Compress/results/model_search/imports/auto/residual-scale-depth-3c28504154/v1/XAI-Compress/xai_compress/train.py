from __future__ import annotations

import argparse
import bisect
import csv
import json
import logging
import random
import subprocess
import time
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
from .telemetry import (
    collection_abs_max,
    collection_finite_and_abs_max,
    collection_l2_norm,
    diagnostic_scalar_max,
)
from .utils.device import detect_device, gpu_memory_stats, reset_peak_memory, select_device

EXCLUDED_EXTENSIONS = {".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".xaic", ".pt", ".pth"}
LOGGER = logging.getLogger("xai_compress.train")


def require_finite(value, stage, epoch=None, step=None):
    if torch.isfinite(value).all():
        return
    raise FloatingPointError(f"FIRST NON-FINITE STAGE = {stage}; epoch={epoch}; step={step}")


def require_finite_gradients(model, epoch=None, step=None, prefix="gradient"):
    """Fail on the first non-finite gradient and retain its parameter name."""
    for name, parameter in model.named_parameters():
        if parameter.grad is not None:
            require_finite(parameter.grad, f"{prefix}:{name}", epoch, step)


def require_finite_optimizer_state(optimizer, epoch=None, step=None):
    """Fail on the first non-finite tensor in an optimizer state."""
    for parameter_index, state in enumerate(optimizer.state.values()):
        for key, value in state.items():
            if torch.is_tensor(value):
                require_finite(value, f"optimizer:{parameter_index}:{key}", epoch, step)


def _collection_abs_max(values, device):
    # ``device`` remains for compatibility with older diagnostic callers; the
    # result is deliberately a device-neutral Python float.
    del device
    return collection_abs_max(values)


def aggregate_diagnostic_scalars(values) -> float:
    """Aggregate optional scalar telemetry without coupling tensor devices."""
    return diagnostic_scalar_max(values)


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
        file_ranges = []
        cumulative = []
        total_candidates = 0
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
            count = 1 if usable <= context_length else ((usable - context_length) // stride) + 1
            file_ranges.append((str(path), int(usable), int(count)))
            total_candidates += count
            cumulative.append(total_candidates)
        if total_candidates < 1:
            raise ValueError("no non-empty training samples")
        # Sample global candidate indices directly. This keeps initialization
        # O(files + max_samples), rather than walking billions of byte offsets
        # merely to maintain a bounded reservoir on large Kaggle corpora.
        selected = range(total_candidates) if total_candidates <= max_samples else rng.sample(range(total_candidates), max_samples)
        samples = []
        for global_index in selected:
            file_index = bisect.bisect_right(cumulative, global_index)
            previous = cumulative[file_index - 1] if file_index else 0
            path, usable, _ = file_ranges[file_index]
            offset = (global_index - previous) * stride
            length = min(context_length, usable - offset)
            samples.append((path, int(offset), int(length)))
        self.samples = samples
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


def _grad_scaler(enabled: bool, initial_scale=65536.0, growth_interval=2000):
    if hasattr(torch, "amp") and hasattr(torch.amp, "GradScaler"):
        return torch.amp.GradScaler("cuda", enabled=enabled, init_scale=float(initial_scale),
                                    growth_interval=int(growth_interval))
    from torch.cuda.amp import GradScaler

    return GradScaler(enabled=enabled, init_scale=float(initial_scale), growth_interval=int(growth_interval))


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
    residual_scale=1.0,
    compile_model=False,
    multi_gpu=False,
    gradient_checkpointing=False,
    val_frac=0.1,
    early_stopping_patience=5,
    checkpoint_every=5,
    max_periodic_checkpoints=3,
    status_path=None,
    numerical_debug=False,
    amp_initial_scale=65536.0,
    amp_growth_interval=2000,
    stability_output=None,
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
        elif arch in ("transformer-v2", "causal-byte-transformer-v2"):
            arch = "causal-byte-transformer-v2"
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
            residual_scale=residual_scale,
        )
    start_epoch = 1
    resumed_metrics = None
    resumed_scheduler_state = None
    model = build_model(cfg).to(device)
    core = model.module if hasattr(model, "module") else model
    epoch_activation_stats = {}

    observed_block_stages = {
        "block_input",
        "attention_normalized_input",
        "attention_q",
        "attention_k",
        "attention_v",
        "attention_context",
        "attention_output",
        "residual_attention",
        "ffn_normalized_input",
        "ffn_first_projection",
        "ffn_gate_activation",
        "ffn_gated_product",
        "ffn_output",
        "ffn_dropout",
        "residual_ffn",
    }

    def observe_activation(stage, value, layer):
        if stage not in observed_block_stages and stage not in {"embedding", "output_logits"}:
            return
        if numerical_debug:
            require_finite(value, f"activation:{stage}" if layer is None else f"activation:blocks.{layer}:{stage}")
        detached = value.detach().float()
        key = (None if layer is None else int(layer), stage)
        observed_max = detached.abs().max()
        observed_sum_squares = detached.square().sum()
        current = epoch_activation_stats.get(key)
        if current is None:
            epoch_activation_stats[key] = {
                "abs_max": observed_max,
                "sum_squares": observed_sum_squares,
                "numel": detached.numel(),
                "observations": 1,
            }
        else:
            current["abs_max"] = torch.maximum(current["abs_max"], observed_max)
            current["sum_squares"] = current["sum_squares"] + observed_sum_squares
            current["numel"] += detached.numel()
            current["observations"] += 1

    if hasattr(core,"numerical_debug"):
        core.numerical_debug=bool(numerical_debug)
    if numerical_debug and hasattr(core, "activation_observer"):
        core.activation_observer = observe_activation
    if gradient_checkpointing and hasattr(model, "gradient_checkpointing"):
        model.gradient_checkpointing = True
    if multi_gpu and torch.cuda.device_count() > 1:
        model = nn.DataParallel(model)
        print(f"DataParallel on {torch.cuda.device_count()} GPUs")
    if compile_model and hasattr(torch, "compile"):
        model = torch.compile(model)
    opt = torch.optim.AdamW((model.module if hasattr(model, "module") else model).parameters(), lr=lr)
    use_amp = bool(amp) and str(device).startswith("cuda")
    scaler = _grad_scaler(use_amp, amp_initial_scale, amp_growth_interval)
    if resume:
        loaded, obj = load_checkpoint(resume, device)
        core = model.module if hasattr(model, "module") else model
        core.load_state_dict(loaded.state_dict())
        if obj.get("optimizer_state"):
            opt.load_state_dict(obj["optimizer_state"])
        if obj.get("scaler_state") and use_amp:
            scaler.load_state_dict(obj["scaler_state"])
        start_epoch = int(obj.get("epoch", 0)) + 1
        resumed_metrics = obj.get("metrics") or {}
        resumed_scheduler_state = obj.get("scheduler_state")
        print(f"resumed from {resume} at epoch {start_epoch}")
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="min", factor=0.5, patience=1)
    if resumed_scheduler_state:
        scheduler.load_state_dict(resumed_scheduler_state)
    criterion = nn.CrossEntropyLoss(ignore_index=-100)
    best = float((resumed_metrics or {}).get("best_validation_cross_entropy", (resumed_metrics or {}).get("val_cross_entropy", float("inf"))))
    patience = max(1, int(early_stopping_patience))
    stale = 0
    metrics = []
    output_path = Path(output)
    latest_path = output_path.with_name(output_path.stem + ".latest" + output_path.suffix)
    csv_path = output_path.with_suffix(".metrics.csv")
    history_path = output_path.with_suffix(".history.json")
    stability_path = Path(stability_output) if stability_output else None
    status_path = Path(status_path) if status_path else None

    if resume:
        resume_path = Path(resume)
        history_candidates = [history_path, resume_path.with_suffix(".history.json")]
        if resume_path.stem.endswith(".latest"):
            history_candidates.append(resume_path.with_name(resume_path.stem[:-len(".latest")] + ".history.json"))
        previous_history_path = next((candidate for candidate in history_candidates if candidate.is_file()), None)
        if previous_history_path is not None:
            try:
                previous_history = json.loads(previous_history_path.read_text(encoding="utf-8"))
                metrics = [row for row in previous_history if int(row.get("epoch", 0)) < start_epoch]
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                metrics = []
    if metrics:
        stale = 0
        for previous in reversed(metrics):
            previous_val = float(previous.get("val_cross_entropy", float("inf")))
            if previous_val <= best:
                break
            stale += 1

    def write_status(status, **values):
        if status_path is None:
            return
        status_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"status": status, "last_update_timestamp": time.time(), **values}
        temporary = status_path.with_suffix(status_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(status_path)

    def failure_snapshot(current_loss=None):
        trainable = model.module if hasattr(model, "module") else model
        parameters = list(trainable.parameters())
        gradients = [parameter.grad for parameter in parameters if parameter.grad is not None]
        optimizer_tensors = [value for state in opt.state.values() for value in state.values() if torch.is_tensor(value)]

        parameters_finite, parameter_max = collection_finite_and_abs_max(parameters)
        gradients_finite, gradient_max = collection_finite_and_abs_max(gradients)
        optimizer_finite, optimizer_max = collection_finite_and_abs_max(optimizer_tensors)
        gradient_norm = None
        if gradients:
            candidate = collection_l2_norm(gradients)
            if np.isfinite(candidate):
                gradient_norm = candidate
        return {
            "loss": current_loss,
            "grad_scaler_scale": float(scaler.get_scale()),
            "gradient_norm": gradient_norm,
            "gradient_abs_max_finite_values": gradient_max,
            "gradients_finite": gradients_finite,
            "parameter_abs_max_finite_values": parameter_max,
            "parameters_finite": parameters_finite,
            "optimizer_state_abs_max_finite_values": optimizer_max,
            "optimizer_state_finite": optimizer_finite,
        }

    def write_metrics():
        if not metrics:
            return
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=metrics[0].keys())
            writer.writeheader()
            writer.writerows(metrics)
        history_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        if stability_path is not None:
            stability_path.parent.mkdir(parents=True, exist_ok=True)
            with stability_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=metrics[0].keys())
                writer.writeheader()
                writer.writerows(metrics)
    reset_peak_memory()
    run_started = time.perf_counter()
    global_step = 0
    last_gradient_norm = None
    write_status("INITIALIZING", epoch=start_epoch - 1, step=0, last_checkpoint=str(resume) if resume else None)
    for epoch in range(start_epoch, epochs + 1):
        epoch_started = time.perf_counter()
        epoch_activation_stats.clear()
        model.train()
        total = n = 0
        epoch_gradient_abs_max = 0.0
        epoch_gradient_norm_max = 0.0
        epoch_gradient_norm_sum = 0.0
        epoch_gradient_norm_count = 0
        opt.zero_grad(set_to_none=True)
        for step, (x, y) in enumerate(train_loader, start=1):
            global_step += 1
            if step == 1 or step % 100 == 0:
                write_status("TRAINING", epoch=epoch, step=step, train_loss=(total / n if n else None),
                             validation_loss=None, BPB=None, elapsed_seconds=time.perf_counter()-run_started,
                             ETA=None, GPU=str(device), VRAM=gpu_memory_stats(), last_checkpoint=str(latest_path))
            x = x.to(device, non_blocking=pin)
            y = y.to(device, non_blocking=pin)
            try:
                with _autocast(device, use_amp):
                    logits, _ = model(x)
                    loss = criterion(logits.reshape(-1, 256), y.reshape(-1)) / max(1, grad_accum)
            except FloatingPointError as exc:
                write_status("FAILED", epoch=epoch, step=step, train_loss=None,
                             validation_loss=None, BPB=None,
                             elapsed_seconds=time.perf_counter()-run_started, ETA=None,
                             GPU=str(device), VRAM=gpu_memory_stats(),
                             last_checkpoint=str(latest_path),
                             exception_type=type(exc).__name__, exception=str(exc),
                             **failure_snapshot(),
                             activation_max_by_layer={str(layer): float(epoch_activation_stats.get((layer, "residual_ffn"), {"abs_max": torch.zeros((), device=device)})["abs_max"].item()) for layer in range(cfg.num_layers)})
                raise
            if not torch.isfinite(loss):
                write_status("FAILED", epoch=epoch, step=step, train_loss=None,
                             validation_loss=None, BPB=None,
                             elapsed_seconds=time.perf_counter()-run_started, ETA=None,
                             GPU=str(device), VRAM=gpu_memory_stats(),
                             last_checkpoint=str(latest_path),
                             exception_type="FloatingPointError",
                             exception="non-finite training loss", **failure_snapshot())
                raise FloatingPointError(f"non-finite training loss at epoch {epoch}, step {step}")
            try:
                scaler.scale(loss).backward()
                if step % max(1, grad_accum) == 0:
                    scaler.unscale_(opt)
                    trainable = model.module if hasattr(model, "module") else model
                    if numerical_debug:
                        require_finite_gradients(trainable, epoch, step)
                    gradients = [parameter.grad for parameter in trainable.parameters() if parameter.grad is not None]
                    step_gradient_abs_max = _collection_abs_max(gradients, device)
                    epoch_gradient_abs_max = max(epoch_gradient_abs_max, step_gradient_abs_max)
                    grad_norm = nn.utils.clip_grad_norm_(trainable.parameters(), 1.0)
                    last_gradient_norm = float(grad_norm.detach().item())
                    epoch_gradient_norm_max = max(epoch_gradient_norm_max, last_gradient_norm)
                    epoch_gradient_norm_sum += last_gradient_norm
                    epoch_gradient_norm_count += 1
                    if numerical_debug:
                        require_finite(grad_norm,"total_gradient_norm",epoch,global_step)
                        require_finite_gradients(trainable, epoch, step, "clipped_gradient")
                    scaler.step(opt)
                    scaler.update()
                    if numerical_debug:
                        for name,parameter in trainable.named_parameters():
                            require_finite(parameter,f"parameter:{name}",epoch,step)
                        require_finite_optimizer_state(opt, epoch, step)
                    opt.zero_grad(set_to_none=True)
            except FloatingPointError as exc:
                current_loss = float(loss.detach().item()) if bool(torch.isfinite(loss.detach()).item()) else None
                write_status("FAILED", epoch=epoch, step=step, train_loss=(total / n if n else None),
                             validation_loss=None, BPB=None,
                             elapsed_seconds=time.perf_counter()-run_started, ETA=None,
                             GPU=str(device), VRAM=gpu_memory_stats(), last_checkpoint=str(latest_path),
                             exception_type=type(exc).__name__, exception=str(exc),
                             **failure_snapshot(current_loss))
                raise
            count = int((y != -100).sum().item())
            total += float(loss.detach().item()) * max(1, grad_accum) * count
            n += count
        write_status("VALIDATING", epoch=epoch, step=step, train_loss=(total / max(1, n)),
                     validation_loss=None, BPB=None, elapsed_seconds=time.perf_counter()-run_started,
                     ETA=None, GPU=str(device), VRAM=gpu_memory_stats(), last_checkpoint=str(latest_path))
        model.eval()
        vt = vn = 0
        with torch.inference_mode():
            for x, y in val_loader:
                x = x.to(device, non_blocking=pin)
                y = y.to(device, non_blocking=pin)
                try:
                    with _autocast(device, use_amp):
                        logits, _ = model(x)
                        loss = criterion(logits.reshape(-1, 256), y.reshape(-1))
                except FloatingPointError as exc:
                    write_status("FAILED", epoch=epoch, step=0, train_loss=total/max(1,n),
                                 validation_loss=None, BPB=None,
                                 elapsed_seconds=time.perf_counter()-run_started, ETA=None,
                                 GPU=str(device), VRAM=gpu_memory_stats(),
                                 last_checkpoint=str(latest_path),
                                 exception_type=type(exc).__name__, exception=str(exc),
                                 **failure_snapshot())
                    raise
                if not torch.isfinite(loss):
                    write_status("FAILED", epoch=epoch, step=0, train_loss=total/max(1,n),
                                 validation_loss=None, BPB=None,
                                 elapsed_seconds=time.perf_counter()-run_started, ETA=None,
                                 GPU=str(device), VRAM=gpu_memory_stats(),
                                 last_checkpoint=str(latest_path),
                                 exception_type="FloatingPointError",
                                 exception="non-finite validation loss", **failure_snapshot())
                    raise FloatingPointError(f"non-finite validation loss at epoch {epoch}")
                count = int((y != -100).sum().item())
                vt += float(loss.detach().item()) * count
                vn += count
        tr = total / max(1, n)
        va = vt / max(1, vn)
        scheduler.step(va)
        gpu = gpu_memory_stats()
        gpu_utilization = None
        if str(device).startswith("cuda"):
            try:
                value = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, check=True).stdout.splitlines()[0]
                gpu_utilization = float(value.strip())
            except (OSError, subprocess.SubprocessError, IndexError, ValueError):
                pass
        epoch_seconds = time.perf_counter() - epoch_started
        elapsed_seconds = time.perf_counter() - run_started
        trainable = model.module if hasattr(model, "module") else model
        parameter_abs_max = _collection_abs_max(trainable.parameters(), device)
        optimizer_tensors = [value for state in opt.state.values() for value in state.values() if torch.is_tensor(value)]
        optimizer_state_abs_max = _collection_abs_max(optimizer_tensors, device)
        activation_fields = {}
        for layer in range(cfg.num_layers):
            block_maxima = []
            for stage in sorted(observed_block_stages):
                stats = epoch_activation_stats.get((layer, stage))
                prefix = f"block_{layer}_{stage}"
                if stats is None:
                    activation_fields[f"{prefix}_abs_max"] = 0.0
                    activation_fields[f"{prefix}_rms"] = 0.0
                    continue
                block_maxima.append(stats["abs_max"])
                activation_fields[f"{prefix}_abs_max"] = float(stats["abs_max"].item())
                activation_fields[f"{prefix}_rms"] = float(torch.sqrt(stats["sum_squares"] / max(1, stats["numel"])).item())
            # Diagnostic tensors can originate from different devices during
            # a CUDA train/validation boundary.  Aggregate scalar observations
            # on the host instead of stacking device tensors.  This does not
            # affect the model, loss, gradients, or optimizer.
            activation_fields[f"block_{layer}_activation_abs_max"] = aggregate_diagnostic_scalars(block_maxima)
            activation_fields[f"max_activation_layer_{layer}"] = activation_fields[f"block_{layer}_residual_ffn_abs_max"]
            activation_fields[f"block_{layer}_ffn_input_rms"] = activation_fields[f"block_{layer}_ffn_normalized_input_rms"]
            activation_fields[f"block_{layer}_ffn_hidden_rms"] = activation_fields[f"block_{layer}_ffn_gated_product_rms"]
        logits_stats = epoch_activation_stats.get((None, "output_logits"))
        embedding_stats = epoch_activation_stats.get((None, "embedding"))
        row = {
            "epoch": epoch,
            "train_cross_entropy": tr,
            "val_cross_entropy": va,
            "val_bpb_estimate": float(va / np.log(2)),
            "learning_rate": opt.param_groups[0]["lr"],
            "grad_scaler_scale": float(scaler.get_scale()),
            "gradient_norm": last_gradient_norm,
            "gradient_norm_epoch_max": epoch_gradient_norm_max,
            "gradient_norm_epoch_mean": epoch_gradient_norm_sum / max(1, epoch_gradient_norm_count),
            "gradient_abs_max": epoch_gradient_abs_max,
            "parameter_abs_max": parameter_abs_max,
            "optimizer_state_abs_max": optimizer_state_abs_max,
            "logits_abs_max": float(logits_stats["abs_max"].item()) if logits_stats else 0.0,
            "embedding_activation_abs_max": float(embedding_stats["abs_max"].item()) if embedding_stats else 0.0,
            "embedding_parameter_abs_max": float(trainable.embedding.weight.detach().float().abs().max().item()) if hasattr(trainable, "embedding") else 0.0,
            "vram_max_bytes": gpu.get("max_allocated_bytes", 0.0),
            "vram_allocated_bytes": gpu.get("allocated_bytes", 0.0),
            "vram_reserved_bytes": gpu.get("reserved_bytes", 0.0),
            "gpu_utilization_percent": gpu_utilization,
            "samples_per_second": len(train_ds) / max(epoch_seconds, 1e-9),
            "epoch_seconds": epoch_seconds,
            "elapsed_seconds": elapsed_seconds,
            "eta_seconds": (elapsed_seconds / max(1, epoch - start_epoch + 1)) * max(0, epochs - epoch),
            **activation_fields,
        }
        metrics.append(row)
        print(row)
        core = model.module if hasattr(model, "module") else model
        tracked = {**row, "best_validation_cross_entropy": min(best, va), "best_validation_bpb": min(best, va) / np.log(2)}
        write_status("SAVING", epoch=epoch, step=step, train_loss=tr, validation_loss=va,
                     BPB=row["val_bpb_estimate"], elapsed_seconds=elapsed_seconds,
                     ETA=row["eta_seconds"], GPU=str(device), VRAM=gpu, last_checkpoint=str(latest_path))
        save_checkpoint(latest_path, core, opt, epoch, {**tracked, "checkpoint_role": "latest"}, scaler=scaler if use_amp else None, scheduler=scheduler)
        if checkpoint_every > 0 and epoch % checkpoint_every == 0:
            periodic = output_path.with_name(f"{output_path.stem}.epoch-{epoch:04d}{output_path.suffix}")
            save_checkpoint(periodic, core, opt, epoch, {**tracked, "checkpoint_role": "periodic"}, scaler=scaler if use_amp else None, scheduler=scheduler)
            periodic_files = sorted(output_path.parent.glob(f"{output_path.stem}.epoch-*{output_path.suffix}"), key=lambda p:p.stat().st_mtime, reverse=True)
            for expired in periodic_files[max(0, int(max_periodic_checkpoints)):]:
                expired.unlink()
        write_metrics()
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
                    "best_validation_cross_entropy": va,
                    "best_validation_bpb": float(va / np.log(2)),
                    "parameter_count": sum(p.numel() for p in core.parameters()),
                    "train_dataset": train_ds.summary,
                    "validation_dataset": val_ds.summary,
                    "train_files": len(train_paths),
                    "validation_files": len(val_paths),
                },
                scaler=scaler if use_amp else None,
                scheduler=scheduler,
            )
        else:
            stale += 1
            if stale >= patience:
                write_status("EARLY_STOPPED", epoch=epoch, step=step, train_loss=tr, validation_loss=va,
                             BPB=row["val_bpb_estimate"], elapsed_seconds=elapsed_seconds,
                             ETA=0, GPU=str(device), VRAM=gpu, last_checkpoint=str(latest_path))
                break
    write_metrics()
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
    if not (status_path and status_path.exists() and json.loads(status_path.read_text()).get("status") == "EARLY_STOPPED"):
        write_status("COMPLETED", epoch=metrics[-1]["epoch"] if metrics else start_epoch-1, step=0,
                     train_loss=metrics[-1]["train_cross_entropy"] if metrics else None,
                     validation_loss=metrics[-1]["val_cross_entropy"] if metrics else None,
                     BPB=metrics[-1]["val_bpb_estimate"] if metrics else None,
                     elapsed_seconds=time.perf_counter()-run_started, ETA=0, GPU=str(device),
                     VRAM=gpu_memory_stats(), last_checkpoint=str(latest_path))
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
    parser.add_argument("--early-stopping-patience", type=int, default=5)
    parser.add_argument("--checkpoint-every", type=int, default=5)
    parser.add_argument("--max-periodic-checkpoints", type=int, default=3)
    parser.add_argument("--status-path")
    parser.add_argument("--stability-output")
    parser.add_argument("--numerical-debug", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--amp-initial-scale", type=float, default=65536.0)
    parser.add_argument("--amp-growth-interval", type=int, default=2000)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    train(**vars(args))


if __name__ == "__main__":
    main()
