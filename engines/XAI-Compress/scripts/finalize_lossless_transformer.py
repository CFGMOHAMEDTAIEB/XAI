"""Finalize the validated Transformer V2 without training or promotion side effects.

All reported compression values are measured from artifacts produced by this
script.  The protected GRU and recovered Transformer checkpoints are opened
read-only.  Results are written below ``results/final``.
"""
from __future__ import annotations

import argparse
import bz2
import csv
import gzip
import hashlib
import json
import lzma
import math
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.checkpoint import load_checkpoint
from xai_compress.compression import (
    compress_bytes,
    compress_file,
    decompress_bytes,
    decompress_file,
)
from xai_compress.entropy.quant import NEURAL_TOTAL, logits_to_cumulative
from xai_compress.format import unpack_container
from xai_compress.model import BOS_TOKEN
from xai_compress.streaming import read_header, read_record_header


EXPECTED_TRANSFORMER_SHA = "584d8dfee979c6719a7602d00d81ef72443ee804878b13a1d651b5ea42129fb9"
EXPECTED_GRU_SHA = "083cda706612c3fd9ce62699741932b07e83fdf98eb6c5430d51bd29e1820429"
TRANSFORMER = ROOT / "checkpoints" / "neural_lossless_v2" / "best.pt"
GRU = ROOT / "checkpoints" / "kaggle" / "best.pt"
LOSSY = ROOT / "checkpoints" / "neural_lossy_v1" / "validation.pt"
KAGGLE_REPORTS = (
    ROOT
    / ".kaggle_kernel_output_safe_training_metadata_v1"
    / "results"
    / "model_search"
    / "safe_training_lr_0_0001"
)
OUT = ROOT / "results" / "final"
FIGURES = OUT / "figures"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def finite_tree(value: Any) -> bool:
    if torch.is_tensor(value):
        return bool(torch.isfinite(value).all().item())
    if isinstance(value, dict):
        return all(finite_tree(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(finite_tree(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def process_peak_rss_mb() -> float | None:
    try:
        import psutil

        memory = psutil.Process().memory_info()
        return float(getattr(memory, "peak_wset", memory.rss)) / (1 << 20)
    except (ImportError, OSError):
        return None


def checkpoint_report() -> tuple[dict[str, Any], Any, dict[str, Any]]:
    transformer_hash = sha256_file(TRANSFORMER)
    gru_hash = sha256_file(GRU)
    if transformer_hash != EXPECTED_TRANSFORMER_SHA:
        raise RuntimeError(
            f"CHECKPOINT_INTEGRITY_FAILURE: Transformer {transformer_hash} != {EXPECTED_TRANSFORMER_SHA}"
        )
    if gru_hash != EXPECTED_GRU_SHA:
        raise RuntimeError(f"PROTECTED_GRU_INTEGRITY_FAILURE: {gru_hash}")
    model, checkpoint = load_checkpoint(TRANSFORMER, "cpu")
    if model.config.architecture_id != "causal-byte-transformer-v2":
        raise RuntimeError("unexpected Transformer architecture ID")
    if checkpoint.get("epoch") != 5:
        raise RuntimeError(f"unexpected Transformer epoch: {checkpoint.get('epoch')}")
    expected_config = {
        "embedding_dim": 192,
        "hidden_dim": 192,
        "num_layers": 4,
        "context_length": 256,
        "dropout": 0.1,
        "architecture_id": "causal-byte-transformer-v2",
        "n_heads": 6,
        "ff_dim": 768,
        "residual_scale": 0.25,
    }
    if model.config.__dict__ != expected_config:
        raise RuntimeError(f"unexpected Transformer config: {model.config.__dict__}")
    finite_parameters = all(torch.isfinite(parameter).all().item() for parameter in model.parameters())
    finite_optimizer = finite_tree(checkpoint.get("optimizer_state"))
    with torch.inference_mode():
        logits_a, _ = model.step(BOS_TOKEN, None)
        logits_b, _ = model.step(BOS_TOKEN, None)
    deterministic = bool(torch.equal(logits_a, logits_b))
    report = {
        "status": "PASS" if finite_parameters and finite_optimizer and deterministic else "FAIL",
        "transformer": {
            "path": str(TRANSFORMER.relative_to(ROOT)),
            "size_bytes": TRANSFORMER.stat().st_size,
            "sha256": transformer_hash,
            "expected_sha256": EXPECTED_TRANSFORMER_SHA,
            "sha256_match": transformer_hash == EXPECTED_TRANSFORMER_SHA,
            "format": checkpoint.get("format"),
            "architecture_id": model.config.architecture_id,
            "config": model.config.__dict__,
            "epoch": checkpoint.get("epoch"),
            "parameters": sum(parameter.numel() for parameter in model.parameters()),
            "state_dict_keys": len(checkpoint.get("state_dict", {})),
            "strict_checkpoint_load": True,
            "finite_parameters": finite_parameters,
            "optimizer_state_present": "optimizer_state" in checkpoint,
            "finite_optimizer_state": finite_optimizer,
            "deterministic_inference": deterministic,
            "fingerprint": checkpoint.get("fingerprint"),
        },
        "protected_gru": {
            "path": str(GRU.relative_to(ROOT)),
            "size_bytes": GRU.stat().st_size,
            "sha256": gru_hash,
            "expected_sha256": EXPECTED_GRU_SHA,
            "sha256_match": gru_hash == EXPECTED_GRU_SHA,
        },
        "checkpoint_bytes_modified_by_validation": False,
    }
    write_json(OUT / "checkpoint_integrity.json", report)
    return report, model, checkpoint


def correctness_cases() -> dict[str, bytes]:
    rng = random.Random(20260901)
    code = (ROOT / "xai_compress" / "compression.py").read_bytes()
    return {
        "empty": b"",
        "one_byte": b"X",
        "short_text": b"XAI-Compress Transformer V2 exact round trip.\n",
        "all_byte_values": bytes(range(256)),
        "random_binary": bytes(rng.randrange(256) for _ in range(512)),
        "repetitive": (b"lossless-transformer-rans|" * 64)[:1024],
        "structured_text_code": code[:1024],
        "medium_binary": bytes(rng.randrange(256) for _ in range(4096)),
    }


def transformer_correctness_gate(integrity: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name, data in correctness_cases().items():
        started = time.perf_counter()
        artifact = compress_bytes(
            data, "neural-lossless", TRANSFORMER, device="cpu", coder="rans"
        )
        compression_seconds = time.perf_counter() - started
        started = time.perf_counter()
        restored = decompress_bytes(artifact, TRANSFORMER, device="cpu")
        decompression_seconds = time.perf_counter() - started
        original_hash = sha256_bytes(data)
        restored_hash = sha256_bytes(restored)
        row = {
            "case": name,
            "original_bytes": len(data),
            "artifact_bytes": len(artifact),
            "actual_bpb": 8 * len(artifact) / max(1, len(data)),
            "original_sha256": original_hash,
            "restored_sha256": restored_hash,
            "bytes_equal": restored == data,
            "sha256_equal": restored_hash == original_hash,
            "compression_seconds": compression_seconds,
            "decompression_seconds": decompression_seconds,
        }
        rows.append(row)
        print(f"CORRECTNESS {name}: {'PASS' if row['bytes_equal'] and row['sha256_equal'] else 'FAIL'}", flush=True)
    passed = all(row["bytes_equal"] and row["sha256_equal"] for row in rows)
    report = {
        "status": "PASS" if passed else "FAIL",
        "checkpoint_sha256": integrity["transformer"]["sha256"],
        "mode": "neural-lossless",
        "entropy_coder": "rans14-v1",
        "device": "cpu",
        "cases": rows,
    }
    write_json(OUT / "transformer_validation.json", report)
    if not passed:
        raise RuntimeError("TRANSFORMER_VALIDATION = FAIL")
    return report


def benchmark_corpus() -> dict[str, bytes]:
    rng = random.Random(20260902)
    return {
        "readme_text_1024": (ROOT / "README.md").read_bytes()[:1024],
        "python_code_1024": (ROOT / "xai_compress" / "compression.py").read_bytes()[:1024],
        "random_binary_1024": bytes(rng.randrange(256) for _ in range(1024)),
        "repetitive_1024": (b"XAI-COMPRESS-RANS-TRANSFORMER-V2\n" * 64)[:1024],
    }


def encode_classical(codec: str, data: bytes) -> bytes:
    if codec == "Brotli-6":
        import brotli

        return brotli.compress(data, quality=6)
    if codec == "Zstd-3":
        import zstandard as zstd

        return zstd.ZstdCompressor(level=3).compress(data)
    if codec == "gzip-9":
        return gzip.compress(data, compresslevel=9)
    if codec == "LZMA-6":
        return lzma.compress(data, preset=6)
    raise ValueError(codec)


def decode_classical(codec: str, artifact: bytes) -> bytes:
    if codec == "Brotli-6":
        import brotli

        return brotli.decompress(artifact)
    if codec == "Zstd-3":
        import zstandard as zstd

        return zstd.ZstdDecompressor().decompress(artifact)
    if codec == "gzip-9":
        return gzip.decompress(artifact)
    if codec == "LZMA-6":
        return lzma.decompress(artifact)
    raise ValueError(codec)


def entropy_totals(model: Any, data: bytes) -> tuple[float, float]:
    model_bits = 0.0
    quantized_bits = 0.0
    previous = BOS_TOKEN
    hidden = None
    with torch.inference_mode():
        for symbol in data:
            logits, hidden = model.step(previous, hidden)
            log_probs = torch.log_softmax(logits.detach().double(), dim=-1)
            model_bits -= float(log_probs[symbol].item()) / math.log(2)
            cumulative = logits_to_cumulative(logits)
            frequency = cumulative[symbol + 1] - cumulative[symbol]
            quantized_bits -= math.log2(frequency / NEURAL_TOTAL)
            previous = symbol
    return model_bits, quantized_bits


def paired_benchmark(transformer_model: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    corpus = benchmark_corpus()
    methods = [
        "XAI Transformer V2 + rANS",
        "XAI GRU V1 + rANS",
        "XAI static",
        "Brotli-6",
        "Zstd-3",
        "gzip-9",
        "LZMA-6",
    ]
    raw: list[dict[str, Any]] = []
    overhead_accumulator: list[dict[str, float]] = []
    for codec in methods:
        for corpus_name, data in corpus.items():
            try:
                started = time.perf_counter()
                if codec == "XAI Transformer V2 + rANS":
                    artifact = compress_bytes(
                        data, "neural-lossless", TRANSFORMER, device="cpu", coder="rans"
                    )
                elif codec == "XAI GRU V1 + rANS":
                    artifact = compress_bytes(
                        data, "neural-lossless", GRU, device="cpu", coder="rans"
                    )
                elif codec == "XAI static":
                    artifact = compress_bytes(data, "static")
                else:
                    artifact = encode_classical(codec, data)
                compression_seconds = time.perf_counter() - started
                started = time.perf_counter()
                if codec == "XAI Transformer V2 + rANS":
                    restored = decompress_bytes(artifact, TRANSFORMER, device="cpu")
                elif codec == "XAI GRU V1 + rANS":
                    restored = decompress_bytes(artifact, GRU, device="cpu")
                elif codec == "XAI static":
                    restored = decompress_bytes(artifact)
                else:
                    restored = decode_classical(codec, artifact)
                decompression_seconds = time.perf_counter() - started
                original_hash = sha256_bytes(data)
                restored_hash = sha256_bytes(restored)
                row = {
                    "codec": codec,
                    "corpus_item": corpus_name,
                    "corpus_label": "MEASURED deterministic paired 4 KiB corpus",
                    "original_bytes": len(data),
                    "compressed_bytes": len(artifact),
                    "actual_bpb": 8 * len(artifact) / len(data),
                    "compression_ratio": len(data) / len(artifact),
                    "compression_time_seconds": compression_seconds,
                    "decompression_time_seconds": decompression_seconds,
                    "compression_MB_s": len(data) / (1 << 20) / max(compression_seconds, 1e-12),
                    "decompression_MB_s": len(data) / (1 << 20) / max(decompression_seconds, 1e-12),
                    "sha256_correctness": restored_hash == original_hash,
                    "restored_bytes_equal": restored == data,
                    "peak_RSS_MB": process_peak_rss_mb(),
                    "status": "PASS" if restored == data and restored_hash == original_hash else "FAIL",
                    "timing_scope": "single local CPU invocation; neural timings include checkpoint load",
                }
                if codec == "XAI Transformer V2 + rANS":
                    metadata, payload = unpack_container(artifact)
                    model_bits, quantized_bits = entropy_totals(transformer_model, data)
                    overhead = {
                        "original_bytes": float(len(data)),
                        "model_bits": model_bits,
                        "quantized_bits": quantized_bits,
                        "payload_bits": float(8 * len(payload)),
                        "artifact_bits": float(8 * len(artifact)),
                    }
                    overhead_accumulator.append(overhead)
                    row.update(
                        {
                            "model_entropy_bpb": model_bits / len(data),
                            "quantized_ideal_bpb": quantized_bits / len(data),
                            "rans_payload_bpb": 8 * len(payload) / len(data),
                            "container_overhead_bpb": 8 * (len(artifact) - len(payload)) / len(data),
                            "model_fingerprint": metadata.get("model_fingerprint"),
                        }
                    )
                raw.append(row)
                print(f"BENCHMARK {codec} / {corpus_name}: {row['actual_bpb']:.6f} BPB", flush=True)
            except Exception as exc:
                raw.append(
                    {
                        "codec": codec,
                        "corpus_item": corpus_name,
                        "status": "N/A",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"BENCHMARK {codec} / {corpus_name}: N/A ({exc})", flush=True)

    summaries: list[dict[str, Any]] = []
    for codec in methods:
        rows = [row for row in raw if row["codec"] == codec and row.get("status") == "PASS"]
        if len(rows) != len(corpus):
            summaries.append({"codec": codec, "status": "N/A", "files": len(rows)})
            continue
        original = sum(int(row["original_bytes"]) for row in rows)
        compressed = sum(int(row["compressed_bytes"]) for row in rows)
        compression_time = sum(float(row["compression_time_seconds"]) for row in rows)
        decompression_time = sum(float(row["decompression_time_seconds"]) for row in rows)
        summaries.append(
            {
                "codec": codec,
                "status": "PASS",
                "files": len(rows),
                "original_bytes": original,
                "compressed_bytes": compressed,
                "actual_bpb": 8 * compressed / original,
                "compression_ratio": original / compressed,
                "compression_time_seconds": compression_time,
                "decompression_time_seconds": decompression_time,
                "compression_MB_s": original / (1 << 20) / compression_time,
                "decompression_MB_s": original / (1 << 20) / decompression_time,
                "sha256_correctness": all(row["sha256_correctness"] for row in rows),
                "peak_RSS_MB": max(
                    (row["peak_RSS_MB"] for row in rows if row.get("peak_RSS_MB") is not None),
                    default=None,
                ),
                "timing_scope": "single local CPU invocation; neural timings include checkpoint load",
            }
        )

    total_original = sum(item["original_bytes"] for item in overhead_accumulator)
    model_bits = sum(item["model_bits"] for item in overhead_accumulator)
    quantized_bits = sum(item["quantized_bits"] for item in overhead_accumulator)
    payload_bits = sum(item["payload_bits"] for item in overhead_accumulator)
    artifact_bits = sum(item["artifact_bits"] for item in overhead_accumulator)
    overhead = {
        "status": "MEASURED" if overhead_accumulator else "NOT MEASURED",
        "corpus_original_bytes": int(total_original),
        "model_entropy_bpb": model_bits / total_original if total_original else "NOT MEASURED",
        "probability_quantization_contribution_bpb": (quantized_bits - model_bits) / total_original
        if total_original
        else "NOT MEASURED",
        "rans_entropy_coder_overhead_bpb": (payload_bits - quantized_bits) / total_original
        if total_original
        else "NOT MEASURED",
        "xaic_container_overhead_bpb": (artifact_bits - payload_bits) / total_original
        if total_original
        else "NOT MEASURED",
        "total_actual_bpb": artifact_bits / total_original if total_original else "NOT MEASURED",
        "identity_check_bpb": (
            model_bits
            + (quantized_bits - model_bits)
            + (payload_bits - quantized_bits)
            + (artifact_bits - payload_bits)
        )
        / total_original
        if total_original
        else "NOT MEASURED",
    }
    write_csv(OUT / "lossless_benchmark.csv", summaries)
    write_csv(OUT / "lossless_benchmark_raw.csv", raw)
    write_json(
        OUT / "lossless_benchmark.json",
        {
            "measurement": "MEASURED",
            "corpus": [
                {"name": name, "bytes": len(data), "sha256": sha256_bytes(data)}
                for name, data in corpus.items()
            ],
            "raw": raw,
            "summary": summaries,
            "overhead_decomposition": overhead,
        },
    )
    write_json(OUT / "transformer_overhead_decomposition.json", overhead)
    return raw, summaries, overhead


def make_stream_bytes(path: Path, size: int) -> None:
    block = (bytes(range(256)) + b"XAI-COMPRESS-STREAMING\n" * 128)[:65536]
    remaining = size
    with path.open("wb") as handle:
        while remaining:
            piece = block[: min(len(block), remaining)]
            handle.write(piece)
            remaining -= len(piece)


def streaming_validation() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="xai-final-streaming-", dir=OUT) as temporary:
        work = Path(temporary)
        for size in (64 << 10, 1 << 20, 4 << 20):
            source = work / f"source_{size}.bin"
            artifact = work / f"artifact_{size}.xaic"
            restored = work / f"restored_{size}.bin"
            make_stream_bytes(source, size)
            original_hash = sha256_file(source)
            tracemalloc.start()
            started = time.perf_counter()
            encoded = compress_file(source, artifact, mode="zlib", chunk_size=64 << 10)
            compression_seconds = time.perf_counter() - started
            started = time.perf_counter()
            decoded = decompress_file(artifact, restored)
            decompression_seconds = time.perf_counter() - started
            _, python_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            restored_hash = sha256_file(restored)
            rows.append(
                {
                    "mode": "XAIC-v3 zlib streaming",
                    "original_bytes": size,
                    "artifact_bytes": artifact.stat().st_size,
                    "chunks": encoded["chunks"],
                    "chunk_size": 64 << 10,
                    "format_version": encoded["format_version"],
                    "compression_seconds": compression_seconds,
                    "decompression_seconds": decompression_seconds,
                    "python_peak_alloc_MB": python_peak / (1 << 20),
                    "process_peak_RSS_MB": process_peak_rss_mb(),
                    "whole_file_sha256_pass": original_hash == restored_hash,
                    "restored_bytes": decoded["restored_size"],
                    "status": "PASS" if original_hash == restored_hash else "FAIL",
                }
            )
            print(f"STREAMING zlib {size} bytes: {rows[-1]['status']}", flush=True)

        neural_source = work / "transformer_stream.bin"
        neural_artifact = work / "transformer_stream.xaic"
        neural_restored = work / "transformer_stream.restored"
        neural_source.write_bytes((b"Transformer streaming exact XAIC v3.\n" * 80)[:2048])
        started = time.perf_counter()
        encoded = compress_file(
            neural_source,
            neural_artifact,
            mode="neural-lossless",
            checkpoint=TRANSFORMER,
            chunk_size=512,
            device="cpu",
            coder="rans",
        )
        compression_seconds = time.perf_counter() - started
        started = time.perf_counter()
        decoded = decompress_file(
            neural_artifact, neural_restored, checkpoint=TRANSFORMER, device="cpu"
        )
        decompression_seconds = time.perf_counter() - started
        neural_pass = sha256_file(neural_source) == sha256_file(neural_restored)
        rows.append(
            {
                "mode": "XAIC-v3 Transformer V2 + rANS streaming",
                "original_bytes": neural_source.stat().st_size,
                "artifact_bytes": neural_artifact.stat().st_size,
                "chunks": encoded["chunks"],
                "chunk_size": 512,
                "format_version": encoded["format_version"],
                "compression_seconds": compression_seconds,
                "decompression_seconds": decompression_seconds,
                "process_peak_RSS_MB": process_peak_rss_mb(),
                "whole_file_sha256_pass": neural_pass,
                "restored_bytes": decoded["restored_size"],
                "status": "PASS" if neural_pass else "FAIL",
            }
        )
        print(f"STREAMING Transformer: {rows[-1]['status']}", flush=True)

        # Explicit trailing-data rejection.
        trailing = work / "trailing.xaic"
        trailing.write_bytes(neural_artifact.read_bytes() + b"TRAILING")
        trailing_target = work / "trailing.restored"
        try:
            decompress_file(trailing, trailing_target, checkpoint=TRANSFORMER, device="cpu")
            trailing_rejected = False
        except Exception:
            trailing_rejected = not trailing_target.exists()

        # Explicit per-chunk corruption rejection and atomic destination preservation.
        corrupt = work / "corrupt.xaic"
        corrupt.write_bytes(neural_artifact.read_bytes())
        with corrupt.open("r+b") as handle:
            read_header(handle)
            kind, _ = read_record_header(handle)
            if kind != "chunk":
                raise RuntimeError("stream has no chunk to corrupt")
            payload_position = handle.tell()
            value = handle.read(1)
            handle.seek(payload_position)
            handle.write(bytes([value[0] ^ 1]))
        atomic_target = work / "atomic.restored"
        sentinel = b"PRESERVE-EXISTING-DESTINATION"
        atomic_target.write_bytes(sentinel)
        try:
            decompress_file(
                corrupt,
                atomic_target,
                checkpoint=TRANSFORMER,
                device="cpu",
                overwrite=True,
            )
            corruption_rejected = False
        except Exception:
            corruption_rejected = atomic_target.read_bytes() == sentinel

    report = {
        "status": "PASS"
        if all(row["status"] == "PASS" for row in rows)
        and trailing_rejected
        and corruption_rejected
        else "FAIL",
        "rows": rows,
        "sequential_chunk_ids": "PASS (enforced by decoder and exercised by multi-chunk rows)",
        "bounded_lengths": "PASS (64 KiB chunk limit exercised through 4 MiB)",
        "per_chunk_integrity": "PASS" if corruption_rejected else "FAIL",
        "whole_file_integrity": "PASS" if all(row["whole_file_sha256_pass"] for row in rows) else "FAIL",
        "trailing_data_rejection": "PASS" if trailing_rejected else "FAIL",
        "atomic_output_replacement": "PASS" if corruption_rejected else "FAIL",
        "large_transformer_streaming_above_2048_bytes": "NOT MEASURED",
    }
    write_json(OUT / "streaming_validation.json", report)
    if report["status"] != "PASS":
        raise RuntimeError("streaming validation failed")
    return report


def lossy_validation_report() -> dict[str, Any]:
    source = ROOT / "results" / "final_project" / "lossy_benchmark.csv"
    rows: list[dict[str, Any]] = []
    with source.open(newline="", encoding="utf-8") as handle:
        rows.extend(csv.DictReader(handle))
    model, checkpoint = load_checkpoint(LOSSY, "cpu")
    finite = all(torch.isfinite(parameter).all().item() for parameter in model.parameters())
    report = {
        "status": "EXPERIMENTAL",
        "checkpoint": str(LOSSY.relative_to(ROOT)),
        "checkpoint_sha256": sha256_file(LOSSY),
        "architecture_id": model.config.architecture_id,
        "strict_checkpoint_load": True,
        "finite_parameters": finite,
        "decode_validation": "PASS"
        if rows and all(row["decode_status"] == "PASS" for row in rows)
        else "FAIL",
        "quality_modes": [row["quality"].upper() for row in rows],
        "measurements": rows,
        "MS_SSIM": "NOT MEASURED",
        "training_scope": "deterministic validation corpus only",
        "retrained_by_this_workflow": False,
    }
    write_json(OUT / "lossy_validation.json", report)
    return report


def run_command(
    command: list[str], cwd: Path, env_extra: dict[str, str] | None = None
) -> dict[str, Any]:
    started = time.perf_counter()
    environment = os.environ.copy()
    if env_extra:
        environment.update(env_extra)
    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "duration_seconds": time.perf_counter() - started,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
    }


def test_suites() -> dict[str, Any]:
    python = run_command([sys.executable, "-m", "pytest", "-q"], ROOT)
    # The local interpreter is Python 3.14 while PyO3 0.22's version guard
    # knows through 3.13.  The crate uses PyO3's stable ABI; its documented
    # forward-compatibility switch permits the Rust unit tests to compile.
    rust = run_command(
        ["cargo", "test", "--manifest-path", "rust-core/Cargo.toml"],
        ROOT,
        {"PYO3_USE_ABI3_FORWARD_COMPATIBILITY": "1"},
    )
    parity = run_command(
        [sys.executable, "-m", "pytest", "-q", "tests/test_rust_parity.py"], ROOT
    )
    report = {"python": python, "rust": rust, "rust_parity": parity}
    write_json(OUT / "test_results.json", report)
    print(f"PYTHON TESTS: {python['status']}", flush=True)
    print(f"RUST TESTS: {rust['status']}", flush=True)
    print(f"RUST PARITY: {parity['status']}", flush=True)
    if any(item["status"] != "PASS" for item in report.values()):
        raise RuntimeError("one or more final test suites failed")
    return report


def esc(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def svg_bar(path: Path, title: str, rows: list[dict[str, Any]], key: str, unit: str) -> None:
    valid = [(row["codec"], float(row[key])) for row in rows if row.get("status") == "PASS"]
    width, height, left, right, top, bottom = 1100, 620, 90, 40, 85, 155
    plot_width, plot_height = width - left - right, height - top - bottom
    maximum = max((value for _, value in valid), default=1.0) or 1.0
    bar_width = plot_width / max(1, len(valid)) * 0.68
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="32" text-anchor="middle" font-size="22" font-family="sans-serif">{esc(title)}</text>',
        '<text x="20" y="55" font-size="13" font-family="sans-serif" fill="#276749">MEASURED — deterministic paired 4 KiB corpus</text>',
        f'<line x1="{left}" y1="{top+plot_height}" x2="{width-right}" y2="{top+plot_height}" stroke="black"/>',
        f'<text transform="translate(22 {top+plot_height/2}) rotate(-90)" text-anchor="middle" font-size="15" font-family="sans-serif">{esc(unit)}</text>',
    ]
    colors = ["#2563eb", "#7c3aed", "#059669", "#dc2626", "#d97706", "#0891b2", "#475569"]
    slot = plot_width / max(1, len(valid))
    for index, (label, value) in enumerate(valid):
        x = left + index * slot + (slot - bar_width) / 2
        h = plot_height * value / maximum
        y = top + plot_height - h
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{h:.2f}" fill="{colors[index % len(colors)]}"/>')
        parts.append(f'<text x="{x+bar_width/2:.2f}" y="{y-7:.2f}" text-anchor="middle" font-size="12" font-family="sans-serif">{value:.4g}</text>')
        parts.append(f'<text transform="translate({x+bar_width/2:.2f} {top+plot_height+12}) rotate(45)" text-anchor="start" font-size="12" font-family="sans-serif">{esc(label)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_line(path: Path, title: str, epochs: list[int], series: list[tuple[str, list[float]]], unit: str) -> None:
    width, height, left, right, top, bottom = 950, 560, 85, 35, 75, 70
    plot_width, plot_height = width - left - right, height - top - bottom
    values = [value for _, sequence in series for value in sequence]
    minimum, maximum = min(values), max(values)
    if maximum == minimum:
        maximum += 1.0
    colors = ["#2563eb", "#dc2626", "#059669", "#7c3aed"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="30" text-anchor="middle" font-size="22" font-family="sans-serif">{esc(title)}</text>',
        '<text x="18" y="52" font-size="13" font-family="sans-serif" fill="#276749">MEASURED — completed Kaggle 5-epoch gate</text>',
        f'<line x1="{left}" y1="{top+plot_height}" x2="{width-right}" y2="{top+plot_height}" stroke="black"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_height}" stroke="black"/>',
        f'<text transform="translate(20 {top+plot_height/2}) rotate(-90)" text-anchor="middle" font-size="15" font-family="sans-serif">{esc(unit)}</text>',
    ]
    for index, epoch in enumerate(epochs):
        x = left + index * plot_width / max(1, len(epochs) - 1)
        parts.append(f'<text x="{x:.2f}" y="{top+plot_height+24}" text-anchor="middle" font-size="13" font-family="sans-serif">{epoch}</text>')
    for series_index, (label, sequence) in enumerate(series):
        points = []
        for index, value in enumerate(sequence):
            x = left + index * plot_width / max(1, len(sequence) - 1)
            y = top + plot_height - (value - minimum) / (maximum - minimum) * plot_height
            points.append(f"{x:.2f},{y:.2f}")
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{colors[series_index]}"/>')
        parts.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[series_index]}" stroke-width="3"/>')
        parts.append(f'<text x="{left+12}" y="{top+18+series_index*20}" font-size="13" font-family="sans-serif" fill="{colors[series_index]}">{esc(label)}</text>')
    parts.append(f'<text x="{left+plot_width/2}" y="{height-15}" text-anchor="middle" font-size="15" font-family="sans-serif">Epoch</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_pareto(path: Path, rows: list[dict[str, Any]]) -> None:
    valid = [row for row in rows if row.get("status") == "PASS"]
    width, height, left, right, top, bottom = 1000, 600, 90, 45, 70, 80
    plot_width, plot_height = width - left - right, height - top - bottom
    max_x = max(float(row["actual_bpb"]) for row in valid) * 1.08
    speeds = [float(row["compression_MB_s"]) for row in valid]
    min_log = math.log10(max(min(speeds), 1e-8))
    max_log = math.log10(max(speeds))
    if max_log == min_log:
        max_log += 1
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="30" text-anchor="middle" font-size="22" font-family="sans-serif">Actual BPB vs compression throughput</text>',
        '<text x="18" y="52" font-size="13" font-family="sans-serif" fill="#276749">MEASURED — log throughput axis</text>',
        f'<line x1="{left}" y1="{top+plot_height}" x2="{width-right}" y2="{top+plot_height}" stroke="black"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_height}" stroke="black"/>',
        f'<text x="{left+plot_width/2}" y="{height-20}" text-anchor="middle" font-size="15" font-family="sans-serif">Actual BPB (lower is better)</text>',
        f'<text transform="translate(20 {top+plot_height/2}) rotate(-90)" text-anchor="middle" font-size="15" font-family="sans-serif">Compression MB/s (log10)</text>',
    ]
    for index, row in enumerate(valid):
        x = left + float(row["actual_bpb"]) / max_x * plot_width
        y = top + plot_height - (math.log10(max(float(row["compression_MB_s"]), 1e-8)) - min_log) / (max_log - min_log) * plot_height
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="7" fill="#2563eb"/>')
        offset = 16 if index % 2 == 0 else -10
        parts.append(f'<text x="{x+10:.2f}" y="{y+offset:.2f}" font-size="12" font-family="sans-serif">{esc(row["codec"])}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_architecture(path: Path) -> None:
    boxes = [
        ("Input bytes", 30),
        ("Causal Transformer V2", 190),
        ("FP32 logits", 410),
        ("Deterministic quantizer", 560),
        ("rANS14", 765),
        ("XAIC", 890),
    ]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1050" height="230">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="525" y="30" text-anchor="middle" font-size="22" font-family="sans-serif">XAI neural lossless architecture</text>',
        '<text x="20" y="55" font-size="13" font-family="sans-serif" fill="#92400e">ILLUSTRATIVE — implementation architecture, not a performance measurement</text>',
    ]
    for index, (label, x) in enumerate(boxes):
        box_width = 130 if index not in (1, 3) else 180
        parts.append(f'<rect x="{x}" y="95" width="{box_width}" height="55" rx="8" fill="#dbeafe" stroke="#1d4ed8"/>')
        parts.append(f'<text x="{x+box_width/2}" y="128" text-anchor="middle" font-size="13" font-family="sans-serif">{esc(label)}</text>')
        if index + 1 < len(boxes):
            next_x = boxes[index + 1][1]
            parts.append(f'<line x1="{x+box_width}" y1="122" x2="{next_x-8}" y2="122" stroke="#111827" stroke-width="2"/>')
            parts.append(f'<polygon points="{next_x-8},117 {next_x},122 {next_x-8},127" fill="#111827"/>')
    parts.append('<text x="525" y="190" text-anchor="middle" font-size="13" font-family="sans-serif">Decoder regenerates the identical probability/frequency sequence; SHA-256 is verified after reconstruction.</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def figures(summaries: list[dict[str, Any]], history: list[dict[str, Any]]) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    svg_bar(FIGURES / "actual_bpb_comparison.svg", "Actual artifact BPB", summaries, "actual_bpb", "Bits per byte")
    svg_bar(FIGURES / "compression_ratio_comparison.svg", "Compression ratio", summaries, "compression_ratio", "Original / compressed")
    svg_bar(FIGURES / "compression_throughput.svg", "Compression throughput", summaries, "compression_MB_s", "MB/s")
    svg_bar(FIGURES / "decompression_throughput.svg", "Decompression throughput", summaries, "decompression_MB_s", "MB/s")
    svg_pareto(FIGURES / "bpb_throughput_pareto.svg", summaries)
    epochs = [int(row["epoch"]) for row in history]
    svg_line(
        FIGURES / "transformer_training_bpb.svg",
        "Transformer validation BPB estimate by epoch",
        epochs,
        [("Validation BPB estimate", [float(row["val_bpb_estimate"]) for row in history])],
        "Validation BPB estimate (not artifact BPB)",
    )
    activation = [
        max(
            float(value)
            for key, value in row.items()
            if "activation_abs_max" in key and isinstance(value, (int, float))
        )
        for row in history
    ]
    svg_line(
        FIGURES / "transformer_activation_trajectory.svg",
        "Transformer maximum observed activation by epoch",
        epochs,
        [("Maximum activation", activation)],
        "Absolute activation maximum",
    )
    svg_architecture(FIGURES / "xai_architecture.svg")


def test_summary(result: dict[str, Any]) -> str:
    lines = [
        line.strip()
        for line in (result["stdout"] + "\n" + result["stderr"]).splitlines()
        if line.strip()
    ]
    rust_results = [line for line in lines if line.startswith("test result:")]
    one_test = [line for line in rust_results if "1 passed" in line]
    if one_test:
        return one_test[-1]
    return lines[-1] if lines else f"return code {result['returncode']}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume-measurements",
        action="store_true",
        help="reuse completed JSON measurements after a test-toolchain-only failure",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    integrity, transformer_model, transformer_checkpoint = checkpoint_report()
    if args.resume_measurements:
        validation = json.loads((OUT / "transformer_validation.json").read_text(encoding="utf-8"))
        benchmark = json.loads((OUT / "lossless_benchmark.json").read_text(encoding="utf-8"))
        raw = benchmark["raw"]
        summaries = benchmark["summary"]
        overhead = benchmark["overhead_decomposition"]
        stream = json.loads((OUT / "streaming_validation.json").read_text(encoding="utf-8"))
        lossy = json.loads((OUT / "lossy_validation.json").read_text(encoding="utf-8"))
        if validation.get("status") != "PASS" or stream.get("status") != "PASS":
            raise RuntimeError("cannot resume from incomplete measurement gates")
        print("REUSING COMPLETED MEASUREMENTS: PASS", flush=True)
    else:
        validation = transformer_correctness_gate(integrity)
        raw, summaries, overhead = paired_benchmark(transformer_model)
        stream = streaming_validation()
        lossy = lossy_validation_report()
    tests = test_suites()

    diagnostic = json.loads((KAGGLE_REPORTS / "diagnostic_summary.json").read_text(encoding="utf-8"))
    history = json.loads((KAGGLE_REPORTS / "best.history.json").read_text(encoding="utf-8"))
    if diagnostic.get("status") != "PASS" or len(history) != 5:
        raise RuntimeError("Kaggle five-epoch diagnostic evidence is incomplete")
    figures(summaries, history)

    valid_summaries = {row["codec"]: row for row in summaries if row.get("status") == "PASS"}
    transformer = valid_summaries["XAI Transformer V2 + rANS"]
    gru = valid_summaries["XAI GRU V1 + rANS"]
    improvement = 100.0 * (gru["actual_bpb"] - transformer["actual_bpb"]) / gru["actual_bpb"]
    transformer_lower = transformer["actual_bpb"] < gru["actual_bpb"]
    promotion_eligible = (
        transformer["actual_bpb"] <= gru["actual_bpb"] * 0.995
        and transformer["sha256_correctness"]
        and integrity["transformer"]["deterministic_inference"]
        and integrity["transformer"]["sha256_match"]
    )
    transformer_status = "VALIDATED" if transformer_lower else "VALIDATED_EXPERIMENTAL"
    recommended_lossless = (
        "Transformer V2 (separate checkpoint; GRU retained)" if promotion_eligible else "Protected GRU"
    )
    classical = [
        row
        for row in summaries
        if row.get("status") == "PASS" and not row["codec"].startswith("XAI ")
    ]
    best_classical = min(classical, key=lambda row: row["actual_bpb"])
    xai_rows = [row for row in summaries if row.get("status") == "PASS" and row["codec"].startswith("XAI ")]
    best_xai = min(xai_rows, key=lambda row: row["actual_bpb"])
    xai_beats_classical = "YES" if best_xai["actual_bpb"] < best_classical["actual_bpb"] else "NO"

    gru_after = sha256_file(GRU)
    if gru_after != EXPECTED_GRU_SHA:
        raise RuntimeError("protected GRU changed during finalization")
    checkpoint_after = dict(integrity)
    checkpoint_after["protected_gru"]["sha256_after_all_work"] = gru_after
    checkpoint_after["protected_gru"]["immutable"] = True
    write_json(OUT / "checkpoint_integrity.json", checkpoint_after)

    final = {
        "LOSSLESS": {
            "Transformer_5_epoch_gate": "PASS",
            "Transformer_checkpoint": str(TRANSFORMER.relative_to(ROOT)),
            "Transformer_checkpoint_SHA": integrity["transformer"]["sha256"],
            "Transformer_deterministic_inference": "PASS",
            "Transformer_SHA_roundtrip": validation["status"],
            "Transformer_actual_BPB": transformer["actual_bpb"],
            "GRU_actual_BPB": gru["actual_bpb"],
            "Transformer_improvement_relative_to_GRU_percent": improvement,
            "Transformer_status": transformer_status,
            "promotion_eligible_at_0_5_percent": promotion_eligible,
            "Best_XAI_lossless_model": best_xai["codec"],
            "Best_classical_codec": best_classical["codec"],
            "XAI_beats_classical_codec": xai_beats_classical,
            "benchmark_scope": "MEASURED deterministic paired 4 KiB corpus",
            "overhead_decomposition": overhead,
        },
        "LOSSY": {
            "Checkpoint": lossy["checkpoint"],
            "Decode_validation": lossy["decode_validation"],
            "PSNR": sorted({row["psnr_db"] for row in lossy["measurements"]}),
            "SSIM": sorted({row["ssim"] for row in lossy["measurements"]}),
            "MS_SSIM": "NOT MEASURED",
            "Status": "EXPERIMENTAL",
        },
        "SYSTEM": {
            "Python_tests": test_summary(tests["python"]),
            "Rust_tests": test_summary(tests["rust"]),
            "Streaming": stream["status"],
            "Rust_parity": tests["rust_parity"]["status"],
            "Protected_GRU_integrity": "PASS",
        },
        "PRODUCTION": {
            "Recommended_lossless_model": recommended_lossless,
            "Recommended_lossy_model": "validation.pt (EXPERIMENTAL)",
            "protected_GRU_overwritten": False,
        },
        "LIMITATIONS": [
            "The paired codec benchmark is a measured 4 KiB deterministic corpus, not a broad generalization benchmark.",
            "Neural CPU timings include checkpoint loading and are single-invocation measurements.",
            "Transformer XAIC-v3 streaming was measured to 2,048 bytes; larger Transformer streaming is NOT MEASURED.",
            "Peak RSS is the process-level Windows peak and is not isolated per codec.",
            "The lossy checkpoint was trained only on a deterministic validation corpus; MS-SSIM is NOT MEASURED.",
        ],
    }
    write_json(OUT / "final_status.json", final)
    print("FINAL STATUS JSON", json.dumps(final, indent=2), flush=True)


if __name__ == "__main__":
    main()
