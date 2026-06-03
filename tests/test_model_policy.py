"""Auto-select decision table (docs/ai/03 §3) + Turkish guards."""

from __future__ import annotations

import pytest

from scribeflow import devices, model_policy
from scribeflow.devices import HostInfo


@pytest.mark.parametrize(
    ("device", "vram", "ram", "want", "expected"),
    [
        ("cuda", 16.0, 0.0, "default", "large-v3"),  # Colab T4 16GB — do NOT downgrade
        ("cuda", 16.0, 0.0, "speed", "large-v3-turbo"),
        ("cuda", 16.0, 0.0, "quality", "large-v3"),
        ("cuda", 24.0, 0.0, "default", "large-v3"),
        ("cuda", 6.0, 0.0, "default", "large-v3-turbo"),
        ("cuda", 4.0, 0.0, "default", "large-v3-turbo"),
        ("cuda", 4.0, 0.0, "quality", "large-v3"),
        ("cpu", 0.0, 8.0, "default", "small"),
        ("cpu", 0.0, 8.0, "speed", "small"),
        ("cpu", 0.0, 8.0, "quality", "medium"),
        ("cpu", 0.0, 16.0, "default", "large-v3-turbo"),
        ("cpu", 0.0, 16.0, "speed", "medium"),
        ("cpu", 0.0, 16.0, "quality", "large-v3"),
    ],
)
def test_choose_model_table(device, vram, ram, want, expected) -> None:
    assert model_policy.choose_model(device, vram_gb=vram, ram_gb=ram, want=want) == expected


def test_override_always_wins() -> None:
    assert model_policy.choose_model("cpu", ram_gb=8.0, override="large-v3") == "large-v3"
    # even an otherwise-forbidden model is honored when explicitly requested
    assert (
        model_policy.choose_model("cuda", vram_gb=16.0, override="distil-large-v3")
        == "distil-large-v3"
    )


@pytest.mark.parametrize(
    ("device", "vram", "ram", "want"),
    [
        ("cuda", 16.0, 0.0, "default"),
        ("cuda", 4.0, 0.0, "speed"),
        ("cpu", 0.0, 8.0, "default"),
        ("cpu", 0.0, 16.0, "speed"),
    ],
)
def test_never_auto_selects_distil_tiny_base(device, vram, ram, want) -> None:
    model = model_policy.choose_model(device, vram_gb=vram, ram_gb=ram, want=want)
    assert model not in {"tiny", "base"}
    assert not model.startswith("distil")


def _patch_host(monkeypatch, **overrides) -> None:
    from dataclasses import replace

    host = HostInfo(
        is_colab=False,
        is_apple_silicon=False,
        has_cuda=False,
        vram_gb=0.0,
        cpu_cores=8,
        ram_gb=16.0,
        device="cpu",
        compute_type="int8",
    )
    host = replace(host, **overrides)
    monkeypatch.setattr(devices, "detect_host", lambda: host)


@pytest.mark.parametrize("ram", [8.0, 16.0])
def test_metal_is_accelerated_tier_not_ram_downgraded(ram) -> None:
    # whisper.cpp Metal must never be downgraded to a draft model by system RAM.
    assert model_policy.choose_model("metal", ram_gb=ram) == "large-v3-turbo"
    assert model_policy.choose_model("metal", ram_gb=ram, want="quality") == "large-v3"
    assert model_policy.choose_model("metal", ram_gb=ram) not in {"tiny", "base", "small"}


def test_apple_silicon_faster_whisper_cuda_override_is_clamped(monkeypatch) -> None:
    _patch_host(monkeypatch, is_apple_silicon=True, device="cpu", compute_type="int8")
    res = model_policy.auto_select(backend="faster-whisper", device="cuda")
    assert res.device == "cpu"  # invalid cuda on Apple Silicon → clamped
    assert res.compute_type == "int8"
    assert "clamped" in res.reason  # reason reflects the actual choice


def test_auto_select_apple_silicon_never_offers_cuda(monkeypatch) -> None:
    _patch_host(monkeypatch, is_apple_silicon=True, device="cpu", compute_type="int8")
    res = model_policy.auto_select()
    assert res.device == "cpu"  # NEVER cuda/mps for faster-whisper on Apple Silicon
    assert res.compute_type == "int8"
    assert res.backend == "faster-whisper"
    assert "apple-silicon" in res.reason


def test_auto_select_apple_silicon_routes_to_whispercpp_when_preferred(monkeypatch) -> None:
    _patch_host(monkeypatch, is_apple_silicon=True, device="cpu", compute_type="int8")
    res = model_policy.auto_select(prefer_whispercpp_on_apple=True)
    assert res.backend == "whispercpp"
    assert res.device == "metal"  # whisper.cpp uses the Metal path on Apple Silicon


def test_auto_select_apple_routes_to_whispercpp_when_binary_available(monkeypatch) -> None:
    _patch_host(monkeypatch, is_apple_silicon=True, device="cpu", compute_type="int8")
    monkeypatch.setattr(
        "scribeflow.backends.registry.is_available", lambda name: name == "whispercpp"
    )
    res = model_policy.auto_select()  # no explicit backend, no prefer flag
    assert res.backend == "whispercpp"
    assert res.device == "metal"
    assert res.compute_type == "metal"


def test_auto_select_apple_falls_back_to_faster_whisper_without_binary(monkeypatch) -> None:
    _patch_host(monkeypatch, is_apple_silicon=True, device="cpu", compute_type="int8")
    monkeypatch.setattr("scribeflow.backends.registry.is_available", lambda name: False)
    res = model_policy.auto_select()
    assert res.backend == "faster-whisper"
    assert res.device == "cpu"  # never cuda/mps for faster-whisper on Apple Silicon


def test_auto_select_cuda_host(monkeypatch) -> None:
    _patch_host(monkeypatch, has_cuda=True, vram_gb=16.0, device="cuda", compute_type="float16")
    res = model_policy.auto_select()
    assert res.device == "cuda"
    assert res.compute_type == "float16"
    assert res.model == "large-v3"


def test_auto_select_override_wins(monkeypatch) -> None:
    _patch_host(monkeypatch, has_cuda=True, vram_gb=16.0, device="cuda", compute_type="float16")
    res = model_policy.auto_select(model="large-v3-turbo", compute_type="int8_float16")
    assert res.model == "large-v3-turbo"
    assert res.compute_type == "int8_float16"
