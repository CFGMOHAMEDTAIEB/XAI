from __future__ import annotations
import hashlib, json, struct
from dataclasses import dataclass

MAGIC = b"XAIC"
FORMAT_VERSION = 1
SUPPORTED_FORMAT_VERSIONS = {1, 2}
PREFIX = struct.Struct(">4sBI")  # magic, version, metadata length
MAX_METADATA = 1 << 20
MAX_OUTPUT_DEFAULT = 8 << 30

class FormatError(ValueError): pass

def _canonical(obj): return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
def sha256(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def pack_container(metadata: dict, payload: bytes, format_version: int | None = None) -> bytes:
    ver = int(format_version or metadata.get("format_version") or FORMAT_VERSION)
    if ver not in SUPPORTED_FORMAT_VERSIONS:
        raise FormatError("unsupported format version")
    md = dict(metadata)
    md.update({"format_version": ver, "payload_size": len(payload), "payload_sha256": sha256(payload)})
    raw = _canonical(md)
    if len(raw) > MAX_METADATA: raise FormatError("metadata too large")
    return PREFIX.pack(MAGIC, ver, len(raw)) + raw + hashlib.sha256(raw).digest() + payload

def unpack_container(blob: bytes, max_output_size=MAX_OUTPUT_DEFAULT):
    if len(blob) < PREFIX.size + 32: raise FormatError("truncated container")
    magic, version, md_len = PREFIX.unpack_from(blob)
    if magic != MAGIC: raise FormatError("invalid magic")
    if version not in SUPPORTED_FORMAT_VERSIONS: raise FormatError("unsupported format version")
    if md_len <= 0 or md_len > MAX_METADATA: raise FormatError("invalid metadata length")
    md_start = PREFIX.size; md_end = md_start + md_len; digest_end = md_end + 32
    if digest_end > len(blob): raise FormatError("truncated metadata")
    raw = blob[md_start:md_end]
    if hashlib.sha256(raw).digest() != blob[md_end:digest_end]: raise FormatError("header integrity failure")
    try: md = json.loads(raw.decode("utf-8"))
    except Exception as e: raise FormatError("invalid metadata JSON") from e
    required = {"format_version","mode","coder_version","original_size","original_sha256","payload_size","payload_sha256"}
    if not required.issubset(md): raise FormatError("missing metadata field")
    if md["format_version"] != version: raise FormatError("metadata version mismatch")
    if not isinstance(md["original_size"], int) or not 0 <= md["original_size"] <= max_output_size: raise FormatError("unsafe original size")
    if not isinstance(md["payload_size"], int) or md["payload_size"] < 0: raise FormatError("invalid payload size")
    payload = blob[digest_end:]
    if len(payload) != md["payload_size"]: raise FormatError("payload length mismatch or unexpected extra bytes")
    if sha256(payload) != md["payload_sha256"]: raise FormatError("payload integrity failure")
    return md, payload
