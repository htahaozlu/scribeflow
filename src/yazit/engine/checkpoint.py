"""Resume bookkeeping: RunIdentity persistence/validation, the skip guard, and
progress/summary read+write. See docs/ai/02 §3 & §5 and docs/ai/05 §5.

RunIdentity is the correctness fix Codex flagged: because the transcript is
rebuilt from disk, resuming with a *different* backend/model/chunking/options
could silently mix outputs. We persist the identity and refuse to resume on a
mismatch unless ``--overwrite`` starts a fresh run.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from yazit.engine import io_atomic
from yazit.engine.types import RunIdentity


class CheckpointIdentityError(RuntimeError):
    """Resuming a run whose persisted identity differs from the current request."""


def _canonical(value: Any) -> Any:
    """JSON round-trip so non-native values (tuples/sets in BackendFingerprint.extra)
    compare equal to their persisted list forms — otherwise an identical run would
    falsely mismatch after a reload."""
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def identity_to_dict(identity: RunIdentity) -> dict[str, Any]:
    """Canonical JSON-comparable form (used for both persistence and equality)."""
    return asdict(identity)


def identities_match(stored: Any, current: RunIdentity) -> bool:
    """True iff a previously stored identity dict equals the current identity.

    A missing/empty stored identity means "nothing to conflict with" → matches,
    so a fresh run is never blocked (the chunk-level skip guard, by contrast,
    requires a *positive* identity — see :func:`should_skip_chunk`).
    """
    if not stored:
        return True
    return _canonical(stored) == _canonical(identity_to_dict(current))


def validate_resume_identity(
    existing_progress: dict[str, Any], current: RunIdentity, *, overwrite: bool
) -> None:
    """Raise :class:`CheckpointIdentityError` on a mismatch (unless overwriting)."""
    if overwrite:
        return
    stored = existing_progress.get("run_identity")
    if stored and not identities_match(stored, current):
        raise CheckpointIdentityError(
            "Checkpoint identity mismatch — refusing to mix outputs from a "
            "different backend/model/chunking/options. Re-run with --overwrite to "
            "start a fresh run with the new identity."
        )


def should_skip_chunk(
    index: int,
    completed_chunks: set[int],
    chunk_text_path: Path,
    chunk_json_path: Path,
    current: RunIdentity,
) -> bool:
    """Strengthened skip guard (docs/ai/05 §5).

    A chunk is skipped ONLY when progress records it AND both on-disk artifacts
    exist AND the chunk's stored identity matches the current run. Never trust
    ``progress.json`` alone — a torn/stale progress file must stay non-fatal.
    """
    if index not in completed_chunks:
        return False
    if not (chunk_text_path.exists() and chunk_json_path.exists()):
        return False
    chunk_json = io_atomic.read_json(chunk_json_path, default={})
    stored_identity = chunk_json.get("run_identity")
    # Require a POSITIVE identity match: a chunk whose JSON is corrupt/torn (read
    # back as {}) or lacks an identity cannot be confirmed complete → redo it,
    # so a damaged chunk record self-heals (deterministic re-transcribe).
    return bool(stored_identity) and identities_match(stored_identity, current)


def load_progress(progress_path: Path, video_name: str) -> dict[str, Any]:
    return io_atomic.read_json(
        progress_path,
        default={
            "video_name": video_name,
            "started_at": io_atomic.timestamp(),
            "completed_chunks": [],
        },
    )


def write_progress(progress_path: Path, payload: dict[str, Any]) -> None:
    io_atomic.write_json(progress_path, payload)


def write_summary(summary_path: Path, payload: dict[str, Any]) -> None:
    io_atomic.write_json(summary_path, payload)
