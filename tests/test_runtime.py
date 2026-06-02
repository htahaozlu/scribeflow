"""Runtime targets + the Errno-107 split (docs/ai/01, docs/ai/05 §4)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.fakes import FakeDeterministicBackend
from yazit.engine import pipeline
from yazit.engine.pipeline import EngineConfig, run_batch
from yazit.engine.types import ChunkingSpec
from yazit.runtime.base import resolve_runtime
from yazit.runtime.colab import ColabRuntime
from yazit.runtime.local import LocalRuntime
from yazit.runtime.remote import RemoteRuntime


def test_local_runtime_defaults_and_overrides(tmp_path: Path) -> None:
    rt = LocalRuntime()
    default = rt.resolve_dirs(None, None, None)
    assert default.output_dir == Path("yazit-output")
    assert default.workspace_dir == Path("yazit-workspace")

    explicit = rt.resolve_dirs(tmp_path / "o", tmp_path / "w", tmp_path / "c")
    assert explicit.output_dir == tmp_path / "o"
    assert explicit.workspace_dir == tmp_path / "w"
    assert explicit.cache_dir == tmp_path / "c"


def test_colab_runtime_bakes_in_the_errno107_split() -> None:
    dirs = ColabRuntime().resolve_dirs(None, None, None)
    # heavy I/O on LOCAL /content scratch — never the Drive FUSE mount
    assert str(dirs.workspace_dir).startswith("/content")
    assert "/drive/" not in str(dirs.workspace_dir)
    assert str(dirs.cache_dir).startswith("/content")
    # durable transcripts on Drive
    assert str(dirs.output_dir).startswith("/content/drive/MyDrive")
    # the two are distinct roots
    assert dirs.workspace_dir != dirs.output_dir


def test_colab_bootstrap_no_crash_off_colab() -> None:
    ColabRuntime().bootstrap()  # google.colab import fails gracefully (no raise)


def test_remote_runtime_is_stub() -> None:
    with pytest.raises(NotImplementedError):
        RemoteRuntime().resolve_dirs(None, None, None)
    with pytest.raises(NotImplementedError):
        RemoteRuntime().bootstrap()


def test_resolve_runtime_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_runtime("local").name == "local"
    assert resolve_runtime("colab").name == "colab"
    monkeypatch.setattr("yazit.devices.detect_colab", lambda: True)
    assert resolve_runtime(None).name == "colab"
    monkeypatch.setattr("yazit.devices.detect_colab", lambda: False)
    assert resolve_runtime(None).name == "local"


def test_fuse_failure_during_chunking_preserves_committed_transcripts(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A forced Errno-107 (Drive FUSE drop) while chunking video B must not lose
    video A's already-committed transcript (the whole point of the split)."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    a = media_dir / "a.mp4"
    b = media_dir / "b.mp4"
    shutil.copy2(sample_video, a)
    shutil.copy2(sample_video, b)

    config = EngineConfig(
        output_dir=tmp_path / "out",
        workspace_dir=tmp_path / "ws",
        chunking=ChunkingSpec(chunk_seconds=2),
    )
    backend = FakeDeterministicBackend()

    real_prepare = pipeline.prepare_audio_chunks

    def fuse_dropping_prepare(media_path, chunks_dir, spec, log_path):
        if media_path.stem == "b":
            raise OSError(107, "Transport endpoint is not connected")
        return real_prepare(media_path, chunks_dir, spec, log_path)

    monkeypatch.setattr(pipeline, "prepare_audio_chunks", fuse_dropping_prepare)

    with pytest.raises(OSError):
        run_batch(config, backend, [a, b])

    # Video A finished and committed BEFORE B's chunking failure — it survives.
    a_dir = config.output_dir / "a"
    transcript = (a_dir / "a_transcript.txt").read_text(encoding="utf-8")
    assert "chunk 0 sentence 0 alpha beta" in transcript
    import json

    progress = json.loads((a_dir / "progress.json").read_text(encoding="utf-8"))
    assert progress["status"] == "completed"
    assert list(a_dir.rglob("*.tmp")) == []
