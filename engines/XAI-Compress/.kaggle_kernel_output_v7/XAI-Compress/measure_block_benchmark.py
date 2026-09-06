import json, time, tracemalloc
from pathlib import Path
import torch

from xai_compress.arithmetic import ArithmeticEncoder
from xai_compress.checkpoint import load_checkpoint
from xai_compress.compression import logits_to_cumulative
from xai_compress.model import BOS_TOKEN

model, _ = load_checkpoint('checkpoints/gru_hq_v1.pt', 'cpu')
model.eval()

rows = []
for p in sorted(Path('data/test').rglob('*')):
    if not p.is_file():
        continue
    data = p.read_bytes()

    def legacy():
        enc = ArithmeticEncoder()
        hidden = None
        prev = BOS_TOKEN
        with torch.inference_mode():
            for symbol in data:
                logits, hidden = model.step(prev, hidden)
                enc.write(logits_to_cumulative(logits), symbol)
                prev = symbol
        return enc.finish()

    def optimized():
        enc = ArithmeticEncoder()
        hidden = None
        prev = BOS_TOKEN
        with torch.inference_mode():
            for block_start in range(0, len(data), 4096):
                block = data[block_start:block_start + 4096]
                if not block:
                    continue
                seq = [prev] + list(block[:-1])
                logits, hidden = model.forward_sequence(torch.tensor(seq, dtype=torch.long), hidden)
                for logit, symbol in zip(logits, block):
                    enc.write_fast(logits_to_cumulative(logit), symbol)
                prev = block[-1]
        return enc.finish()

    tracemalloc.start()
    t = time.perf_counter(); old = legacy(); old_t = time.perf_counter() - t
    _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()

    tracemalloc.start()
    t = time.perf_counter(); newb = optimized(); new_t = time.perf_counter() - t
    _, peak2 = tracemalloc.get_traced_memory(); tracemalloc.stop()

    rows.append({
        'file': p.name,
        'orig': len(data),
        'legacy_sec': round(old_t, 4),
        'optimized_sec': round(new_t, 4),
        'speedup': round(old_t / max(new_t, 1e-9), 2),
        'legacy_peak_mb': round(peak / 1024 / 1024, 3),
        'optimized_peak_mb': round(peak2 / 1024 / 1024, 3),
        'same': old == newb,
    })

print(json.dumps(rows, indent=2))
