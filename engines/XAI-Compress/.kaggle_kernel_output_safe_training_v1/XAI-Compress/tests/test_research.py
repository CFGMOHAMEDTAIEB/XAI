import csv
import json

from xai_compress.datasets.pipeline import dataset_report
from xai_compress.research import ExperimentRecord, append_experiment, machine_manifest, read_csv, utc_now


def test_experiment_log_and_manifest(tmp_path):
    path = tmp_path / "experiments.csv"
    record = ExperimentRecord("exp-test", utc_now(), "completed", model="tiny")
    append_experiment(path, record)
    rows = read_csv(path)
    assert rows[0]["experiment_id"] == "exp-test"
    assert rows[0]["model"] == "tiny"
    manifest = machine_manifest()
    assert manifest["timestamp_utc"]
    assert "software" in manifest


def test_dataset_report_is_bounded_and_deduplicated(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"AB" * 100)
    (tmp_path / "duplicate.txt").write_bytes(b"AB" * 100)
    (tmp_path / "b.bin").write_bytes(bytes(range(256)))
    report = dataset_report(tmp_path, sample_bytes=32)
    assert report["files_discovered"] == 3
    assert report["files_unique"] == 2
    assert report["sampled_bytes"] <= 64
    assert len(report["byte_frequencies"]) == 256
