"""Remote runtime — DEFERRED to a later release (interface stub only, docs/ai/05 §10).

The seam exists so a remote/SSH execution target can slot in without touching the
engine; resolving dirs or bootstrapping raises until it is implemented.
"""

from __future__ import annotations

from pathlib import Path

from scribeflow.engine.types import RuntimeDirs


class RemoteRuntime:
    name = "remote"

    def resolve_dirs(
        self,
        output_dir: Path | None,
        workspace_dir: Path | None,
        cache_dir: Path | None,
    ) -> RuntimeDirs:
        raise NotImplementedError("The remote runtime target is not implemented in v1.")

    def bootstrap(self) -> None:
        raise NotImplementedError("The remote runtime target is not implemented in v1.")
