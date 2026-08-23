from __future__ import annotations
import hashlib, json
from pathlib import Path
import torch
from .model import CausalByteGRU, ModelConfig

class CheckpointError(ValueError): pass

def _tensor_bytes(t): return t.detach().cpu().contiguous().numpy().tobytes()

def model_fingerprint(model: CausalByteGRU) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(model.config.__dict__, sort_keys=True, separators=(",", ":")).encode())
    for name, tensor in sorted(model.state_dict().items()):
        h.update(name.encode()); h.update(str(tensor.dtype).encode()); h.update(str(tuple(tensor.shape)).encode()); h.update(_tensor_bytes(tensor))
    return h.hexdigest()

def save_checkpoint(path, model, optimizer=None, epoch=0, metrics=None):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    obj = {"format":"xai-compress-checkpoint-v1", "config":model.config.__dict__, "state_dict":model.state_dict(),
           "fingerprint":model_fingerprint(model), "epoch":epoch, "metrics":metrics or {}}
    if optimizer is not None: obj["optimizer_state"] = optimizer.state_dict()
    torch.save(obj, path)

def load_checkpoint(path, device="cpu"):
    path = Path(path)
    if not path.is_file(): raise CheckpointError(f"checkpoint not found: {path}")
    try: obj = torch.load(path, map_location=device, weights_only=False)
    except Exception as e: raise CheckpointError(f"cannot load checkpoint: {e}") from e
    if obj.get("format") != "xai-compress-checkpoint-v1": raise CheckpointError("unsupported checkpoint format")
    try: config = ModelConfig(**obj["config"]); model = CausalByteGRU(config); model.load_state_dict(obj["state_dict"], strict=True)
    except Exception as e: raise CheckpointError(f"incompatible checkpoint: {e}") from e
    actual = model_fingerprint(model)
    if actual != obj.get("fingerprint"): raise CheckpointError("checkpoint fingerprint mismatch")
    model.to(device); model.eval()
    return model, obj
