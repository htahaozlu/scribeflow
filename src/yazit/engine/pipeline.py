"""Orchestration — ``process_video`` / ``run_batch``.

Ported from the proven engine with exactly two seams changed: media is supplied
as resolved local paths (the Source layer feeds these — docs/ai/05 §4) and the
inlined ``WhisperModel(...).transcribe(...)`` became
``backend.transcribe_chunk(ChunkRequest(...))`` consuming a normalized
``TranscriptionResult`` (docs/ai/05 §2). The per-chunk commit ordering, atomic
writes, dual-condition + identity skip guard, derived-not-appended transcript,
and temperature-0 determinism are preserved EXACTLY (docs/ai/02 §4–§5).
"""

from __future__ import annotations

import contextlib
import shutil
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from yazit.engine import artifacts, checkpoint, io_atomic
from yazit.engine.chunking import file_signature, prepare_audio_chunks, probe_duration
from yazit.engine.text import clean_transcript, tail_prompt
from yazit.engine.types import (
    ChunkingSpec,
    ChunkRequest,
    RunIdentity,
    TranscribeOptions,
    TranscriptionBackend,
)


@dataclass
class EngineConfig:
    """Engine-level job config. Model/device live on the backend's fingerprint,
    not here — the engine is backend-agnostic."""

    output_dir: Path  # DURABLE: transcripts + checkpoints (safe over Drive FUSE)
    workspace_dir: Path  # SCRATCH: audio chunks (heavy I/O, must be local)
    chunking: ChunkingSpec = field(default_factory=ChunkingSpec)
    options: TranscribeOptions = field(default_factory=TranscribeOptions)
    overwrite: bool = False
    keep_audio_chunks: bool = True


def _run_identity(
    backend: TranscriptionBackend, config: EngineConfig, media_path: Path
) -> RunIdentity:
    return RunIdentity(
        source=file_signature(media_path),
        chunking=config.chunking,
        backend=backend.fingerprint,
        options=config.options,
    )


