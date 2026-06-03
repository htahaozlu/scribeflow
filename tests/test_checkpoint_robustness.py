"""Robustness regressions found by P1 adversarial verification.

Locks: (1) a corrupt-but-present JSON checkpoint is non-fatal and self-heals
(invariant 3); (2) a null/garbage ``completed_chunks`` does not abort;
(3) temp files orphaned by a torn ``os.replace`` are swept on the next run
(invariant 1); (4) tuples in ``BackendFingerprint.extra`` do not cause a false
identity mismatch after a JSON round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scribeflow.engine import io_atomic
from scribeflow.engine.checkpoint import identities_match, identity_to_dict
from scribeflow.engine.pipeline import EngineConfig, run_batch
from scribeflow.engine.text import build_full_transcript
from scribeflow.engine.types import (
    BackendFingerprint,
    ChunkingSpec,
    FileSignature,
    RunIdentity,
    TranscribeOptions,
)
from tests.fakes import AtomicWriteCrasher, CrashInjected, FakeDeterministicBackend

N_CHUNKS = 3


def _config(tmp_path: Path) -> EngineConfig:
    return EngineConfig(
        output_dir=tmp_path / "output",
        workspace_dir=tmp_path / "workspace",
        chunking=ChunkingSpec(chunk_seconds=2),
    )


def _video_dir(config: EngineConfig, media: Path) -> Path:
    return Path(config.output_dir) / media.stem


def _assert_final(video_dir: Path, n: int = N_CHUNKS) -> None:
    chunk_outputs = video_dir / "chunk_outputs"
    transcript = (video_dir / f"{video_dir.name}_transcript.txt").read_text(encoding="utf-8")
    assert transcript.strip() == build_full_transcript(chunk_outputs)
    for i in range(n):
        assert transcript.count(f"chunk {i} sentence 0 alpha beta") == 1
    progress = io_atomic.read_json(video_dir / "progress.json", default={})
    assert progress.get("status") == "completed"
    assert progress.get("completed_chunks") == list(range(n))
    for jf in chunk_outputs.glob("chunk_*.json"):
        json.loads(jf.read_text(encoding="utf-8"))
    assert list(video_dir.rglob("*.tmp")) == []


def _crash_after_chunk0(
    config: EngineConfig, backend: FakeDeterministicBackend, media: Path, monkeypatch
) -> None:
    """Drive a partial (status=running, completed_chunks=[0]) state, then return."""
    crasher = AtomicWriteCrasher(
        monkeypatch, lambda k, p, h: k == "json" and p.endswith("chunk_001.json")
    )
    crasher.install()
    with pytest.raises(CrashInjected):
        run_batch(config, backend, [media])
    crasher.crashed = True  # ensure inert for the resume


def test_corrupt_chunk_json_on_resume_self_heals(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    backend = FakeDeterministicBackend()
    video_dir = _video_dir(config, sample_video)
    _crash_after_chunk0(config, backend, sample_video, monkeypatch)

    # Corrupt an already-completed chunk's JSON; resume must not crash.
    (video_dir / "chunk_outputs" / "chunk_000.json").write_text("{ broken", encoding="utf-8")
    run_batch(config, backend, [sample_video])

    json.loads((video_dir / "chunk_outputs" / "chunk_000.json").read_text(encoding="utf-8"))
    _assert_final(video_dir)


def test_corrupt_progress_json_is_non_fatal(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    backend = FakeDeterministicBackend()
    video_dir = _video_dir(config, sample_video)
    _crash_after_chunk0(config, backend, sample_video, monkeypatch)

    (video_dir / "progress.json").write_text("{ not json at all", encoding="utf-8")
    run_batch(config, backend, [sample_video])
    _assert_final(video_dir)


def test_null_completed_chunks_is_non_fatal(sample_video: Path, tmp_path: Path) -> None:
    config = _config(tmp_path)
    video_dir = _video_dir(config, sample_video)
    video_dir.mkdir(parents=True, exist_ok=True)
    io_atomic.write_json(
        video_dir / "progress.json",
        {"video_name": sample_video.name, "status": "running", "completed_chunks": None},
    )
    run_batch(config, FakeDeterministicBackend(), [sample_video])
    _assert_final(video_dir)


def test_orphan_tmp_swept_on_resume(sample_video: Path, tmp_path: Path) -> None:
    config = _config(tmp_path)
    backend = FakeDeterministicBackend()
    run_batch(config, backend, [sample_video])
    video_dir = _video_dir(config, sample_video)

    # Simulate temp files left by a torn os.replace during finalization.
    (video_dir / "summary.json.tmp").write_text("partial", encoding="utf-8")
    (video_dir / "chunk_outputs" / "chunk_000.json.tmp").write_text("partial", encoding="utf-8")

    # Resume hits the completed short-circuit, but the sweep runs first.
    run_batch(config, backend, [sample_video])
    assert list(video_dir.rglob("*.tmp")) == []
    _assert_final(video_dir)


def test_concurrent_atomic_writes_never_corrupt(tmp_path: Path) -> None:
    """Two threads hammering the SAME path (the concurrent-web-job scenario) must
    never produce a torn file — unique temp names keep each write isolated."""
    import threading

    target = tmp_path / "shared.json"
    payload_a = {"writer": "a", "data": list(range(60))}
    payload_b = {"writer": "b", "data": list(range(60, 120))}
    errors: list[Exception] = []

    def writer(payload: dict) -> None:
        try:
            for _ in range(60):
                io_atomic.write_json(target, payload)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(p,)) for p in (payload_a, payload_b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    result = json.loads(target.read_text(encoding="utf-8"))  # always one complete payload
    assert result in (payload_a, payload_b)
    assert list(tmp_path.glob("*.tmp")) == []  # no orphaned temp files


def test_identity_match_with_tuple_in_extra() -> None:
    fingerprint = BackendFingerprint(
        backend="faster-whisper",
        model="large-v3",
        extra={"langs": ("tr", "en"), "beams": (1, 2)},
    )
    identity = RunIdentity(
        source=FileSignature(name="a.mp4", size_bytes=1, mtime=2),
        chunking=ChunkingSpec(),
        backend=fingerprint,
        options=TranscribeOptions(),
    )
    # Persisted form turns tuples into lists.
    stored = json.loads(json.dumps(identity_to_dict(identity)))
    assert identities_match(stored, identity) is True

    changed = RunIdentity(
        source=FileSignature(name="a.mp4", size_bytes=1, mtime=2),
        chunking=ChunkingSpec(),
        backend=BackendFingerprint(backend="faster-whisper", model="DIFFERENT"),
        options=TranscribeOptions(),
    )
    assert identities_match(stored, changed) is False
