from xai_compress.benchmarks.suite import aggregate, classify_file
from xai_compress.benchmarks.suite import BenchmarkRow


def test_aggregate_and_classify(tmp_path):
    (tmp_path / "a.py").write_text("print(1)\n")
    assert classify_file(tmp_path / "a.py") == "code"
    rows = [
        BenchmarkRow("d", "a", "text", "gzip", 100, 40, 2.5, 3.2, 0.01, 0.01, 1, 1, True),
        BenchmarkRow("d", "b", "text", "gzip", 50, 20, 2.5, 3.2, 0.01, 0.01, 1, 1, True),
    ]
    summary = aggregate(rows)
    assert summary["gzip"]["original"] == 150
    assert summary["gzip"]["lossless"] == 2
