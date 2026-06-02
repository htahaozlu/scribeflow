"""The only writer of per-chunk checkpoint artifacts + the derived transcript.

Backends NEVER write these files — they only return a normalized
``TranscriptionResult`` (docs/ai/05 §2). The pipeline calls the functions here
in the exact order frozen by docs/ai/02 §4. ``clean_transcript`` runs in the
pipeline, so the chunk JSON keeps the RAW segment text while the chunk txt and
the final transcript hold the CLEANED text (store both — docs/ai/05 §2).
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from yazit.engine import io_atomic
from yazit.engine.checkpoint import identity_to_dict
from yazit.engine.text import build_full_transcript
from yazit.engine.types import RunIdentity, TranscriptionResult


def write_chunk_text(chunk_text_path: Path, cleaned_text: str) -> None:
    """Step 3 (docs/ai/02 §4): atomic write of the cleaned chunk text."""
    io_atomic.write_text(chunk_text_path, cleaned_text + "\n")


def write_chunk_json(
    chunk_json_path: Path,
    *,
    video_name: str,
    index: int,
    chunk_name: str,
    result: TranscriptionResult,
    cleaned_text: str,
    identity: RunIdentity,
) -> None:
    """Step 4 (docs/ai/02 §4): atomic write of the chunk record (raw + cleaned)."""
    io_atomic.write_json(
        chunk_json_path,
        {
            "video_name": video_name,
            "chunk_index": index,
            "chunk_name": chunk_name,
            "created_at": io_atomic.timestamp(),
            "language": result.language,
            "duration": round(result.duration, 2),
            "raw_text": result.text,
            "transcript": cleaned_text,
            "segments": [
                {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text}
                for s in result.segments
            ],
            "fingerprint": asdict(result.fingerprint),
            "run_identity": identity_to_dict(identity),
        },
    )


def rebuild_transcript(chunk_outputs_dir: Path, transcript_path: Path) -> str:
    """Step 6 (docs/ai/02 §4): derive the transcript from ALL on-disk chunk txts
    and atomically write it. Never appended — always the sorted concatenation, so
    partial/duplicate runs self-heal (invariant 4)."""
    full = build_full_transcript(chunk_outputs_dir)
    io_atomic.write_text(transcript_path, full + ("\n" if full else ""))
    return full
