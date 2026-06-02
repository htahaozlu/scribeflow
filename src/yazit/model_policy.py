"""Auto-select the model + compute type for the detected hardware (docs/ai/03 §3).

Turkish-focused: never auto-select an English-only ``distil-*`` model, nor the
low-quality ``tiny``/``base`` tiers. A user ``--model`` / ``--backend`` /
``--compute-type`` override always wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from yazit import devices

Want = Literal["default", "speed", "quality"]

# Single global fallback if forced to pick one (docs/ai/03 §3).
GLOBAL_DEFAULT_MODEL = "large-v3-turbo"

# Never auto-selected for Turkish (English-only / too low quality).
FORBIDDEN_AUTO_MODELS = {"tiny", "base"}

# Condensed catalog for ``yazit models`` (docs/ai/03 §1).
MODEL_CATALOG: dict[str, dict[str, str]] = {
    "large-v3": {"params": "1550M", "turkish": "best", "note": "highest quality"},
    "large-v3-turbo": {"params": "809M", "turkish": "very good", "note": "~6–8x faster (default)"},
    "large-v2": {"params": "1550M", "turkish": "very good", "note": ""},
    "medium": {"params": "769M", "turkish": "good", "note": "good budget"},
    "small": {"params": "244M", "turkish": "draft", "note": "drafts only"},
    "base": {"params": "74M", "turkish": "weak", "note": "not auto-selected"},
    "tiny": {"params": "39M", "turkish": "avoid", "note": "not auto-selected"},
    "distil-large-v3": {"params": "756M", "turkish": "English-only", "note": "excluded for TR"},
}


def _pick(table: dict[str, str], want: str) -> str:
    return table.get(want, table["default"])


def choose_model(
    device: str,
    *,
    vram_gb: float = 0.0,
    ram_gb: float = 0.0,
    want: Want = "default",
    override: str | None = None,
) -> str:
    """Apply the docs/ai/03 §3 decision table. ``override`` short-circuits."""
    if override:
        return override

    if device == "cuda":
        if vram_gb >= 12:  # Colab T4 is 16GB — do NOT downgrade here.
            return _pick(
                {"speed": "large-v3-turbo", "quality": "large-v3", "default": "large-v3"}, want
            )
        # 4–8 GB
        return _pick(
            {"speed": "large-v3-turbo", "quality": "large-v3", "default": "large-v3-turbo"}, want
        )

    # CPU (incl. Apple Silicon, which is CPU-only for faster-whisper)
    if ram_gb and ram_gb < 12:  # ~8 GB tier
        return _pick({"speed": "small", "quality": "medium", "default": "small"}, want)
    return _pick(
        {"speed": "medium", "quality": "large-v3", "default": GLOBAL_DEFAULT_MODEL}, want
    )


@dataclass(frozen=True)
class ModelResolution:
    backend: str
    model: str
    device: str
    compute_type: str
    reason: str


def auto_select(
    *,
    want: Want = "default",
    backend: str | None = None,
    model: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
    prefer_whispercpp_on_apple: bool = False,
) -> ModelResolution:
    """Resolve a full (backend, model, device, compute_type) for this host.

    Overrides always win. ``prefer_whispercpp_on_apple`` is wired by P6 (the
    whisper.cpp Metal path); in P2 the Apple-Silicon default is faster-whisper
    CPU int8 — and crucially never cuda/mps for faster-whisper (docs/ai/03 §2).
    """
    host = devices.detect_host()
    chosen_device = device or host.device
    chosen_compute = compute_type or host.compute_type
    chosen_model = choose_model(
        chosen_device, vram_gb=host.vram_gb, ram_gb=host.ram_gb, want=want, override=model
    )

    chosen_backend = backend or "faster-whisper"
    reason_bits = []
    if host.is_apple_silicon:
        reason_bits.append("apple-silicon → faster-whisper CPU int8 (CT2 has no Metal)")
        if prefer_whispercpp_on_apple and not backend:
            chosen_backend = "whispercpp"
            reason_bits.append("routed to whisper.cpp (Metal)")
    elif host.has_cuda:
        reason_bits.append(f"cuda {host.vram_gb}GB → {chosen_compute}")
    else:
        reason_bits.append(f"cpu {host.ram_gb}GB → int8")

    # Guard: never let auto-selection (no explicit model) land on a forbidden tier.
    if not model and chosen_model in FORBIDDEN_AUTO_MODELS:
        chosen_model = GLOBAL_DEFAULT_MODEL
        reason_bits.append(f"avoided {FORBIDDEN_AUTO_MODELS} → {GLOBAL_DEFAULT_MODEL}")

    return ModelResolution(
        backend=chosen_backend,
        model=chosen_model,
        device=chosen_device,
        compute_type=chosen_compute,
        reason="; ".join(reason_bits) or "default",
    )
