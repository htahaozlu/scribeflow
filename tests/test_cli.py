"""CLI verbs: transcribe / models / doctor (docs/ai/05 §8).

The real model is never downloaded — ``registry.create_backend`` is patched to
return the deterministic fake, while real ffmpeg chunking still runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes import FakeDeterministicBackend
from yazit.backends import registry
from yazit.cli import main


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "create_backend", lambda *a, **k: FakeDeterministicBackend())


def test_transcribe_zero_config_produces_transcript(
    sample_video: Path, tmp_path: Path, fake_backend: None, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "transcribe",
            str(sample_video),
            "--out",
            str(tmp_path / "out"),
            "--workspace",
            str(tmp_path / "ws"),
            "--chunk-minutes",
            "1",  # 60s -> the 5s fixture is a single chunk
        ]
    )
    assert rc == 0
    transcript = tmp_path / "out" / sample_video.stem / f"{sample_video.stem}_transcript.txt"
    assert transcript.exists()
    assert "chunk 0 sentence 0 alpha beta" in transcript.read_text(encoding="utf-8")
    assert "Done" in capsys.readouterr().out


def test_transcribe_json_output(
    sample_video: Path, tmp_path: Path, fake_backend: None, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "transcribe",
            str(sample_video),
            "--out",
            str(tmp_path / "out"),
            "--workspace",
            str(tmp_path / "ws"),
            "--chunk-minutes",
            "1",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["media_count"] == 1
    assert payload["videos"][0]["status"] == "completed"


def test_transcribe_missing_source_errors(tmp_path: Path) -> None:
    assert main(["transcribe", str(tmp_path / "nope.mp4")]) == 2


def test_transcribe_unavailable_backend_errors(
    sample_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "is_available", lambda name: False)
    rc = main(
        ["transcribe", str(sample_video), "--backend", "whispercpp", "--out", str(tmp_path / "o")]
    )
    assert rc == 3


def test_models_json(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["models", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "host" in payload and "auto_select" in payload and "catalog" in payload
    # auto-pick is never a forbidden tier
    assert payload["auto_select"]["model"] not in {"tiny", "base"}
    assert not payload["auto_select"]["model"].startswith("distil")


def test_models_human_readable(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["models"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "auto-pick" in out
    assert "large-v3" in out


def test_doctor_json_reports_ffmpeg_and_backends(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["doctor", "--json"])
    payload = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in payload["checks"]}
    assert "ffmpeg" in names
    assert "backend:faster-whisper" in names
    assert "device" in names
    # ffmpeg + faster-whisper are present in this environment -> ready
    assert payload["ok"] is True
    assert rc == 0


def test_lang_alias_accepted(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["models", "--lang", "tr"]) == 0
    assert main(["models", "--ui-lang", "en"]) == 0


def test_bad_env_yields_friendly_config_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("YAZIT_CHUNK_MINUTES", "abc")
    rc = main(["models"])  # a verb that doesn't even use chunk_minutes
    assert rc == 5
    err = capsys.readouterr().err
    assert "config error" in err
    assert "Traceback" not in err  # never a raw traceback


def test_transcribe_engine_error_is_friendly(
    sample_video: Path, tmp_path: Path, fake_backend: None, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _boom(*a: object, **k: object) -> None:
        raise RuntimeError("ffmpeg exploded")

    monkeypatch.setattr("yazit.cli.run_batch", _boom)
    rc = main(
        [
            "transcribe",
            str(sample_video),
            "--out",
            str(tmp_path / "o"),
            "--workspace",
            str(tmp_path / "w"),
            "--chunk-minutes",
            "1",
        ]
    )
    assert rc == 7
    err = capsys.readouterr().err
    assert "transcription failed" in err
    assert "ffmpeg exploded" in err
    assert "Traceback" not in err


def test_no_color_disables_ansi(
    sample_video: Path, tmp_path: Path, fake_backend: None, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    main(["models"])
    assert "\033[" not in capsys.readouterr().out
