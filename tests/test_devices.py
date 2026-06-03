"""Device detection rules (docs/ai/03 §2, §4) — the Apple-Silicon gotcha."""

from __future__ import annotations

import pytest

from scribeflow import devices


def test_apple_silicon_is_cpu_int8(monkeypatch) -> None:
    monkeypatch.setattr(devices, "detect_apple_silicon", lambda: True)
    # Even if a CUDA probe would (spuriously) succeed, Apple Silicon must stay CPU.
    monkeypatch.setattr(devices, "detect_cuda", lambda: (True, 16.0))
    assert devices.choose_device_and_compute() == ("cpu", "int8")


@pytest.mark.parametrize(
    ("vram", "expected_compute"),
    [(16.0, "float16"), (8.0, "float16"), (6.0, "int8_float16"), (4.0, "int8_float16")],
)
def test_cuda_compute_type_by_vram(monkeypatch, vram, expected_compute) -> None:
    monkeypatch.setattr(devices, "detect_apple_silicon", lambda: False)
    monkeypatch.setattr(devices, "detect_cuda", lambda: (True, vram))
    assert devices.choose_device_and_compute() == ("cuda", expected_compute)


def test_plain_cpu(monkeypatch) -> None:
    monkeypatch.setattr(devices, "detect_apple_silicon", lambda: False)
    monkeypatch.setattr(devices, "detect_cuda", lambda: (False, 0.0))
    assert devices.choose_device_and_compute() == ("cpu", "int8")