def process_video(
    backend: TranscriptionBackend,
    config: EngineConfig,
    media_path: Path,
    batch_log_path: Path,
) -> dict[str, Any]:
    """Single-video resumable loop (docs/ai/02 §4). Returns the final summary."""
    video_key = media_path.stem
    video_output_dir = Path(config.output_dir) / video_key
    video_workspace_dir = Path(config.workspace_dir) / video_key
    audio_chunks_dir = video_workspace_dir / "audio_chunks"
    chunk_outputs_dir = video_output_dir / "chunk_outputs"
    log_path = video_output_dir / "activity.log"
    progress_path = video_output_dir / "progress.json"
    transcript_path = video_output_dir / f"{video_key}_transcript.txt"
    summary_path = video_output_dir / "summary.json"

    if config.overwrite:
        if video_output_dir.exists():
            shutil.rmtree(video_output_dir)
        if video_workspace_dir.exists():
            shutil.rmtree(video_workspace_dir)

    video_output_dir.mkdir(parents=True, exist_ok=True)
    video_workspace_dir.mkdir(parents=True, exist_ok=True)
    chunk_outputs_dir.mkdir(parents=True, exist_ok=True)

    # Sweep temp files orphaned by a torn os.replace in a prior run (e.g. a crash
    # during finalization). These are a leak, never data loss — the real file is
    # always the previous valid version — but they must not survive (invariant 1).
    # Done before the completed-skip so a completed-resume also cleans up.
    _sweep_orphan_temp(video_output_dir)

    identity = _run_identity(backend, config, media_path)
    identity_dict = checkpoint.identity_to_dict(identity)

    existing_progress = checkpoint.load_progress(progress_path, media_path.name)

    # Refuse to resume across a backend/model/chunking/options change (docs/ai/05 §5).
    # Validated BEFORE the completed-skip so a backend swap on a finished video
    # also raises instead of silently returning stale output.
    checkpoint.validate_resume_identity(existing_progress, identity, overwrite=config.overwrite)

    if (
        existing_progress.get("status") == "completed"
        and transcript_path.exists()
        and not config.overwrite
    ):
        io_atomic.append_log(log_path, f"Video already completed, skipped: {media_path.name}")
        return io_atomic.read_json(
            summary_path, default={"status": "completed", "video_name": media_path.name}
        )

    io_atomic.append_log(batch_log_path, f"Video started: {media_path.name}")
    io_atomic.append_log(log_path, f"Processing video: {media_path}")

    source_duration = probe_duration(media_path)
    chunks = prepare_audio_chunks(
        media_path=media_path,
        chunks_dir=audio_chunks_dir,
        spec=config.chunking,
        log_path=log_path,
    )

    completed_chunks = {int(index) for index in (existing_progress.get("completed_chunks") or [])}
    total_chunks = len(chunks)

    for chunk in chunks:
        index = chunk.index
        chunk_text_path = chunk_outputs_dir / f"chunk_{index:03d}.txt"
        chunk_json_path = chunk_outputs_dir / f"chunk_{index:03d}.json"

        if checkpoint.should_skip_chunk(
            index, completed_chunks, chunk_text_path, chunk_json_path, identity
        ):
            io_atomic.append_log(
                log_path, f"Chunk skipped (already saved): {index + 1}/{total_chunks}"
            )
            continue

        # Step 1 — continuity hint from the previous chunk's tail.
        prompt_context: list[str] = []
        previous_chunk_txt = chunk_outputs_dir / f"chunk_{index - 1:03d}.txt"
        if previous_chunk_txt.exists():
            prompt_context.append(previous_chunk_txt.read_text(encoding="utf-8"))
        initial_prompt = tail_prompt(prompt_context)

        options = config.options
        if initial_prompt is not None:
            options = replace(options, initial_prompt=initial_prompt)

        io_atomic.append_log(log_path, f"Chunk transcribe started: {index + 1}/{total_chunks}")
        started_at = time.time()

        # Step 2 — backend transcribe (the only seam vs the inlined WhisperModel).
        result = backend.transcribe_chunk(
            ChunkRequest(
                audio_path=chunk.path,
                chunk_index=index,
                chunk_name=chunk.name,
                options=options,
            )
        )

        raw_text = result.text.strip()
        cleaned_text = clean_transcript(raw_text) or raw_text

        # Step 3 — atomic chunk txt (cleaned). Step 4 — atomic chunk json (raw+cleaned).
        artifacts.write_chunk_text(chunk_text_path, cleaned_text)
        artifacts.write_chunk_json(
            chunk_json_path,
            video_name=media_path.name,
            index=index,
            chunk_name=chunk.name,
            result=result,
            cleaned_text=cleaned_text,
            identity=identity,
        )

        # Step 5 — record in memory. Step 6 — rebuild transcript from ALL chunk txts.
        completed_chunks.add(index)
        artifacts.rebuild_transcript(chunk_outputs_dir, transcript_path)

        elapsed = time.time() - started_at
        progress = {
            "video_name": media_path.name,
            "video_path": str(media_path),
            "chunking": {"chunk_seconds": config.chunking.chunk_seconds},
            "language": config.options.language,
            "total_chunks": total_chunks,
            "completed_chunks": sorted(completed_chunks),
            "completed_count": len(completed_chunks),
            "remaining_count": total_chunks - len(completed_chunks),
            "last_completed_chunk": index,
            "last_updated_at": io_atomic.timestamp(),
            "status": "running" if len(completed_chunks) < total_chunks else "completed",
            "transcript_path": str(transcript_path),
            "fingerprint": dict(_fingerprint_dict(backend)),
            "run_identity": identity_dict,
        }
        # Step 7 — progress (records the index only AFTER artifacts committed).
        checkpoint.write_progress(progress_path, progress)
        # Step 8 — summary snapshot.
        checkpoint.write_summary(
            summary_path,
            {
                **progress,
                "video_duration_seconds": source_duration,
                "last_chunk_elapsed_seconds": round(elapsed, 2),
            },
        )
        io_atomic.append_log(
            log_path,
            f"Chunk saved: {index + 1}/{total_chunks} | "
            f"elapsed: {io_atomic.format_seconds(elapsed)}",
        )

    # Idempotent finalization — rebuild once more from disk.
    final_transcript = artifacts.rebuild_transcript(chunk_outputs_dir, transcript_path)
    final_summary: dict[str, Any] = {
        "video_name": media_path.name,
        "video_path": str(media_path),
        "status": "completed",
        "completed_at": io_atomic.timestamp(),
        "language": config.options.language,
        "chunking": {"chunk_seconds": config.chunking.chunk_seconds},
        "total_chunks": total_chunks,
        "video_duration_seconds": source_duration,
        "transcript_path": str(transcript_path),
        "transcript_chars": len(final_transcript),
        "output_dir": str(video_output_dir),
        "workspace_dir": str(video_workspace_dir),
        "fingerprint": dict(_fingerprint_dict(backend)),
        "run_identity": identity_dict,
    }
    checkpoint.write_summary(summary_path, final_summary)
    checkpoint.write_progress(
        progress_path,
        {
            **final_summary,
            "completed_chunks": list(range(total_chunks)),
            "completed_count": total_chunks,
            "remaining_count": 0,
        },
    )

    if not config.keep_audio_chunks and audio_chunks_dir.exists():
        shutil.rmtree(audio_chunks_dir)
        io_atomic.append_log(log_path, "Audio chunks cleaned up.")

    io_atomic.append_log(log_path, f"Video completed: {media_path.name}")
    io_atomic.append_log(batch_log_path, f"Video completed: {media_path.name}")
    return final_summary


