"""Crash-injection tests — the heart of the resume guarantee (docs/ai/02 §6).

A kill is simulated between the per-chunk commit steps (docs/ai/02 §4):
    step 3  write chunk_NNN.txt   (cleaned)
    step 4  write chunk_NNN.json  (raw + cleaned)
    step 6  rebuild transcript    (derived from ALL chunk txts)
    step 7  write progress.json   (records the index)
Targeting chunk index 1 (a completed chunk before it, a pending one after it),
we assert the post-crash disk state, then resume and assert the final transcript
has every chunk exactly once with no corruption — proving invariants 1–6.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scribeflow.engine import io_atomic
from scribeflow.engine.pipeline import EngineConfig, run_batch
from scribeflow.engine.text import build_full_transcript
from scribeflow.engine.types import ChunkingSpec
from tests.fakes import (
    AtomicWriteCrasher,
    CrashInjected,
    FakeDeterministicBackend,
    ReplaceCrasher,
)

N_CHUNKS = 3  # 5s fixture / 2s chunk length


def _config(tmp_path: Path) -> EngineConfig:
    return EngineConfig(
        output_dir=tmp_path / "output",
        workspace_dir=tmp_path / "workspace",
        chunking=ChunkingSpec(chunk_seconds=2),
    )


def _video_dir(config: EngineConfig, media: Path) -> Path:
    return Path(config.output_dir) / media.stem


def _assert_final_integrity(video_dir: Path, n: int = N_CHUNKS) -> None:
    chunk_outputs = video_dir / "chunk_outputs"
    transcript = (video_dir / f"{video_dir.name}_transcript.txt").read_text(encoding="utf-8")

    # Invariant 4: the transcript is exactly the sorted concat of chunk txts.
    assert transcript.strip() == build_full_transcript(chunk_outputs)

    # No duplication: each chunk's unique marker appears exactly once.
    for i in range(n):
        marker = f"chunk {i} sentence 0 alpha beta"
        assert transcript.count(marker) == 1, f"chunk {i} duplicated/missing"

    progress = io_atomic.read_json(video_dir / "progress.json", default={})
    assert progress.get("status") == "completed"
    assert progress.get("completed_chunks") == list(range(n))

    # Invariant 1: every JSON on disk is complete (no half-written file readable),
    # and no temp files leak into the final state.
    for jf in chunk_outputs.glob("chunk_*.json"):
        json.loads(jf.read_text(encoding="utf-8"))
    assert list(video_dir.rglob("*.tmp")) == [], "no .tmp may survive to the final state"


def test_clean_run_end_to_end(sample_video: Path, tmp_path: Path) -> None:
    config = _config(tmp_path)
    run_batch(config, FakeDeterministicBackend(), [sample_video])
    _assert_final_integrity(_video_dir(config, sample_video))


def test_crash_between_steps_3_and_4(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kill after chunk_001.txt, before chunk_001.json."""
    config = _config(tmp_path)
    backend = FakeDeterministicBackend()
    video_dir = _video_dir(config, sample_video)
    chunk_outputs = video_dir / "chunk_outputs"

    crasher = AtomicWriteCrasher(
        monkeypatch, lambda k, p, h: k == "json" and p.endswith("chunk_001.json")
    )
    crasher.install()
    with pytest.raises(CrashInjected):
        run_batch(config, backend, [sample_video])

    # Post-crash: txt committed, json absent, progress still only knows chunk 0.
    assert (chunk_outputs / "chunk_001.txt").exists()
    assert not (chunk_outputs / "chunk_001.json").exists()
    assert io_atomic.read_json(video_dir / "progress.json", default={})["completed_chunks"] == [0]

    # Resume (crasher now inert) -> clean completion.
    run_batch(config, backend, [sample_video])
    _assert_final_integrity(video_dir)


