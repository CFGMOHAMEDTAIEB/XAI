from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any

import torch

from ...checkpoint import load_checkpoint, model_fingerprint
from ...entropy.quant import logits_to_cumulative
from ...entropy.rans import RANSDecoder, RANSEncoder
from ...model import BOS_TOKEN
from .base import CodecAdapter, CodecError, CodecResult


class ModelRegistry:
    """Lazy process-local singleton cache used only when a neural strategy wins."""

    _lock = threading.Lock()
    _models: dict[tuple[str, str], tuple[Any, dict, float]] = {}

    @classmethod
    def get(cls, checkpoint: str | Path, device: str = "cpu") -> tuple[Any, dict, float, bool]:
        path = str(Path(checkpoint).resolve())
        key = (path, device)
        with cls._lock:
            if key in cls._models:
                model, obj, load_seconds = cls._models[key]
                return model, obj, load_seconds, False
            started = time.perf_counter()
            model, obj = load_checkpoint(path, device)
            load_seconds = time.perf_counter() - started
            cls._models[key] = (model, obj, load_seconds)
            return model, obj, load_seconds, True

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._models.clear()


class NeuralRansCodec(CodecAdapter):
    def __init__(self, codec_id: str, checkpoint: str | Path, expected_architecture: str, device: str = "cpu"):
        self.codec_id = codec_id
        self.checkpoint = Path(checkpoint)
        self.expected_architecture = expected_architecture
        self.device = device

    def available(self) -> bool:
        return self.checkpoint.is_file()

    def available_levels(self) -> tuple[None, ...]:
        return (None,)

    def _model(self) -> tuple[Any, dict, float, bool]:
        if not self.available():
            raise CodecError(f"missing neural checkpoint: {self.checkpoint}")
        model, obj, load_seconds, cold = ModelRegistry.get(self.checkpoint, self.device)
        if model.config.architecture_id != self.expected_architecture:
            raise CodecError(
                f"checkpoint architecture {model.config.architecture_id!r} != {self.expected_architecture!r}"
            )
        return model, obj, load_seconds, cold

    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        model, _, load_seconds, cold = self._model()
        encoder = RANSEncoder()
        hidden = None
        previous = BOS_TOKEN
        with torch.inference_mode():
            model.eval()
            for symbol in data:
                logits, hidden = model.step(previous, hidden)
                encoder.write_fast(logits_to_cumulative(logits), symbol)
                previous = symbol
        return CodecResult(
            encoder.finish(),
            {
                "level": None,
                "coder": "rans14-v1",
                "original_size": len(data),
                "model_fingerprint": model_fingerprint(model),
                "architecture_id": model.config.architecture_id,
                "checkpoint_load_seconds": load_seconds if cold else 0.0,
                "checkpoint_cache": "cold" if cold else "warm",
            },
        )

    def decompress(self, data: bytes, metadata: dict) -> bytes:
        model, _, _, _ = self._model()
        if metadata.get("model_fingerprint") != model_fingerprint(model):
            raise CodecError("neural model fingerprint mismatch")
        size = metadata.get("original_size")
        if not isinstance(size, int) or size < 0:
            raise CodecError("neural chunk missing original_size")
        decoder = RANSDecoder(data)
        hidden = None
        previous = BOS_TOKEN
        out = bytearray()
        with torch.inference_mode():
            model.eval()
            for _ in range(size):
                logits, hidden = model.step(previous, hidden)
                symbol = decoder.read_fast(logits_to_cumulative(logits))
                out.append(symbol)
                previous = symbol
        return bytes(out)
