from __future__ import annotations

import os
import struct
import tempfile
import zlib
from pathlib import Path
from typing import Iterable, Iterator

from .analyzer import analyze_block, choose_strategy
from .arithmetic import AdaptiveByteModel, ArithmeticDecoder, ArithmeticEncoder, CodecError
from .entropy.quant import NEURAL_TOTAL, logits_batch_to_cumulative, logits_to_cumulative
from .entropy.rans import RANSDecoder, RANSEncoder
from .format import pack_container, sha256, unpack_container, FormatError
from .utils.device import select_device

CODER_VERSION = "arithmetic32-v1"
CODER_RANS = "rans14-v1"
CHUNK_HEADER = struct.Struct(">BII")  # codec_id, raw_len, payload_len

CODEC_STORE = 0
CODEC_STATIC_AC = 1
CODEC_NEURAL_AC = 2
CODEC_ZLIB = 3
CODEC_NEURAL_RANS = 5

DEFAULT_CHUNK = 1 << 16


class CompressionError(ValueError):
    pass


def _encode_static(data: bytes) -> bytes:
    enc = ArithmeticEncoder()
    model = AdaptiveByteModel()
    for symbol in data:
        enc.write(model.cumulative(), symbol)
        model.update(symbol)
    return enc.finish()


def _decode_static(payload: bytes, size: int) -> bytes:
    dec = ArithmeticDecoder(payload)
    model = AdaptiveByteModel()
    out = bytearray()
    for _ in range(size):
        symbol = dec.read(model.cumulative())
        out.append(symbol)
        model.update(symbol)
    return bytes(out)


def _is_gru(model) -> bool:
    return "gru" in str(getattr(model.config, "architecture_id", ""))


def _neural_block_logits(model, data: bytes, start: int, length: int, hidden):
    from .model import BOS_TOKEN

    block = data[start : start + length]
    if _is_gru(model):
        prev = BOS_TOKEN if start == 0 else data[start - 1]
        return model.predict_block(block, prev_token=prev, hidden=hidden)
    ctx = int(model.config.context_length)
    cs = max(0, start - (ctx - 1))
    device = next(model.parameters()).device
    if cs == 0:
        tokens = [BOS_TOKEN] + list(data[0 : start + length - 1])
        offset = start
    else:
        tokens = list(data[cs - 1 : start + length - 1])
        offset = start - cs
    import torch

    x = torch.as_tensor(tokens, dtype=torch.long, device=device)
    logits, _ = model.forward_sequence(x, None)
    return logits[offset : offset + length], hidden


def _write_symbols(encoder, tables: list[list[int]], data: bytes, start: int) -> None:
    for j, table in enumerate(tables):
        encoder.write_fast(table, data[start + j])


def _encode_neural(data: bytes, checkpoint: str, block_size: int = 4096, device: str | None = None, coder: str = "arithmetic"):
    import torch

    from .checkpoint import load_checkpoint, model_fingerprint

    device = select_device(device)
    model, _ = load_checkpoint(checkpoint, device)
    Encoder = RANSEncoder if coder == "rans" else ArithmeticEncoder
    enc = Encoder()
    hidden = None
    with torch.inference_mode():
        model.eval()
        if _is_gru(model):
            # Decoder inference is necessarily autoregressive. Use the exact
            # same GRU step path here: fused sequence kernels can differ by a
            # few floating-point bits and cross deterministic quantization
            # boundaries on longer streams.
            from .model import BOS_TOKEN
            previous = BOS_TOKEN
            for symbol in data:
                logits, hidden = model.step(previous, hidden)
                enc.write_fast(logits_to_cumulative(logits), symbol)
                previous = symbol
        else:
            # Entropy decoding is autoregressive. Generate transformer tables
            # with the exact same incremental KV-cache path so bounded context
            # and positional rollover cannot diverge from the decoder.
            from .model import BOS_TOKEN

            previous = BOS_TOKEN
            for symbol in data:
                logits, hidden = model.step(previous, hidden)
                enc.write_fast(logits_to_cumulative(logits), symbol)
                previous = symbol
    return enc.finish(), model_fingerprint(model), model.config.__dict__


