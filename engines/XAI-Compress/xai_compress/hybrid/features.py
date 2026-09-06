from __future__ import annotations

import math
import mimetypes
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

MAX_FEATURE_SCAN_BYTES = 256 << 10
LOCAL_WINDOW = 4096

COMPRESSED_EXTENSIONS = {
    ".7z", ".aac", ".avi", ".bz2", ".flac", ".gz", ".jpeg", ".jpg",
    ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".ogg", ".png", ".rar",
    ".safetensors", ".webm", ".webp", ".xz", ".zip", ".pt", ".pth",
}

MAGIC_SIGNATURES: tuple[tuple[bytes, str, bool], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png", True),
    (b"\xff\xd8\xff", "jpeg", True),
    (b"RIFF", "riff", True),
    (b"\x1aE\xdf\xa3", "matroska", True),
    (b"ID3", "mp3", True),
    (b"OggS", "ogg", True),
    (b"PK\x03\x04", "zip", True),
    (b"\x1f\x8b", "gzip", True),
    (b"7z\xbc\xaf'\x1c", "7z", True),
    (b"Rar!\x1a\x07", "rar", True),
    (b"%PDF-", "pdf", True),
    (b"\x7fELF", "elf", False),
    (b"MZ", "pe", False),
    (b"SQLite format 3\x00", "sqlite", False),
)


def entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def bounded_file_sample(path: str | Path, maximum: int = MAX_FEATURE_SCAN_BYTES) -> bytes:
    source = Path(path)
    size = source.stat().st_size
    if size <= maximum:
        return source.read_bytes()
    section = maximum // 3
    with source.open("rb") as handle:
        beginning = handle.read(section)
        handle.seek(max(0, size // 2 - section // 2))
        middle = handle.read(section)
        handle.seek(max(0, size - (maximum - 2 * section)))
        end = handle.read(maximum - 2 * section)
    return beginning + middle + end


def _magic(data: bytes) -> tuple[str, bool]:
    for signature, category, compressed in MAGIC_SIGNATURES:
        if data.startswith(signature):
            if category == "riff" and len(data) >= 12:
                subtype = data[8:12]
                if subtype == b"WEBP":
                    return "webp", True
                if subtype in (b"AVI ", b"WAVE"):
                    return subtype.decode("ascii", "replace").strip().lower(), True
            return category, compressed
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "iso-media", True
    return "unknown", False


def _mime_category(extension: str, magic: str) -> str:
    if magic in {"png", "jpeg", "webp"}:
        return "image"
    if magic in {"iso-media", "matroska", "avi"}:
        return "video"
    if magic in {"mp3", "ogg", "wave"}:
        return "audio"
    if magic in {"zip", "gzip", "7z", "rar"}:
        return "archive"
    if magic == "pdf":
        return "document"
    guessed, _ = mimetypes.guess_type("x" + extension)
    return guessed.split("/", 1)[0] if guessed else "unknown"


def _repetition(data: bytes, ngram: int = 4) -> tuple[float, float]:
    if len(data) < ngram:
        return 0.0, 0.0
    grams = [data[index : index + ngram] for index in range(0, len(data) - ngram + 1, ngram)]
    counts = Counter(grams)
    repeated = sum(count for count in counts.values() if count > 1)
    ratio = repeated / max(1, len(grams))
    dictionary_ratio = len(counts) / max(1, len(grams))
    return ratio, 1.0 - dictionary_ratio


def _lz_match_estimate(data: bytes) -> float:
    if len(data) < 8:
        return 0.0
    seen: set[bytes] = set()
    matches = 0
    tested = 0
    for index in range(0, len(data) - 7, 8):
        block = data[index : index + 8]
        tested += 1
        if block in seen:
            matches += 1
        seen.add(block)
    return matches / max(1, tested)


def _native_byte_stats(data: bytes) -> dict[str, Any] | None:
    try:
        import xai_compress_core

        function = getattr(xai_compress_core, "byte_stats", None)
        return dict(function(data)) if function is not None else None
    except (ImportError, AttributeError, RuntimeError, TypeError, ValueError):
        return None


def extract_features(
    sample: bytes,
    *,
    file_size: int | None = None,
    extension: str = "",
) -> dict[str, Any]:
    data = bytes(sample[:MAX_FEATURE_SCAN_BYTES])
    length = len(data)
    native = _native_byte_stats(data)
    counts = list(native["counts"]) if native else [0] * 256
    if native is None:
        for value in data:
            counts[value] += 1
    frequencies = [count / length for count in counts] if length else [0.0] * 256
    unique = sum(count > 0 for count in counts)
    if native:
        printable = int(native["printable"])
        ascii_count = int(native["ascii"])
        digits = int(native["digits"])
        whitespace = int(native["whitespace"])
        newlines = int(native["newlines"])
        longest_run = int(native["longest_run"])
        run_total = int(native["run_total"])
        run_count = int(native["run_count"])
        repetition_score = float(native["repetition_score"])
        repeated_ngram_ratio = float(native["repeated_ngram_ratio"])
        lz_match_ratio = float(native["lz_match_ratio"])
        byte_entropy = float(native["entropy"])
        local_mean = float(native["local_entropy_mean"])
        local_std = float(native["local_entropy_std"])
        entropy_gradient = float(native["entropy_gradient"])
        delta_entropy = float(native["delta_entropy"])
    else:
        printable = sum(value in (9, 10, 13) or 32 <= value <= 126 for value in data)
        ascii_count = sum(value < 128 for value in data)
        digits = sum(48 <= value <= 57 for value in data)
        whitespace = sum(value in b" \t\r\n" for value in data)
        newlines = data.count(10)
        longest_run = 0
        run_total = 0
        run_count = 0
        index = 0
        while index < length:
            end = index + 1
            while end < length and data[end] == data[index]:
                end += 1
            run = end - index
            run_count += 1
            longest_run = max(longest_run, run)
            if run > 1:
                run_total += run
            index = end
        repetition_score, repeated_ngram_ratio = _repetition(data)
        lz_match_ratio = _lz_match_estimate(data)
        local = [entropy(data[index : index + LOCAL_WINDOW]) for index in range(0, length, LOCAL_WINDOW)] or [0.0]
        delta = bytes(((data[index] - data[index - 1]) & 0xFF) for index in range(1, length))
        byte_entropy = entropy(data)
        local_mean = statistics.mean(local)
        local_std = statistics.pstdev(local)
        entropy_gradient = max(local) - min(local)
        delta_entropy = entropy(delta)
    magic, magic_compressed = _magic(data)
    normalized_extension = extension.lower() if extension.startswith(".") or not extension else "." + extension.lower()
    text_like = length == 0 or printable / max(1, length) >= 0.85
    json_score = float(text_like and data.lstrip()[:1] in (b"{", b"[") and b":" in data)
    csv_score = float(text_like and newlines > 1 and data.count(b",") >= newlines)
    source_tokens = sum(data.count(token) for token in (b"def ", b"class ", b"import ", b"function", b"#include", b"{", b"}"))
    features: dict[str, Any] = {
        "file_size": int(file_size if file_size is not None else length),
        "log2_file_size": math.log2(max(1, int(file_size if file_size is not None else length))),
        "sample_size": length,
        "byte_entropy": byte_entropy,
        "unique_byte_count": unique,
        "zero_ratio": counts[0] / max(1, length),
        "ascii_ratio": ascii_count / max(1, length),
        "printable_ratio": printable / max(1, length),
        "digit_ratio": digits / max(1, length),
        "whitespace_ratio": whitespace / max(1, length),
        "newline_ratio": newlines / max(1, length),
        "max_byte_frequency": max(frequencies),
        "mean_byte_frequency": statistics.mean(frequencies),
        "byte_frequency_std": statistics.pstdev(frequencies),
        "run_length_score": run_total / max(1, length),
        "longest_run": longest_run,
        "run_count": run_count,
        "mean_run_length": length / max(1, run_count),
        "repetition_score": repetition_score,
        "repeated_ngram_ratio": repeated_ngram_ratio,
        "lz_match_estimate": lz_match_ratio,
        "estimated_lz_match_ratio": lz_match_ratio,
        "local_entropy_mean": local_mean,
        "local_entropy_std": local_std,
        "entropy_gradient": entropy_gradient,
        "first_order_delta_entropy": delta_entropy,
        "extension": normalized_extension or "<none>",
        "mime_category": _mime_category(normalized_extension, magic),
        "is_text_like": float(text_like),
        "is_binary_like": float(not text_like),
        "is_already_compressed": float(magic_compressed or normalized_extension in COMPRESSED_EXTENSIONS),
        "already_compressed_score": float(magic_compressed or normalized_extension in COMPRESSED_EXTENSIONS),
        "magic_signature_category": magic,
        "structured_text_score": min(1.0, (json_score + csv_score + min(1.0, source_tokens / 20)) / 2),
        "json_like_score": json_score,
        "csv_like_score": csv_score,
        "source_code_like_score": min(1.0, source_tokens / 20),
        "numeric_array_score": min(1.0, digits / max(1, printable)),
        "numeric_data_score": min(1.0, digits / max(1, printable)),
    }
    for key, value in features.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"non-finite feature: {key}")
    return features


def extract_file_features(path: str | Path, maximum: int = MAX_FEATURE_SCAN_BYTES) -> dict[str, Any]:
    source = Path(path)
    return extract_features(
        bounded_file_sample(source, maximum),
        file_size=source.stat().st_size,
        extension=source.suffix,
    )
