from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
from pathlib import Path

EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".idea", ".vscode", "dist", "build", "target", ".test-tmp", "xai_compress.egg-info"}
EXCLUDED_GLOBS = ("*.pyc", "*.pyo", "*.tmp", "*.log", "*.xaic", "*.pt", "*.pth", "*.metrics.csv")
EXCLUDED_ROOTS = {"data", "checkpoints", "results"}
REQUIRED = ("pyproject.toml", "xai_compress", "benchmark.py")


def should_include(relative: Path) -> bool:
    if any(part in EXCLUDED_DIRS or part.startswith(".kaggle_") for part in relative.parts):
        return False
    if relative.parts and relative.parts[0] in EXCLUDED_ROOTS:
        return relative.as_posix() in {"data/README.md", "results/README.md"}
    return not any(fnmatch.fnmatch(relative.name.lower(), pattern) for pattern in EXCLUDED_GLOBS)


def validate_project(root: Path) -> None:
    missing = [name for name in REQUIRED if not (root / name).exists()]
    if missing:
        raise SystemExit(f"Invalid XAI-Compress project; missing: {', '.join(missing)}")


def build_package(root: Path, staging: Path, username: str, slug: str) -> dict:
    root, staging = root.resolve(), staging.resolve()
    validate_project(root)
    if staging == root or root in staging.parents and staging.name != ".kaggle_build":
        raise ValueError("staging must be a dedicated build directory")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    copied = 0
    for source in root.rglob("*"):
        rel = source.relative_to(root)
        if not source.is_file() or not should_include(rel):
            continue
        target = staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    metadata = {
        "title": "XAI-Compress Source",
        "id": f"{username}/{slug}",
        "licenses": [{"name": "other"}],
        "isPrivate": True,
    }
    (staging / "dataset-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"dataset_id": metadata["id"], "files": copied, "staging": str(staging)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--username", default=os.getenv("KAGGLE_USERNAME"))
    parser.add_argument("--dataset", default=os.getenv("KAGGLE_DATASET", "xai-compress-source"))
    args = parser.parse_args()
    if not args.username:
        raise SystemExit("Set KAGGLE_USERNAME or pass --username")
    staging = args.staging or args.project / ".kaggle_build"
    print(json.dumps(build_package(args.project, staging, args.username, args.dataset), indent=2))


if __name__ == "__main__":
    main()
