from __future__ import annotations
import json, time
from pathlib import Path
from xai_compress.compression import compress_bytes, decompress_bytes

DATA_DIR = Path('data/test')
EXCLUDE = {'.zip', '.7z', '.rar', '.gz', '.bz2', '.xz', '.xaic', '.pt', '.pth'}
EXCLUDE_DIRS = {'.git', '.venv', '__pycache__', 'node_modules'}
MAX_FILES = 25
MAX_SIZE = 200_000

files: list[Path] = []
for p in sorted(DATA_DIR.rglob('*')):
    if not p.is_file():
        continue
    if any(part in EXCLUDE_DIRS for part in p.parts):
        continue
    if p.suffix.lower() in EXCLUDE:
        continue
    try:
        size = p.stat().st_size
    except OSError:
        continue
    if 0 < size <= MAX_SIZE:
        files.append(p)
    if len(files) >= MAX_FILES:
        break

if not files:
    raise RuntimeError(f'No benchmark files found under {DATA_DIR}')

print(json.dumps({'selected_files': len(files), 'max_size_bytes': MAX_SIZE}, indent=2))

for ck in ['checkpoints/gru_hq_v1.pt', 'checkpoints/gru_smoke.pt']:
    total_orig = 0
    total_comp = 0
    total_time_c = 0.0
    total_time_d = 0.0
    ok = True
    good = 0
    for p in files:
        try:
            data = p.read_bytes()
        except OSError:
            continue
        total_orig += len(data)

        t0 = time.perf_counter()
        blob = compress_bytes(data, mode='neural', checkpoint=ck)
        ct = time.perf_counter() - t0

        t1 = time.perf_counter()
        restored = decompress_bytes(blob, checkpoint=ck)
        dt = time.perf_counter() - t1

        total_comp += len(blob)
        total_time_c += ct
        total_time_d += dt

        if restored != data:
            ok = False
            break
        good += 1

    print(json.dumps({
        'checkpoint': ck,
        'files_processed': good,
        'original_total_bytes': total_orig,
        'compressed_total_bytes': total_comp,
        'compression_ratio': (total_comp / total_orig) if total_orig else 0.0,
        'avg_bits_per_byte': ((8.0 * total_comp) / total_orig) if total_orig else 0.0,
        'compress_seconds': total_time_c,
        'decompress_seconds': total_time_d,
        'compress_mb_per_sec': ((total_orig / (1024 * 1024)) / total_time_c) if total_time_c else 0.0,
        'decompress_mb_per_sec': ((total_orig / (1024 * 1024)) / total_time_d) if total_time_d else 0.0,
        'roundtrip_ok': ok,
    }, indent=2))
