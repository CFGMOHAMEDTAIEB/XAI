from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from ..compression import compress_bytes, decompress_bytes
from ..utils.metrics import bits_per_byte, compression_ratio, throughput_mbs


@dataclass
class BenchmarkRow:
    dataset: str
    file: str
    category: str
    codec: str
    original_size: int
    compressed_size: int
    ratio: float
    bpb: float
    compress_seconds: float
    decompress_seconds: float
    compress_mbs: float
    decompress_mbs: float
    lossless: bool
    notes: str = ""


def _timed(fn, *args):
    start = time.perf_counter()
    out = fn(*args)
    return out, time.perf_counter() - start


def _python_codecs() -> dict[str, tuple[Callable[[bytes], bytes], Callable[[bytes], bytes]]]:
    import bz2
    import gzip
    import lzma

    codecs = {
        "gzip": (lambda b: gzip.compress(b, 9), gzip.decompress),
        "bz2": (bz2.compress, bz2.decompress),
        "lzma": (lzma.compress, lzma.decompress),
    }
    try:
        import zstandard as zstd

        codecs["zstd"] = (zstd.ZstdCompressor(level=19).compress, zstd.ZstdDecompressor().decompress)
    except ImportError:
        pass
    try:
        import brotli

        codecs["brotli"] = (lambda b: brotli.compress(b, quality=11), brotli.decompress)
    except ImportError:
        pass
    return codecs


def _run_external(cmd: list[str], data: bytes, tmp: Path) -> bytes | None:
    src = tmp / "in.bin"
    dst = tmp / "out.bin"
    src.write_bytes(data)
    try:
        subprocess.run(cmd + [str(src), str(dst)], check=True, capture_output=True, timeout=120)
        if dst.is_file():
            return dst.read_bytes()
    except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None
    return None


def classify_file(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".py": "code",
        ".c": "code",
        ".cpp": "code",
        ".h": "code",
        ".js": "code",
        ".ts": "code",
        ".rs": "code",
        ".json": "structured",
        ".csv": "structured",
        ".xml": "structured",
        ".yml": "structured",
        ".yaml": "structured",
        ".txt": "text",
        ".md": "text",
        ".log": "text",
        ".bin": "binary",
        ".exe": "binary",
        ".rand": "high_entropy",
    }
    return mapping.get(suffix, "mixed")


def benchmark_file(path: Path, checkpoint: str | None, tmp: Path, include_external: bool = True) -> list[BenchmarkRow]:
    data = path.read_bytes()
    rows: list[BenchmarkRow] = []
    dataset = path.parent.name

    def add(codec: str, blob: bytes, restored: bytes, ct: float, dt: float, notes: str = "") -> None:
        rows.append(
            BenchmarkRow(
                dataset=dataset,
                file=str(path),
                category=classify_file(path),
                codec=codec,
                original_size=len(data),
                compressed_size=len(blob),
                ratio=compression_ratio(len(data), len(blob)),
                bpb=bits_per_byte(len(blob), len(data)),
                compress_seconds=ct,
                decompress_seconds=dt,
                compress_mbs=throughput_mbs(len(data), ct),
                decompress_mbs=throughput_mbs(len(data), dt),
                lossless=restored == data,
                notes=notes,
            )
        )

    for name, (enc, dec) in _python_codecs().items():
        blob, ct = _timed(enc, data)
        restored, dt = _timed(dec, blob)
        add(name, blob, restored, ct, dt)

    blob, ct = _timed(compress_bytes, data, "static")
    restored, dt = _timed(decompress_bytes, blob)
    add("xai_static", blob, restored, ct, dt)

    blob, ct = _timed(compress_bytes, data, "hybrid", checkpoint)
    restored, dt = _timed(decompress_bytes, blob, checkpoint)
    add("xai_hybrid", blob, restored, ct, dt)

    if checkpoint:
        blob, ct = _timed(compress_bytes, data, "neural", checkpoint)
        restored, dt = _timed(decompress_bytes, blob, checkpoint)
        add("xai_neural", blob, restored, ct, dt)

    if include_external and shutil.which("7z"):
        src = tmp / "ext_in.bin"
        archive = tmp / "ext.7z"
        src.write_bytes(data)
        t0 = time.perf_counter()
        try:
            subprocess.run(["7z", "a", "-t7z", "-mx=9", str(archive), str(src)], check=True, capture_output=True, timeout=120)
            ct = time.perf_counter() - t0
            blob = archive.read_bytes() if archive.is_file() else b""
            out_dir = tmp / "ext_out"
            out_dir.mkdir(exist_ok=True)
            t1 = time.perf_counter()
            subprocess.run(["7z", "x", f"-o{out_dir}", str(archive)], check=True, capture_output=True, timeout=120)
            dt = time.perf_counter() - t1
            restored = (out_dir / src.name).read_bytes()
            add("7zip", blob, restored, ct, dt)
        except (subprocess.SubprocessError, OSError, FileNotFoundError):
            add("7zip", b"", b"", 0.0, 0.0, notes="unavailable")

    return rows


def run_suite(data_dir: str | Path, checkpoint: str | None = None, output: str | None = None) -> list[BenchmarkRow]:
    root = Path(data_dir)
    files = [p for p in root.rglob("*") if p.is_file()]
    rows: list[BenchmarkRow] = []
    tmp = Path(output).parent / ".bench_tmp" if output else root / ".bench_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        for path in files:
            rows.extend(benchmark_file(path, checkpoint, tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if output and rows:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
        summary = aggregate(rows)
        Path(str(out) + ".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return rows


def aggregate(rows: list[BenchmarkRow]) -> dict:
    by_codec: dict[str, dict] = {}
    for row in rows:
        item = by_codec.setdefault(
            row.codec,
            {"original": 0, "compressed": 0, "compress_seconds": 0.0, "decompress_seconds": 0.0, "files": 0, "lossless": 0},
        )
        item["original"] += row.original_size
        item["compressed"] += row.compressed_size
        item["compress_seconds"] += row.compress_seconds
        item["decompress_seconds"] += row.decompress_seconds
        item["files"] += 1
        item["lossless"] += int(row.lossless)
    report = {}
    for codec, item in by_codec.items():
        report[codec] = {
            **item,
            "ratio": compression_ratio(item["original"], item["compressed"]),
            "bpb": bits_per_byte(item["compressed"], item["original"]),
            "compress_mbs": throughput_mbs(item["original"], item["compress_seconds"]),
            "decompress_mbs": throughput_mbs(item["original"], item["decompress_seconds"]),
        }
    return report
