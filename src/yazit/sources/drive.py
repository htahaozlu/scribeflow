"""Google Drive source.

On Colab the Drive folder is already mounted at a local path
(``/content/drive/MyDrive/...``) — so it is discovered exactly like a local
folder. The non-mounted Drive API download path is a v1 stub (docs/ai/05 §10).
URIs: ``drive:/content/drive/MyDrive/lectures`` or a bare mounted path.
"""

from __future__ import annotations

from pathlib import Path

from yazit.engine.chunking import discover_media, file_signature
from yazit.engine.types import ResolvedMedia, RuntimeDirs, SourceSpec


class DriveSource:
    def resolve(self, spec: SourceSpec, dirs: RuntimeDirs) -> tuple[ResolvedMedia, ...]:
        raw = spec.uri[len("drive:") :] if spec.uri.lower().startswith("drive:") else spec.uri
        path = Path(raw).expanduser()
        if path.exists():
            files = discover_media(path) if path.is_dir() else [path]
            if not files:
                raise FileNotFoundError(f"No media under mounted Drive path: {path}")
            return tuple(
                ResolvedMedia(
                    local_path=p,
                    display_name=p.name,
                    source_id=p.stem,
                    origin_uri=spec.uri,
                    signature=file_signature(p),
                )
                for p in files
            )
        raise NotImplementedError(
            "Non-mounted Drive API download is a v1 stub. On Colab the folder is "
            "mounted and resolved as a local path; install 'yazit[drive]' for the "
            "API path (planned)."
        )
