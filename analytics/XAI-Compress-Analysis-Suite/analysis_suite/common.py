from __future__ import annotations
import hashlib, os, time
from pathlib import Path
import psutil


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def timed_with_memory(function, *args, **kwargs):
    process = psutil.Process(os.getpid())
    before = process.memory_info().rss
    start = time.perf_counter()
    result = function(*args, **kwargs)
    elapsed = time.perf_counter() - start
    after = process.memory_info().rss
    return result, elapsed, max(0, after - before)


def category(path: Path) -> str:
    suffix = path.suffix.lower() or '[no-extension]'
    groups = {
        'text': {'.txt', '.log', '.md', '.csv', '.tsv', '.json', '.jsonl', '.xml', '.yaml', '.yml'},
        'already_compressed': {'.zip', '.7z', '.rar', '.gz', '.bz2', '.xz', '.jpg', '.jpeg', '.png', '.mp3', '.mp4', '.pdf'},
        'database': {'.db', '.sqlite', '.sqlite3'},
        'numpy': {'.npy', '.npz'},
        'binary': {'.bin', '.dat', '.exe', '.dll'},
    }
    for name, extensions in groups.items():
        if suffix in extensions:
            return name
    return 'other'
