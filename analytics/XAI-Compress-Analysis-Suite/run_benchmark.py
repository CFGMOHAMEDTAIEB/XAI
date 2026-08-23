from __future__ import annotations
import argparse, bz2, csv, gzip, lzma, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from analysis_suite.common import category, sha256_bytes, timed_with_memory


def classical_codecs():
    codecs = {
        'gzip': (gzip.compress, gzip.decompress),
        'bz2': (bz2.compress, bz2.decompress),
        'lzma': (lzma.compress, lzma.decompress),
    }
    try:
        import zstandard as zstd
        codecs['zstd'] = (zstd.ZstdCompressor(level=3).compress, zstd.ZstdDecompressor().decompress)
    except ImportError:
        pass
    try:
        import brotli
        codecs['brotli'] = (brotli.compress, brotli.decompress)
    except ImportError:
        pass
    return codecs


def result_row(path, codec, data, artifact, restored, compress_s, decompress_s, comp_mem, decomp_mem):
    original_size = len(data)
    compressed_size = len(artifact)
    equal = restored == data and sha256_bytes(restored) == sha256_bytes(data)
    denominator = max(1, original_size)
    return {
        'file': str(path),
        'file_name': path.name,
        'extension': path.suffix.lower() or '[none]',
        'category': category(path),
        'codec': codec,
        'original_size': original_size,
        'compressed_size_total': compressed_size,
        'compression_ratio': original_size / max(1, compressed_size),
        'space_saving_percent': 100.0 * (1.0 - compressed_size / denominator),
        'bits_per_byte': 8.0 * compressed_size / denominator,
        'compress_seconds': compress_s,
        'decompress_seconds': decompress_s,
        'compress_mib_per_second': (original_size / (1024 * 1024)) / max(compress_s, 1e-12),
        'decompress_mib_per_second': (original_size / (1024 * 1024)) / max(decompress_s, 1e-12),
        'compress_memory_delta_bytes': comp_mem,
        'decompress_memory_delta_bytes': decomp_mem,
        'original_sha256': sha256_bytes(data),
        'restored_sha256': sha256_bytes(restored),
        'lossless': equal,
        'error': '',
    }


def error_row(path, codec, data, error):
    return {
        'file': str(path), 'file_name': path.name, 'extension': path.suffix.lower() or '[none]',
        'category': category(path), 'codec': codec, 'original_size': len(data),
        'compressed_size_total': '', 'compression_ratio': '', 'space_saving_percent': '',
        'bits_per_byte': '', 'compress_seconds': '', 'decompress_seconds': '',
        'compress_mib_per_second': '', 'decompress_mib_per_second': '',
        'compress_memory_delta_bytes': '', 'decompress_memory_delta_bytes': '',
        'original_sha256': sha256_bytes(data), 'restored_sha256': '', 'lossless': False,
        'error': f'{type(error).__name__}: {error}',
    }


def main():
    parser = argparse.ArgumentParser(description='Fair XAI-Compress benchmark')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--checkpoint')
    parser.add_argument('--output', required=True)
    parser.add_argument('--max-file-size', type=int, default=256 * 1024 * 1024)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    paths = sorted(p for p in data_dir.rglob('*') if p.is_file())
    if not paths:
        raise SystemExit(f'No test files found under {data_dir}')

    from xai_compress.compression import compress_bytes, decompress_bytes
    rows = []
    codecs = classical_codecs()
    for path in paths:
        size = path.stat().st_size
        if size > args.max_file_size:
            print(f'SKIP too large for current in-memory benchmark: {path} ({size} bytes)')
            continue
        data = path.read_bytes()
        for name, (encoder, decoder) in codecs.items():
            try:
                artifact, ct, cm = timed_with_memory(encoder, data)
                restored, dt, dm = timed_with_memory(decoder, artifact)
                rows.append(result_row(path, name, data, artifact, restored, ct, dt, cm, dm))
            except Exception as exc:
                rows.append(error_row(path, name, data, exc))

        modes = [('xai_static', 'static', None)]
        if args.checkpoint:
            modes.append(('xai_neural', 'neural', args.checkpoint))
        for name, mode, checkpoint in modes:
            try:
                artifact, ct, cm = timed_with_memory(compress_bytes, data, mode, checkpoint)
                restored, dt, dm = timed_with_memory(decompress_bytes, artifact, checkpoint)
                rows.append(result_row(path, name, data, artifact, restored, ct, dt, cm, dm))
            except Exception as exc:
                rows.append(error_row(path, name, data, exc))

    if not rows:
        raise SystemExit('No benchmark rows were produced')
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    failures = sum(not bool(row['lossless']) for row in rows)
    print({'rows': len(rows), 'files': len(set(row['file'] for row in rows)), 'failures': failures, 'output': str(output)})

if __name__ == '__main__':
    main()
