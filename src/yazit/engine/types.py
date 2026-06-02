"""Shared vocabulary for the engine: dataclasses + the backend/contract Protocols.

This module is the single home of the cross-cutting types so the engine never
imports from ``yazit.backends`` (which would invert the dependency direction —
backends implement these contracts, the engine only depends on them). See
docs/ai/05-architecture.md §2–§5. ``yazit.backends.base`` re-exports the
``TranscriptionBackend`` Protocol for discoverability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

# --------------------------------------------------------------------------- #
# Chunking (docs/ai/05 §3)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChunkingSpec:
    """Backend-agnostic audio segmentation parameters. Chunk = resumability unit."""

    chunk_seconds: int = 20 * 60
    sample_rate: int = 16_000
    channels: int = 1
    codec: str = "pcm_s16le"


@dataclass(frozen=True)
class AudioChunk:
    index: int
    path: Path
    name: str
    start_seconds: float
    duration_seconds: float


# --------------------------------------------------------------------------- #
# Source signature (docs/ai/05 §4)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FileSignature:
    name: str
    size_bytes: int
    mtime: int
    sha256: str | None = None  # only for copied/downloaded media


@dataclass(frozen=True)
class SourceSpec:
    kind: Literal["local", "upload", "drive", "url"]
    uri: str


@dataclass(frozen=True)
class ResolvedMedia:
    """A source materialized to a local file the engine can chunk."""

    local_path: Path
    display_name: str
    source_id: str
    origin_uri: str
    signature: FileSignature


@dataclass(frozen=True)
class RuntimeDirs:
    """Where each kind of I/O lives. The Errno-107 split (docs/ai/01, §4 of doc 05):
    heavy/scratch I/O on a LOCAL ``workspace_dir``; only small durable transcripts
    + checkpoints on ``output_dir`` (which may be a Drive FUSE mount)."""

    workspace_dir: Path  # SCRATCH / heavy I/O: downloads, audio chunks, temp files
    output_dir: Path  # DURABLE: chunk_outputs/, transcript, progress.json, summary.json
    cache_dir: Path  # model downloads


# --------------------------------------------------------------------------- #
# Backend Protocol vocabulary (docs/ai/05 §2 — from the Codex memo)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TranscriptSegment:
    start: float  # chunk-relative seconds
    end: float
    text: str


@dataclass(frozen=True)
class TranscribeOptions:
    language: str = "tr"
    task: Literal["transcribe"] = "transcribe"
    beam_size: int = 5
    temperature: float = 0.0  # determinism — docs/ai/02 invariant 5
    initial_prompt: str | None = None  # from tail_prompt(previous chunk)
    vad_filter: bool = True
    word_timestamps: bool = False


@dataclass(frozen=True)
class ChunkRequest:
    audio_path: Path
    chunk_index: int
    chunk_name: str
    options: TranscribeOptions


@dataclass(frozen=True)
class BackendFingerprint:
    backend: str  # "faster-whisper" | "whispercpp" | "openai-whisper" | "fake"
    model: str
    version: str | None = None
    device: str | None = None
    compute_type: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TranscriptionResult:
    text: str  # raw joined segment text (cleaning happens in the pipeline)
    segments: tuple[TranscriptSegment, ...]
    language: str
    duration: float
    fingerprint: BackendFingerprint


@runtime_checkable
class TranscriptionBackend(Protocol):
    """The unifying seam. Adapters normalize backend output ONLY — they never
    write checkpoint files (docs/ai/05 §2)."""

    @property
    def fingerprint(self) -> BackendFingerprint: ...

    def transcribe_chunk(self, request: ChunkRequest) -> TranscriptionResult: ...


# --------------------------------------------------------------------------- #
# Run identity (docs/ai/05 §5) — prevents silent cross-run corruption
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunIdentity:
    """Persisted in progress.json / summary.json / each chunk_NNN.json. Resuming
    with a different source/chunking/backend/options must raise, never mix."""

    source: FileSignature
    chunking: ChunkingSpec
    backend: BackendFingerprint
    options: TranscribeOptions
