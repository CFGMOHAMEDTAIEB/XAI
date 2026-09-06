from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DeviceInfo:
    cuda_available: bool
    device: str
    gpu_count: int
    gpu_name: str | None
    vram_bytes: int | None
    cuda_version: str | None
    cudnn_version: str | None
    torch_version: str
    torch_cuda_compiled: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def report_lines(self) -> list[str]:
        vram = f"{self.vram_bytes / (1024 ** 3):.2f} GiB" if self.vram_bytes else "n/a"
        return [
            f"CUDA available        : {self.cuda_available}",
            f"Selected device       : {self.device}",
            f"GPU name              : {self.gpu_name or 'n/a'}",
            f"GPU count             : {self.gpu_count}",
            f"VRAM                  : {vram}",
            f"CUDA version          : {self.cuda_version or 'n/a'}",
            f"cuDNN version         : {self.cudnn_version or 'n/a'}",
            f"PyTorch               : {self.torch_version}",
            f"PyTorch CUDA support  : {self.torch_cuda_compiled}",
        ]


def detect_device() -> DeviceInfo:
    import torch

    cuda_ok = bool(torch.cuda.is_available())
    gpu_name = None
    vram = None
    if cuda_ok:
        gpu_name = torch.cuda.get_device_name(0)
        try:
            free, total = torch.cuda.mem_get_info()
            vram = int(total)
        except Exception:
            props = torch.cuda.get_device_properties(0)
            vram = int(getattr(props, "total_memory", 0)) or None
    cudnn = None
    try:
        if torch.backends.cudnn.is_available():
            cudnn = str(torch.backends.cudnn.version())
    except Exception:
        cudnn = None
    return DeviceInfo(
        cuda_available=cuda_ok,
        device="cuda" if cuda_ok else "cpu",
        gpu_count=int(torch.cuda.device_count()) if cuda_ok else 0,
        gpu_name=gpu_name,
        vram_bytes=vram,
        cuda_version=getattr(torch.version, "cuda", None),
        cudnn_version=cudnn,
        torch_version=torch.__version__,
        torch_cuda_compiled=bool(torch.backends.cuda.is_built()),
    )


def select_device(requested: str | None = None) -> str:
    info = detect_device()
    if requested is None or requested == "auto":
        return info.device
    if requested.startswith("cuda") and not info.cuda_available:
        raise RuntimeError("CUDA was requested but is not available")
    return requested


def gpu_memory_stats() -> dict[str, float]:
    import torch

    if not torch.cuda.is_available():
        return {"allocated_bytes": 0.0, "reserved_bytes": 0.0, "max_allocated_bytes": 0.0}
    return {
        "allocated_bytes": float(torch.cuda.memory_allocated()),
        "reserved_bytes": float(torch.cuda.memory_reserved()),
        "max_allocated_bytes": float(torch.cuda.max_memory_allocated()),
    }


def reset_peak_memory() -> None:
    import torch

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()
