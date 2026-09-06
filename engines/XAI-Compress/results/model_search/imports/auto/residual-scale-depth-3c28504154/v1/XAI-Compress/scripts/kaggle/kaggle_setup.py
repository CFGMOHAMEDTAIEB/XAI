from __future__ import annotations
import importlib.util, json, shutil, subprocess, sys
from collections import Counter
from pathlib import Path

def discover_project(input_root=Path("/kaggle/input")) -> Path:
    candidates = [p.parent for p in input_root.rglob("pyproject.toml") if (p.parent / "xai_compress").is_dir()]
    if not candidates: raise FileNotFoundError("No attached Kaggle input contains pyproject.toml and xai_compress/")
    return sorted(candidates, key=lambda p: len(p.parts))[0]

def discover_datasets(input_root=Path("/kaggle/input"), project=None):
    project = project.resolve() if project else None
    return [p for p in sorted(input_root.iterdir()) if p.is_dir() and (not project or p.resolve() not in project.parents and p.resolve() != project)]

def dataset_stats(root: Path) -> dict:
    files = [p for p in root.rglob("*") if p.is_file()]
    sizes=[];readable=0
    excluded_extensions={".zip",".7z",".rar",".gz",".bz2",".xz",".xaic",".pt",".pth"}
    for p in files:
        try:
            size=p.stat().st_size
            with p.open("rb") as handle: handle.read(1)
            readable += 1;sizes.append((p,size))
        except OSError: pass
    supported=sum(p.suffix.lower() not in excluded_extensions and s>0 for p,s in sizes)
    return {"path": str(root), "files": len(files), "bytes": sum(s for _, s in sizes),
            "readable_files":readable, "supported_files":supported,
            "excluded_files":len(files)-supported,
            "extensions": dict(Counter(p.suffix.lower() or "<none>" for p, _ in sizes)),
            "largest": [{"path": str(p), "bytes": s} for p, s in sorted(sizes, key=lambda x: x[1], reverse=True)[:10]]}

def check_dependencies(names=("torch", "numpy", "psutil")):
    missing = [n for n in names if importlib.util.find_spec(n) is None]
    if missing: raise RuntimeError("Missing offline dependencies: " + ", ".join(missing))

def setup(source=None, destination=Path("/kaggle/working/XAI-Compress")):
    source = Path(source) if source else discover_project()
    destination = Path(destination)
    if destination.exists(): shutil.rmtree(destination)
    shutil.copytree(source, destination)
    check_dependencies()
    subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(destination), "--no-deps", "--no-build-isolation"], check=True)
    return destination

if __name__ == "__main__":
    project = discover_project(); print("Detected source:", project)
    print("Inputs:", json.dumps([str(p) for p in discover_datasets(project=project)], indent=2))
    print("Writable project:", setup(project))
