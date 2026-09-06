import hashlib, os, pytest
from xai_compress.compression import compress_bytes,decompress_bytes
from xai_compress.format import FormatError

CASES=[b"",b"A",b"\x00"*1000,b"hello world "*100,bytes(range(256)),bytes((i*73+19)%256 for i in range(4096))]
@pytest.mark.parametrize("data",CASES)
def test_static_roundtrip(data):
    blob=compress_bytes(data,"static"); out=decompress_bytes(blob)
    assert out==data
    assert hashlib.sha256(out).digest()==hashlib.sha256(data).digest()
    if len(data)>16: assert data not in blob[-len(data):] or blob[-len(data):] != data

def test_deterministic():
    data=b"deterministic"*100
    assert compress_bytes(data)==compress_bytes(data)

def test_truncated_and_extra_rejected():
    blob=compress_bytes(b"abc"*100)
    with pytest.raises(Exception): decompress_bytes(blob[:-1])
    with pytest.raises(Exception): decompress_bytes(blob+b"x")

def test_modified_payload_rejected():
    blob=bytearray(compress_bytes(b"abc"*100)); blob[-1]^=1
    with pytest.raises(Exception): decompress_bytes(bytes(blob))

def test_modified_header_rejected():
    blob=bytearray(compress_bytes(b"abc")); blob[12]^=1
    with pytest.raises(Exception): decompress_bytes(bytes(blob))
