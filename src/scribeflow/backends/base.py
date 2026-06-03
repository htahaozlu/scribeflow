"""Public backend contract surface.

The Protocol and its dataclasses live in :mod:`scribeflow.engine.types` (so the engine
never imports ``scribeflow.backends`` — that would invert the dependency direction).
This module re-exports them as the canonical import point for backend authors
(docs/ai/05 §1–§2).

Adapter rule (hard): a backend normalizes its engine's output into a
``TranscriptionResult`` and NOTHING else. It must never write ``chunk_NNN.txt``,
``chunk_NNN.json``, ``progress.json`` or ``summary.json`` — the pipeline owns all
checkpoint state.
"""

from __future__ import annotations

from scribeflow.engine.types import (
    BackendFingerprint,
    ChunkRequest,
    TranscribeOptions,
    TranscriptionBackend,
    TranscriptionResult,
    TranscriptSegment,
)

__all__ = [
    "BackendFingerprint",
    "ChunkRequest",
    "TranscribeOptions",
    "TranscriptSegment",
    "TranscriptionBackend",
    "TranscriptionResult",
]
