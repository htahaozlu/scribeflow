"""Backend registry — name → factory, with availability/extras resolution.

P2 implements only ``faster-whisper`` (the default, base install). The other two
names are registered so ``yazit models`` / ``yazit doctor`` can report them and
their extras; their factories are wired in P6.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any

from yazit.backends.faster_whisper import FasterWhisperBackend
from yazit.engine.types import TranscriptionBackend


@dataclass(frozen=True)
class BackendSpec:
    name: str
    import_name: str  # module probed for availability
    extra: str | None  # pip extra providing it (None = base install)
    implemented: bool  # whether create_backend can build it yet


KNOWN_BACKENDS: dict[str, BackendSpec] = {
    "faster-whisper": BackendSpec("faster-whisper", "faster_whisper", None, True),
    "whispercpp": BackendSpec("whispercpp", "", "cpp", True),  # availability = binary on PATH
    "openai-whisper": BackendSpec("openai-whisper", "whisper", "openai", True),
}

DEFAULT_BACKEND = "faster-whisper"


def is_available(name: str) -> bool:
    spec = KNOWN_BACKENDS.get(name)
    if spec is None:
        return False
    if name == "whispercpp":
        # whisper.cpp is a separate binary, not a Python import.
        from yazit.backends.whispercpp import find_whispercpp_binary

        return find_whispercpp_binary() is not None
    return importlib.util.find_spec(spec.import_name) is not None


def available_backends() -> list[str]:
    return [name for name in KNOWN_BACKENDS if is_available(name)]


def create_backend(
    name: str,
    *,
    model: str,
    device: str = "cpu",
    compute_type: str = "int8",
    **kwargs: Any,
) -> TranscriptionBackend:
    spec = KNOWN_BACKENDS.get(name)
    if spec is None:
        raise ValueError(
            f"Unknown backend {name!r}. Known: {sorted(KNOWN_BACKENDS)}"
        )
    if name == "faster-whisper":
        return FasterWhisperBackend(model, device=device, compute_type=compute_type, **kwargs)
    if name == "whispercpp":
        from yazit.backends.whispercpp import WhisperCppBackend

        return WhisperCppBackend(model, device=device, compute_type=compute_type, **kwargs)
    if name == "openai-whisper":
        from yazit.backends.openai_whisper import OpenaiWhisperBackend

        return OpenaiWhisperBackend(model, device=device, compute_type=compute_type, **kwargs)
    raise NotImplementedError(f"Backend {name!r} has no factory.")  # pragma: no cover
