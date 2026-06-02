"""faster-whisper backend — the default (docs/ai/03 §5, docs/ai/05 §2).

Wraps the inlined ``WhisperModel(...).transcribe(...)`` from the proven engine.
The segment normalization (strip, skip empty, join with a single space) matches
the reference exactly. VAD is tuned to the doc-03 §6 Turkish default
(``min_silence_duration_ms=500``), which intentionally differs from
faster-whisper's built-in 2000ms — so silence-cut boundaries (and thus output)
are NOT byte-identical to the reference, by design. Cleaning itself happens in
the pipeline, not here.
"""

from __future__ import annotations

from typing import Any

from yazit.engine.types import (
    BackendFingerprint,
    ChunkRequest,
    TranscriptionResult,
    TranscriptSegment,
)


class FasterWhisperBackend:
    """Default :class:`~yazit.engine.types.TranscriptionBackend`.

    The heavy ``WhisperModel`` is loaded lazily on first transcribe (so building
    the backend / reading its fingerprint stays cheap and import-light). A model
    object may be injected for tests.
    """

    def __init__(
        self,
        model_name: str,
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: str | None = None,
        model: Any | None = None,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._download_root = download_root
        self._model = model

    def _ensure_model(self) -> Any:
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
                download_root=self._download_root,
            )
        return self._model

    @property
    def fingerprint(self) -> BackendFingerprint:
        version: str | None = None
        try:
            import faster_whisper

            version = getattr(faster_whisper, "__version__", None)
        except Exception:
            version = None
        return BackendFingerprint(
            backend="faster-whisper",
            model=self._model_name,
            version=version,
            device=self._device,
            compute_type=self._compute_type,
            extra={},
        )

    def transcribe_chunk(self, request: ChunkRequest) -> TranscriptionResult:
        model = self._ensure_model()
        opts = request.options
        language_arg = None if opts.language in ("auto", "") else opts.language
        segments_iter, info = model.transcribe(
            str(request.audio_path),
            language=language_arg,
            task=opts.task,
            beam_size=opts.beam_size,
            temperature=opts.temperature,
            condition_on_previous_text=False,  # engine uses tail_prompt instead
            initial_prompt=opts.initial_prompt,
            vad_filter=opts.vad_filter,
            vad_parameters={"min_silence_duration_ms": 500},
            word_timestamps=opts.word_timestamps,
        )

        segments: list[TranscriptSegment] = []
        parts: list[str] = []
        for segment in segments_iter:
            text = (segment.text or "").strip()
            if not text:
                continue
            parts.append(text)
            segments.append(
                TranscriptSegment(
                    start=round(float(segment.start), 2),
                    end=round(float(segment.end), 2),
                    text=text,
                )
            )

        raw_text = " ".join(parts).strip()
        fallback_lang = opts.language if opts.language not in ("auto", "") else "und"
        language = getattr(info, "language", None) or fallback_lang
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        return TranscriptionResult(
            text=raw_text,
            segments=tuple(segments),
            language=language,
            duration=duration,
            fingerprint=self.fingerprint,
        )
