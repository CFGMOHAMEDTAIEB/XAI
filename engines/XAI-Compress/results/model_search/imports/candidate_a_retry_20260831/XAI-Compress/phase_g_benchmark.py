from __future__ import annotations

import argparse
import bz2
import csv
import gzip
import hashlib
import json
import lzma
import time
from pathlib import Path

from xai_compress.checkpoint import load_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes

EXCLUDED_EXTENSIONS = {'.zip', '.7z', '.rar', '.gz', '.bz2', '.xz', '.xaic', '.pt', '.pth'}
EXCLUDED_DIRS = {'.git', '.venv', '__pycache__', 'node_modules'}


def select_files(root: Path, max_files: int, max_bytes: int) -> list[Path]:
    selected = []
    total = 0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in EXCLUDED_EXTENSIONS:
            continue
        size = path.stat().st_size
        if size <= 0 or size > 50_000 or total + size > max_bytes:
            continue
        selected.append(path)
        total += size
        if len(selected) >= max_files:
            break
    if not selected:
        raise RuntimeError(f'No benchmark files selected under {root}')
    return selected


def run_codec(name, data, encode, decode, metadata=None):
    start = time.perf_counter(); blob = encode(data); compress_seconds = time.perf_counter() - start
    start = time.perf_counter(); restored = decode(blob); decompress_seconds = time.perf_counter() - start
    original_size = len(data); compressed_size = len(blob)
    return {
        'codec': name,
        'original_size': original_size,
        'compressed_size': compressed_size,
        'compression_ratio': compressed_size / max(1, original_size),
        'saving_percent': (1 - compressed_size / max(1, original_size)) * 100,
        'compression_seconds': compress_seconds,
        'decompression_seconds': decompress_seconds,
        'compression_mb_per_sec': original_size / (1024 * 1024) / max(compress_seconds, 1e-12),
        'decompression_mb_per_sec': original_size / (1024 * 1024) / max(decompress_seconds, 1e-12),
        'sha256_match': hashlib.sha256(restored).digest() == hashlib.sha256(data).digest(),
        **(metadata or {}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data_dir', type=Path)
    parser.add_argument('--v1', required=True)
    parser.add_argument('--v2', required=True)
    parser.add_argument('--output', type=Path, default=Path('phase_g_results.csv'))
    parser.add_argument('--max-files', type=int, default=25)
    parser.add_argument('--max-bytes', type=int, default=5_000_000)
    args = parser.parse_args()

    files = select_files(args.data_dir, args.max_files, args.max_bytes)
    models = {}
    for label, checkpoint in [('V1', args.v1), ('V2', args.v2)]:
        model, _ = load_checkpoint(checkpoint, 'cpu')
        models[label] = {
            'checkpoint': checkpoint,
            'parameter_count': sum(p.numel() for p in model.parameters()),
            'model_config': model.config.__dict__,
        }

    rows = []
    for path in files:
        data = path.read_bytes()
        base = {'file': str(path), 'file_extension': path.suffix.lower() or '[none]'}
        codecs = [
            ('static_xai', lambda x: compress_bytes(x, mode='static'), lambda x: decompress_bytes(x)),
            ('gzip', gzip.compress, gzip.decompress),
            ('bz2', bz2.compress, bz2.decompress),
            ('lzma', lzma.compress, lzma.decompress),
        ]
        try:
            import zstandard as zstd
            zc, zd = zstd.ZstdCompressor().compress, zstd.ZstdDecompressor().decompress
            codecs.append(('zstd', zc, zd))
        except ImportError:
            pass
        try:
            import brotli
            codecs.append(('brotli', brotli.compress, brotli.decompress))
        except ImportError:
            pass
        for name, encode, decode in codecs:
            rows.append({**base, **run_codec(name, data, encode, decode)})
        for label, checkpoint in [('V1', args.v1), ('V2', args.v2)]:
            metadata = models[label]
            rows.append({**base, **run_codec(
                f'neural_{label}', data,
                lambda x, ck=checkpoint: compress_bytes(x, mode='neural', checkpoint=ck),
                lambda x, ck=checkpoint: decompress_bytes(x, checkpoint=ck),
                metadata,
            )})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', newline='', encoding='utf-8') as handle:
        fieldnames = list(dict.fromkeys(field for row in rows for field in row))
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)

    summary = []
    for codec in sorted({row['codec'] for row in rows}):
        group = [row for row in rows if row['codec'] == codec]
        original = sum(row['original_size'] for row in group)
        compressed = sum(row['compressed_size'] for row in group)
        summary.append({
            'codec': codec,
            'files': len(group),
            'original_bytes': original,
            'compressed_bytes': compressed,
            'ratio': compressed / max(1, original),
            'saving_percent': (1 - compressed / max(1, original)) * 100,
            'compression_seconds': sum(row['compression_seconds'] for row in group),
            'decompression_seconds': sum(row['decompression_seconds'] for row in group),
            'sha256_all_match': all(row['sha256_match'] for row in group),
        })
    print(json.dumps({'selected_files': [str(path) for path in files], 'summary': summary}, indent=2))


if __name__ == '__main__':
    main()