def _decode_neural(payload: bytes, size: int, checkpoint: str, expected_fp: str, device: str | None = None, coder: str = "arithmetic") -> bytes:
    import torch

    from .checkpoint import CheckpointError, load_checkpoint, model_fingerprint
    from .model import BOS_TOKEN

    device = select_device(device)
    model, _ = load_checkpoint(checkpoint, device)
    if model_fingerprint(model) != expected_fp:
        raise CheckpointError("wrong checkpoint for this artifact")
    Decoder = RANSDecoder if coder == "rans" else ArithmeticDecoder
    dec = Decoder(payload)
    hidden = None
    prev = BOS_TOKEN
    out = bytearray()
    with torch.inference_mode():
        model.eval()
        for _ in range(size):
            logits, hidden = model.step(prev, hidden)
            table = logits_to_cumulative(logits)
            symbol = dec.read_fast(table)
            out.append(symbol)
            prev = symbol
    return bytes(out)


def _pack_chunk(codec_id: int, raw: bytes, payload: bytes) -> bytes:
    return CHUNK_HEADER.pack(codec_id, len(raw), len(payload)) + payload


def _iter_chunks(data: bytes, chunk_size: int) -> Iterator[bytes]:
    if chunk_size <= 0:
        raise CompressionError("chunk_size must be positive")
    if not data:
        yield b""
        return
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]


def _iter_file_chunks(path: Path, chunk_size: int) -> Iterator[bytes]:
    with path.open("rb", buffering=1024 * 1024) as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            yield block


def _encode_chunk(block: bytes, strategy: str, neural_state: dict | None, coder: str) -> bytes:
    if not block or strategy == "store":
        return _pack_chunk(CODEC_STORE, block, block)
    if strategy == "zlib":
        payload = zlib.compress(block, 9)
        if len(payload) >= len(block):
            return _pack_chunk(CODEC_STORE, block, block)
        return _pack_chunk(CODEC_ZLIB, block, payload)
    if strategy == "static":
        return _pack_chunk(CODEC_STATIC_AC, block, _encode_static(block))
    if strategy == "neural":
        if not neural_state:
            raise CompressionError("neural chunk requires a checkpoint")
        payload, fp, cfg = _encode_neural(block, neural_state["checkpoint"], neural_state.get("block_size", 4096), neural_state.get("device"), coder)
        neural_state["fingerprint"] = fp
        neural_state["config"] = cfg
        codec = CODEC_NEURAL_RANS if coder == "rans" else CODEC_NEURAL_AC
        packed = _pack_chunk(codec, block, payload)
        if len(packed) >= 1 + 8 + len(block) and len(payload) >= len(block):
            z = zlib.compress(block, 9)
            if len(z) < len(payload):
                return _pack_chunk(CODEC_ZLIB if len(z) < len(block) else CODEC_STORE, block, z if len(z) < len(block) else block)
        return packed
    raise CompressionError(f"unknown strategy {strategy}")


def _decode_chunk(codec_id: int, raw_len: int, payload: bytes, checkpoint: str | None, expected_fp: str, device: str | None) -> bytes:
    if codec_id == CODEC_STORE:
        if len(payload) != raw_len:
            raise CompressionError("store chunk length mismatch")
        return payload
    if codec_id == CODEC_ZLIB:
        data = zlib.decompress(payload)
        if len(data) != raw_len:
            raise CompressionError("zlib chunk length mismatch")
        return data
    if codec_id == CODEC_STATIC_AC:
        return _decode_static(payload, raw_len)
    if codec_id == CODEC_NEURAL_AC:
        if not checkpoint:
            raise CompressionError("neural artifact requires a checkpoint")
        return _decode_neural(payload, raw_len, checkpoint, expected_fp, device, coder="arithmetic")
    if codec_id == CODEC_NEURAL_RANS:
        if not checkpoint:
            raise CompressionError("neural artifact requires a checkpoint")
        return _decode_neural(payload, raw_len, checkpoint, expected_fp, device, coder="rans")
    raise CompressionError(f"unsupported chunk codec {codec_id}")


def _parse_chunks(payload: bytes) -> Iterable[tuple[int, int, bytes]]:
    pos = 0
    n = len(payload)
    while pos < n:
        if pos + CHUNK_HEADER.size > n:
            raise CompressionError("truncated chunk header")
        codec_id, raw_len, comp_len = CHUNK_HEADER.unpack_from(payload, pos)
        pos += CHUNK_HEADER.size
        if pos + comp_len > n:
            raise CompressionError("truncated chunk payload")
        yield codec_id, raw_len, payload[pos : pos + comp_len]
        pos += comp_len


