"""Fetch the unchanged official API 35 archive into the Android CLI cache."""
import concurrent.futures
import hashlib
import os
from pathlib import Path
import time
import urllib.request

URL = 'https://dl.google.com/android/repository/sys-img/google_apis/x86_64-35_r09.zip'
SIZE = 1738815903
SHA1 = '0103e6dab21290c4b9d16550a3ce99476f884eef'
CACHE = Path(r'C:\Users\ss\AppData\Local\Android\sdk\.sdk\arch')
TARGET = CACHE / SHA1
TEMP = CACHE / (SHA1 + '.parallel')
CHUNK = 4 * 1024 * 1024

def fetch(start):
    end = min(start + CHUNK, SIZE) - 1
    for attempt in range(4):
        try:
            request = urllib.request.Request(URL, headers={'Range': f'bytes={start}-{end}'})
            with urllib.request.urlopen(request, timeout=90) as response:
                if response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {start}-{end}/'):
                    raise RuntimeError('Server did not return the requested byte range')
                remaining = end - start + 1
                with TEMP.open('r+b') as stream:
                    stream.seek(start)
                    while remaining:
                        block = response.read(min(262144, remaining))
                        if not block:
                            raise RuntimeError('Incomplete HTTP range')
                        stream.write(block)
                        remaining -= len(block)
            return end - start + 1
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2)

CACHE.mkdir(parents=True, exist_ok=True)
with TEMP.open('wb') as stream:
    stream.truncate(SIZE)
started = time.monotonic()
completed = 0
last_print = started
with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
    futures = [pool.submit(fetch, start) for start in range(0, SIZE, CHUNK)]
    for future in concurrent.futures.as_completed(futures):
        completed += future.result()
        now = time.monotonic()
        if now - last_print >= 10 or completed == SIZE:
            print(f'{completed / SIZE:.1%}, {completed / 1048576:.0f} MiB, {completed / (now-started) / 1048576:.2f} MiB/s', flush=True)
            last_print = now
with TEMP.open('rb') as stream:
    actual = hashlib.file_digest(stream, 'sha1').hexdigest()
if actual != SHA1:
    raise RuntimeError(f'Official archive checksum mismatch: {actual}')
os.replace(TEMP, TARGET)
print(f'VERIFIED SHA1={actual}; cached at {TARGET}', flush=True)
