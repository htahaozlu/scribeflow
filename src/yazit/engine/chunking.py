"""ffmpeg audio segmentation (kept — better than moviepy). Ported from the
proven engine; the only changes are the two allowed seams: the ffmpeg error
string is now backend/runtime-neutral, and ``chunk_minutes`` became the
``ChunkingSpec`` (seconds + sample rate + channels + codec). See docs/ai/02 §1,
docs/ai/05 §3.

Layer-A checkpoint (the audio-chunk cache): WAVs are reused only when a
*completed* manifest's identity (file signature + chunking spec + ffmpeg
version) matches the current file AND every listed chunk physically exists.
Otherwise the directory is wiped and regenerated. ``completed: True`` is written
only after ffmpeg succeeds and chunks are confirmed present (docs/ai/02 §3).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from yazit.engine import io_atomic
from yazit.engine.types import AudioChunk, ChunkingSpec, FileSignature

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
}
# Audio containers are valid input too — ffmpeg extracts/segments either way.
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def discover_media(input_dir: Path) -> list[Path]:
    """Sorted recursive discovery of media files (was ``discover_videos``)."""
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
    )


def ensure_ffmpeg() -> None:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg — it is the one required system "
            "dependency (see the README for per-OS instructions)."
        ) from exc


@lru_cache(maxsize=1)
def ffmpeg_version() -> str:
    """First line of ``ffmpeg -version`` (used in the chunk-cache identity)."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-version"],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip().splitlines()[0] if out.stdout.strip() else "unknown"
    except Exception:
        return "unknown"


def probe_duration(media_path: Path) -> float | None:
    """Media duration in seconds via ``ffprobe`` (was ``media_duration_seconds``)."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    try:
        return round(float(result.stdout.strip()), 2)
    except Exception:
        return None


def file_signature(path: Path, *, with_hash: bool = False) -> FileSignature:
    """Cheap identity for cache validation: name + size + mtime (+ optional hash)."""
    stats = path.stat()
    sha256: str | None = None
    if with_hash:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        sha256 = digest.hexdigest()
    return FileSignature(
        name=path.name,
        size_bytes=stats.st_size,
        mtime=int(stats.st_mtime),
        sha256=sha256,
    )


def _signature_key(sig: FileSignature) -> dict[str, Any]:
    # Only the cheap, always-available fields participate in the cache key.
    return {"name": sig.name, "size_bytes": sig.size_bytes, "mtime": sig.mtime}


def _build_audio_chunks(chunk_paths: list[Path], spec: ChunkingSpec) -> tuple[AudioChunk, ...]:
    chunks: list[AudioChunk] = []
    for index, path in enumerate(chunk_paths):
        duration = probe_duration(path)
        chunks.append(
            AudioChunk(
                index=index,
                path=path,
                name=path.name,
                start_seconds=float(index * spec.chunk_seconds),
                duration_seconds=float(duration if duration is not None else spec.chunk_seconds),
            )
        )
    return tuple(chunks)


def prepare_audio_chunks(
    media_path: Path,
    chunks_dir: Path,
    spec: ChunkingSpec,
    log_path: Path,
) -> tuple[AudioChunk, ...]:
    """Segment ``media_path`` into fixed-duration WAVs under ``chunks_dir``.

    Reuses cached WAVs when the manifest identity matches (Layer A); otherwise
    wipes and regenerates. Returns the ordered chunks.
    """
    ensure_ffmpeg()
    manifest_path = chunks_dir / "manifest.json"
    current_sig = _signature_key(file_signature(media_path))
    current_chunking = asdict(spec)
    current_ffmpeg = ffmpeg_version()
    manifest = io_atomic.read_json(manifest_path, default={})

    if (
        manifest.get("completed")
        and manifest.get("file_signature") == current_sig
        and manifest.get("chunking") == current_chunking
        and manifest.get("ffmpeg_version") == current_ffmpeg
    ):
        chunk_paths = [chunks_dir / name for name in manifest.get("chunks", [])]
        if chunk_paths and all(path.exists() for path in chunk_paths):
            io_atomic.append_log(
                log_path, f"Audio chunks found, regeneration skipped: {media_path.name}"
            )
            return _build_audio_chunks(chunk_paths, spec)

    if chunks_dir.exists():
        shutil.rmtree(chunks_dir)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = chunks_dir / "chunk_%03d.wav"
    io_atomic.append_log(
        log_path,
        f"Generating audio chunks: {media_path.name} | chunk length: {spec.chunk_seconds}s",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            str(spec.channels),
            "-ar",
            str(spec.sample_rate),
            "-f",
            "segment",
            "-segment_time",
            str(spec.chunk_seconds),
            "-c:a",
            spec.codec,
            str(output_pattern),
        ],
        check=True,
    )

    chunk_paths = sorted(chunks_dir.glob("chunk_*.wav"))
    if not chunk_paths:
        raise RuntimeError(f"Failed to create audio chunks: {media_path}")

    # Written LAST: only a completed, identity-stamped manifest enables reuse.
    io_atomic.write_json(
        manifest_path,
        {
            "created_at": io_atomic.timestamp(),
            "completed": True,
            "chunking": current_chunking,
            "ffmpeg_version": current_ffmpeg,
            "file_signature": current_sig,
            "chunks": [path.name for path in chunk_paths],
        },
    )
    io_atomic.append_log(log_path, f"Chunk count: {len(chunk_paths)}")
    return _build_audio_chunks(chunk_paths, spec)


class Chunker(Protocol):
    def prepare(
        self, media_path: Path, chunks_dir: Path, spec: ChunkingSpec, log_path: Path
    ) -> tuple[AudioChunk, ...]: ...


class FfmpegChunker:
    """Default :class:`Chunker` — thin wrapper over :func:`prepare_audio_chunks`."""

    def prepare(
        self, media_path: Path, chunks_dir: Path, spec: ChunkingSpec, log_path: Path
    ) -> tuple[AudioChunk, ...]:
        return prepare_audio_chunks(media_path, chunks_dir, spec, log_path)
