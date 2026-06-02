"""Source contract: materialize media locally, then the engine runs unchanged.

Sources resolve to local ``Path``s (the engine assumes local files for ffmpeg).
Downloads/copies land in ``dirs.workspace_dir`` (scratch); durability is a RUNTIME
concern, never a source concern (docs/ai/05 §4).
"""

from __future__ import annotations

from typing import Protocol

from yazit.engine.types import ResolvedMedia, RuntimeDirs, SourceSpec


class SourceAdapter(Protocol):
    def resolve(self, spec: SourceSpec, dirs: RuntimeDirs) -> tuple[ResolvedMedia, ...]: ...


def infer_kind(uri: str) -> str:
    """Guess the source kind from a CLI argument."""
    low = uri.lower()
    if low.startswith(("http://", "https://", "www.")):
        return "url"
    if low.startswith("drive:"):
        return "drive"
    return "local"


def resolve_source(spec: SourceSpec, dirs: RuntimeDirs) -> tuple[ResolvedMedia, ...]:
    """Dispatch to the adapter for ``spec.kind`` and return resolved local media."""
    from yazit.sources.drive import DriveSource
    from yazit.sources.local import LocalSource
    from yazit.sources.upload import UploadSource
    from yazit.sources.url import UrlSource

    adapters: dict[str, type] = {
        "local": LocalSource,
        "url": UrlSource,
        "drive": DriveSource,
        "upload": UploadSource,
    }
    cls = adapters.get(spec.kind)
    if cls is None:
        raise ValueError(f"Unknown source kind: {spec.kind!r}")
    adapter: SourceAdapter = cls()
    return adapter.resolve(spec, dirs)
