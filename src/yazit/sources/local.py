"""Local source — returns existing paths as-is (no copy)."""

from __future__ import annotations

from pathlib import Path

from yazit.engine.chunking import discover_media, file_signature
from yazit.engine.types import ResolvedMedia, RuntimeDirs, SourceSpec


def _to_media(path: Path, origin: str) -> ResolvedMedia:
    return ResolvedMedia(
        local_path=path,
        display_name=path.name,
        source_id=path.stem,
        origin_uri=origin,
        signature=file_signature(path),
    )


class LocalSource:
    def resolve(self, spec: SourceSpec, dirs: RuntimeDirs) -> tuple[ResolvedMedia, ...]:
        path = Path(spec.uri).expanduser()
        if path.is_dir():
            files = discover_media(path)
        elif path.is_file():
            files = [path]
        else:
            raise FileNotFoundError(f"No media found at: {path}")
        if not files:
            raise FileNotFoundError(f"No media files under: {path}")
        return tuple(_to_media(p, str(p)) for p in files)
