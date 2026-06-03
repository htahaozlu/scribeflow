"""RunIdentity guard (docs/ai/05 §5). Resuming with a different backend/model
must raise instead of silently mixing outputs; --overwrite starts fresh.

(Pre-validates the P2 gate; the logic lives in checkpoint.py, built in P1.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scribeflow.engine import io_atomic
from scribeflow.engine.checkpoint import CheckpointIdentityError
from scribeflow.engine.pipeline import EngineConfig, run_batch
from scribeflow.engine.types import ChunkingSpec
from tests.fakes import FakeDeterministicBackend


def _config(tmp_path: Path, *, overwrite: bool = False) -> EngineConfig:
    return EngineConfig(
        output_dir=tmp_path / "output",
        workspace_dir=tmp_path / "workspace",
        chunking=ChunkingSpec(chunk_seconds=2),
        overwrite=overwrite,
    )


def test_identity_mismatch_raises(sample_video: Path, tmp_path: Path) -> None:
    run_batch(_config(tmp_path), FakeDeterministicBackend(model="model-a"), [sample_video])

    with pytest.raises(CheckpointIdentityError):
        run_batch(_config(tmp_path), FakeDeterministicBackend(model="model-b"), [sample_video])


def test_overwrite_starts_fresh_run(sample_video: Path, tmp_path: Path) -> None:
    run_batch(_config(tmp_path), FakeDeterministicBackend(model="model-a"), [sample_video])
    run_batch(
        _config(tmp_path, overwrite=True),
        FakeDeterministicBackend(model="model-b"),
        [sample_video],
    )

    progress_path = tmp_path / "output" / sample_video.stem / "progress.json"
    progress = io_atomic.read_json(progress_path, default={})
    assert progress["status"] == "completed"
    assert progress["run_identity"]["backend"]["model"] == "model-b"


def test_same_identity_resumes_cleanly(sample_video: Path, tmp_path: Path) -> None:
    backend = FakeDeterministicBackend(model="model-a")
    run_batch(_config(tmp_path), backend, [sample_video])
    # Same identity -> no raise, idempotent finalization.
    run_batch(_config(tmp_path), backend, [sample_video])
    progress_path = tmp_path / "output" / sample_video.stem / "progress.json"
    progress = io_atomic.read_json(progress_path, default={})
    assert progress["status"] == "completed"
