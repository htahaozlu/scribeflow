"""ffmpeg segmentation + Layer-A cache identity (docs/ai/02 §3, docs/ai/05 §3).

Runs real ffmpeg on the bundled 5s fixture with a 2s chunk length to produce
three chunks, then asserts the cache reuses on an identity match and regenerates
on any identity change.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

from yazit.engine import io_atomic
from yazit.engine.chunking import prepare_audio_chunks
from yazit.engine.types import ChunkingSpec

SPEC = ChunkingSpec(chunk_seconds=2)


def _prepare(media: Path, chunks_dir: Path, spec: ChunkingSpec = SPEC):
    log = chunks_dir.parent / "activity.log"
    return prepare_audio_chunks(media, chunks_dir, spec, log)


def test_segments_into_three_16k_mono_pcm(sample_video: Path, tmp_path: Path) -> None:
    chunks_dir = tmp_path / "audio_chunks"
    chunks = _prepare(sample_video, chunks_dir)

    assert len(chunks) == 3
    assert [c.name for c in chunks] == ["chunk_000.wav", "chunk_001.wav", "chunk_002.wav"]
    assert [c.index for c in chunks] == [0, 1, 2]
    assert [c.start_seconds for c in chunks] == [0.0, 2.0, 4.0]

    for chunk in chunks:
        assert chunk.path.exists()
        with wave.open(str(chunk.path), "rb") as wav:
            assert wav.getframerate() == 16000  # 16 kHz
            assert wav.getnchannels() == 1  # mono
            assert wav.getsampwidth() == 2  # 16-bit pcm_s16le

    manifest = json.loads((chunks_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["completed"] is True
    assert manifest["chunking"] == {
        "chunk_seconds": 2,
        "sample_rate": 16000,
        "channels": 1,
        "codec": "pcm_s16le",
    }
    assert manifest["chunks"] == ["chunk_000.wav", "chunk_001.wav", "chunk_002.wav"]


def test_cache_reused_on_identity_match(sample_video: Path, tmp_path: Path) -> None:
    chunks_dir = tmp_path / "audio_chunks"
    _prepare(sample_video, chunks_dir)
    sentinel = chunks_dir / "_sentinel"
    sentinel.write_text("keep", encoding="utf-8")  # survives only if NOT regenerated

    chunks = _prepare(sample_video, chunks_dir)
    assert len(chunks) == 3
    assert sentinel.exists(), "cache should have been reused (no rmtree)"


def test_cache_invalidated_on_chunk_length_change(sample_video: Path, tmp_path: Path) -> None:
    chunks_dir = tmp_path / "audio_chunks"
    _prepare(sample_video, chunks_dir, ChunkingSpec(chunk_seconds=2))
    sentinel = chunks_dir / "_sentinel"
    sentinel.write_text("keep", encoding="utf-8")

    chunks = _prepare(sample_video, chunks_dir, ChunkingSpec(chunk_seconds=1))
    assert not sentinel.exists(), "changing chunk length must wipe + regenerate"
    assert len(chunks) == 5  # 5s / 1s


def test_cache_invalidated_on_signature_change(sample_video: Path, tmp_path: Path) -> None:
    chunks_dir = tmp_path / "audio_chunks"
    _prepare(sample_video, chunks_dir)
    sentinel = chunks_dir / "_sentinel"
    sentinel.write_text("keep", encoding="utf-8")

    # Corrupt the stored file signature -> next prepare must regenerate.
    manifest_path = chunks_dir / "manifest.json"
    manifest = io_atomic.read_json(manifest_path, default={})
    manifest["file_signature"]["size_bytes"] += 1
    io_atomic.write_json(manifest_path, manifest)

    _prepare(sample_video, chunks_dir)
    assert not sentinel.exists(), "signature mismatch must wipe + regenerate"
