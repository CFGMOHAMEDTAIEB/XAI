from pathlib import Path

def test_training_source_has_no_read_bytes():
    source=(Path(__file__).parents[1]/"xai_compress"/"train.py").read_text()
    assert ".read_bytes()" not in source
    assert "max_samples" in source
    assert "max_bytes_per_file" in source
