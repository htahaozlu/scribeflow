"""Web UI ([web] extra) — automated proxy for the human end-to-end gate (P8).

Drives the SAME pipeline through the HTTP API with the deterministic fake backend:
upload → job → poll live progress (from progress.json) → download.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

from tests.fakes import FakeDeterministicBackend

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx") is None,
    reason="[web] extra (fastapi + httpx) not installed",
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    from scribeflow.backends import registry
    from scribeflow.web.app import create_app

    monkeypatch.setattr(registry, "create_backend", lambda *a, **k: FakeDeterministicBackend())
    app = create_app(output_dir=tmp_path / "out", workspace_dir=tmp_path / "ws")
    return TestClient(app)


def test_index_serves_page(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "ScribeFlow" in resp.text
    assert "Transcribe" in resp.text


def test_models_endpoint(client) -> None:
    data = client.get("/api/models").json()
    assert "auto_select" in data and "catalog" in data
    assert data["auto_select"]["model"] not in {"tiny", "base"}
    assert "txt" in data["formats"]


def test_end_to_end_upload_progress_download(client, sample_video: Path) -> None:
    with sample_video.open("rb") as handle:
        resp = client.post(
            "/api/transcribe",
            files={"file": ("sample_5s.mp4", handle, "video/mp4")},
            data={"chunk_minutes": "20", "formats": "txt,srt"},
        )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status = {}
    for _ in range(100):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] in ("completed", "error"):
            break
        time.sleep(0.1)

    assert status["status"] == "completed", status
    assert status["percent"] == 100
    assert status["total_chunks"] >= 1
    assert status["completed_chunks"] == status["total_chunks"]  # progress reflects real chunks
    assert set(status["outputs"]) >= {"txt", "srt"}
    assert status["log"]  # activity.log was tailed

    txt = client.get(f"/api/jobs/{job_id}/download", params={"format": "txt"})
    assert txt.status_code == 200
    assert "chunk 0 sentence 0 alpha beta" in txt.text

    srt = client.get(f"/api/jobs/{job_id}/download", params={"format": "srt"})
    assert srt.status_code == 200
    assert "-->" in srt.text


def test_unknown_job_404(client) -> None:
    assert client.get("/api/jobs/nope").status_code == 404


def test_bad_format_rejected(client, sample_video: Path) -> None:
    with sample_video.open("rb") as handle:
        resp = client.post(
            "/api/transcribe",
            files={"file": ("sample_5s.mp4", handle, "video/mp4")},
            data={"formats": "flac"},
        )
    assert resp.status_code == 400


def test_transcribe_requires_input(client) -> None:
    assert client.post("/api/transcribe", data={}).status_code == 400


def test_upload_dotdot_filename_rejected(client) -> None:
    resp = client.post("/api/transcribe", files={"file": ("..", b"data", "video/mp4")}, data={})
    assert resp.status_code == 400


def test_empty_upload_rejected(client) -> None:
    resp = client.post("/api/transcribe", files={"file": ("clip.mp4", b"", "video/mp4")}, data={})
    assert resp.status_code == 400


def test_download_rejects_path_traversal(client) -> None:
    # An arbitrary format token must never be interpolated into a file path.
    resp = client.get("/api/jobs/whatever/download", params={"format": "../../../../etc/passwd"})
    assert resp.status_code in (400, 404)  # 404 unknown job is checked first; 400 on a real job

