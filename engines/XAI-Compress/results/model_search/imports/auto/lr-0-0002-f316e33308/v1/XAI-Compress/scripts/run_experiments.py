#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from xai_compress.datasets.corpus import write_corpus
from xai_compress.benchmarks.suite import run_suite, aggregate
from xai_compress.train import train


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    corpus = write_corpus(root / "data" / "synthetic_bench")
    results_dir = root / "experiments" / "runs"
    results_dir.mkdir(parents=True, exist_ok=True)
    ckpt = results_dir / "tiny_gru.pt"
    train(
        str(corpus),
        str(ckpt),
        epochs=1,
        batch_size=8,
        context_length=64,
        max_samples=256,
        max_bytes_per_file=1_000_000,
        embedding_dim=32,
        hidden_dim=64,
        num_layers=1,
        amp=False,
        preset="tiny",
    )
    rows = run_suite(corpus, str(ckpt), str(results_dir / "benchmark.csv"))
    summary = aggregate(rows)
    (results_dir / "benchmark.summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
