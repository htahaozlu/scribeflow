"""Runtime target contract — decides RuntimeDirs (scratch vs durable) + bootstrap.

The runtime target owns directory defaults so it can bake in the Errno-107 split
(heavy I/O local, durable transcripts on Drive). User-supplied dirs always win.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from yazit.engine.types import RuntimeDirs


@runtime_checkable
class RuntimeTarget(Protocol):
    name: str

    def resolve_dirs(
        self,
        output_dir: Path | None,
        workspace_dir: Path | None,
        cache_dir: Path | None,
    ) -> RuntimeDirs: ...

    def bootstrap(self) -> None: ...


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "yazit"


def resolve_runtime(name: str | None = None) -> RuntimeTarget:
    """Pick a runtime target. ``None``/``"auto"`` detects Colab vs local."""
    from yazit.runtime.colab import ColabRuntime
    from yazit.runtime.local import LocalRuntime

    if name == "local":
        return LocalRuntime()
    if name == "colab":
        return ColabRuntime()
    from yazit.devices import detect_colab

    return ColabRuntime() if detect_colab() else LocalRuntime()
