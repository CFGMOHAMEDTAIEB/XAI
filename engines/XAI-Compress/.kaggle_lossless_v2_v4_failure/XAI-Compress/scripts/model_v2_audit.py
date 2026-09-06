"""Measure the old neural model's end-to-end BPB decomposition.

This is intentionally an audit utility: it does not train or modify a model.
All terms are measured on the same bytes and sum to the XAIC artifact size.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import torch

from xai_compress.checkpoint import load_checkpoint
from xai_compress.compression import compress_bytes
from xai_compress.entropy.quant import NEURAL_TOTAL, logits_to_cumulative
from xai_compress.format import unpack_container
from xai_compress.model import BOS_TOKEN


def measure_file(path: Path, checkpoint: Path) -> dict:
    data = path.read_bytes()
    model, _ = load_checkpoint(checkpoint, "cpu")
    model.eval()
    hidden = None
    previous = BOS_TOKEN
    model_bits = 0.0
    quantized_bits = 0.0
    with torch.inference_mode():
        for symbol in data:
            logits, hidden = model.step(previous, hidden)
            log_probs = torch.log_softmax(logits.double(), dim=-1)
            model_bits += float(-log_probs[symbol] / math.log(2.0))
            cumulative = logits_to_cumulative(logits)
            frequency = cumulative[symbol + 1] - cumulative[symbol]
            quantized_bits += -math.log2(frequency / NEURAL_TOTAL)
            previous = symbol
    artifact = compress_bytes(data, "neural", checkpoint)
    _, payload = unpack_container(artifact)
    payload_bits = 8 * len(payload)
    artifact_bits = 8 * len(artifact)
    n = max(1, len(data))
    return {
        "file": str(path),
        "original_bytes": len(data),
        "model_entropy_bits": model_bits,
        "model_entropy_bpb": model_bits / n,
        "quantization_loss_bits": quantized_bits - model_bits,
        "quantization_loss_bpb": (quantized_bits - model_bits) / n,
        "entropy_coder_overhead_bits": payload_bits - quantized_bits,
        "entropy_coder_overhead_bpb": (payload_bits - quantized_bits) / n,
        "container_overhead_bits": artifact_bits - payload_bits,
        "container_overhead_bpb": (artifact_bits - payload_bits) / n,
        "payload_bytes": len(payload),
        "artifact_bytes": len(artifact),
        "actual_bpb": artifact_bits / n,
        "identity_error_bits": artifact_bits - (model_bits + (quantized_bits-model_bits) + (payload_bits-quantized_bits) + (artifact_bits-payload_bits)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/model_v2/lossless_bpb_breakdown.csv"))
    args = parser.parse_args()
    rows = [measure_file(path, args.checkpoint) for path in sorted(args.corpus.rglob("*")) if path.is_file()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(f"wrote {args.output}: {len(rows)} measured files")


if __name__ == "__main__":
    main()
