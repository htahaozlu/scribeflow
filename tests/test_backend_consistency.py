"""P6 — the three backends normalize to ONE shape (docs/ai/05 §2, docs/ai/06 P6).

No model downloads / whisper.cpp binary needed: faster-whisper uses an injected
fake model, openai-whisper an injected fake model, whisper.cpp a fake ``-oj`` JSON
(its real subprocess plumbing is covered separately with a monkeypatched binary).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scribeflow.backends import registry
from scribeflow.backends.faster_whisper import FasterWhisperBackend
from scribeflow.backends.openai_whisper import OpenaiWhisperBackend, normalize_openai
from scribeflow.backends.whispercpp import (
    WhisperCppBackend,
    find_whispercpp_binary,
    parse_whispercpp_json,
    resolve_model_path,
)
from scribeflow.engine.types import ChunkRequest, TranscribeOptions, TranscriptSegment
from tests.fakes import FakeOpenaiModel, FakeWhisperModel

SEGMENTS = [(0.0, 1.5, "merhaba dunya"), (1.5, 3.0, "nasilsin bugun")]
EXPECTED = (
    TranscriptSegment(0.0, 1.5, "merhaba dunya"),
    TranscriptSegment(1.5, 3.0, "nasilsin bugun"),
)


def _request(tmp_path: Path) -> ChunkRequest:
    audio = tmp_path / "chunk_000.wav"
    audio.write_bytes(b"\x00")
    return ChunkRequest(
        audio_path=audio, chunk_index=0, chunk_name="chunk_000.wav", options=TranscribeOptions()
    )


def _whispercpp_json() -> dict:
    # whisper.cpp -oj: offsets in MILLISECONDS, language under "result".
    return {
        "transcription": [
            {"offsets": {"from": 0, "to": 1500}, "text": " merhaba dunya"},
            {"offsets": {"from": 1500, "to": 3000}, "text": "nasilsin bugun "},
        ],
        "result": {"language": "tr"},
    }


def test_three_backends_normalize_identically(tmp_path: Path) -> None:
    req = _request(tmp_path)
    fw = FasterWhisperBackend(
        "m", model=FakeWhisperModel(SEGMENTS, duration=3.0)
    ).transcribe_chunk(req)
    oa = OpenaiWhisperBackend("m", model_obj=FakeOpenaiModel(SEGMENTS)).transcribe_chunk(req)
    wc_segments, wc_lang, wc_duration = parse_whispercpp_json(_whispercpp_json())

    # Same normalized segments, language, and joined raw text across all three.
    assert fw.segments == oa.segments == wc_segments == EXPECTED
    assert fw.language == oa.language == wc_lang == "tr"
    assert fw.text == oa.text == "merhaba dunya nasilsin bugun"
    assert fw.duration == oa.duration == wc_duration == 3.0

    # ...but each reports its own backend in the fingerprint.
    assert fw.fingerprint.backend == "faster-whisper"
    assert oa.fingerprint.backend == "openai-whisper"


def test_duration_consistent_across_backends(tmp_path: Path) -> None:
    """Even when faster-whisper reports info.duration far beyond the speech, the
    normalized duration (spoken extent) agrees across all three backends."""
    req = _request(tmp_path)
    fw = FasterWhisperBackend(
        "m", model=FakeWhisperModel(SEGMENTS, duration=20.0)
    ).transcribe_chunk(req)
    oa = OpenaiWhisperBackend("m", model_obj=FakeOpenaiModel(SEGMENTS)).transcribe_chunk(req)
    _, _, wc_duration = parse_whispercpp_json(_whispercpp_json())
    assert fw.duration == oa.duration == wc_duration == 3.0


def test_create_whispercpp_forwards_download_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the CLI always passes download_root to create_backend; the
    whisper.cpp backend must accept it (uses it as the ggml models dir)."""
    (tmp_path / "ggml-tiny.bin").write_bytes(b"\x00")
    monkeypatch.setattr(
        "scribeflow.backends.whispercpp.find_whispercpp_binary",
        lambda explicit=None: "/usr/bin/true",
    )
    backend = registry.create_backend(
        "whispercpp",
        model="tiny",
        device="metal",
        compute_type="metal",
        download_root=str(tmp_path),
    )
    assert backend.fingerprint.backend == "whispercpp"


