"""Environment detection (docs/ai/03 §4).

Ported verbatim from the design doc. The single most important rule lives in
:func:`choose_device_and_compute`: CTranslate2 has NO Metal/MPS backend, so on
Apple Silicon faster-whisper is CPU-only — we never return ``cuda``/``mps`` there
(Mac GPU acceleration is the whisper.cpp backend's job, added in P6).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass


def detect_colab() -> bool:
    try:
        import google.colab  # noqa: F401
    except ImportError:
        return False
    return True


def detect_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def detect_cuda() -> tuple[bool, float]:
    """Return ``(has_cuda, vram_gb)`` or ``(False, 0.0)``."""
    try:
        import torch

        if torch.cuda.is_available():
            _, total = torch.cuda.mem_get_info(0)
            return True, round(total / 1024**3, 1)
    except Exception:
        pass
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                text=True,
            )
            return True, round(int(out.strip().splitlines()[0]) / 1024, 1)
        except Exception:
            pass
    return False, 0.0


def detect_cpu_ram() -> tuple[int, float]:
    """Return ``(cpu_cores, ram_gb)``. ``ram_gb`` is 0.0 if it cannot be read."""
    cores = os.cpu_count() or 1
    ram_gb = 0.0
    try:
        import psutil

        ram_gb = round(psutil.virtual_memory().total / 1024**3, 1)
    except ImportError:
        try:
            ram_gb = round(
                os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1
            )
        except (ValueError, AttributeError, OSError):
            ram_gb = 0.0
    return cores, ram_gb


def choose_device_and_compute() -> tuple[str, str]:
    """Pick the faster-whisper ``(device, compute_type)`` for this host (docs/ai/03 §2,§4).

    Apple Silicon → CPU int8 (CT2 has no Metal). CUDA → float16 (>=8GB VRAM) else
    int8_float16. Everything else → CPU int8 (float16 on CPU is silently demoted).

    Note: ``compute_type`` here is host/VRAM-derived per the authoritative §4 code,
    NOT ``want``-aware. The §3 table's per-want compute_type column is in tension
    with this (a doc-internal contradiction); we deliberately follow §4 + the §2
    guidance endorsing int8_float16 for ≤6–8GB. Do not thread ``want`` in here to
    chase the §3 table without first reconciling the spec.
    """
    if detect_apple_silicon():
        return "cpu", "int8"
    has_cuda, vram = detect_cuda()
    if has_cuda:
        return "cuda", ("float16" if vram >= 8 else "int8_float16")
    return "cpu", "int8"


@dataclass(frozen=True)
class HostInfo:
    """A snapshot of the detected environment (drives ``yazit doctor`` / ``models``)."""

    is_colab: bool
    is_apple_silicon: bool
    has_cuda: bool
    vram_gb: float
    cpu_cores: int
    ram_gb: float
    device: str
    compute_type: str


def detect_host() -> HostInfo:
    has_cuda, vram = detect_cuda()
    cores, ram = detect_cpu_ram()
    device, compute = choose_device_and_compute()
    return HostInfo(
        is_colab=detect_colab(),
        is_apple_silicon=detect_apple_silicon(),
        has_cuda=has_cuda,
        vram_gb=vram,
        cpu_cores=cores,
        ram_gb=ram,
        device=device,
        compute_type=compute,
    )
