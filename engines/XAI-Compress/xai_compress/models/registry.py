from __future__ import annotations

from ..model import CausalByteGRU, ModelConfig
from .transformer import CausalByteTransformer


ARCHITECTURES = {
    "causal-byte-gru-v1": CausalByteGRU,
    "gru": CausalByteGRU,
    "causal-byte-transformer-v1": CausalByteTransformer,
    "transformer": CausalByteTransformer,
}


def build_model(config: ModelConfig):
    """Construct the model identified by a checkpoint-compatible config."""
    try:
        model_type = ARCHITECTURES[config.architecture_id]
    except KeyError as exc:
        choices = ", ".join(sorted(ARCHITECTURES))
        raise ValueError(
            f"unsupported architecture_id: {config.architecture_id!r}; "
            f"expected one of: {choices}"
        ) from exc
    return model_type(config)


__all__ = ["ARCHITECTURES", "build_model"]
