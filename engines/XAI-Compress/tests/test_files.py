from pathlib import Path
import pytest
from xai_compress.compression import compress_file,decompress_file

def test_file_roundtrip_and_atomic(tmp_path):
    src=tmp_path/"input.bin"; art=tmp_path/"out.xaic"; dst=tmp_path/"restored.bin"
    src.write_bytes(bytes(range(256))*8)
    compress_file(src,art); src.unlink(); decompress_file(art,dst)
    assert dst.read_bytes()==bytes(range(256))*8

def test_failed_decompression_leaves_no_output(tmp_path):
    art=tmp_path/"bad.xaic"; dst=tmp_path/"out.bin"; art.write_bytes(b"bad")
    with pytest.raises(Exception): decompress_file(art,dst)
    assert not dst.exists()
