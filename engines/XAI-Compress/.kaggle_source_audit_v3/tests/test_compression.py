from xai_compress.compression import compress_bytes, decompress_bytes


def test_static_compress_produces_container():
    blob = compress_bytes(b"abc" * 50, "static")
    assert blob.startswith(b"XAIC")
    assert decompress_bytes(blob) == b"abc" * 50