def _fingerprint_dict(backend: TranscriptionBackend) -> dict[str, Any]:
    return asdict(backend.fingerprint)


def _sweep_orphan_temp(directory: Path) -> None:
    """Remove ``*.tmp`` files left by a torn ``os.replace`` (recursively)."""
    for tmp in directory.rglob("*.tmp"):
        with contextlib.suppress(OSError):
            tmp.unlink()


def run_batch(
    config: EngineConfig,
    backend: TranscriptionBackend,
    media_paths: Sequence[Path],
) -> dict[str, Any]:
    """Loop ``process_video`` over resolved media, maintaining ``batch_summary.json``.

    Media discovery is a seam (the Source layer resolves paths — docs/ai/05 §4);
    the engine receives ready local paths so it runs unchanged.
    """
    output_dir = Path(config.output_dir)
    workspace_dir = Path(config.workspace_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    _sweep_orphan_temp(output_dir)  # clears batch_summary.json.tmp and any per-video leftovers

    batch_log_path = output_dir / "batch_activity.log"
    batch_summary_path = output_dir / "batch_summary.json"

    media_list = list(media_paths)
    if not media_list:
        raise RuntimeError("No media supplied to run_batch.")

    fingerprint = _fingerprint_dict(backend)
    io_atomic.append_log(
        batch_log_path,
        f"Batch started | backend={fingerprint.get('backend')} | "
        f"model={fingerprint.get('model')} | media_count={len(media_list)}",
    )

    batch_results: dict[str, Any] = {
        "started_at": io_atomic.timestamp(),
        "backend": fingerprint,
        "media_count": len(media_list),
        "videos": [],
    }
    io_atomic.write_json(batch_summary_path, batch_results)

    for media_path in media_list:
        summary = process_video(
            backend=backend,
            config=config,
            media_path=media_path,
            batch_log_path=batch_log_path,
        )
        batch_results["videos"].append(summary)
        batch_results["last_updated_at"] = io_atomic.timestamp()
        io_atomic.write_json(batch_summary_path, batch_results)

    batch_results["completed_at"] = io_atomic.timestamp()
    io_atomic.write_json(batch_summary_path, batch_results)
    io_atomic.append_log(batch_log_path, "Batch completed.")
    return batch_results
