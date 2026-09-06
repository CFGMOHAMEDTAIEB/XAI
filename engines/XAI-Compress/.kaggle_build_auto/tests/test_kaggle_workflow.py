import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    path=ROOT/"scripts"/"kaggle"/f"{name}.py"
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def test_package_filter_and_metadata(tmp_path):
    mod=load("prepare_kaggle_package")
    project=tmp_path/"project"; (project/"xai_compress").mkdir(parents=True)
    for name in ("pyproject.toml","benchmark.py","xai_compress/__init__.py","xai_compress/train.py"): (project/name).write_text("x")
    (project/"data"/"train").mkdir(parents=True);(project/"data"/"train"/"huge.bin").write_bytes(b"x")
    (project/"run.log").write_text("secret-ish log")
    result=mod.build_package(project,tmp_path/"stage","alice","source")
    assert result["dataset_id"]=="alice/source"
    assert not (tmp_path/"stage/data/train/huge.bin").exists()
    assert not (tmp_path/"stage/run.log").exists()
    manifest=json.loads((tmp_path/"stage/source-sha256.json").read_text())
    assert set(manifest)=={"xai_compress/train.py"}
    assert load("verify_package").verify(tmp_path/"stage")["verified"] is True

def test_project_and_dataset_discovery(tmp_path):
    mod=load("kaggle_setup")
    source=tmp_path/"source";(source/"xai_compress").mkdir(parents=True);(source/"pyproject.toml").write_text("")
    data=tmp_path/"training";data.mkdir();(data/"a.bin").write_bytes(b"abc")
    assert mod.discover_project(tmp_path)==source
    stats=mod.dataset_stats(data);assert stats["files"]==1 and stats["bytes"]==3
