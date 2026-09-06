import hashlib, json, subprocess, time
import sys
import types
from pathlib import Path

import torch

from xai_compress.arithmetic import ArithmeticEncoder
from xai_compress.checkpoint import load_checkpoint
from xai_compress.compression import compress_bytes, decompress_bytes, logits_to_cumulative
from xai_compress.model import BOS_TOKEN

EXCLUDED = {'.zip', '.7z', '.rar', '.gz', '.bz2', '.xz', '.xaic', '.pt', '.pth'}
files = []
for p in sorted(Path('data/test').rglob('*')):
    if not p.is_file():
        continue
    if p.suffix.lower() in EXCLUDED:
        continue
    try:
        size = p.stat().st_size
    except OSError:
        continue
    if 0 < size <= 200_000:
        files.append(p)
    if len(files) >= 5:
        break

if not files:
    raise RuntimeError('No benchmark files found under data/test')

legacy_src = subprocess.check_output(
    ['git', '-C', str(Path('C:/Users/ss/Desktop/XAI/XAI')), 'show', 'HEAD:engines/ai_compression/XAI-Compress/xai_compress/compression.py'],
    text=True,
)
project_root = Path('C:/Users/ss/Desktop/XAI/XAI/engines/ai_compression/XAI-Compress')
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

legacy_module = types.ModuleType('xai_compress.legacy_history')
legacy_module.__dict__['__package__'] = 'xai_compress'
legacy_module.__dict__['__file__'] = str(project_root / 'xai_compress' / 'compression.py')
legacy_module.__dict__['__name__'] = 'xai_compress.legacy_history'
sys.modules['xai_compress.legacy_history'] = legacy_module
exec(legacy_src, legacy_module.__dict__)
legacy_logits_to_cumulative = legacy_module.logits_to_cumulative
legacy_compress_bytes = legacy_module.compress_bytes
legacy_decompress_bytes = legacy_module.decompress_bytes

model, _ = load_checkpoint('checkpoints/gru_hq_v1.pt', 'cpu')
model.eval()

rows = []
for p in files:
    data = p.read_bytes()
    sha = hashlib.sha256(data).hexdigest()

    def legacy_run():
        return legacy_compress_bytes(data, mode='neural', checkpoint='checkpoints/gru_hq_v1.pt')

    def optimized_run():
        return compress_bytes(data, mode='neural', checkpoint='checkpoints/gru_hq_v1.pt')

    def static_run():
        return compress_bytes(data, mode='static')

    for label, runner in [('static', static_run), ('legacy_neural', legacy_run), ('optimized_neural', optimized_run)]:
        t0 = time.perf_counter(); blob = runner(); ct = time.perf_counter() - t0
        if label == 'legacy_neural':
            t1 = time.perf_counter(); restored = legacy_decompress_bytes(blob, checkpoint='checkpoints/gru_hq_v1.pt'); dt = time.perf_counter() - t1
        elif label == 'optimized_neural':
            t1 = time.perf_counter(); restored = decompress_bytes(blob, checkpoint='checkpoints/gru_hq_v1.pt'); dt = time.perf_counter() - t1
        else:
            t1 = time.perf_counter(); restored = decompress_bytes(blob); dt = time.perf_counter() - t1
        ok = restored == data and hashlib.sha256(restored).hexdigest() == sha
        rows.append({
            'file': str(p),
            'codec': label,
            'original_size': len(data),
            'compressed_size': len(blob),
            'compression_ratio': len(blob) / max(1, len(data)),
            'compression_percent': (1 - len(blob) / max(1, len(data))) * 100.0,
            'compression_time_seconds': ct,
            'decompression_time_seconds': dt,
            'restored_size': len(restored),
            'sha256_match': ok,
        })

    # deterministic output check for optimized neural path
    again = compress_bytes(data, mode='neural', checkpoint='checkpoints/gru_hq_v1.pt')
    rows.append({
        'file': str(p),
        'codec': 'deterministic_check',
        'original_size': len(data),
        'compressed_size': len(again),
        'compression_ratio': len(again) / max(1, len(data)),
        'compression_percent': (1 - len(again) / max(1, len(data))) * 100.0,
        'compression_time_seconds': 0.0,
        'decompression_time_seconds': 0.0,
        'restored_size': len(data),
        'sha256_match': again == compress_bytes(data, mode='neural', checkpoint='checkpoints/gru_hq_v1.pt'),
    })

print(json.dumps(rows, indent=2))