def _encode_hybrid(data: bytes, checkpoint: str | None, chunk_size: int, device: str | None, coder: str) -> tuple[bytes, dict]:
    neural_state = {"checkpoint": checkpoint, "device": device, "block_size": 4096} if checkpoint else None
    out = bytearray()
    used = set()
    for block in _iter_chunks(data, chunk_size):
        strategy = choose_strategy(block, neural_available=bool(checkpoint))
        if strategy == "neural" and not checkpoint:
            strategy = "zlib"
        used.add(strategy)
        out += _encode_chunk(block, strategy, neural_state, coder)
    extra = {"payload_layout": "chunks-v1", "chunk_size": chunk_size, "strategies": sorted(used)}
    if neural_state and neural_state.get("fingerprint"):
        extra["model_fingerprint"] = neural_state["fingerprint"]
        extra["model_config"] = neural_state.get("config", {})
    return bytes(out), extra


def compress_bytes(
    data: bytes,
    mode: str = "static",
    checkpoint=None,
    chunk_size: int = DEFAULT_CHUNK,
    device: str | None = None,
    coder: str = "arithmetic",
) -> bytes:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    data = bytes(data)
    metadata = {
        "mode": mode,
        "coder_version": CODER_RANS if coder == "rans" and mode != "static" else CODER_VERSION,
        "original_size": len(data),
        "original_sha256": sha256(data),
        "chunk_size": chunk_size,
    }
    format_version = 1
    if mode == "static":
        payload = _encode_static(data)
    elif mode == "neural":
        if not checkpoint:
            raise CompressionError("neural mode requires --checkpoint")
        payload, fp, cfg = _encode_neural(data, checkpoint, device=device, coder=coder)
        metadata.update({"model_fingerprint": fp, "model_config": cfg})
        if coder == "rans":
            metadata["coder_version"] = CODER_RANS
    elif mode in ("hybrid", "auto"):
        payload, extra = _encode_hybrid(data, checkpoint, chunk_size, device, coder)
        metadata.update(extra)
        metadata["mode"] = "hybrid"
        format_version = 2
        metadata["coder_version"] = CODER_RANS if coder == "rans" else CODER_VERSION
    elif mode == "zlib":
        payload = zlib.compress(data, 9)
        metadata["coder_version"] = "zlib-9"
    else:
        raise CompressionError("mode must be static, neural, hybrid, auto, or zlib")
    return pack_container(metadata, payload, format_version=format_version)


def decompress_bytes(blob: bytes, checkpoint=None, max_output_size=8 << 30, device: str | None = None) -> bytes:
    md, payload = unpack_container(blob, max_output_size=max_output_size)
    layout = md.get("payload_layout", "single")
    if layout == "chunks-v1":
        out = bytearray()
        expected_fp = md.get("model_fingerprint", "")
        for codec_id, raw_len, chunk_payload in _parse_chunks(payload):
            out += _decode_chunk(codec_id, raw_len, chunk_payload, checkpoint, expected_fp, device)
        data = bytes(out)
    elif md["mode"] == "static":
        if md["coder_version"] != CODER_VERSION:
            raise CompressionError("unsupported coder version")
        data = _decode_static(payload, md["original_size"])
    elif md["mode"] == "neural":
        if not checkpoint:
            raise CompressionError("neural artifact requires a checkpoint")
        coder = "rans" if md.get("coder_version") == CODER_RANS else "arithmetic"
        data = _decode_neural(payload, md["original_size"], checkpoint, md.get("model_fingerprint", ""), device, coder)
    elif md["mode"] == "zlib":
        data = zlib.decompress(payload)
    else:
        raise CompressionError("unsupported coding mode")
    if len(data) != md["original_size"]:
        raise CompressionError("decoded size mismatch")
    if sha256(data) != md["original_sha256"]:
        raise CompressionError("reconstructed SHA-256 mismatch")
    return data