def test_parse_whispercpp_json_ms_to_seconds_and_drops_empty() -> None:
    data = {
        "transcription": [
            {"offsets": {"from": 500, "to": 2750}, "text": "bir cumle"},
            {"offsets": {"from": 2750, "to": 3000}, "text": "   "},  # empty → dropped
        ],
        "result": {"language": "tr"},
    }
    segments, language, duration = parse_whispercpp_json(data)
    assert segments == (TranscriptSegment(0.5, 2.75, "bir cumle"),)
    assert language == "tr"
    assert duration == 2.75


def test_parse_whispercpp_json_language_fallback() -> None:
    _, language, _ = parse_whispercpp_json({"transcription": []})
    assert language == "und"


def test_normalize_openai_falls_back_to_text_field() -> None:
    segments, language, text, duration = normalize_openai(
        {"segments": [], "text": "  whole thing  ", "language": "en"}, fallback_lang="tr"
    )
    assert segments == ()
    assert text == "whole thing"
    assert language == "en"
    assert duration == 0.0


def test_whispercpp_subprocess_plumbing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_file = tmp_path / "ggml-m.bin"
    model_file.write_bytes(b"\x00")
    monkeypatch.setattr(
        "scribeflow.backends.whispercpp.find_whispercpp_binary",
        lambda explicit=None: "/usr/bin/true",
    )

    def fake_run(cmd, check, capture_output):
        # whisper.cpp writes <prefix>.json; the prefix follows "-of".
        prefix = Path(cmd[cmd.index("-of") + 1])
        prefix.with_suffix(".json").write_text(json.dumps(_whispercpp_json()), encoding="utf-8")

    monkeypatch.setattr("scribeflow.backends.whispercpp.subprocess.run", fake_run)

    backend = WhisperCppBackend("m", models_dir=str(tmp_path))
    result = backend.transcribe_chunk(_request(tmp_path))
    assert result.segments == EXPECTED
    assert result.fingerprint.backend == "whispercpp"
    assert result.text == "merhaba dunya nasilsin bugun"


def test_whispercpp_validates_binary_and_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    find = "scribeflow.backends.whispercpp.find_whispercpp_binary"
    monkeypatch.setattr(find, lambda explicit=None: None)
    with pytest.raises(RuntimeError, match="binary not found"):
        WhisperCppBackend("m")

    monkeypatch.setattr(find, lambda explicit=None: "/usr/bin/true")
    with pytest.raises(RuntimeError, match="model not found"):
        WhisperCppBackend("does-not-exist", models_dir=str(tmp_path))


def test_resolve_model_path_explicit_and_dir(tmp_path: Path) -> None:
    ggml = tmp_path / "ggml-large-v3.bin"
    ggml.write_bytes(b"\x00")
    assert resolve_model_path(str(ggml)) == ggml
    assert resolve_model_path("large-v3", models_dir=str(tmp_path)) == ggml
    assert resolve_model_path("missing", models_dir=str(tmp_path)) is None


def test_registry_wires_all_three() -> None:
    assert set(registry.KNOWN_BACKENDS) == {"faster-whisper", "whispercpp", "openai-whisper"}
    # openai-whisper is import-detected; faster-whisper is base.
    assert registry.is_available("faster-whisper")
    # whispercpp availability tracks the binary, not a python import.
    assert registry.is_available("whispercpp") == (find_whispercpp_binary() is not None)
    created = registry.create_backend("openai-whisper", model="tiny", device="cpu")
    assert created.fingerprint.backend == "openai-whisper"
