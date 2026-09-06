from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class TransformError(ValueError):
    pass


@dataclass(frozen=True)
class TransformAdapter:
    transform_id: str
    forward_fn: Callable[[bytes], tuple[bytes, dict]]
    inverse_fn: Callable[[bytes, dict], bytes]

    def forward(self, data: bytes) -> tuple[bytes, dict]:
        return self.forward_fn(bytes(data))

    def inverse(self, data: bytes, metadata: dict | None = None) -> bytes:
        return self.inverse_fn(bytes(data), dict(metadata or {}))


def _identity(data: bytes) -> tuple[bytes, dict]:
    return data, {}


def _identity_inverse(data: bytes, metadata: dict) -> bytes:
    return data


def _rle(data: bytes) -> tuple[bytes, dict]:
    if not data:
        return b"", {}
    out = bytearray()
    index = 0
    while index < len(data):
        value = data[index]
        end = index + 1
        while end < len(data) and data[end] == value and end - index < 255:
            end += 1
        out.extend((end - index, value))
        index = end
    return bytes(out), {}


def _rle_inverse(data: bytes, metadata: dict) -> bytes:
    if len(data) % 2:
        raise TransformError("truncated RLE pair")
    out = bytearray()
    for index in range(0, len(data), 2):
        count, value = data[index], data[index + 1]
        if count == 0:
            raise TransformError("invalid zero RLE count")
        out.extend(bytes([value]) * count)
    return bytes(out)


def _delta(data: bytes) -> tuple[bytes, dict]:
    if not data:
        return b"", {}
    out = bytearray([data[0]])
    out.extend((data[index] - data[index - 1]) & 0xFF for index in range(1, len(data)))
    return bytes(out), {}


def _delta_inverse(data: bytes, metadata: dict) -> bytes:
    if not data:
        return b""
    out = bytearray([data[0]])
    for delta in data[1:]:
        out.append((out[-1] + delta) & 0xFF)
    return bytes(out)


def _byte_shuffle(data: bytes) -> tuple[bytes, dict]:
    return data[::2] + data[1::2], {"original_size": len(data)}


def _byte_shuffle_inverse(data: bytes, metadata: dict) -> bytes:
    size = metadata.get("original_size")
    if not isinstance(size, int) or size < 0 or size != len(data):
        raise TransformError("invalid byte-shuffle size")
    even_count = (size + 1) // 2
    even, odd = data[:even_count], data[even_count:]
    out = bytearray(size)
    out[::2], out[1::2] = even, odd
    return bytes(out)


def _zero_run(data: bytes) -> tuple[bytes, dict]:
    out = bytearray()
    index = 0
    while index < len(data):
        if data[index] != 0:
            out.append(data[index])
            index += 1
            continue
        end = index + 1
        while end < len(data) and data[end] == 0 and end - index < 255:
            end += 1
        out.extend((0, end - index))
        index = end
    return bytes(out), {}


def _zero_run_inverse(data: bytes, metadata: dict) -> bytes:
    out = bytearray()
    index = 0
    while index < len(data):
        value = data[index]
        index += 1
        if value:
            out.append(value)
            continue
        if index >= len(data) or data[index] == 0:
            raise TransformError("invalid zero-run marker")
        out.extend(b"\0" * data[index])
        index += 1
    return bytes(out)


TOKENS = (
    b"    ",
    b"\r\n",
    b"\n",
    b'": ',
    b'","',
    b"true",
    b"false",
    b"null",
    b"def ",
    b"class ",
    b"import ",
    b"return ",
)
TOKEN_MARKER = 0xFF


def _dictionary(data: bytes) -> tuple[bytes, dict]:
    out = bytearray()
    index = 0
    ordered = sorted(enumerate(TOKENS, 1), key=lambda item: (-len(item[1]), item[0]))
    while index < len(data):
        matched = False
        for code, token in ordered:
            if data.startswith(token, index):
                out.extend((TOKEN_MARKER, code))
                index += len(token)
                matched = True
                break
        if matched:
            continue
        value = data[index]
        out.append(value)
        if value == TOKEN_MARKER:
            out.append(0)
        index += 1
    return bytes(out), {"dictionary": "structured-v1"}


def _dictionary_inverse(data: bytes, metadata: dict) -> bytes:
    if metadata.get("dictionary") != "structured-v1":
        raise TransformError("unknown dictionary transform metadata")
    out = bytearray()
    index = 0
    while index < len(data):
        value = data[index]
        index += 1
        if value != TOKEN_MARKER:
            out.append(value)
            continue
        if index >= len(data):
            raise TransformError("truncated dictionary token")
        code = data[index]
        index += 1
        if code == 0:
            out.append(TOKEN_MARKER)
        elif 1 <= code <= len(TOKENS):
            out.extend(TOKENS[code - 1])
        else:
            raise TransformError("invalid dictionary token")
    return bytes(out)


TRANSFORMS = {
    item.transform_id: item
    for item in (
        TransformAdapter("identity", _identity, _identity_inverse),
        TransformAdapter("rle", _rle, _rle_inverse),
        TransformAdapter("delta", _delta, _delta_inverse),
        TransformAdapter("byte-shuffle", _byte_shuffle, _byte_shuffle_inverse),
        TransformAdapter("zero-run", _zero_run, _zero_run_inverse),
        TransformAdapter("dictionary", _dictionary, _dictionary_inverse),
    )
}


def get_transform(transform_id: str) -> TransformAdapter:
    try:
        return TRANSFORMS[transform_id]
    except KeyError as exc:
        raise TransformError(f"unsupported transform_id: {transform_id}") from exc
