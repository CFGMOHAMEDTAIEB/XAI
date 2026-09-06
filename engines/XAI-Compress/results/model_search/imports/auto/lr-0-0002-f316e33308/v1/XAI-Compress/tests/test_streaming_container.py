import struct

import pytest

from xai_compress.compression import compress_bytes, compress_file, decompress_file
from xai_compress.streaming import CHUNK, PREFIX, STREAM_VERSION, StreamingFormatError, read_header


def test_v3_multichunk_stream_roundtrip(tmp_path):
    data = bytes(range(256)) * 100
    source, artifact, restored = tmp_path / "in", tmp_path / "out.xaic", tmp_path / "restored"
    source.write_bytes(data)
    info = compress_file(source, artifact, mode="hybrid", chunk_size=257)
    assert info["format_version"] == STREAM_VERSION
    assert info["chunks"] > 2
    restored_info = decompress_file(artifact, restored)
    assert restored.read_bytes() == data
    assert restored_info["chunks"] == info["chunks"]


@pytest.mark.parametrize("size", [0, 1, 2, 7])
def test_v3_tiny_chunks_and_empty(tmp_path, size):
    data = b"abcabcabc"[:size]
    source, artifact, restored = tmp_path / "in", tmp_path / "out", tmp_path / "restored"
    source.write_bytes(data)
    compress_file(source, artifact, mode="zlib", chunk_size=1)
    decompress_file(artifact, restored)
    assert restored.read_bytes() == data


def _payload_offset(blob: bytes) -> int:
    _, _, metadata_len = PREFIX.unpack_from(blob)
    return PREFIX.size + metadata_len + 32 + CHUNK.size


def test_v3_chunk_checksum_failure_cleans_temp(tmp_path):
    source, artifact, restored = tmp_path / "in", tmp_path / "out", tmp_path / "restored"
    source.write_bytes(b"checksum me" * 100)
    compress_file(source, artifact, mode="zlib", chunk_size=128)
    blob = bytearray(artifact.read_bytes())
    blob[_payload_offset(blob)] ^= 1
    artifact.write_bytes(blob)
    with pytest.raises(Exception):
        decompress_file(artifact, restored)
    assert not restored.exists()
    assert not list(tmp_path.glob("restored.*.tmp"))


def test_v3_global_checksum_and_truncation_fail(tmp_path):
    source, artifact = tmp_path / "in", tmp_path / "out"
    source.write_bytes(b"footer" * 100)
    compress_file(source, artifact, chunk_size=64)
    original = artifact.read_bytes()
    for name, corrupt in (("truncated", original[:-5]), ("footer", original[:-1] + bytes([original[-1] ^ 1]))):
        bad, restored = tmp_path / name, tmp_path / (name + ".raw")
        bad.write_bytes(corrupt)
        with pytest.raises(Exception):
            decompress_file(bad, restored)
        assert not restored.exists()


def test_file_decoder_keeps_legacy_compatibility(tmp_path):
    data = b"legacy" * 100
    artifact, restored = tmp_path / "legacy.xaic", tmp_path / "restored"
    artifact.write_bytes(compress_bytes(data, "static"))
    decompress_file(artifact, restored)
    assert restored.read_bytes() == data
