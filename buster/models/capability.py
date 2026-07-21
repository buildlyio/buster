"""Hardware capability detection → typed capability profile.

Detection is best-effort and never fails: unknown values fall back to safe
defaults. This drives model-class recommendation and the onboarding explanation.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Literal

import psutil
from pydantic import BaseModel

GpuBackend = Literal["metal", "cuda", "rocm", "none"]


class CapabilityProfile(BaseModel):
    platform: str                       # macos | linux | ...
    architecture: str                   # arm64 | x86_64 | ...
    memory_gb: float
    available_memory_gb: float
    cpu_cores: int
    disk_free_gb: float
    gpu_backend: GpuBackend
    local_runtime: str                  # ollama | none
    recommended_model_class: str        # e.g. "4b-12b"
    supports_local_embeddings: bool
    is_raspberry_pi: bool = False

    def explain(self) -> str:
        """Human-readable summary for onboarding / doctor."""
        gpu = {
            "metal": "Apple Metal GPU acceleration",
            "cuda": "NVIDIA CUDA GPU acceleration",
            "rocm": "AMD ROCm GPU acceleration",
            "none": "CPU-only inference",
        }[self.gpu_backend]
        lines = [
            f"Platform: {self.platform} ({self.architecture})",
            f"Memory: {self.memory_gb:.0f} GB total, {self.available_memory_gb:.1f} GB available",
            f"CPU cores: {self.cpu_cores}",
            f"Disk free: {self.disk_free_gb:.0f} GB",
            f"Acceleration: {gpu}",
            f"Local runtime: {self.local_runtime}",
            f"Recommended model class: {self.recommended_model_class}",
        ]
        if self.is_raspberry_pi:
            lines.append("Detected Raspberry Pi-class hardware (minimum tier).")
        return "\n".join(lines)


def _detect_platform() -> str:
    system = platform.system().lower()
    return {"darwin": "macos", "linux": "linux"}.get(system, system)


def _detect_gpu(plat: str, arch: str) -> GpuBackend:
    if plat == "macos" and arch == "arm64":
        return "metal"
    # NVIDIA
    if shutil.which("nvidia-smi"):
        try:
            subprocess.run(
                ["nvidia-smi"], capture_output=True, timeout=5, check=True
            )
            return "cuda"
        except Exception:
            pass
    # AMD ROCm
    if shutil.which("rocminfo") or shutil.which("rocm-smi"):
        return "rocm"
    return "none"


def _detect_raspberry_pi(plat: str) -> bool:
    if plat != "linux":
        return False
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as fh:
            data = fh.read().lower()
        if "raspberry pi" in data or "bcm2" in data:
            return True
    except OSError:
        pass
    try:
        with open("/proc/device-tree/model", encoding="utf-8", errors="ignore") as fh:
            return "raspberry pi" in fh.read().lower()
    except OSError:
        return False


def _recommend_model_class(memory_gb: float, gpu: GpuBackend, is_pi: bool) -> str:
    """Rough guidance keyed on RAM/VRAM availability."""
    if is_pi or memory_gb < 4:
        return "1b-3b"
    if memory_gb < 8:
        return "3b-7b"
    if memory_gb < 16:
        return "4b-12b" if gpu != "none" else "3b-8b"
    if memory_gb < 32:
        return "7b-14b" if gpu != "none" else "4b-12b"
    return "14b-32b"


def detect_capabilities() -> CapabilityProfile:
    plat = _detect_platform()
    arch = platform.machine().lower()
    arch = {"aarch64": "arm64", "amd64": "x86_64"}.get(arch, arch)

    vm = psutil.virtual_memory()
    memory_gb = vm.total / (1024**3)
    available_gb = vm.available / (1024**3)
    cores = psutil.cpu_count(logical=True) or 1

    try:
        disk_free_gb = psutil.disk_usage("/").free / (1024**3)
    except Exception:
        disk_free_gb = 0.0

    gpu = _detect_gpu(plat, arch)
    is_pi = _detect_raspberry_pi(plat)
    runtime = "ollama" if shutil.which("ollama") else "none"

    return CapabilityProfile(
        platform=plat,
        architecture=arch,
        memory_gb=round(memory_gb, 1),
        available_memory_gb=round(available_gb, 1),
        cpu_cores=cores,
        disk_free_gb=round(disk_free_gb, 1),
        gpu_backend=gpu,
        local_runtime=runtime,
        recommended_model_class=_recommend_model_class(memory_gb, gpu, is_pi),
        supports_local_embeddings=runtime == "ollama",
        is_raspberry_pi=is_pi,
    )
