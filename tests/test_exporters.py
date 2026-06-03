"""Exporters (docs/ai/06 P7): valid, timecode-correct srt/vtt/json with global
offsets (chunk_index * chunk_seconds added to chunk-relative segment times)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes import FakeDeterministicBackend
from yazit.backends import registry
from yazit.cli import main
from yazit.engine.exporters import (
    ExportedSegment,
    _timestamp,
    export,
    load_global_segments,
    to_srt,
    to_vtt,
)
from yazit.engine.pipeline import EngineConfig, run_batch
from yazit.engine.types import ChunkingSpec


def test_timestamp_formats() -> None:
    assert _timestamp(0, ",") == "00:00:00,000"
    assert _timestamp(3661.5, ",") == "01:01:01,500"
    assert _timestamp(3661.5, ".") == "01:01:01.500"
    assert _timestamp(-5, ",") == "00:00:00,000"  # clamped


def test_to_srt_and_vtt_structure() -> None:
    segs = [ExportedSegment(0.0, 1.5, "first"), ExportedSegment(2.0, 3.25, "second")]
    srt = to_srt(segs)
    assert srt.splitlines()[:3] == ["1", "00:00:00,000 --> 00:00:01,500", "first"]
    vtt = to_vtt(segs)
    assert vtt.startswith("WEBVTT")
    assert "00:00:02.000 --> 00:00:03.250" in vtt


def _run(sample_video: Path, tmp_path: Path) -> Path:
    config = EngineConfig(
        output_dir=tmp_path / "out",
        workspace_dir=tmp_path / "ws",
        chunking=ChunkingSpec(chunk_seconds=2),
    )
    run_batch(config, FakeDeterministicBackend(), [sample_video])
    return tmp_path / "out" / sample_video.stem


def test_global_offsets_account_for_chunk_start(sample_video: Path, tmp_path: Path) -> None:
    video_dir = _run(sample_video, tmp_path)
    segs = load_global_segments(video_dir)
    # 3 chunks (5s / 2s) × 3 sentences each.
    assert len(segs) == 9
    # chunk 0 starts at 0; chunk 1 shifted by 2s; chunk 2 by 4s.
    assert (segs[0].start, segs[0].end) == (0.0, 1.0)
    assert (segs[3].start, segs[3].end) == (2.0, 3.0)  # first segment of chunk 1
    assert (segs[6].start, segs[6].end) == (4.0, 5.0)  # first segment of chunk 2
    # monotonic non-decreasing starts
    assert all(segs[i].start <= segs[i + 1].start for i in range(len(segs) - 1))


def test_export_writes_valid_files(sample_video: Path, tmp_path: Path) -> None:
    video_dir = _run(sample_video, tmp_path)
    written = export(video_dir, ("txt", "srt", "vtt", "json"))

    assert written["txt"].name.endswith("_transcript.txt")
    srt = written["srt"].read_text(encoding="utf-8")
    assert "00:00:02,000 --> 00:00:03,000" in srt  # chunk-1 offset applied
    vtt = written["vtt"].read_text(encoding="utf-8")
    assert vtt.startswith("WEBVTT")
    assert "00:00:04.000 --> 00:00:05.000" in vtt  # chunk-2 offset applied
    data = json.loads(written["json"].read_text(encoding="utf-8"))
    assert data["segments"][3]["start"] == 2.0
    assert len(data["segments"]) == 9


def test_export_rejects_unknown_format(sample_video: Path, tmp_path: Path) -> None:
    video_dir = _run(sample_video, tmp_path)
    with pytest.raises(ValueError, match="Unknown format"):
        export(video_dir, ("flac",))


def test_export_validates_before_writing_any_file(sample_video: Path, tmp_path: Path) -> None:
    video_dir = _run(sample_video, tmp_path)
    before = set(video_dir.iterdir())
    with pytest.raises(ValueError, match="Unknown format"):
        export(video_dir, ("srt", "flac"))  # srt valid + first, flac invalid
    assert set(video_dir.iterdir()) == before  # nothing written (no partial .srt)


def test_chunk_seconds_falls_back_to_summary(sample_video: Path, tmp_path: Path) -> None:
    from yazit.engine.exporters import _chunk_seconds

    video_dir = _run(sample_video, tmp_path)
    (video_dir / "progress.json").write_text("{}", encoding="utf-8")  # lose chunking here
    assert _chunk_seconds(video_dir) == 2  # recovered from summary.json


def test_cli_transcribe_format_generates_subtitles(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "create_backend", lambda *a, **k: FakeDeterministicBackend())
    rc = main(
        [
            "transcribe",
            str(sample_video),
            "--out",
            str(tmp_path / "out"),
            "--workspace",
            str(tmp_path / "ws"),
            "--chunk-minutes",
            "1",  # one chunk → offsets trivially 0 but files must be valid
            "--format",
            "srt,vtt,json",
        ]
    )
    assert rc == 0
    base = tmp_path / "out" / sample_video.stem / sample_video.stem
    assert base.with_suffix(".srt").exists()
    assert base.with_suffix(".vtt").exists()
    assert base.with_suffix(".json").exists()
    assert base.with_suffix(".vtt").read_text(encoding="utf-8").startswith("WEBVTT")
