from __future__ import annotations

import hashlib
import os
from pathlib import Path


def write_corpus(root: Path) -> Path:
    root = Path(root)
    mapping = {
        "text/article.txt": (
            "The history of lossless compression is a history of probability. "
            "Shannon showed that the cross-entropy of a model is the compressed size. "
            * 40
        ).encode(),
        "text/log.txt": b"".join(f"2026-08-27T17:00:{i:02d} INFO worker={i%3} status=ok\n".encode() for i in range(200)),
        "code/sample.py": (
            "def fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n\n"
            * 30
        ).encode(),
        "code/sample.js": (b"export const add = (a, b) => a + b;\n" * 80),
        "structured/data.json": (
            '{"users":[' + ",".join(f'{{"id":{i},"name":"user{i}"}}' for i in range(80)) + "]}"
        ).encode(),
        "structured/table.csv": b"id,name,value\n" + b"".join(f"{i},item{i},{i*i}\n".encode() for i in range(120)),
        "structured/doc.xml": b"<root>" + b"".join(f"<row id='{i}'>value</row>".encode() for i in range(80)) + b"</root>",
        "binary/pattern.bin": bytes(range(256)) * 32,
        "binary/nulls.bin": b"\x00\x01\xff" * 1000,
        "high_entropy/random.rand": hashlib.sha256(b"seed").digest() * 200,
        "repetitive/zeros.bin": b"\x00" * 4096,
    }
    for rel, data in mapping.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root
