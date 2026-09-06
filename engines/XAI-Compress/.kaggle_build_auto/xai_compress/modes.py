"""Canonical public compression-mode identities.

`neural` remains a legacy spelling and is deliberately interpreted as
lossless.  Lossy is never selected implicitly.
"""
from __future__ import annotations

STATIC = "static"
NEURAL_LOSSLESS = "neural-lossless"
NEURAL_LOSSY = "neural-lossy"
LEGACY_NEURAL = "neural"

PUBLIC_MODES = (STATIC, NEURAL_LOSSLESS, NEURAL_LOSSY)
CLI_MODES = PUBLIC_MODES + (LEGACY_NEURAL, "hybrid", "auto", "zlib")


def canonical_mode(mode: str) -> str:
    value = str(mode).strip().lower()
    return NEURAL_LOSSLESS if value == LEGACY_NEURAL else value


def is_lossless(mode: str) -> bool:
    return canonical_mode(mode) != NEURAL_LOSSY
