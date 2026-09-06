import hashlib
import pytest
from xai_compress.arithmetic import AdaptiveByteModel, ArithmeticDecoder, ArithmeticEncoder
from xai_compress.entropy.quant import logits_to_cumulative, uniform_cumulative
from xai_compress.entropy.rans import RANSDecoder, RANSEncoder

CASES = [b"", b"A", b"\x00" * 200, b"hello world " * 50, bytes(range(256)), bytes((i * 73 + 19) % 256 for i in range(2048))]


@pytest.mark.parametrize("data", CASES)
def test_arithmetic_adaptive_roundtrip(data):
    enc = ArithmeticEncoder()
    model = AdaptiveByteModel()
    for symbol in data:
        enc.write(model.cumulative(), symbol)
        model.update(symbol)
    payload = enc.finish()
    dec = ArithmeticDecoder(payload)
    model = AdaptiveByteModel()
    out = bytearray()
    for _ in range(len(data)):
        symbol = dec.read(model.cumulative())
        out.append(symbol)
        model.update(symbol)
    assert bytes(out) == data


@pytest.mark.parametrize("data", CASES)
def test_rans_uniform_roundtrip(data):
    table = uniform_cumulative()
    enc = RANSEncoder()
    for symbol in data:
        enc.write(table, symbol)
    payload = enc.finish()
    dec = RANSDecoder(payload)
    out = bytearray()
    for _ in range(len(data)):
        out.append(dec.read(table))
    assert bytes(out) == data


def test_logits_quantization_positive_and_total():
    import torch

    logits = torch.randn(256)
    cum = logits_to_cumulative(logits)
    assert len(cum) == 257
    assert cum[0] == 0
    assert all(cum[i + 1] > cum[i] for i in range(256))
    assert cum[-1] == 16384
