import hashlib

from xai_compress.compression import compress_bytes, compress_file, decompress_bytes, decompress_file
from xai_compress.format import unpack_container


def test_xaic_v1_and_v2_lossless_compatibility():
    data = (b"XAIC compatibility\x00\xff" * 40)
    version_1 = compress_bytes(data, "static")
    metadata_1, _ = unpack_container(version_1)
    assert metadata_1["format_version"] == 1
    assert hashlib.sha256(decompress_bytes(version_1)).digest() == hashlib.sha256(data).digest()

    version_2 = compress_bytes(data, "hybrid", checkpoint=None, chunk_size=64)
    metadata_2, _ = unpack_container(version_2)
    assert metadata_2["format_version"] == 2
    assert hashlib.sha256(decompress_bytes(version_2)).digest() == hashlib.sha256(data).digest()


def test_xaic_v3_streaming_lossless_compatibility(tmp_path):
    data = bytes(range(256)) * 16
    source = tmp_path / "source.bin"
    artifact = tmp_path / "artifact.xaic"
    restored = tmp_path / "restored.bin"
    source.write_bytes(data)
    info = compress_file(source, artifact, mode="static", chunk_size=257)
    assert info["format_version"] == 3
    restored_info = decompress_file(artifact, restored)
    assert restored_info["format_version"] == 3
    assert hashlib.sha256(restored.read_bytes()).digest() == hashlib.sha256(data).digest()


# XAIC v4 is the explicitly lossy media container and is covered by
# tests/test_lossy_v1.py; an exact byte SHA requirement would be invalid there.
