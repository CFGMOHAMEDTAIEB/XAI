import hashlib
import pytest
from xai_compress.compression import compress_bytes, decompress_bytes
from xai_compress.model import CausalByteGRU, ModelConfig
from xai_compress.checkpoint import save_checkpoint
from xai_compress.models.transformer import CausalByteTransformer

CASES = [
    b"",
    b"A",
    "unicøde ✓ café".encode(),
    b"{\"a\":1,\"b\":[2,3]}",
    b"def foo():\n    return 1\n",
    b"\x00" * 1000,
    bytes(range(256)),
    bytes((i * 73 + 19) % 256 for i in range(4096)),
    b"AB" * 5000,
]


@pytest.mark.parametrize("data", CASES)
def test_static_bytes_equal(data):
    blob = compress_bytes(data, "static")
    assert decompress_bytes(blob) == data


@pytest.mark.parametrize("data", CASES)
def test_hybrid_bytes_equal(data):
    blob = compress_bytes(data, "hybrid")
    assert decompress_bytes(blob) == data


@pytest.mark.parametrize("data", CASES)
def test_zlib_mode_bytes_equal(data):
    blob = compress_bytes(data, "zlib")
    assert decompress_bytes(blob) == data


def test_neural_gru_roundtrip(tmp_path):
    model = CausalByteGRU(ModelConfig(embedding_dim=8, hidden_dim=12, num_layers=1, context_length=16))
    ckpt = tmp_path / "tiny.pt"
    save_checkpoint(ckpt, model)
    data = b"neural-roundtrip-test" * 20
    blob = compress_bytes(data, "neural", str(ckpt))
    assert decompress_bytes(blob, str(ckpt)) == data


def test_neural_transformer_roundtrip(tmp_path):
    cfg = ModelConfig(
        architecture_id="causal-byte-transformer-v1",
        embedding_dim=16,
        hidden_dim=16,
        num_layers=2,
        n_heads=4,
        ff_dim=32,
        context_length=32,
        dropout=0.0,
    )
    model = CausalByteTransformer(cfg)
    ckpt = tmp_path / "tr.pt"
    save_checkpoint(ckpt, model)
    data = b"transformer-bytes-must-match-exactly!!" * 8
    blob = compress_bytes(data, "neural", str(ckpt))
    assert decompress_bytes(blob, str(ckpt)) == data


def test_neural_rans_roundtrip(tmp_path):
    model = CausalByteGRU(ModelConfig(embedding_dim=8, hidden_dim=12, num_layers=1, context_length=16))
    ckpt = tmp_path / "tiny.pt"
    save_checkpoint(ckpt, model)
    data = b"rans-neural" * 30
    blob = compress_bytes(data, "neural", str(ckpt), coder="rans")
    assert decompress_bytes(blob, str(ckpt)) == data
    assert hashlib.sha256(decompress_bytes(blob, str(ckpt))).digest() == hashlib.sha256(data).digest()