def test_crash_between_steps_4_and_7_at_transcript(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kill after chunk_001.json, before the transcript rebuild for chunk 1."""
    config = _config(tmp_path)
    backend = FakeDeterministicBackend()
    video_dir = _video_dir(config, sample_video)
    chunk_outputs = video_dir / "chunk_outputs"

    crasher = AtomicWriteCrasher(
        monkeypatch,
        lambda k, p, h: k == "text"
        and p.endswith("_transcript.txt")
        and ("json", "chunk_001.json") in h,
    )
    crasher.install()
    with pytest.raises(CrashInjected):
        run_batch(config, backend, [sample_video])

    # Post-crash: both chunk-1 artifacts exist, but the transcript hasn't yet
    # gained chunk 1 and progress hasn't recorded it.
    assert (chunk_outputs / "chunk_001.json").exists()
    transcript = (video_dir / f"{video_dir.name}_transcript.txt").read_text(encoding="utf-8")
    assert "chunk 1 sentence 0 alpha beta" not in transcript
    assert io_atomic.read_json(video_dir / "progress.json", default={})["completed_chunks"] == [0]

    run_batch(config, backend, [sample_video])
    _assert_final_integrity(video_dir)


def test_crash_between_steps_6_and_7(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dangerous case: transcript already rebuilt with chunk 1, but progress
    not yet updated. Resume must NOT duplicate chunk 1 (invariant 4)."""
    config = _config(tmp_path)
    backend = FakeDeterministicBackend()
    video_dir = _video_dir(config, sample_video)

    crasher = AtomicWriteCrasher(
        monkeypatch,
        lambda k, p, h: k == "json"
        and p.endswith("progress.json")
        and ("json", "chunk_001.json") in h,
    )
    crasher.install()
    with pytest.raises(CrashInjected):
        run_batch(config, backend, [sample_video])

    # Artifact is ahead of bookkeeping: transcript has chunk 1, progress says [0].
    transcript = (video_dir / f"{video_dir.name}_transcript.txt").read_text(encoding="utf-8")
    assert "chunk 1 sentence 0 alpha beta" in transcript
    assert io_atomic.read_json(video_dir / "progress.json", default={})["completed_chunks"] == [0]

    run_batch(config, backend, [sample_video])
    _assert_final_integrity(video_dir)


def test_torn_replace_leaves_no_partial_file(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Crash DURING the atomic write (tmp written, os.replace fails) for
    chunk_001.json. The .tmp must never be read as the real file (invariant 1)."""
    config = _config(tmp_path)
    backend = FakeDeterministicBackend()
    video_dir = _video_dir(config, sample_video)
    chunk_outputs = video_dir / "chunk_outputs"

    crasher = ReplaceCrasher(monkeypatch, name_endswith="chunk_001.json")
    crasher.install()
    with pytest.raises(CrashInjected):
        run_batch(config, backend, [sample_video])

    # Torn state: a (uniquely-named) tmp present, real file absent, read_json blind to the tmp.
    tmps = [
        p
        for p in chunk_outputs.iterdir()
        if p.name.startswith("chunk_001.json") and p.suffix == ".tmp"
    ]
    assert tmps, "the torn write should leave its temp file behind"
    assert not (chunk_outputs / "chunk_001.json").exists()
    assert io_atomic.read_json(chunk_outputs / "chunk_001.json", default={"missing": True}) == {
        "missing": True
    }

    run_batch(config, backend, [sample_video])
    _assert_final_integrity(video_dir)


def test_resume_skips_completed_chunks_without_retranscribing(
    sample_video: Path, tmp_path: Path
) -> None:
    """A second clean run must skip every already-committed chunk (counts backend
    calls to prove the dual-condition + identity skip guard fires)."""
    config = _config(tmp_path)

    class CountingBackend(FakeDeterministicBackend):
        calls = 0

        def transcribe_chunk(self, request):
            type(self).calls += 1
            return super().transcribe_chunk(request)

    backend = CountingBackend()
    run_batch(config, backend, [sample_video])
    assert CountingBackend.calls == N_CHUNKS

    # Re-run: everything is already committed -> zero new transcription calls.
    run_batch(config, backend, [sample_video])
    assert CountingBackend.calls == N_CHUNKS
    _assert_final_integrity(_video_dir(config, sample_video))
