"""Optional FastAPI web UI ([web] extra) — wraps the SAME pipeline (docs/ai/05 §9).

One calm page: pick/upload a source → auto-or-choose model → run → live progress
by polling ``progress.json`` + tailing ``activity.log`` (the checkpoint files are
purpose-built for this) → download txt/srt/vtt/json. No business logic lives in
the UI; it only drives ``run_batch`` and reads checkpoint files.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from scribeflow.__about__ import APP_NAME
from scribeflow.backends import registry
from scribeflow.devices import detect_host
from scribeflow.engine import io_atomic
from scribeflow.engine.exporters import VALID_FORMATS, export
from scribeflow.engine.pipeline import EngineConfig, run_batch
from scribeflow.engine.types import ChunkingSpec, SourceSpec, TranscribeOptions
from scribeflow.model_policy import MODEL_CATALOG, auto_select
from scribeflow.runtime.local import LocalRuntime
from scribeflow.sources.base import infer_kind, resolve_source

STATIC_DIR = Path(__file__).parent / "static"


@dataclass
class Job:
    id: str
    video_dir: Path
    formats: tuple[str, ...]
    status: str = "starting"  # starting | running | completed | error
    error: str | None = None


def _tail(path: Path, lines: int = 12) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]


def create_app(*, output_dir: Path | None = None, workspace_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title=f"{APP_NAME} Web")
    dirs = LocalRuntime().resolve_dirs(output_dir, workspace_dir, None)
    jobs: dict[str, Job] = {}
    index_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    def _run_job(job: Job, media_paths: list[Path], config: EngineConfig, backend: Any) -> None:
        try:
            job.status = "running"
            run_batch(config, backend, media_paths)
            export(job.video_dir, job.formats)
            job.status = "completed"
        except Exception as exc:
            # Any failure becomes the job's error, surfaced to the client (never a crash).
            job.status = "error"
            job.error = str(exc)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return index_html

    @app.get("/api/models")
    def models() -> dict[str, Any]:
        return {
            "host": asdict(detect_host()),
            "auto_select": asdict(auto_select()),
            "catalog": MODEL_CATALOG,
            "formats": list(VALID_FORMATS),
        }

    @app.post("/api/transcribe")
    async def transcribe(
        file: UploadFile | None = File(default=None),
        source: str | None = Form(default=None),
        model: str | None = Form(default=None),
        backend: str | None = Form(default=None),
        language: str = Form(default="tr"),
        chunk_minutes: int = Form(default=20),
        formats: str = Form(default="txt,srt"),
    ) -> JSONResponse:
        fmt_tuple = tuple(f.strip() for f in formats.split(",") if f.strip()) or ("txt",)
        for fmt in fmt_tuple:
            if fmt not in VALID_FORMATS:
                raise HTTPException(status_code=400, detail=f"unknown format {fmt!r}")

        if file is not None and file.filename:
            safe_name = Path(file.filename).name
            if safe_name in ("", ".", ".."):
                raise HTTPException(status_code=400, detail="invalid upload filename")
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="uploaded file is empty")
            uploads = dirs.workspace_dir / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            target = uploads / safe_name
            target.write_bytes(content)
            media_paths = [target]
        elif source:
            spec = SourceSpec(kind=infer_kind(source), uri=source)  # type: ignore[arg-type]
            try:
                media_paths = [m.local_path for m in resolve_source(spec, dirs)]
            except (FileNotFoundError, RuntimeError, NotImplementedError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            raise HTTPException(status_code=400, detail="provide a file upload or a source")

        resolution = auto_select(backend=backend, model=model)
        try:
            transcriber = registry.create_backend(
                resolution.backend,
                model=resolution.model,
                device=resolution.device,
                compute_type=resolution.compute_type,
                download_root=str(dirs.cache_dir),
            )
        except (RuntimeError, NotImplementedError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        config = EngineConfig(
            output_dir=dirs.output_dir,
            workspace_dir=dirs.workspace_dir,
            chunking=ChunkingSpec(chunk_seconds=max(1, chunk_minutes) * 60),
            options=TranscribeOptions(language=language),
        )
        job = Job(
            id=uuid.uuid4().hex,
            video_dir=dirs.output_dir / media_paths[0].stem,
            formats=fmt_tuple,
        )
        jobs[job.id] = job
        thread = threading.Thread(
            target=_run_job, args=(job, media_paths, config, transcriber), daemon=True
        )
        thread.start()
        return JSONResponse({"job_id": job.id})

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        progress = io_atomic.read_json(job.video_dir / "progress.json", default={})
        total = int(progress.get("total_chunks") or 0)
        completed = int(
            progress.get("completed_count") or len(progress.get("completed_chunks", []))
        )
        # Terminal "completed" comes from job.status (set AFTER export() finishes),
        # not progress.json — otherwise the UI would stop polling between the last
        # chunk and the subtitle export, and the download links would be missing.
        if job.status in ("error", "completed"):
            status = job.status
        else:
            prog = progress.get("status")
            status = "running" if prog in ("running", "completed") else (prog or job.status)
        percent = (100 * completed // total) if total else (100 if status == "completed" else 0)
        outputs = []
        if status == "completed":
            for fmt in job.formats:
                name = (
                    f"{job.video_dir.name}_transcript.txt"
                    if fmt == "txt"
                    else f"{job.video_dir.name}.{fmt}"
                )
                if (job.video_dir / name).exists():
                    outputs.append(fmt)
        return {
            "job_id": job_id,
            "status": status,
            "completed_chunks": completed,
            "total_chunks": total,
            "percent": percent,
            "log": _tail(job.video_dir / "activity.log"),
            "error": job.error,
            "outputs": outputs,
        }

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str, format: str = "txt") -> FileResponse:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        if format not in VALID_FORMATS:  # never interpolate an arbitrary token into a path
            raise HTTPException(status_code=400, detail=f"unknown format {format!r}")
        name = (
            f"{job.video_dir.name}_transcript.txt"
            if format == "txt"
            else f"{job.video_dir.name}.{format}"
        )
        path = job.video_dir / name
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"{format} not available")
        return FileResponse(path, filename=name)

    return app


app = create_app()  # for `uvicorn scribeflow.web.app:app`
