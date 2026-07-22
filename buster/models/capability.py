"""Hardware capability detection → typed capability profile.

Detection is best-effort and never fails: unknown values fall back to safe
defaults. This drives model-class recommendation and the onboarding explanation.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from functools import lru_cache
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


def _model_billions(name: str) -> float | None:
    """Best-effort parameter size (in billions) parsed from a model name."""
    import re

    m = re.search(r"(\d+(?:\.\d+)?)\s*b\b", name.lower())
    if m:
        return float(m.group(1))
    # e4b / e2b style (effective params)
    m = re.search(r"e(\d+)b", name.lower())
    return float(m.group(1)) if m else None


def suggest_faster_model(active_model: str, available: list[str]) -> str | None:
    """If the active model looks large for this machine and a smaller one is
    available locally, suggest it. Returns a suggestion string or None."""
    prof = detect_capabilities()
    size = _model_billions(active_model)
    if size is None:
        return None
    # Rough "large for this box" heuristic keyed on RAM + acceleration.
    threshold = 14.0 if prof.gpu_backend != "none" and prof.memory_gb >= 16 else 8.0
    if prof.is_raspberry_pi:
        threshold = 3.0
    if size <= threshold:
        return None
    smaller = sorted(
        [(m, _model_billions(m)) for m in available if _model_billions(m) and _model_billions(m) < size
         and "embed" not in m.lower()],
        key=lambda x: x[1] or 0,
    )
    if not smaller:
        return None
    pick = smaller[-1][0]  # largest that's still under the active one
    return (f"'{active_model}' (~{size:g}B) is large for this machine "
            f"({prof.memory_gb:.0f} GB, {prof.gpu_backend}); "
            f"'{pick}' would respond faster.")


@lru_cache(maxsize=1)
def _static_detection() -> dict:
    """Detection that never changes within a session but is expensive: GPU
    probes (subprocess), /proc reads, PATH lookups. Memoized for the process."""
    plat = _detect_platform()
    arch = platform.machine().lower()
    arch = {"aarch64": "arm64", "amd64": "x86_64"}.get(arch, arch)
    return {
        "platform": plat,
        "architecture": arch,
        "cpu_cores": psutil.cpu_count(logical=True) or 1,
        "gpu_backend": _detect_gpu(plat, arch),
        "is_raspberry_pi": _detect_raspberry_pi(plat),
        "local_runtime": "ollama" if shutil.which("ollama") else "none",
    }


def detect_capabilities() -> CapabilityProfile:
    static = _static_detection()
    plat = static["platform"]
    arch = static["architecture"]
    cores = static["cpu_cores"]
    gpu = static["gpu_backend"]
    is_pi = static["is_raspberry_pi"]
    runtime = static["local_runtime"]

    # Dynamic values are cheap; read fresh each call.
    vm = psutil.virtual_memory()
    memory_gb = vm.total / (1024**3)
    available_gb = vm.available / (1024**3)
    try:
        disk_free_gb = psutil.disk_usage("/").free / (1024**3)
    except Exception:
        disk_free_gb = 0.0

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
