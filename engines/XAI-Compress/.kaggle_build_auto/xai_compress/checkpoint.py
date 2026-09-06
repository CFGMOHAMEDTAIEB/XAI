from __future__ import annotations

import hashlib
import json
import os
import tempfile
import random
from pathlib import Path

import torch

from .model import ModelConfig
from .models.registry import build_model

class CheckpointError(ValueError):
    pass


def _tensor_bytes(t):
    return t.detach().cpu().contiguous().numpy().tobytes()


def _fingerprint_config(config) -> dict:
    data = dict(config.__dict__)
    arch = data.get("architecture_id", "causal-byte-gru-v1")
    if arch in ("causal-byte-gru-v1", "gru"):
        keys = ("embedding_dim", "hidden_dim", "num_layers", "context_length", "dropout", "architecture_id")
        return {k: data[k] for k in keys if k in data}
    # Preserve fingerprints of V2 checkpoints created before residual scaling
    # became an explicitly configurable, opt-in candidate dimension.
    if float(data.get("residual_scale", 1.0)) == 1.0:
        data.pop("residual_scale", None)
    return data


def model_fingerprint(model) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(_fingerprint_config(model.config), sort_keys=True, separators=(",", ":")).encode())
    for name, tensor in sorted(model.state_dict().items()):
        h.update(name.encode())
        h.update(str(tensor.dtype).encode())
        h.update(str(tuple(tensor.shape)).encode())
        h.update(_tensor_bytes(tensor))
    return h.hexdigest()


def save_checkpoint(path, model, optimizer=None, epoch=0, metrics=None, scaler=None, scheduler=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    core = model.module if hasattr(model, "module") else model
    obj = {
        "format": "xai-compress-checkpoint-v1",
        "config": core.config.__dict__,
        "state_dict": core.state_dict(),
        "fingerprint": model_fingerprint(core),
        "epoch": epoch,
        "metrics": metrics or {},
        "rng_state": {
            "python": random.getstate(),
            "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
        },
    }
    if optimizer is not None:
        obj["optimizer_state"] = optimizer.state_dict()
    if scaler is not None:
        obj["scaler_state"] = scaler.state_dict()
    if scheduler is not None:
        obj["scheduler_state"] = scheduler.state_dict()
    # Never replace a known-good checkpoint with a partial write.  Keep the
    # temporary file on the same filesystem so os.replace remains atomic.
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            torch.save(obj, handle)
            handle.flush()
            os.fsync(handle.fileno())
        if os.path.getsize(temporary) <= 0:
            raise CheckpointError("checkpoint temporary file is empty")
        load_checkpoint(temporary, "cpu")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_checkpoint(path, device="cpu"):
    path = Path(path)
    if not path.is_file():
        raise CheckpointError(f"checkpoint not found: {path}")
    try:
        obj = torch.load(path, map_location=device, weights_only=False)
    except Exception as e:
        raise CheckpointError(f"cannot load checkpoint: {e}") from e
    if obj.get("format") != "xai-compress-checkpoint-v1":
        raise CheckpointError("unsupported checkpoint format")
    try:
        raw = dict(obj["config"])
        fields = ModelConfig.__dataclass_fields__
        config = ModelConfig(**{k: v for k, v in raw.items() if k in fields})
        model = build_model(config)
        model.load_state_dict(obj["state_dict"], strict=True)
    except Exception as e:
        raise CheckpointError(f"incompatible checkpoint: {e}") from e
    actual = model_fingerprint(model)
    if actual != obj.get("fingerprint"):
        raise CheckpointError("checkpoint fingerprint mismatch")
    model.to(device)
    model.eval()
    return model, obj
