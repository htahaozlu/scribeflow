"""Source adapters (docs/ai/05 §4). The URL test serves the fixture over a local
http server so the real yt-dlp download path runs without external network."""

from __future__ import annotations

import functools
import http.server
import importlib.util
import shutil
import socketserver
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from scribeflow.engine.types import RuntimeDirs, SourceSpec
from scribeflow.sources.base import infer_kind, resolve_source
from scribeflow.sources.drive import DriveSource
from scribeflow.sources.local import LocalSource
from scribeflow.sources.upload import UploadSource


def _dirs(tmp_path: Path) -> RuntimeDirs:
    return RuntimeDirs(
        workspace_dir=tmp_path / "ws",
        output_dir=tmp_path / "out",
        cache_dir=tmp_path / "cache",
    )


def test_infer_kind() -> None:
    assert infer_kind("https://youtu.be/x") == "url"
    assert infer_kind("http://example.com/a.mp4") == "url"
    assert infer_kind("drive:/content/drive/MyDrive/x") == "drive"
    assert infer_kind("./local/file.mp4") == "local"


def test_local_source_file(sample_video: Path, tmp_path: Path) -> None:
    media = LocalSource().resolve(SourceSpec(kind="local", uri=str(sample_video)), _dirs(tmp_path))
    assert len(media) == 1
    assert media[0].local_path == sample_video
    assert media[0].signature.size_bytes > 0


def test_local_source_dir(tmp_path: Path, fixtures_dir: Path) -> None:
    spec = SourceSpec(kind="local", uri=str(fixtures_dir))
    media = LocalSource().resolve(spec, _dirs(tmp_path))
    assert any(m.local_path.name == "sample_5s.mp4" for m in media)


def test_local_source_missing_raises(tmp_path: Path) -> None:
    spec = SourceSpec(kind="local", uri=str(tmp_path / "nope.mp4"))
    with pytest.raises(FileNotFoundError):
        LocalSource().resolve(spec, _dirs(tmp_path))


def test_upload_source_copies_into_workspace(sample_video: Path, tmp_path: Path) -> None:
    dirs = _dirs(tmp_path)
    media = UploadSource().resolve(SourceSpec(kind="upload", uri=str(sample_video)), dirs)
    assert len(media) == 1
    assert media[0].local_path.parent == dirs.workspace_dir / "uploads"
    assert media[0].local_path.exists()
    assert media[0].signature.sha256 is not None  # uploads are hashed


def test_upload_dedups_basename_collisions(sample_video: Path, tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "a").mkdir(parents=True)
    (src / "b").mkdir()
    shutil.copy2(sample_video, src / "a" / "clip.mp4")
    shutil.copy2(sample_video, src / "b" / "clip.mp4")

    media = UploadSource().resolve(SourceSpec(kind="upload", uri=str(src)), _dirs(tmp_path))
    assert len(media) == 2
    paths = {m.local_path for m in media}
    assert len(paths) == 2  # neither file was overwritten/dropped
    assert all(m.local_path.exists() for m in media)


def test_drive_source_mounted_path(tmp_path: Path, fixtures_dir: Path) -> None:
    # A "mounted" Drive folder is just a local path → discovered like local.
    spec = SourceSpec(kind="drive", uri=f"drive:{fixtures_dir}")
    media = DriveSource().resolve(spec, _dirs(tmp_path))
    assert any(m.local_path.name == "sample_5s.mp4" for m in media)


def test_drive_source_unmounted_is_stub(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError):
        DriveSource().resolve(SourceSpec(kind="drive", uri="drive:/not/mounted/x"), _dirs(tmp_path))


# --------------------------------------------------------------------------- #
# URL source — real yt-dlp against a local http server (no external network)
# --------------------------------------------------------------------------- #


@pytest.fixture
def http_base(fixtures_dir: Path) -> Iterator[str]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(fixtures_dir))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.skipif(
    importlib.util.find_spec("yt_dlp") is None, reason="yt-dlp ([url] extra) not installed"
)
def test_url_source_downloads_into_workspace(http_base: str, tmp_path: Path) -> None:
    from scribeflow.sources.url import UrlSource

    dirs = _dirs(tmp_path)
    spec = SourceSpec(kind="url", uri=f"{http_base}/sample_5s.mp4")
    media = UrlSource().resolve(spec, dirs)

    assert len(media) == 1
    resolved = media[0]
    assert resolved.local_path.exists()
    # heavy I/O landed in the scratch workspace, not the durable output dir
    assert dirs.workspace_dir in resolved.local_path.parents
    assert dirs.output_dir not in resolved.local_path.parents
    assert resolved.origin_uri == spec.uri


def test_resolve_source_dispatch(sample_video: Path, tmp_path: Path) -> None:
    media = resolve_source(SourceSpec(kind="local", uri=str(sample_video)), _dirs(tmp_path))
    assert media[0].local_path == sample_video
