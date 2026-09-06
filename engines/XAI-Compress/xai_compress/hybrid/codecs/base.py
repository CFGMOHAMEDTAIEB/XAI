from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class CodecError(ValueError):
    pass


@dataclass(frozen=True)
class CodecResult:
    payload: bytes
    metadata: dict[str, Any] = field(default_factory=dict)


class CodecAdapter(ABC):
    codec_id: str

    @abstractmethod
    def compress(self, data: bytes, level: int | None = None) -> CodecResult:
        raise NotImplementedError

    @abstractmethod
    def decompress(self, data: bytes, metadata: dict[str, Any]) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def available_levels(self) -> tuple[int | None, ...]:
        raise NotImplementedError

    def available(self) -> bool:
        return True

    def metadata(self) -> dict[str, Any]:
        return {"codec_id": self.codec_id, "levels": list(self.available_levels()), "available": self.available()}


@dataclass(frozen=True)
class Strategy:
    codec: str
    level: int | None = None
    transform: str = "identity"

    @property
    def strategy_id(self) -> str:
        level = "default" if self.level is None else str(self.level)
        return f"{self.codec}|{level}|{self.transform}"

    @classmethod
    def parse(cls, value: str) -> "Strategy":
        try:
            codec, raw_level, transform = value.split("|", 2)
        except ValueError as exc:
            raise CodecError(f"invalid strategy ID: {value}") from exc
        level = None if raw_level == "default" else int(raw_level)
        return cls(codec=codec, level=level, transform=transform)
