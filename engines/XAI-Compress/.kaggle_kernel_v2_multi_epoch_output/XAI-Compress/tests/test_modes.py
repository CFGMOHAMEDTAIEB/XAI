import pytest

from xai_compress.compression import CompressionError, compress_bytes, decompress_bytes
from xai_compress.modes import NEURAL_LOSSLESS, NEURAL_LOSSY, STATIC, canonical_mode, is_lossless


def test_public_mode_semantics_are_explicit():
    assert canonical_mode("neural") == NEURAL_LOSSLESS
    assert canonical_mode(STATIC) == STATIC
    assert is_lossless("neural")
    assert is_lossless(NEURAL_LOSSLESS)
    assert not is_lossless(NEURAL_LOSSY)


def test_static_remains_backward_compatible():
    data = b"three-mode-static-contract" * 4
    assert decompress_bytes(compress_bytes(data, STATIC)) == data


def test_lossy_bytes_are_rejected_not_mislabeled():
    with pytest.raises(CompressionError, match="media-only"):
        compress_bytes(b"arbitrary binary", NEURAL_LOSSY)
