"""Build a compact, diverse codec-selector dataset from actual measurements."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import random
import struct
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xai_compress.hybrid.codecs import available_registry
from xai_compress.hybrid.features import extract_features
from xai_compress.hybrid.profiles import label_measurements, load_profiles
from xai_compress.hybrid.selector import candidate_catalog, measure_strategy


@dataclass(frozen=True)
class Sample:
    sample_id: str
    source_group: str
    category: str
    extension: str
    data: bytes
    origin: str


def bounded(path: Path, size: int) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def repeat_to(data: bytes, size: int) -> bytes:
    if not data:
        return b"\0" * size
    return (data * (size // len(data) + 1))[:size]


def wav_bytes(samples: int = 8192) -> bytes:
    values = np.asarray(
        [int(16000 * math.sin(2 * math.pi * 440 * index / 16000)) for index in range(samples)],
        dtype="<i2",
    ).tobytes()
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(values))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
        + b"data"
        + struct.pack("<I", len(values))
        + values
    )


def build_samples(max_sample_bytes: int) -> list[Sample]:
    readme = (ROOT / "README.md").read_bytes()
    code = (ROOT / "xai_compress" / "compression.py").read_bytes()
    config = (ROOT / "configs" / "model_search_v2.json").read_bytes()
    csv_data = (ROOT / "phase_i_actual_benchmark.csv").read_bytes()
    log_candidates = sorted(ROOT.glob(".kaggle_kernel_output_*/*.log"))
    log_data = bounded(log_candidates[-1], max_sample_bytes) if log_candidates else repeat_to(b"INFO codec benchmark complete\n", 8192)
    image_path = ROOT / "results" / "final_project" / "lossy_validation_corpus" / "image_6.ppm"
    image = image_path.read_bytes() if image_path.is_file() else repeat_to(b"P6\n32 32\n255\n", 4096)
    mp4 = next(iter((ROOT / "data" / "test").rglob("*.mp4")), None)
    video = bounded(mp4, max_sample_bytes) if mp4 else b"\0\0\0\x18ftypmp42" + bytes(range(256)) * 32
    executable = bounded(Path(sys.executable), max_sample_bytes)
    checkpoint = bounded(ROOT / "checkpoints" / "kaggle" / "best.pt", max_sample_bytes)
    rng = random.Random(20260901)
    random_4k = bytes(rng.randrange(256) for _ in range(4096))
    random_16k = bytes(rng.randrange(256) for _ in range(16384))
    numeric = np.linspace(-1, 1, 8192, dtype="<f4").tobytes()
    numeric_delta = np.cumsum(np.ones(8192, dtype="<i4")).tobytes()
    xml = repeat_to(b'<record id="42"><name>XAI</name><value>123.45</value></record>\n', 16384)
    json_lines = repeat_to(b'{"timestamp":123456,"level":"INFO","codec":"zstd","bytes":4096}\n', 16384)
    database = b"SQLite format 3\0" + repeat_to(struct.pack("<II", 1, 4096) + b"database-row\0", 16384)
    pdf = repeat_to(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\nstream\nxai compression\nendstream\n", 8192)
    samples = [
        Sample("text_readme_4k", "readme", "text", ".md", readme[:4096], "README.md"),
        Sample("text_readme_16k", "readme-expanded", "text", ".txt", repeat_to(readme, 16384), "README repeated"),
        Sample("text_lorem_64k", "lorem", "text", ".txt", repeat_to(b"Information theory makes lossless compression measurable. ", 65536), "generated deterministic text"),
        Sample("code_python_4k", "compression-py", "source_code", ".py", code[:4096], "xai_compress/compression.py"),
        Sample("code_python_16k", "compression-py-expanded", "source_code", ".py", repeat_to(code, 16384), "compression.py repeated"),
        Sample("code_json_config", "model-search-config", "json", ".json", config[:max_sample_bytes], "configs/model_search_v2.json"),
        Sample("json_lines_16k", "json-lines", "json", ".jsonl", json_lines, "generated deterministic JSONL"),
        Sample("csv_benchmark", "phase-i-csv", "csv", ".csv", csv_data[:max_sample_bytes], "phase_i_actual_benchmark.csv"),
        Sample("csv_numeric_16k", "numeric-csv", "csv", ".csv", repeat_to(b"1,2,3,4,5,6,7,8\n", 16384), "generated deterministic CSV"),
        Sample("xml_16k", "xml-records", "xml", ".xml", xml, "generated deterministic XML"),
        Sample("logs_16k", "kaggle-log", "logs", ".log", log_data[:16384], "existing Kaggle log"),
        Sample("pdf_8k", "pdf-fragment", "pdf", ".pdf", pdf, "generated valid-signature PDF fragment"),
        Sample("image_ppm", "validation-image", "image", ".ppm", image[:max_sample_bytes], str(image_path.relative_to(ROOT)) if image_path.is_file() else "generated PPM"),
        Sample("audio_wav", "sine-wave", "audio", ".wav", wav_bytes(), "generated deterministic PCM WAV"),
        Sample("video_mp4_fragment", "ff-c23-video", "video", ".mp4", video[:max_sample_bytes], str(mp4) if mp4 else "generated ISO media fragment"),
        Sample("executable_fragment", "python-executable", "executable", ".exe", executable, str(sys.executable)),
        Sample("model_checkpoint", "protected-gru-fragment", "model", ".pt", checkpoint, "protected GRU prefix only"),
        Sample("database_fragment", "sqlite-fragment", "database", ".sqlite", database, "generated deterministic SQLite-like fragment"),
        Sample("numeric_float", "numeric-float", "scientific", ".bin", numeric, "generated float32 array"),
        Sample("numeric_delta", "numeric-delta", "scientific", ".bin", numeric_delta, "generated monotonic int32 array"),
        Sample("random_4k", "random-4k", "random", ".bin", random_4k, "generated seeded random"),
        Sample("random_16k", "random-16k", "random", ".bin", random_16k, "generated seeded random"),
        Sample("repetitive_4k", "repeat-4k", "repetitive", ".bin", repeat_to(b"ABCD", 4096), "generated repetitive"),
        Sample("repetitive_64k", "repeat-64k", "repetitive", ".bin", repeat_to(b"XAI-COMPRESS|", 65536), "generated repetitive"),
        Sample("zeros_16k", "zeros", "repetitive", ".bin", b"\0" * 16384, "generated zero run"),
        Sample("gzip_text", "gzip-readme", "already_compressed", ".gz", gzip.compress(readme), "gzip-compressed README"),
        Sample("gzip_random", "gzip-random", "already_compressed", ".gz", gzip.compress(random_16k), "gzip-compressed seeded random"),
        # Small complete inputs provide actual neural-codec calibration without
        # turning selector-data generation into another long neural training job.
        Sample("neural_text_256", "neural-text", "neural_calibration", ".txt", repeat_to(b"byte context model ", 256), "generated neural calibration"),
        Sample("neural_binary_256", "neural-binary", "neural_calibration", ".bin", bytes(range(256)), "generated neural calibration"),
    ]
    return [Sample(s.sample_id, s.source_group, s.category, s.extension, s.data[:max_sample_bytes], s.origin) for s in samples]


def split_manifest(samples: list[Sample]) -> dict[str, str]:
    by_category: dict[str, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_category[sample.category].append(sample)
    result: dict[str, str] = {}
    for category, values in sorted(by_category.items()):
        ordered = sorted(values, key=lambda item: hashlib.sha256(("20260901|" + item.source_group).encode()).hexdigest())
        for index, sample in enumerate(ordered):
            if len(ordered) == 1:
                split = "train"
            elif index == len(ordered) - 1:
                split = "test"
            elif len(ordered) >= 3 and index == len(ordered) - 2:
                split = "validation"
            else:
                split = "train"
            result[sample.source_group] = split
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "hybrid_ai" / "selector_dataset.csv")
    parser.add_argument("--max-sample-bytes", type=int, default=65536)
    parser.add_argument("--include-neural", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    samples = build_samples(args.max_sample_bytes)
    splits = split_manifest(samples)
    registry = available_registry(device="cpu")
    all_rows: list[dict] = []
    feature_names: set[str] = set()
    for sample_index, sample in enumerate(samples, 1):
        features = extract_features(sample.data, file_size=len(sample.data), extension=sample.extension)
        feature_names.update(features)
        strategies = candidate_catalog(include_neural=args.include_neural and len(sample.data) <= 256)
        for strategy in strategies:
            if strategy.codec not in registry:
                continue
            try:
                measured = measure_strategy(sample.data, strategy, registry)
            except Exception as exc:
                print(f"N/A {sample.sample_id} {strategy.strategy_id}: {exc}", flush=True)
                continue
            measured.pop("payload", None)
            measured["codec_metadata"] = json.dumps(measured["codec_metadata"], sort_keys=True)
            measured["transform_metadata"] = json.dumps(measured["transform_metadata"], sort_keys=True)
            row = {
                "sample_id": sample.sample_id,
                "source_group": sample.source_group,
                "source_category": sample.category,
                "split": splits[sample.source_group],
                "source_origin": sample.origin,
                "source_size": len(sample.data),
                "source_sha256": hashlib.sha256(sample.data).hexdigest(),
                **features,
                **measured,
            }
            all_rows.append(row)
        print(f"MEASURED {sample_index}/{len(samples)} {sample.sample_id}", flush=True)

    fields = sorted({key for row in all_rows for key in row})
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        grouped[row["sample_id"]].append(row)
    labels: list[dict] = []
    profiles = load_profiles()
    for sample_id, rows in sorted(grouped.items()):
        for profile in profiles:
            ranked = label_measurements(rows, profile, profiles)
            winner = ranked[0]
            labels.append(
                {
                    "sample_id": sample_id,
                    "source_group": winner["source_group"],
                    "source_category": winner["source_category"],
                    "split": winner["split"],
                    "profile": profile,
                    "best_strategy": winner["strategy_id"],
                    "best_codec": winner["codec"],
                    "best_level": winner["level"],
                    "best_transform": winner["transform"],
                    "expected_bpb": winner["actual_bpb"],
                    "expected_compression_time": winner["compression_seconds"],
                    "expected_decompression_time": winner["decompression_seconds"],
                    "profile_score": winner["profile_score"],
                }
            )
    label_path = args.output.with_name("selector_labels.csv")
    with label_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(labels[0]))
        writer.writeheader()
        writer.writerows(labels)
    (args.output.parent / "split_manifest.json").write_text(
        json.dumps(
            {
                "seed": 20260901,
                "split_unit": "source_group",
                "assignments": splits,
                "counts": dict(sorted(Counter(splits.values()).items())),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (args.output.parent / "selector_feature_schema.json").write_text(
        json.dumps({"features": sorted(feature_names), "categorical": ["extension", "mime_category", "magic_signature_category"]}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"samples": len(samples), "measurements": len(all_rows), "labels": len(labels), "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
