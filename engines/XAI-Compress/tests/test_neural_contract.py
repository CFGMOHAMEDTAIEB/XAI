import pytest
from xai_compress.compression import compress_bytes

def test_neural_requires_checkpoint():
    with pytest.raises(Exception): compress_bytes(b"abc",mode="neural")
