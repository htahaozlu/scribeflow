"""Upload source — copy already-local file(s) into the scratch workspace.

Used by the web UI (P8): a browser upload is written to a temp path, then this
adapter copies it into ``dirs.workspace_dir`` and hashes it for the signature.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from scribeflow.engine.chunking import discover_media, file_signature
from scribeflow.engine.types import ResolvedMedia, RuntimeDirs, SourceSpec


class UploadSource:
    def resolve(self, spec: SourceSpec, dirs: RuntimeDirs) -> tuple[ResolvedMedia, ...]:
        src = Path(spec.uri).expanduser()
        uploads = Path(dirs.workspace_dir) / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        files = discover_media(src) if src.is_dir() else [src]
        if not files:
            raise FileNotFoundError(f"No media to upload at: {src}")
        media: list[ResolvedMedia] = []
        for p in files:
            dst = uploads / p.name
            counter = 1
            while dst.exists():  # never silently overwrite a basename collision
                dst = uploads / f"{p.stem}-{counter}{p.suffix}"
                counter += 1
            shutil.copy2(p, dst)
            media.append(
                ResolvedMedia(
                    local_path=dst,
                    display_name=p.name,
                    source_id=p.stem,
                    origin_uri=str(p),
                    signature=file_signature(dst, with_hash=True),
                )
            )
        return tuple(media)
