from xai_compress.compression import compress_bytes, decompress_bytes


def test_decompress_rejects_corruption():
    blob = bytearray(compress_bytes(b"payload-data" * 20, "static"))
    blob[-3] ^= 0x5A
    try:
        decompress_bytes(bytes(blob))
        raised = False
    except Exception:
        raised = True
    assert raised
