"""Colab runtime — bakes in the Drive Errno-107 split (docs/ai/01, docs/ai/05 §4).

Heavy/scratch I/O (downloads, audio chunks, model cache) goes to the LOCAL
``/content`` scratch — never the Drive FUSE mount, which drops under load. Only
the small, durable transcripts + checkpoints go to Drive. Defaults enforce this;
explicit user dirs are honored as given.
"""

from __future__ import annotations

from pathlib import Path

from scribeflow.engine.types import RuntimeDirs

CONTENT = Path("/content")
DRIVE_BASE = Path("/content/drive/MyDrive")


class ColabRuntime:
    name = "colab"

    def resolve_dirs(
        self,
        output_dir: Path | None,
        workspace_dir: Path | None,
        cache_dir: Path | None,
    ) -> RuntimeDirs:
        return RuntimeDirs(
            # local scratch — heavy I/O must NOT traverse the Drive FUSE mount
            workspace_dir=(
                Path(workspace_dir) if workspace_dir else CONTENT / "scribeflow-workspace"
            ),
            # durable — small transcript/checkpoint writes are safe over Drive
            output_dir=Path(output_dir) if output_dir else DRIVE_BASE / "scribeflow-output",
            cache_dir=Path(cache_dir) if cache_dir else CONTENT / "scribeflow-cache",
        )

    def bootstrap(self) -> None:
        try:
            from google.colab import drive

            drive.mount("/content/drive", force_remount=True)
        except Exception:
            # Not running in Colab (or already mounted) — dirs still resolve; the
            # user is responsible for the mount if they target a Drive path.
            return None
