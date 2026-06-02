"""Local runtime — workspace and output both live on the local filesystem."""

from __future__ import annotations

from pathlib import Path

from yazit.config import DEFAULT_OUTPUT_DIR, DEFAULT_WORKSPACE_DIR
from yazit.engine.types import RuntimeDirs
from yazit.runtime.base import default_cache_dir


class LocalRuntime:
    name = "local"

    def resolve_dirs(
        self,
        output_dir: Path | None,
        workspace_dir: Path | None,
        cache_dir: Path | None,
    ) -> RuntimeDirs:
        return RuntimeDirs(
            workspace_dir=Path(workspace_dir or DEFAULT_WORKSPACE_DIR).expanduser(),
            output_dir=Path(output_dir or DEFAULT_OUTPUT_DIR).expanduser(),
            cache_dir=Path(cache_dir).expanduser() if cache_dir else default_cache_dir(),
        )

    def bootstrap(self) -> None:
        # ffmpeg is checked by the CLI; nothing else to set up locally.
        return None
