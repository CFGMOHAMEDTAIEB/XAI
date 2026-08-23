from __future__ import annotations
import os, tempfile
from pathlib import Path
from .arithmetic import ArithmeticEncoder, ArithmeticDecoder, AdaptiveByteModel, CodecError
from .format import pack_container, unpack_container, sha256, FormatError

CODER_VERSION = "arithmetic32-v1"
NEURAL_TOTAL = 16384

class CompressionError(ValueError): pass

def logits_to_cumulative(logits, total=NEURAL_TOTAL) -> list[int]:
    import torch
    if logits.numel() != 256: raise CompressionError("neural model must output 256 logits")
    probs = torch.softmax(logits.detach().to(dtype=torch.float64, device="cpu"), dim=-1).numpy()
    if not (probs == probs).all(): raise CompressionError("non-finite model probabilities")
    # Largest-remainder allocation with one count reserved for every symbol.
    remaining = total - 256
    raw = probs * remaining
    base = raw.astype("int64")
    freq = base + 1
    left = total - int(freq.sum())
    fractions = raw - base
    order = sorted(range(256), key=lambda i: (-float(fractions[i]), i))
    for i in order[:left]: freq[i] += 1
    cum = [0]; running = 0
    for f in freq.tolist(): running += int(f); cum.append(running)
    if running != total: raise CompressionError("frequency quantization error")
    return cum

def _encode_static(data: bytes) -> bytes:
    enc = ArithmeticEncoder(); model = AdaptiveByteModel()
    for symbol in data:
        enc.write(model.cumulative(), symbol); model.update(symbol)
    return enc.finish()

def _decode_static(payload: bytes, size: int) -> bytes:
    dec = ArithmeticDecoder(payload); model = AdaptiveByteModel(); out = bytearray()
    for _ in range(size):
        symbol = dec.read(model.cumulative()); out.append(symbol); model.update(symbol)
    return bytes(out)

def _encode_neural(data: bytes, checkpoint: str):
    import torch
    from .checkpoint import load_checkpoint, model_fingerprint
    from .model import BOS_TOKEN
    model, _ = load_checkpoint(checkpoint, "cpu"); enc = ArithmeticEncoder(); hidden = None; prev = BOS_TOKEN
    with torch.inference_mode():
        for symbol in data:
            logits, hidden = model.step(prev, hidden); enc.write(logits_to_cumulative(logits), symbol); prev = symbol
    return enc.finish(), model_fingerprint(model), model.config.__dict__

def _decode_neural(payload: bytes, size: int, checkpoint: str, expected_fp: str) -> bytes:
    import torch
    from .checkpoint import load_checkpoint, model_fingerprint, CheckpointError
    from .model import BOS_TOKEN
    model, _ = load_checkpoint(checkpoint, "cpu")
    if model_fingerprint(model) != expected_fp: raise CheckpointError("wrong checkpoint for this artifact")
    dec = ArithmeticDecoder(payload); hidden = None; prev = BOS_TOKEN; out = bytearray()
    with torch.inference_mode():
        for _ in range(size):
            logits, hidden = model.step(prev, hidden); symbol = dec.read(logits_to_cumulative(logits)); out.append(symbol); prev = symbol
    return bytes(out)

def compress_bytes(data: bytes, mode="static", checkpoint=None) -> bytes:
    if not isinstance(data, (bytes, bytearray)): raise TypeError("data must be bytes")
    data = bytes(data); metadata = {"mode":mode,"coder_version":CODER_VERSION,"original_size":len(data),"original_sha256":sha256(data)}
    if mode == "static": payload = _encode_static(data)
    elif mode == "neural":
        if not checkpoint: raise CompressionError("neural mode requires --checkpoint")
        payload, fp, cfg = _encode_neural(data, checkpoint); metadata.update({"model_fingerprint":fp,"model_config":cfg})
    else: raise CompressionError("mode must be static or neural")
    return pack_container(metadata, payload)

def decompress_bytes(blob: bytes, checkpoint=None, max_output_size=8 << 30) -> bytes:
    md, payload = unpack_container(blob, max_output_size=max_output_size)
    if md["coder_version"] != CODER_VERSION: raise CompressionError("unsupported coder version")
    if md["mode"] == "static": data = _decode_static(payload, md["original_size"])
    elif md["mode"] == "neural":
        if not checkpoint: raise CompressionError("neural artifact requires a checkpoint")
        data = _decode_neural(payload, md["original_size"], checkpoint, md.get("model_fingerprint", ""))
    else: raise CompressionError("unsupported coding mode")
    if len(data) != md["original_size"]: raise CompressionError("decoded size mismatch")
    if sha256(data) != md["original_sha256"]: raise CompressionError("reconstructed SHA-256 mismatch")
    return data

def compress_file(input_path, output_path, mode="static", checkpoint=None, overwrite=False):
    src, dst = Path(input_path), Path(output_path)
    if not src.is_file(): raise FileNotFoundError(src)
    if dst.exists() and not overwrite: raise FileExistsError(dst)
    blob = compress_bytes(src.read_bytes(), mode=mode, checkpoint=checkpoint)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=dst.name+".", suffix=".tmp", dir=str(dst.parent)); os.close(fd)
    try:
        Path(tmp).write_bytes(blob); os.replace(tmp, dst)
    except Exception:
        Path(tmp).unlink(missing_ok=True); raise
    return {"original_size":src.stat().st_size,"artifact_size":len(blob),"mode":mode}

def decompress_file(input_path, output_path, checkpoint=None, overwrite=False, max_output_size=8 << 30):
    src, dst = Path(input_path), Path(output_path)
    if not src.is_file(): raise FileNotFoundError(src)
    if dst.exists() and not overwrite: raise FileExistsError(dst)
    data = decompress_bytes(src.read_bytes(), checkpoint=checkpoint, max_output_size=max_output_size)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=dst.name+".", suffix=".tmp", dir=str(dst.parent)); os.close(fd)
    try:
        Path(tmp).write_bytes(data); os.replace(tmp, dst)
    except Exception:
        Path(tmp).unlink(missing_ok=True); raise
    return {"restored_size":len(data),"sha256":sha256(data)}
