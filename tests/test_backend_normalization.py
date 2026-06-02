"""faster-whisper adapter normalization (docs/ai/02 §6, docs/ai/05 §2).

Uses an injected fake WhisperModel so no model is downloaded. Asserts the
adapter maps the engine's ``(segments_iter, info)`` to the normalized
``TranscriptionResult`` exactly as the reference engine did (strip, skip empty,
join with a space) and that it never writes checkpoint files.
"""

from __future__ import annotations

from pathlib import Path

from tests.fakes import FakeWhisperModel
from yazit.backends.faster_whisper import FasterWhisperBackend
from yazit.engine.types import ChunkRequest, TranscribeOptions, TranscriptSegment


def _request(tmp_path: Path) -> ChunkRequest:
    audio = tmp_path / "chunk_000.wav"
    audio.write_bytes(b"\x00")  # adapter passes the path to the model; content unused
    return ChunkRequest(
        audio_path=audio,
        chunk_index=0,
        chunk_name="chunk_000.wav",
        options=TranscribeOptions(language="tr", beam_size=5, initial_prompt="prev tail"),
    )


def test_adapter_normalizes_segments(tmp_path: Path) -> None:
    model = FakeWhisperModel(
        segments=[
            (0.0, 1.234, "  birinci cümle  "),
            (1.234, 2.0, "   "),  # whitespace-only -> skipped
            (2.0, 3.567, "ikinci cümle"),
        ],
        language="tr",
        duration=3.57,
    )
    backend = FasterWhisperBackend("tiny", device="cpu", compute_type="int8", model=model)
    result = backend.transcribe_chunk(_request(tmp_path))

    assert result.text == "birinci cümle ikinci cümle"  # stripped, empty skipped, space-joined
    assert result.segments == (
        TranscriptSegment(0.0, 1.23, "birinci cümle"),  # times rounded to 2dp
        TranscriptSegment(2.0, 3.57, "ikinci cümle"),
    )
    assert result.language == "tr"
    assert result.duration == 3.57


def test_adapter_passes_determinism_friendly_options(tmp_path: Path) -> None:
    model = FakeWhisperModel(segments=[(0.0, 1.0, "merhaba dunya")])
    backend = FasterWhisperBackend("tiny", model=model)
    backend.transcribe_chunk(_request(tmp_path))

    _, kwargs = model.calls[0]
    assert kwargs["condition_on_previous_text"] is False  # engine uses tail_prompt
    assert kwargs["temperature"] == 0.0  # determinism (invariant 5)
    assert kwargs["language"] == "tr"
    assert kwargs["beam_size"] == 5
    assert kwargs["vad_filter"] is True
    assert kwargs["initial_prompt"] == "prev tail"
    assert kwargs["vad_parameters"] == {"min_silence_duration_ms": 500}


def test_fingerprint_shape() -> None:
    backend = FasterWhisperBackend("large-v3", device="cuda", compute_type="float16")
    fp = backend.fingerprint
    assert fp.backend == "faster-whisper"
    assert fp.model == "large-v3"
    assert fp.device == "cuda"
    assert fp.compute_type == "float16"
    assert fp.extra == {}


def test_run_batch_via_faster_whisper_adapter(sample_video: Path, tmp_path: Path) -> None:
    """Contract: process_video runs end-to-end against the adapter and persists the
    backend fingerprint + RunIdentity (the adapter writes NO checkpoint files)."""
    from yazit.engine.pipeline import EngineConfig, run_batch
    from yazit.engine.types import ChunkingSpec

    model = FakeWhisperModel(segments=[(0.0, 2.0, "bu bir test cümlesidir burada")])
    backend = FasterWhisperBackend("tiny", device="cpu", compute_type="int8", model=model)
    config = EngineConfig(
        output_dir=tmp_path / "out",
        workspace_dir=tmp_path / "ws",
        chunking=ChunkingSpec(chunk_seconds=2),
    )
    run_batch(config, backend, [sample_video])

    video_dir = tmp_path / "out" / sample_video.stem
    transcript = (video_dir / f"{sample_video.stem}_transcript.txt").read_text(encoding="utf-8")
    assert "bu bir test" in transcript

    import json

    chunk0 = json.loads((video_dir / "chunk_outputs" / "chunk_000.json").read_text("utf-8"))
    assert chunk0["fingerprint"]["backend"] == "faster-whisper"
    assert chunk0["run_identity"]["backend"]["model"] == "tiny"
    assert chunk0["raw_text"]  # raw segment text preserved alongside the cleaned transcript