def compress_file(input_path, output_path, mode="static", checkpoint=None, overwrite=False, chunk_size=DEFAULT_CHUNK, device=None, coder="arithmetic"):
    src, dst = Path(input_path), Path(output_path)
    if not src.is_file():
        raise FileNotFoundError(src)
    if dst.exists() and not overwrite:
        raise FileExistsError(dst)
    if chunk_size <= 0:
        raise CompressionError("chunk_size must be positive")
    size = src.stat().st_size
    from .streaming import atomic_target, write_chunk, write_footer, write_header

    neural_state = {"checkpoint": checkpoint, "device": device, "block_size": 4096} if checkpoint else None
    model_fp = ""
    model_cfg = None
    if checkpoint:
        from .checkpoint import load_checkpoint, model_fingerprint
        loaded, _ = load_checkpoint(checkpoint, select_device(device))
        model_fp = model_fingerprint(loaded)
        model_cfg = loaded.config.__dict__
    metadata = {
        "mode": "hybrid" if mode == "auto" else mode,
        "coder_version": CODER_RANS if coder == "rans" else CODER_VERSION,
        "original_size": size,
        "chunk_size": chunk_size,
        "model_fingerprint": model_fp,
        "model_config": model_cfg,
        "flags": {"chunk_context_reset": True, "optional_index": False},
    }
    tmp = atomic_target(dst)
    encoded_size = 0
    try:
        whole = __import__("hashlib").sha256()
        chunks = 0
        with src.open("rb", buffering=1024 * 1024) as source, tmp.open("wb", buffering=1024 * 1024) as target:
            encoded_size += write_header(target, metadata)
            while True:
                block = source.read(chunk_size)
                if not block:
                    break
                whole.update(block)
                if mode in ("hybrid", "auto"):
                    strategy = choose_strategy(block, neural_available=bool(checkpoint))
                else:
                    strategy = mode
                packed = _encode_chunk(block, strategy, neural_state, coder)
                codec_id, raw_len, payload_len = CHUNK_HEADER.unpack_from(packed)
                payload = packed[CHUNK_HEADER.size:]
                if raw_len != len(block) or payload_len != len(payload):
                    raise CompressionError("internal encoded chunk length mismatch")
                encoded_size += write_chunk(target, chunks, codec_id, block, payload)
                chunks += 1
            encoded_size += write_footer(target, chunks, size, whole.digest())
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return {"original_size": size, "artifact_size": encoded_size, "mode": mode, "format_version": 3, "chunks": chunks}


def decompress_file(input_path, output_path, checkpoint=None, overwrite=False, max_output_size=8 << 30, device=None):
    src, dst = Path(input_path), Path(output_path)
    if not src.is_file():
        raise FileNotFoundError(src)
    if dst.exists() and not overwrite:
        raise FileExistsError(dst)
    with src.open("rb") as probe:
        prefix = probe.read(5)
    if len(prefix) == 5 and prefix[:4] == b"XAIC" and prefix[4] == 3:
        return _decompress_stream_file(src, dst, checkpoint, overwrite, max_output_size, device)
    data = decompress_bytes(src.read_bytes(), checkpoint=checkpoint, max_output_size=max_output_size, device=device)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=dst.name + ".", suffix=".tmp", dir=str(dst.parent))
    os.close(fd)
    try:
        Path(tmp).write_bytes(data)
        os.replace(tmp, dst)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    return {"restored_size": len(data), "sha256": sha256(data)}


def _decompress_stream_file(src: Path, dst: Path, checkpoint, overwrite: bool, max_output_size: int, device):
    from .streaming import StreamingFormatError, atomic_target, read_header, read_record_header

    if dst.exists() and not overwrite:
        raise FileExistsError(dst)
    tmp = atomic_target(dst)
    total = 0
    chunk_count = 0
    whole = __import__("hashlib").sha256()
    try:
        with src.open("rb", buffering=1024 * 1024) as source, tmp.open("wb", buffering=1024 * 1024) as target:
            metadata = read_header(source)
            if metadata["original_size"] > max_output_size:
                raise CompressionError("unsafe original size")
            expected_fp = metadata.get("model_fingerprint", "")
            while True:
                kind, record = read_record_header(source)
                if kind == "footer":
                    footer_chunks, footer_size, footer_digest = record
                    break
                chunk_id, codec_id, raw_len, encoded_len, raw_digest = record
                if chunk_id != chunk_count:
                    raise StreamingFormatError("non-sequential chunk id")
                if raw_len > metadata["chunk_size"] or total + raw_len > max_output_size:
                    raise StreamingFormatError("invalid or unsafe chunk length")
                payload = source.read(encoded_len)
                if len(payload) != encoded_len:
                    raise StreamingFormatError("truncated chunk payload")
                raw = _decode_chunk(codec_id, raw_len, payload, checkpoint, expected_fp, device)
                if __import__("hashlib").sha256(raw).digest() != raw_digest:
                    raise StreamingFormatError(f"chunk {chunk_id} checksum failure")
                target.write(raw)
                whole.update(raw)
                total += len(raw)
                chunk_count += 1
            if footer_chunks != chunk_count or footer_size != total or total != metadata["original_size"]:
                raise StreamingFormatError("stream footer size/count mismatch")
            if whole.digest() != footer_digest:
                raise StreamingFormatError("whole-file checksum failure")
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return {"restored_size": total, "sha256": whole.hexdigest(), "format_version": 3, "chunks": chunk_count}
