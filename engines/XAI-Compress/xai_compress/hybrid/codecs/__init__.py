from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .base import CodecAdapter, CodecError, CodecResult, Strategy
from .classical import (
    BrotliCodec,
    Bzip2Codec,
    DeflateCodec,
    Lzma2Codec,
    RawCodec,
    XaiStaticCodec,
    ZstdCodec,
)
try:
    from .neural import ModelRegistry, NeuralRansCodec
except ImportError:  # Hybrid V3 compact routing is classical-only and can run without PyTorch.
    ModelRegistry = None
    NeuralRansCodec = None

ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=8)
def _build_registry_cached(
    gru_checkpoint: str | None,
    transformer_checkpoint: str | None,
    device: str,
) -> dict[str, CodecAdapter]:
    gru = Path(gru_checkpoint) if gru_checkpoint else ROOT / "checkpoints" / "kaggle" / "best.pt"
    transformer = (
        Path(transformer_checkpoint)
        if transformer_checkpoint
        else ROOT / "checkpoints" / "neural_lossless_v2" / "best.pt"
    )
    adapters: list[CodecAdapter] = [
        RawCodec(),
        ZstdCodec(),
        BrotliCodec(),
        DeflateCodec(),
        Lzma2Codec(),
        Bzip2Codec(),
        XaiStaticCodec(),
    ]
    if NeuralRansCodec is not None:
        adapters.extend([
            NeuralRansCodec("xai-gru", gru, "causal-byte-gru-v1", device),
            NeuralRansCodec("xai-transformer", transformer, "causal-byte-transformer-v2", device),
        ])
    return {adapter.codec_id: adapter for adapter in adapters}


def build_registry(
    gru_checkpoint: str | Path | None = None,
    transformer_checkpoint: str | Path | None = None,
    device: str = "cpu",
) -> dict[str, CodecAdapter]:
    return _build_registry_cached(
        None if gru_checkpoint is None else str(Path(gru_checkpoint)),
        None if transformer_checkpoint is None else str(Path(transformer_checkpoint)),
        device,
    )


def available_registry(**kwargs) -> dict[str, CodecAdapter]:
    return {key: value for key, value in build_registry(**kwargs).items() if value.available()}


__all__ = [
    "CodecAdapter",
    "CodecError",
    "CodecResult",
    "Strategy",
    "ModelRegistry",
    "build_registry",
    "available_registry",
]
