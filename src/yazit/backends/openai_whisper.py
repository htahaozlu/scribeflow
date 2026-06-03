"""openai-whisper backend — the canonical PyTorch reference (docs/ai/03 §5).

``model.transcribe()`` returns ``{'segments': [{start, end, text}], 'language',
'text'}`` which we normalize the same way as the other backends. Cleaning happens
in the pipeline; this only normalizes. Slow / high-VRAM — a correctness baseline.
"""

from __future__ import annotations

from typing import Any

from yazit.engine.types import (
    BackendFingerprint,
    ChunkRequest,
    TranscriptionResult,
    TranscriptSegment,
)


def normalize_openai(
    result: dict[str, Any], fallback_lang: str | None
) -> tuple[tuple[TranscriptSegment, ...], str, str, float]:
    """Normalize an openai-whisper result → (segments, language, text, duration)."""
    segments: list[TranscriptSegment] = []
    parts: list[str] = []
    for seg in result.get("segments", []):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        parts.append(text)
        segments.append(
            TranscriptSegment(
                start=round(float(seg.get("start", 0.0)), 2),
                end=round(float(seg.get("end", 0.0)), 2),
                text=text,
            )
        )
    language = str(result.get("language") or (fallback_lang if fallback_lang else "und"))
    raw_text = " ".join(parts).strip() or (result.get("text") or "").strip()
    duration = segments[-1].end if segments else 0.0
    return tuple(segments), language, raw_text, float(duration)


class OpenaiWhisperBackend:
    def __init__(
        self,
        model: str,
        *,
        device: str = "cpu",
        compute_type: str | None = None,
        download_root: str | None = None,
        model_obj: Any | None = None,
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._download_root = download_root
        self._model = model_obj

    def _ensure_model(self) -> Any:
        if self._model is None:
            import whisper

            self._model = whisper.load_model(
                self._model_name, device=self._device, download_root=self._download_root
            )
        return self._model

    @property
    def fingerprint(self) -> BackendFingerprint:
        version: str | None = None
        try:
            import whisper

            version = getattr(whisper, "__version__", None)
        except Exception:
            version = None
        return BackendFingerprint(
            backend="openai-whisper",
            model=self._model_name,
            version=version,
            device=self._device,
            compute_type=self._compute_type,
            extra={},
        )

    def transcribe_chunk(self, request: ChunkRequest) -> TranscriptionResult:
        model = self._ensure_model()
        opts = request.options
        language = None if opts.language in ("auto", "") else opts.language
        result = model.transcribe(
            str(request.audio_path),
            language=language,
            task=opts.task,
            temperature=opts.temperature,
            beam_size=opts.beam_size,
            condition_on_previous_text=False,  # engine uses tail_prompt instead
            initial_prompt=opts.initial_prompt,
            fp16=(self._device == "cuda"),
            word_timestamps=opts.word_timestamps,
        )
        segments, lang, text, duration = normalize_openai(result, language)
        return TranscriptionResult(
            text=text,
            segments=segments,
            language=lang,
            duration=duration,
            fingerprint=self.fingerprint,
        )
