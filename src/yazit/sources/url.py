"""URL source — download via yt-dlp into the local scratch workspace ([url] extra).

Audio is sufficient for transcription, so we prefer ``bestaudio/best`` to keep the
download small. The file lands in ``dirs.workspace_dir`` (scratch, never Drive).
"""

from __future__ import annotations

from pathlib import Path

from yazit.engine.chunking import file_signature
from yazit.engine.types import ResolvedMedia, RuntimeDirs, SourceSpec


class UrlSource:
    def resolve(self, spec: SourceSpec, dirs: RuntimeDirs) -> tuple[ResolvedMedia, ...]:
        try:
            import yt_dlp
        except ImportError as exc:  # pragma: no cover - exercised via the extras path
            raise RuntimeError(
                "yt-dlp is required for URL sources. Install: pip install 'yazit[url]'"
            ) from exc

        download_dir = Path(dirs.workspace_dir) / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        ydl_opts = {
            "outtmpl": str(download_dir / "%(title).80s-%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(spec.uri, download=True)
            path = Path(ydl.prepare_filename(info))
            if not path.exists():
                candidates = sorted(download_dir.glob(f"*{info.get('id', '')}*"))
                if not candidates:
                    raise RuntimeError(f"Download produced no file for: {spec.uri}")
                path = candidates[0]

        return (
            ResolvedMedia(
                local_path=path,
                display_name=str(info.get("title") or path.name),
                source_id=str(info.get("id") or path.stem),
                origin_uri=spec.uri,
                signature=file_signature(path, with_hash=True),
            ),
        )
