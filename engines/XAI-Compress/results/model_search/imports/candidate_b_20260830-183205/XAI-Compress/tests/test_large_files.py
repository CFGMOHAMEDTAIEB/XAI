from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.datasets.corpus import write_corpus


def test_large_file_hybrid_streaming(tmp_path):
    data = bytes((i * 131 + 7) % 256 for i in range(2_000_000))
    src = tmp_path / "large.bin"
    src.write_bytes(data)
    blob = compress_bytes(data, "hybrid", chunk_size=64 * 1024)
    assert decompress_bytes(blob) == data


def test_corpus_roundtrip(tmp_path):
    root = write_corpus(tmp_path / "corpus")
    for path in root.rglob("*"):
        if path.is_file():
            original = path.read_bytes()
            blob = compress_bytes(original, "hybrid")
            assert decompress_bytes(blob) == original
