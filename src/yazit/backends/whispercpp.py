"""whisper.cpp backend — the Apple-Silicon GPU path (Metal/Core ML).

A separate binary driven via ``subprocess`` emitting JSON (``-oj -of <prefix>``).
whisper.cpp does its own long-form windowing, but those windows are NOT durable
checkpoints — we feed it one of OUR fixed chunks at a time and ignore its
internal windowing (docs/ai/03 §5, docs/ai/05 §2-§3). Offsets in the JSON are in
milliseconds; we normalize to seconds. Binary + model file are validated at
construction.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from yazit.engine.types import (
    BackendFingerprint,
    ChunkRequest,
    TranscriptionResult,
    TranscriptSegment,
)

_BINARY_CANDIDATES = ("whisper-cli", "whisper-cpp", "main")


def find_whispercpp_binary(explicit: str | None = None) -> str | None:
    """Locate the whisper.cpp CLI: explicit arg → ``YAZIT_WHISPERCPP_BIN`` → PATH."""
    if explicit and Path(explicit).expanduser().exists():
        return str(Path(explicit).expanduser())
    env = os.environ.get("YAZIT_WHISPERCPP_BIN")
    if env and Path(env).expanduser().exists():
        return str(Path(env).expanduser())
    for name in _BINARY_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def resolve_model_path(model: str, models_dir: str | None = None) -> Path | None:
    """Resolve a ggml model: an explicit path, or ``ggml-<model>.bin`` under
    ``models_dir`` / ``YAZIT_WHISPERCPP_MODELS``."""
    explicit = Path(model).expanduser()
    if explicit.exists():
        return explicit
    search_dirs = []
    if models_dir:
        search_dirs.append(Path(models_dir).expanduser())
    env = os.environ.get("YAZIT_WHISPERCPP_MODELS")
    if env:
        search_dirs.append(Path(env).expanduser())
    for directory in search_dirs:
        for name in (f"ggml-{model}.bin", f"{model}.bin", model):
            candidate = directory / name
            if candidate.exists():
                return candidate
    return None


def parse_whispercpp_json(data: dict[str, Any]) -> tuple[tuple[TranscriptSegment, ...], str, float]:
    """Normalize whisper.cpp ``-oj`` output → (segments, language, duration).

    ``offsets`` are milliseconds (converted to seconds). Empty segments dropped.
    """
    segments: list[TranscriptSegment] = []
    for seg in data.get("transcription", []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        offsets = seg.get("offsets", {}) or {}
        start = float(offsets.get("from", 0)) / 1000.0
        end = float(offsets.get("to", 0)) / 1000.0
        segments.append(TranscriptSegment(start=round(start, 2), end=round(end, 2), text=text))
    result = data.get("result", {}) or {}
    language = str(result.get("language") or "und")
    duration = segments[-1].end if segments else 0.0
    return tuple(segments), language, float(duration)


class WhisperCppBackend:
    def __init__(
        self,
        model: str,
        *,
        binary: str | None = None,
        models_dir: str | None = None,
        device: str = "metal",
        compute_type: str | None = None,
        threads: int | None = None,
        download_root: str | None = None,
    ) -> None:
        self._model_name = model
        self._binary = find_whispercpp_binary(binary)
        if self._binary is None:
            raise RuntimeError(
                "whisper.cpp binary not found. Build whisper.cpp (cmake) and put "
                "'whisper-cli' on PATH, or set YAZIT_WHISPERCPP_BIN. "
                "(pip install 'yazit[cpp]' for the pywhispercpp binding.)"
            )
        # The CLI passes its model cache dir as download_root; for whisper.cpp it
        # doubles as the ggml models directory when models_dir is not given.
        self._model_path = resolve_model_path(model, models_dir or download_root)
        if self._model_path is None:
            raise RuntimeError(
                f"whisper.cpp ggml model not found for {model!r}. Pass a path to a "
                "ggml .bin or set YAZIT_WHISPERCPP_MODELS to a directory containing "
                f"ggml-{model}.bin."
            )
        self._device = device
        self._compute_type = compute_type
        self._threads = threads

    @property
    def fingerprint(self) -> BackendFingerprint:
        return BackendFingerprint(
            backend="whispercpp",
            model=self._model_name,
            version=None,
            device=self._device,
            compute_type=self._compute_type,
            extra={"binary": str(self._binary), "model_path": str(self._model_path)},
        )

    def _command(self, request: ChunkRequest, prefix: Path) -> list[str]:
        opts = request.options
        cmd = [
            str(self._binary),
            "-m",
            str(self._model_path),
            "-f",
            str(request.audio_path),
            "-oj",
            "-of",
            str(prefix),
            "--no-context",  # the engine supplies continuity via --prompt instead
        ]
        language = None if opts.language in ("auto", "") else opts.language
        if language:
            cmd += ["-l", language]
        if opts.initial_prompt:
            cmd += ["--prompt", opts.initial_prompt]
        if opts.beam_size:
            cmd += ["-bs", str(opts.beam_size)]
        if self._threads:
            cmd += ["-t", str(self._threads)]
        return cmd

    def transcribe_chunk(self, request: ChunkRequest) -> TranscriptionResult:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "out"
            subprocess.run(self._command(request, prefix), check=True, capture_output=True)
            data = json.loads(prefix.with_suffix(".json").read_text(encoding="utf-8"))
        segments, language, duration = parse_whispercpp_json(data)
        raw_text = " ".join(s.text for s in segments).strip()
        opt_lang = request.options.language
        if language == "und" and opt_lang not in ("auto", ""):
            language = opt_lang
        return TranscriptionResult(
            text=raw_text,
            segments=segments,
            language=language,
            duration=duration,
            fingerprint=self.fingerprint,
        )
