"""Test doubles: a deterministic backend + crash-injection harnesses.

The fake backend lets the whole engine run end-to-end with NO ML dependency,
exercising real chunking + real checkpointing while keeping transcription
deterministic (so re-doing a half-written chunk yields identical text —
docs/ai/02 §5 invariant 5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scribeflow.engine import io_atomic
from scribeflow.engine.types import (
    BackendFingerprint,
    ChunkRequest,
    TranscriptionResult,
    TranscriptSegment,
)


@dataclass
class _FWSegment:
    start: float
    end: float
    text: str


@dataclass
class _FWInfo:
    language: str
    duration: float


class FakeWhisperModel:
    """Mimics ``faster_whisper.WhisperModel`` — ``transcribe`` returns
    ``(segments_iterator, info)``. Lets us test the adapter's normalization with
    no model download. Records the kwargs of each call for assertion."""

    def __init__(
        self,
        segments: list[tuple[float, float, str]],
        *,
        language: str = "tr",
        duration: float = 5.0,
    ) -> None:
        self._segments = segments
        self._language = language
        self._duration = duration
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def transcribe(self, audio: str, **kwargs: Any) -> tuple[Any, _FWInfo]:
        self.calls.append((audio, kwargs))
        segments = (_FWSegment(s, e, t) for (s, e, t) in self._segments)
        return segments, _FWInfo(self._language, self._duration)


class FakeOpenaiModel:
    """Mimics ``whisper.load_model(...)`` — ``transcribe`` returns a dict with
    ``segments`` / ``language`` / ``text`` (the openai-whisper shape)."""

    def __init__(self, segments: list[tuple[float, float, str]], *, language: str = "tr") -> None:
        self._segments = segments
        self._language = language
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def transcribe(self, audio: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((audio, kwargs))
        return {
            "segments": [{"start": s, "end": e, "text": t} for (s, e, t) in self._segments],
            "language": self._language,
            "text": " ".join(t for (_, _, t) in self._segments),
        }


class FakeDeterministicBackend:
    """Implements the TranscriptionBackend Protocol. Output depends only on the
    chunk index, so it is byte-for-byte reproducible across runs."""

    def __init__(self, model: str = "fake-det", sentences_per_chunk: int = 3) -> None:
        self._model = model
        self._spc = sentences_per_chunk

    @property
    def fingerprint(self) -> BackendFingerprint:
        return BackendFingerprint(
            backend="fake",
            model=self._model,
            version="1",
            device="cpu",
            compute_type="int8",
        )

    def transcribe_chunk(self, request: ChunkRequest) -> TranscriptionResult:
        i = request.chunk_index
        segments: list[TranscriptSegment] = []
        parts: list[str] = []
        for s in range(self._spc):
            # >=3 words so clean_transcript keeps it; unique per (chunk, sentence)
            # so nothing is deduped within or across chunks.
            sentence = f"chunk {i} sentence {s} alpha beta"
            parts.append(sentence)
            segments.append(TranscriptSegment(start=float(s), end=float(s + 1), text=sentence))
        raw = ". ".join(parts) + "."
        return TranscriptionResult(
            text=raw,
            segments=tuple(segments),
            language=request.options.language,
            duration=float(self._spc),
            fingerprint=self.fingerprint,
        )


class CrashInjected(Exception):
    """Marker raised by the crash harnesses to simulate a hard process kill."""


class AtomicWriteCrasher:
    """Patch ``io_atomic.write_text`` / ``write_json`` to raise BEFORE writing,
    the first time ``predicate(kind, path, history)`` returns True.

    Because the crash happens before the real atomic write runs, the targeted
    file is simply absent (no tmp, no partial) — modelling a kill *between* two
    commit steps (docs/ai/02 §4 step boundaries 3↔4, 4↔7, 6↔7).
    """

    def __init__(
        self, monkeypatch, predicate: Callable[[str, str, list[tuple[str, str]]], bool]
    ) -> None:
        self.monkeypatch = monkeypatch
        self.predicate = predicate
        self.history: list[tuple[str, str]] = []
        self.crashed = False
        self._real_text = io_atomic.write_text
        self._real_json = io_atomic.write_json

    def _maybe(self, kind: str, path: Path) -> None:
        name = Path(path).name
        if not self.crashed and self.predicate(kind, str(path), list(self.history)):
            self.crashed = True
            raise CrashInjected(f"injected crash before {kind} write: {name}")
        self.history.append((kind, name))

    def install(self) -> None:
        def text(path: Path, content: str) -> None:
            self._maybe("text", path)
            self._real_text(path, content)

        def js(path: Path, data: object) -> None:
            self._maybe("json", path)
            self._real_json(path, data)

        self.monkeypatch.setattr(io_atomic, "write_text", text)
        self.monkeypatch.setattr(io_atomic, "write_json", js)


class ReplaceCrasher:
    """Patch ``Path.replace`` to raise the first time it targets a path matching
    ``name_endswith`` — AFTER the tmp file is written but BEFORE the rename.

    This exercises the real atomic mechanism's torn-write case directly: the
    final file must be left as its previous valid version (or absent), never a
    half-written file, and the leftover ``.tmp`` must never be read as complete
    (docs/ai/02 §5 invariant 1).
    """

    def __init__(self, monkeypatch, name_endswith: str) -> None:
        self.monkeypatch = monkeypatch
        self.name_endswith = name_endswith
        self.crashed = False
        self._real_replace = Path.replace

    def install(self) -> None:
        real_replace = self._real_replace
        harness = self

        def replace(self: Path, target: Path | str) -> Path:
            if not harness.crashed and str(target).endswith(harness.name_endswith):
                harness.crashed = True
                raise CrashInjected(f"injected crash before replace -> {target}")
            return real_replace(self, target)

        self.monkeypatch.setattr(Path, "replace", replace)
