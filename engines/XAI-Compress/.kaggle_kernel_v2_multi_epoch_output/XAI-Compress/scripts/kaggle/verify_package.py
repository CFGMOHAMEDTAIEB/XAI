from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def verify(root: Path) -> dict:
    required = ["dataset-metadata.json", "source-sha256.json", "pyproject.toml", "xai_compress/__init__.py", "xai_compress/train.py"]
    missing = [item for item in required if not (root / item).is_file()]
    forbidden = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and (".venv" in p.parts or p.suffix in {".pt", ".xaic", ".pyc"})]
    if missing or forbidden:
        raise SystemExit(f"Package verification failed: missing={missing}, forbidden={forbidden[:10]}")
    metadata = json.loads((root / "dataset-metadata.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "source-sha256.json").read_text(encoding="utf-8"))
    mismatches = {
        name: {"expected": expected, "actual": hashlib.sha256((root / name).read_bytes()).hexdigest() if (root / name).is_file() else None}
        for name, expected in manifest.items()
        if not (root / name).is_file() or hashlib.sha256((root / name).read_bytes()).hexdigest() != expected
    }
    if mismatches:
        raise SystemExit(f"Package hash verification failed: {mismatches}")
    result = {"dataset_id": metadata["id"], "files": sum(p.is_file() for p in root.rglob("*")), "verified": True}
    print(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("path", type=Path); verify(parser.parse_args().path)
