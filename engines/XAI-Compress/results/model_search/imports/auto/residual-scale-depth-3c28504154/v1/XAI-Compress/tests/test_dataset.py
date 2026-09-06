from pathlib import Path
from xai_compress.datasets.pipeline import content_id, dedupe_paths, split_paths
from xai_compress.train import ByteContextDataset


def test_dataset_lazy_and_split(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    c = tmp_path / "c.txt"
    a.write_bytes(b"hello world " * 50)
    b.write_bytes(b"other file content " * 40)
    c.write_bytes(a.read_bytes())
    unique = dedupe_paths([a, b, c])
    assert len(unique) == 2
    train, val, test = split_paths(unique, seed=0, val_frac=0.5, test_frac=0.0)
    assert train or val
    ds = ByteContextDataset(tmp_path, context_length=8, stride=8, max_samples=20, max_bytes_per_file=4096, seed=1)
    x, y = ds[0]
    assert len(x) == len(y)
    assert ds.summary["samples"] >= 1


def test_content_id_stable(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert content_id(p) == content_id(p)
