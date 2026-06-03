"""Export a finished run to txt / srt / vtt / json (docs/ai/06 P7).

Chunk JSON segment offsets are CHUNK-RELATIVE. Subtitle timecodes are global, so
each chunk's segments are shifted by ``chunk_index * chunk_seconds`` (the chunk
length read from ``progress.json``). No engine change — exporters only read the
checkpoint artifacts the pipeline already wrote.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from scribeflow.engine import io_atomic

VALID_FORMATS = ("txt", "srt", "vtt", "json")
DEFAULT_CHUNK_SECONDS = 20 * 60


@dataclass(frozen=True)
class ExportedSegment:
    start: float  # GLOBAL seconds
    end: float
    text: str


def _chunk_seconds(video_dir: Path) -> int:
    # progress.json is the source of truth; summary.json carries the same value as
    # a fallback for a torn/missing progress file (both written by the pipeline).
    for filename in ("progress.json", "summary.json"):
        data = io_atomic.read_json(video_dir / filename, default={})
        chunking = data.get("chunking") or {}
        if "chunk_seconds" in chunking:
            return int(chunking["chunk_seconds"])
    return DEFAULT_CHUNK_SECONDS


def load_global_segments(video_dir: Path) -> list[ExportedSegment]:
    """Read every chunk JSON in order and shift segments to global timecodes."""
    chunk_seconds = _chunk_seconds(video_dir)
    chunk_outputs = video_dir / "chunk_outputs"
    segments: list[ExportedSegment] = []
    for chunk_json in sorted(chunk_outputs.glob("chunk_*.json")):
        data = io_atomic.read_json(chunk_json, default={})
        if not data:
            continue
        offset = float(int(data.get("chunk_index", 0)) * chunk_seconds)
        for seg in data.get("segments", []):
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                ExportedSegment(
                    start=offset + float(seg.get("start", 0.0)),
                    end=offset + float(seg.get("end", 0.0)),
                    text=text,
                )
            )
    return segments


def _timestamp(seconds: float, sep: str) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, total_ms = divmod(total_ms, 3_600_000)
    minutes, total_ms = divmod(total_ms, 60_000)
    secs, millis = divmod(total_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def to_srt(segments: list[ExportedSegment]) -> str:
    blocks: list[str] = []
    for index, seg in enumerate(segments, start=1):
        blocks.append(
            f"{index}\n"
            f"{_timestamp(seg.start, ',')} --> {_timestamp(seg.end, ',')}\n"
            f"{seg.text}\n"
        )
    return "\n".join(blocks).strip() + "\n"


def to_vtt(segments: list[ExportedSegment]) -> str:
    blocks: list[str] = ["WEBVTT\n"]
    for seg in segments:
        blocks.append(
            f"{_timestamp(seg.start, '.')} --> {_timestamp(seg.end, '.')}\n{seg.text}\n"
        )
    return "\n".join(blocks).strip() + "\n"


def to_json(segments: list[ExportedSegment]) -> str:
    payload = {
        "segments": [
            {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text} for s in segments
        ]
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def export(
    video_dir: Path, formats: tuple[str, ...], out_dir: Path | None = None
) -> dict[str, Path]:
    """Write the requested non-txt formats next to the transcript. ``txt`` is the
    transcript the engine already wrote (returned as-is). Returns format → path."""
    video_dir = Path(video_dir)
    out_dir = Path(out_dir) if out_dir else video_dir
    stem = video_dir.name
    written: dict[str, Path] = {}

    # Validate ALL formats before writing anything (no partial output on a typo).
    for fmt in formats:
        if fmt not in VALID_FORMATS:
            raise ValueError(f"Unknown format {fmt!r}. Valid: {VALID_FORMATS}")

    needs_segments = any(fmt in {"srt", "vtt", "json"} for fmt in formats)
    segments = load_global_segments(video_dir) if needs_segments else []

    for fmt in formats:
        if fmt == "txt":
            written["txt"] = video_dir / f"{stem}_transcript.txt"
            continue
        target = out_dir / f"{stem}.{fmt}"
        renderer = {"srt": to_srt, "vtt": to_vtt, "json": to_json}[fmt]
        io_atomic.write_text(target, renderer(segments))
        written[fmt] = target
    return written
